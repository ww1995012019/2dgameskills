#!/usr/bin/env python3
"""Build a bendable puppet from one reference picture and its fixed set of layers.

    python layer_parts.py plan --image hero.png --out hero/          # prompts for every layer
    (make hero/layers/<slot>.png from each prompt with an image model)
    python layer_parts.py bind --image hero.png --layers hero/layers --out hero/rig
    python generate.py --character hero/rig/character.json --preset hd512 --clips walk --out out/hero

There is nothing to mark and nothing to set per character. plan refuses a reference that breaks the
contract in references/layered-art.md, and bind refuses a layer it can't place, naming the layer to
make again. Joints, scale and cloth all come from the layers themselves.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sprite_anim.layer_slots import HAND_HINTS, KEY_COLOR, SLOTS, hand_prompt, prompt  # noqa: E402
from sprite_anim.puppet_check import HOLE_SHARE, core_mask  # noqa: E402
from sprite_anim.constraints import BAND, LIMITS  # noqa: E402

MIN_HEIGHT = 900         # px: tall enough to give a sharp hd512 frame
MAX_FILL = 0.97          # of the canvas height: a figure touching the edge is cropped
TOP_BAND = 0.10          # of a limb's length: where its root is measured
LEG_LEN = 37.0           # rig units, thigh + shin: the motions are built around it
ANKLE_UP = 5.0           # rig units from sole to ankle
HEEL_BACK = 4.5          # rig units from heel to ankle along the sole, whatever the boot's size
CORE_SHARE = 0.6         # of the waist's half-width: the part of the body that must be solid in every frame
HIPS_WIDTH = 0.8         # of the waist's half-width: what's kept of the hips layer
HIPS_FADE = 0.2          # of the way from waist to hip, over which its lower end fades out
HIPS_ABOVE = 0.3         # of that way, kept above the waist to run up behind the belt
HIDDEN = ("hips",)       # layers that exist to fill what the reference hides: nothing shown to compare
MIN_MATCH = 0.45         # share of a layer's pixels that must match the reference once placed
MIN_COVER = 0.93         # share of the reference silhouette the layers must cover
MAX_SPILL = 0.12         # share of the layers' union allowed outside the reference silhouette
MAX_SAME_LIMB = 0.7      # overlap of a left/right pair past which both layers hold one limb
MAX_SHARED = 0.25        # share of a loose layer that may also be drawn in the torso: more is the same cloth twice
REACH_MID = 0.985        # of the leg's length, hip over ankle at mid-stance: a walk nearly straightens the leg
REACH_END = 0.985       # of the leg's length, hip to the foot furthest out, when both feet are down
STRIDE = 0.58            # of the leg's length, front foot to back foot
IK_SOFT = 0.975          # where the leg's reach starts to ease off: later than the rig's default, or a leg
                         # that nearly straightens would lift its foot off the ground
CONTACT_AHEAD = 0.4      # of the stride, ankle ahead of the hip joint at touch-down: Gait puts the foot at
                         # 0.56 of it, and the heel's roll and the hip's own offset take the rest
HIP_SPREAD = 2.0         # rig units either side of the hip's centre, at most
CLOTH_BEND = 34.0        # degrees a cloth chain may turn between segments and still read as one sheet
CLOTH_CURL = 75.0        # degrees over its whole length
SWING_PAST = 8.0      # degrees a trailing chain may pass straight down or level
GAIT_DROP = 2.2          # rig units the walk lowers the hip


class Rejected(Exception):
    """Input that breaks the contract. The message says what to make again."""


# -- reading pictures --------------------------------------------------------------------------

def key_out(path):
    """Layer picture on magenta -> straight RGBA, undoing the background mixed into its edges."""
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    k = np.minimum(a[..., 0], a[..., 2]) - a[..., 1]
    alpha = np.clip(1 - (k - 22) / 70, 0, 1)
    key = np.array(KEY_COLOR, np.float32)
    # How much background is mixed in follows from the green channel's loss, not from the matte, which
    # is kept tighter so a faint halo drops out.
    mix = np.clip(k / 255, 0, 0.92)[..., None]
    fg = (a - mix * key) / (1 - mix)
    out = np.dstack([np.clip(fg, 0, 255), alpha * 255]).astype(np.uint8)
    out[alpha < 0.02] = 0
    return out


def reference(path):
    """The reference as straight RGBA, background removed. Checks the contract's picture rules."""
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).copy()
    if (np.minimum(a[0, 0, 0], a[0, 0, 2]).astype(int) - a[0, 0, 1]) > 150 and a[0, 0, 3] > 250:
        a = key_out(path)     # the same flat background the layers use
    elif a[..., 3].min() > 250:
        corners = np.array([a[0, 0, :3], a[0, -1, :3], a[-1, 0, :3], a[-1, -1, :3]], int)
        if (corners.max(0) - corners.min(0)).max() > 12:
            raise Rejected("reference: the background is not one flat colour or transparent; generate it again")
        near = np.abs(a[..., :3].astype(int) - np.median(corners, 0)).max(2) <= 28
        im2 = Image.fromarray(near.astype(np.uint8))
        from PIL import ImageDraw
        for p in ((0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1)):
            ImageDraw.floodfill(im2, p, 2)
        a[np.asarray(im2) == 2, 3] = 0
    ys, xs = np.nonzero(a[..., 3] > 128)
    if not len(ys):
        raise Rejected("reference: the picture is empty")
    height = ys.max() - ys.min()
    if height < MIN_HEIGHT:
        raise Rejected(f"reference: the figure is {height} px tall, needs {MIN_HEIGHT}; generate it larger")
    if height > MAX_FILL * a.shape[0] or ys.min() < 4 or ys.max() > a.shape[0] - 5 or xs.min() < 4 or xs.max() > a.shape[1] - 5:
        raise Rejected("reference: the figure touches the canvas edge; generate it again with a margin all round")
    return a


# -- placing a layer on the reference ------------------------------------------------------------

def warp(arr, s, deg, dx, dy, cx, cy, size, resample=Image.BILINEAR):
    """Layer turned and scaled about (cx, cy), then moved, on a canvas of size (w, h)."""
    t = math.radians(deg)
    c, n = math.cos(t) / s, math.sin(t) / s
    tx, ty = cx + dx, cy + dy
    coeff = (c, n, cx - c * tx - n * ty, -n, c, cy + n * tx - c * ty)
    return np.asarray(Image.fromarray(arr).transform(size, Image.AFFINE, coeff, resample=resample))


def small(a, f):
    """Premultiplied downscale, so a dark edge isn't lost and the background doesn't bleed in."""
    p = a.astype(np.float32) / 255
    p[..., :3] *= p[..., 3:]
    size = (a.shape[1] // f, a.shape[0] // f)
    out = np.stack([np.asarray(Image.fromarray(p[..., c]).resize(size, Image.BOX)) for c in range(4)], -1)
    al = out[..., 3:]
    out[..., :3] = np.where(al > 1e-3, out[..., :3] / np.maximum(al, 1e-3), 0)
    return (np.clip(out, 0, 1) * 255).astype(np.uint8)


def score(layer, ref, params, cx, cy):
    """Mean colour error over the layer's pixels. Capped, because a layer holds art the reference
    hides; off the reference silhouette costs the most, so a layer can't sit outside the figure."""
    size = (ref.shape[1], ref.shape[0])
    w = warp(layer, *params, cx, cy, size, Image.NEAREST)
    on = w[..., 3] > 128
    n = int(on.sum())
    if n == 0:
        return 1.0
    seen = ref[..., 3] > 128
    diff = np.abs(w[..., :3].astype(np.float32) - ref[..., :3]).mean(2) / 255
    cost = np.minimum(diff, 0.16)
    cost = np.where(seen, cost, 0.24)
    total = float(cost[on].sum())
    # Pixels the layer loses off the canvas count against it too.
    lost = max(0, int((layer[..., 3] > 128).sum() * params[0] ** 2) - n)
    return (total + lost * 0.24) / (n + lost)


def place(layer, ref):
    """Best scale, turn and shift of a layer onto the reference, coarse to fine."""
    coarse_f = 8
    L, R = small(layer, coarse_f), small(ref, coarse_f)
    ys, xs = np.nonzero(L[..., 3] > 128)
    if not len(ys):
        return None
    cx, cy = float(xs.mean()), float(ys.mean())
    best = None
    for s in np.arange(0.76, 1.30, 0.06):
        for deg in np.arange(-12, 12.1, 4):
            for dy in range(-16, 17, 2):
                for dx in range(-16, 17, 2):
                    e = score(L, R, (s, deg, dx, dy), cx, cy)
                    if best is None or e < best[0]:
                        best = (e, s, deg, dx, dy)
    e, s, deg, dx, dy = best
    params = [s, deg, dx * coarse_f, dy * coarse_f]
    cx, cy = cx * coarse_f, cy * coarse_f
    for f, steps in ((4, (0.03, 2.0, 8.0)), (2, (0.012, 0.8, 4.0)), (2, (0.005, 0.3, 2.0))):
        L, R = small(layer, f), small(ref, f)
        c = (cx / f, cy / f)
        scaled = lambda p: (p[0], p[1], p[2] / f, p[3] / f)
        e = score(L, R, scaled(params), *c)
        improved = True
        while improved:
            improved = False
            for i, step in ((0, steps[0]), (1, steps[1]), (2, steps[2]), (3, steps[2])):
                for sign in (1, -1):
                    trial = list(params)
                    trial[i] += sign * step
                    t = score(L, R, scaled(trial), *c)
                    if t < e - 1e-5:
                        e, params, improved = t, trial, True
    return dict(s=float(params[0]), deg=float(params[1]), dx=float(params[2]), dy=float(params[3]), cx=cx, cy=cy, error=e)


def placed(layer, fit, size):
    p = layer.astype(np.float32) / 255
    p[..., :3] *= p[..., 3:]
    args = (fit["s"], fit["deg"], fit["dx"], fit["dy"], fit["cx"], fit["cy"], size)
    bands = [warp(p[..., c], *args, Image.BICUBIC) for c in range(4)]
    out = np.clip(np.stack(bands, -1), 0, 1)
    al = out[..., 3:]
    out[..., :3] = np.where(al > 1e-3, out[..., :3] / np.maximum(al, 1e-3), 0)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


def place_leg(layer, ref, side):
    """Anchor separated legs to the two planted shoes, not similarly coloured robes.

    The reference contract puts both soles on one ground line. Only use this
    landmark when exactly two substantial, separate footprints are visible;
    ambiguous silhouettes retain the normal colour-based registration.
    """
    seen = ref[..., 3] > 128
    ys, xs = np.nonzero(seen)
    band = max(3, round((ys.max() - ys.min()) * 0.02))
    bottom = int(ys.max())
    occupied = seen[max(0, bottom - band):bottom + 1].any(axis=0)
    # A boot's raised arch can split its sole into heel and toe. Join only
    # tiny gaps in the landmark signal; never alter the source pixels.
    edges = np.diff(np.r_[True, occupied, True].astype(int))
    for a, b in zip(np.flatnonzero(edges == -1), np.flatnonzero(edges == 1)):
        if a > 0 and b < len(occupied) and b - a <= max(2, round(band * 0.15)):
            occupied[a:b] = True
    edges = np.diff(np.r_[False, occupied, False].astype(int))
    spans = [(a, b) for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
             if b - a >= max(8, ref.shape[1] * 0.02)]
    if len(spans) != 2 or spans[1][0] - spans[0][1] < min(b - a for a, b in spans) * 0.25:
        return place(layer, ref)
    left, right = spans[0 if side == "far" else 1]
    target_y = float(np.nonzero(seen[:, left:right])[0].max())
    leg = read_leg(layer[..., 3] > 128)
    width = leg["toe"][0] - leg["heel"][0]
    if width <= 0:
        return place(layer, ref)
    s = (right - 1 - left) / width
    dx = float(left - leg["heel"][0] * s)
    dy = float(target_y - leg["heel"][1] * s)
    return dict(s=float(s), deg=0.0, dx=dx, dy=dy, cx=0.0, cy=0.0,
                error=score(small(layer, 8), small(ref, 8), (s, 0, dx / 8, dy / 8), 0, 0))


# -- reading the skeleton off the layers -----------------------------------------------------------

def band_mid(mask, a, u, lo, hi):
    """Centre of the mask's pixels whose distance along u from a lies in [lo, hi)."""
    ys, xs = np.nonzero(mask)
    t = (xs - a[0]) * u[0] + (ys - a[1]) * u[1]
    pick = (t >= lo) & (t < hi)
    if not pick.any():
        return None
    return np.array([xs[pick].mean(), ys[pick].mean()])


def medial(mask, a, b, n):
    """n points running down the middle of the mask from a to b."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    length = np.hypot(*(b - a)) or 1.0
    u = (b - a) / length
    step = length / (n - 1)
    pts = []
    for i in range(n):
        p = band_mid(mask, a, u, step * (i - 0.5), step * (i + 0.5))
        pts.append(p if p is not None else a + u * step * i)
    pts[0], pts[-1] = a, b
    return pts


def at_length(points, frac):
    """The point a fraction of the way along a polyline."""
    p = np.array(points)
    seg = np.hypot(*np.diff(p, axis=0).T)
    target = seg.sum() * frac
    for i, s in enumerate(seg):
        if target <= s:
            return p[i] + (p[i + 1] - p[i]) * target / (s or 1)
        target -= s
    return p[-1]


def root_and_tip(mask):
    """A hanging layer's top centre and the point furthest from it."""
    ys, xs = np.nonzero(mask)
    top, h = ys.min(), ys.max() - ys.min()
    pick = ys < top + TOP_BAND * h
    root = np.array([xs[pick].mean(), ys[pick].mean()])
    far = np.argmax((xs - root[0]) ** 2 + (ys - root[1]) ** 2)
    return root, np.array([float(xs[far]), float(ys[far])])


def read_leg(mask):
    ys, xs = np.nonzero(mask)
    bottom = ys.max()
    root, _ = root_and_tip(mask)
    band = ys >= bottom - 0.035 * (bottom - ys.min())
    heel = np.array([float(xs[band].min()), float(ys[band].max())])
    toe = np.array([float(xs[band].max()), float(ys[band].max())])
    length = np.hypot(*(heel - root))
    unit = length / (LEG_LEN + ANKLE_UP)
    ankle = heel + (toe - heel) / (np.hypot(*(toe - heel)) or 1) * HEEL_BACK * unit - np.array([0.0, ANKLE_UP * unit])
    knee = at_length(medial(mask, root, ankle, 9), 0.5)
    return dict(hip=root, knee=knee, ankle=ankle, heel=heel, toe=toe)


def read_arm(mask, hand_mask=None):
    root, tip = root_and_tip(mask)
    if hand_mask is not None:
        # The hand's proximal strip locates the wrist, even when a sleeve tail
        # is much farther from the shoulder than the fingertips are.
        ys, xs = np.nonzero(hand_mask)
        center = np.array([xs.mean(), ys.mean()])
        axis = (center - root) / max(float(np.hypot(*(center - root))), 1e-9)
        distances = (xs - root[0]) * axis[0] + (ys - root[1]) * axis[1]
        lo, hi = float(distances.min()), float(distances.max())
        wrist = band_mid(hand_mask, root, axis, lo, lo + max(1, (hi - lo) * 0.18))
        tip = np.array([float(xs[distances.argmax()]), float(ys[distances.argmax()])])
        line = medial(mask, root, wrist, 9)
        shoulder = np.array(at_length(line, 0.05))
        elbow = legal_elbow(mask, shoulder, at_length(line, 0.47), wrist)
        return dict(shoulder=shoulder, elbow=elbow, wrist=wrist, tip=tip)
    line = medial(mask, root, tip, 9)
    return dict(shoulder=np.array(at_length(line, 0.05)), elbow=at_length(line, 0.47), wrist=at_length(line, 0.86), tip=tip)


def legal_elbow(mask, shoulder, elbow, wrist):
    """Choose a supported elbow on the rig's bending side under a loose sleeve.

    The sleeve centreline is not necessarily the arm centreline. Correct only
    invalid inferred bends, keeping the hand and shoulder fixed and choosing
    the closest legal joint inside the actual sleeve artwork.
    """
    lo, hi = LIMITS["elbow"]
    axis = wrist - shoulder
    length2 = float(axis @ axis)
    if length2 <= 1e-9:
        raise Rejected("arm: the shoulder and hand overlap; remake the arm with a clear forearm")
    bend = (angle_down(elbow, wrist) - angle_down(shoulder, elbow) + 180) % 360 - 180
    if lo <= bend <= hi:
        return elbow
    ys, xs = np.nonzero(mask)
    points = np.column_stack((xs, ys)).astype(float)
    along = (points - shoulder) @ axis / length2
    upper = points - shoulder
    lower = wrist - points
    angles = (np.degrees(np.arctan2(lower[:, 0], lower[:, 1])
                         - np.arctan2(upper[:, 0], upper[:, 1])) + 180) % 360 - 180
    valid = (along >= 0.2) & (along <= 0.8) & (angles >= lo) & (angles <= hi)
    comfortable = valid & (angles >= lo + BAND) & (angles <= hi - BAND)
    if comfortable.any():
        valid = comfortable
    if not valid.any():
        raise Rejected("arm: the sleeve has no supported elbow on the rig's bending side; remake the arm")
    candidates = points[valid]
    return candidates[np.argmin(((candidates - elbow) ** 2).sum(axis=1))]


def angle_down(a, b):
    """Degrees from straight down to a->b, forward positive. Picture pixels, y down."""
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))


def angle_up(a, b):
    """Clockwise degrees from straight up to a->b. Picture pixels, y down."""
    return math.degrees(math.atan2(b[0] - a[0], a[1] - b[1]))


def trimmed(layer, waist, hip, half):
    """A hidden layer cut to the body's middle: a model's outline for art nobody should see is a guess,
    and whatever it draws past the robe would ride on the thighs as a stiff block. The lower end fades
    out over the legs, so it leaves no hem."""
    h, w = layer.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (hip - waist).astype(np.float32)
    s = ((xx - waist[0]) * u[0] + (yy - waist[1]) * u[1]) / float(u @ u)
    across = np.abs((xx - waist[0]) * u[1] - (yy - waist[1]) * u[0]) / float(np.hypot(*u))
    keep = np.clip((1.0 - s) / HIPS_FADE, 0, 1) * np.clip(half - across, 0, 1) * (s > -HIPS_ABOVE)
    out = layer.copy()
    out[..., 3] = (out[..., 3] * keep).astype(np.uint8)
    return out


def align_hips(layer, waist, hip):
    """Place a hidden undergarment from the measured waist/crotch, not colour.

    Hidden art cannot be registered against the reference because it is covered
    there. Permit modest redraw drift, but never enlarge a scrap into a torso.
    All original solid-core checks still run after the transform.
    """
    ys, xs = np.nonzero(layer[..., 3] > 128)
    height = float(ys.max() - ys.min())
    distance = float(np.hypot(*(hip - waist)))
    if height <= 0 or distance <= 0:
        return layer, None
    s = distance * (1 + HIPS_ABOVE + HIPS_FADE) / height
    if not 0.6 <= s <= 1.6:
        return layer, None
    top = waist - (hip - waist) * HIPS_ABOVE
    cx, cy = float((xs.min() + xs.max()) / 2), float(ys.min())
    deg = -math.degrees(math.atan2(hip[0] - waist[0], hip[1] - waist[1]))
    fit = dict(s=s, deg=deg, dx=float(top[0] - cx), dy=float(top[1] - cy),
               cx=cx, cy=cy, error=0.0)
    return placed(layer, fit, (layer.shape[1], layer.shape[0])), fit


def bind(ref, layers):
    """Places every layer and works out the rig. Returns (placed layers, spec's puppet + body, report)."""
    size = (ref.shape[1], ref.shape[0])
    missing = [n for n, s in SLOTS.items() if s[2] and n not in layers]
    if missing:
        raise Rejected(f"missing layers: {', '.join(missing)}; make them from the prompts of `plan`")
    out, fits, placements = {}, {}, {}
    seen = ref[..., 3] > 128
    for name in SLOTS:
        if name not in layers:
            continue
        if not (layers[name][..., 3] > 128).any():
            raise Rejected(f"{name}: the layer is empty; make it again")
        # Hidden art has no shown colour to register. Start at the authored
        # position; the measured waist/crotch can correct modest drift below.
        if name in HIDDEN:
            fit = dict(s=1.0, deg=0.0, dx=0.0, dy=0.0, cx=0.0, cy=0.0, error=0.0)
        elif name in ("leg_near", "leg_far"):
            fit = place_leg(layers[name], ref, name.removeprefix("leg_"))
        else:
            fit = place(layers[name], ref)
        out[name] = placed(layers[name], fit, size)
        placements[name] = fit
        fits[name] = {k: round(v, 3) for k, v in fit.items() if k not in ("cx", "cy")}
    # An image model can read "near" and "far" as the same limb. Two layers on one limb cover the same
    # pixels, and no threshold on either layer alone would show it.
    for one, other in (("arm_near", "arm_far"), ("leg_near", "leg_far")):
        a, b = out[one][..., 3] > 128, out[other][..., 3] > 128
        if (a & b).sum() > MAX_SAME_LIMB * min(a.sum(), b.sum()):
            raise Rejected(f"{one} and {other} show the same limb; make {one} again for the limb further right in the picture")
    # Judge each layer only where it shows: the art an arm hides in the reference is new on purpose.
    names = list(out)
    for i, name in enumerate(names):
        shown = out[name][..., 3] > 128
        for front in names[i + 1:]:
            shown &= out[front][..., 3] <= 128
        close = np.abs(out[name][..., :3].astype(np.float32) - ref[..., :3]).mean(2) < 38
        match = float((shown & seen & close).sum() / max(shown.sum(), 1))
        fits[name]["match"] = round(match, 3)
        if match < MIN_MATCH and name not in HIDDEN:
            raise Rejected(f"{name}: only {match:.0%} of what it shows matches the reference; the image model changed it, make it again")
    union = np.zeros(seen.shape, bool)
    for a in out.values():
        union |= a[..., 3] > 128
    cover = float((union & seen).sum() / seen.sum())
    spill = float((union & ~seen).sum() / union.sum())
    if cover < MIN_COVER:
        raise Rejected(f"the layers cover only {cover:.0%} of the reference; some art is in no layer, see layers_check.png")
    if spill > MAX_SPILL:
        raise Rejected(f"{spill:.0%} of the layers lies outside the reference; a layer holds extra art, see layers_check.png")

    masks = {n: a[..., 3] > 128 for n, a in out.items()}
    for name in ("cloth_back", "hair_back"):
        if name in masks and (masks[name] & masks["torso"]).sum() > MAX_SHARED * masks[name].sum():
            raise Rejected(f"torso: it also holds the art of {name}, so that cloth would be drawn twice; make torso again")
    ln, lf = read_leg(masks["leg_near"]), read_leg(masks["leg_far"])
    hand_masks = {}
    for hint, arm in HAND_HINTS.items():
        if hint not in layers:
            continue
        hand = placed(layers[hint], placements[arm], size)[..., 3] > 128
        if not hand.any() or (hand & masks[arm]).sum() < 0.8 * hand.sum():
            raise Rejected(f"{hint}: the hand does not overlap its arm; remake the hint from the finished {arm} layer without moving it")
        hand_masks[arm] = hand
    an = read_arm(masks["arm_near"], hand_masks.get("arm_near"))
    af = read_arm(masks["arm_far"], hand_masks.get("arm_far"))
    if ln["toe"][0] - ln["heel"][0] < 30 or lf["toe"][0] - lf["heel"][0] < 30:
        raise Rejected("legs: no foot found at the bottom of a leg layer; make it again with the boot complete")
    near_px = np.hypot(*(ln["knee"] - ln["hip"])) + np.hypot(*(ln["ankle"] - ln["knee"]))
    far_px = np.hypot(*(lf["knee"] - lf["hip"])) + np.hypot(*(lf["ankle"] - lf["knee"]))
    ppu = (near_px + far_px) / 2 / LEG_LEN

    troot, _ = root_and_tip(masks["torso"])
    hip = (ln["hip"] + lf["hip"]) / 2 + np.array([0.0, 0.5 * np.hypot(*(ln["hip"] - lf["hip"]))])
    neck = troot
    waist = neck + (hip - neck) * 0.62
    ys, xs = np.nonzero(masks["head"])
    head_top = np.array([float(xs[ys < ys.min() + 3].mean()), float(ys.min())])
    head_base = neck + np.array([0.0, -0.02 * np.hypot(*(hip - neck))])

    # The robe around the hips can split and swing clear, so what's behind it has to be solid.
    waist_half = 0.5 * float(masks["torso"][int(round(waist[1]))].sum())
    core_px = CORE_SHARE * waist_half
    out["hips"] = trimmed(out["hips"], waist, hip, HIPS_WIDTH * waist_half)
    masks["hips"] = out["hips"][..., 3] > 128
    solid = masks["torso"] | masks["hips"] | masks["leg_near"] | masks["leg_far"]
    core = core_mask(size, waist, hip, core_px)
    open_share = float((~solid[core]).mean())
    if open_share > HOLE_SHARE:
        aligned, fit = align_hips(layers["hips"], waist, hip)
        if fit is not None:
            out["hips"] = trimmed(aligned, waist, hip, HIPS_WIDTH * waist_half)
            masks["hips"] = out["hips"][..., 3] > 128
            solid = masks["torso"] | masks["hips"] | masks["leg_near"] | masks["leg_far"]
            open_share = float((~solid[core]).mean())
            fits["hips"].update({k: round(v, 3) for k, v in fit.items() if k not in ("cx", "cy")})
    if open_share > HOLE_SHARE:
        raise Rejected(f"hips: {open_share:.0%} of the body below the belt is see-through; make hips again, solid from the waist to the crotch")

    spine = neck - waist
    chest_rest = angle_up(waist, neck)
    body_rest = angle_up(hip, waist)

    u = spine / (np.hypot(*spine) or 1)
    fwd = np.array([-u[1], u[0]])     # picture y runs down, so this is forward for a figure facing right

    def along(p):
        d = (p - waist) / ppu
        return float(d @ fwd), float(d @ u)

    legs = near_px / ppu

    def pelvic(p):
        d = (p - hip) / ppu
        v = (waist - hip) / (np.hypot(*(waist - hip)) or 1)
        return [round(float(d @ np.array([-v[1], v[0]])), 3), round(float(d @ v), 3)]

    round2 = lambda p: [round(v, 3) for v in along(p)]
    # A walking hip rises over the planted leg and sinks when both feet are down, as a stiff leg
    # vaults over its foot. Those two heights, from the leg's length, set the hip and its bob.
    mid = REACH_MID * legs
    low = math.sqrt(max((REACH_END * legs) ** 2 - (CONTACT_AHEAD * STRIDE * legs) ** 2, 0.0))
    # The two hip joints sit level, whatever height the image model happened to stop each leg at: a
    # lower one would keep that leg bent through its whole stance.
    seat_up = (pelvic(ln["hip"])[1] + pelvic(lf["hip"])[1]) / 2
    # Seen from the side both legs turn about nearly one point. In a stride the tops of the two leg
    # layers spread apart, which is pose and not anatomy.
    seat_x = lambda p: round(min(max(pelvic(p)[0], -HIP_SPREAD), HIP_SPREAD), 3)
    body = dict(thigh=round(np.hypot(*(ln["knee"] - ln["hip"])) / ppu, 3), shin=round(np.hypot(*(ln["ankle"] - ln["knee"])) / ppu, 3),
                up_arm=round(np.hypot(*(an["elbow"] - an["shoulder"])) / ppu, 3),
                lo_arm=round(np.hypot(*(an["wrist"] - an["elbow"])) / ppu, 3),
                hip_h=round(ANKLE_UP + GAIT_DROP + (mid + low) / 2 - seat_up, 3),
                pelvis_len=round(np.hypot(*(waist - hip)) / ppu, 3), chest_len=round(along(head_base)[1], 3), neck_len=0.0,
                head_size=round(np.hypot(*(head_top - head_base)) / ppu / 30.0, 3), leg_soft=IK_SOFT, foot_wrap=True,
                # Preserve each measured attachment. Coincident screen-space
                # shoulders are allowed, but must not be forced onto the art.
                sh_n_at=round2(an["shoulder"]), sh_f_at=round2(af["shoulder"]), hip_n_at=[seat_x(ln["hip"]), round(seat_up, 3)], hip_f_at=[seat_x(lf["hip"]), round(seat_up, 3)])

    joints = dict(hip=hip, waist=waist, neck=neck, head_base=head_base, wr_n=an["wrist"], el_n=an["elbow"])
    def half(name):
        """A limb's half-width: its area over its length."""
        root, tip = root_and_tip(masks[name])
        return 0.5 * float(masks[name].sum()) / max(float(np.hypot(*(tip - root))), 1.0)

    data = {}

    def tube(name, bones, rest, **extra):
        data[name] = dict(kind="tube", bones=bones, rest=[[round(float(v), 2) for v in p] for p in rest],
                          radius=round(half(name), 2), **extra)

    arms_rest = {}
    tube("arm_far", ["sh_f", "el_f", "wr_f"], [af["shoulder"], af["elbow"], af["wrist"]])
    tube("arm_near", ["sh_n", "el_n", "wr_n"], [an["shoulder"], an["elbow"], an["wrist"]])
    for side, leg in (("f", lf), ("n", ln)):
        name = "leg_near" if side == "n" else "leg_far"
        shin = (leg["ankle"] - leg["knee"]) / (np.hypot(*(leg["ankle"] - leg["knee"])) or 1)
        tube(name, [f"hip_{side}", f"kn_{side}", f"an_{side}"], [leg["hip"], leg["knee"], leg["ankle"]],
             foot=dict(side=side, ankle=[round(float(v), 2) for v in leg["ankle"]], shin_dir=[round(float(v), 4) for v in shin],
                       blend=round(0.6 * half(name), 2), width=round(half(name), 2),
                       rest_angle=round(math.degrees(math.atan2(leg["toe"][1] - leg["heel"][1], leg["toe"][0] - leg["heel"][0])), 2)))
    # The torso's hanging panels bend between the thighs: a virtual joint below the hip.
    ys, xs = np.nonzero(masks["torso"])
    hem = float(ys.max())
    thighs = ((ln["knee"] + lf["knee"]) / 2 - hip)
    skirt_len = max(hem - hip[1], 0.25 * near_px) * 1.1
    skirt = hip + thighs / (np.hypot(*thighs) or 1) * skirt_len
    tube("torso", ["skirt", "hip", "waist", "head_base"], [skirt, hip, waist, head_base])
    data["head"] = dict(kind="rigid", follow=["head_base", "head_rot"], anchor=[round(float(v), 2) for v in head_base])
    data["hips"] = dict(kind="rigid", follow=["hip", "body_rot"], anchor=[round(float(v), 2) for v in hip])

    weapon_len = None
    weapon_back = 0.0
    wep_rest = None
    fa_n = angle_down(an["elbow"], an["wrist"])
    if "weapon" in out:
        grip = an["wrist"] + (an["wrist"] - an["elbow"]) * 0.14
        ys, xs = np.nonzero(masks["weapon"])
        far = np.argmax((xs - grip[0]) ** 2 + (ys - grip[1]) ** 2)
        tip = np.array([float(xs[far]), float(ys[far])])
        weapon_len = float(np.hypot(*(tip - grip)) / ppu)
        wep_rest = angle_down(grip, tip)
        axis = (tip - grip) / (np.hypot(*(tip - grip)) or 1)
        weapon_back = max(float(-((xs - grip[0]) * axis[0] + (ys - grip[1]) * axis[1]).min()) / ppu, 0.0)
        data["weapon"] = dict(kind="rigid", follow=["wr_n", "wep_a"], anchor=[round(float(v), 2) for v in grip])

    chains = {}
    head_ref = head_base

    def chain(name, joint, frame, base, rest_rot, n, **physics):
        root, tip = root_and_tip(masks[name])
        pts = medial(masks[name], root, tip, n)
        run = sum(np.hypot(*(pts[i + 1] - pts[i])) for i in range(n - 1))
        d = (root - base) / ppu * (1, -1)
        from sprite_anim.mathx import rot
        off = rot(tuple(float(v) for v in d), -rest_rot)
        v = (tip - root) * (1, -1)
        rest = rot(tuple(float(x) for x in v / (np.hypot(*v) or 1)), -rest_rot)
        # Behind the figure means from straight down to level at the back, whatever the art's own slant.
        slant = math.degrees(math.atan2(v[1], v[0]))     # -90 is straight down, -180 level at the back
        swing = [round(-(slant + 180.0) - SWING_PAST, 2), round(max(-90.0 - slant, 0.0) + SWING_PAST, 2)]
        chains[name] = dict(joint=joint, frame=frame, offset=[round(float(x), 3) for x in off], n=n, seg=round(run / (n - 1) / ppu, 3),
                            rest=[round(float(x), 4) for x in rest], swing=swing, **physics)
        data[name] = dict(kind="cloth", chain=name, rest=[[round(float(v), 2) for v in p] for p in pts], radius=round(run / (n - 1) * 0.45, 2))

    if "hair_back" in out:
        chain("hair_back", "head_base", "head_rot", head_ref, 0.0, 6, gravity=260, drag=7.0, stiff=0.09, flutter=160, ground=False, max_bend=CLOTH_BEND, max_curl=CLOTH_CURL)
    if "cloth_back" in out:
        chain("cloth_back", "hip", "body_rot", hip, body_rest, 7, gravity=320, drag=6.0, stiff=0.05, flutter=520, ground=True, max_bend=CLOTH_BEND, max_curl=CLOTH_CURL)

    # Depth is part of the side-view contract. Matching a sleeve's colour in
    # the reference cannot promote the far arm in front of the torso, especially
    # when the arm rotates away from the reference pose.
    order = list(SLOTS)
    ordered = {n: data[n] for n in order if n in data}
    rest_angles = dict(head_rot=0.0, wep_a=wep_rest if wep_rest is not None else 0.0, chest_rot=chest_rest, body_rot=body_rest)
    arm_near_up, arm_near_lo = angle_down(an["shoulder"], an["elbow"]), angle_down(an["elbow"], an["wrist"])
    arm_far_up, arm_far_lo = angle_down(af["shoulder"], af["elbow"]), angle_down(af["elbow"], af["wrist"])
    # The walk keeps the picture's carried pose and swings around it: a character holding a sword
    # forward keeps holding it forward. chest_rot of the walk is pelvis 3 + lean 5.
    lean = 8.0
    # Idle's default chest is pelvis 4 + spine 5. Preserve the reference's
    # whole carried pose there too. Adapting only the free arm can collapse both
    # upper arms onto one path while the weapon arm keeps the default stance.
    gait = dict(idle=dict(arm_n=[round(arm_near_up + 9.0, 2), 2.5 if wep_rest is not None else 1.6,
                                 round(arm_near_lo - arm_near_up, 2), 1.5 if wep_rest is not None else 2.4],
                          arm_f=[round(arm_far_up + 9.0, 2), 1.8, round(arm_far_lo - arm_far_up, 2), 2.6]),
                walk=dict(stride=round(STRIDE * legs, 2), bob=round((mid - low) / 2, 3), arm_n=[round(arm_near_up + lean, 2), 2.5 if wep_rest is not None else 15.0, round(arm_near_lo - arm_near_up, 2), 1.5 if wep_rest is not None else 3.0],
                          arm_f=[round(arm_far_up + lean, 2), 15.0, round(arm_far_lo - arm_far_up, 2), 5.0]))
    if wep_rest is not None:
        gait["walk"].update(wep=round(wep_rest - arm_near_lo, 2), wep_sway=1.5)     # a carried blade stays steady
        gait["idle"].update(wep=round(wep_rest - arm_near_lo, 2), wep_sway=1.5)
    puppet = dict(px_per_unit=round(float(ppu), 4), joints={k: [round(float(x), 2) for x in v] for k, v in joints.items()},
                  rest_angles={k: round(float(v), 3) for k, v in rest_angles.items()}, skirt_len=round(float(skirt_len / ppu), 3),
                  core_radius=round(core_px / ppu, 3),
                  rest_arm={"n": [[round(float(v), 2) for v in an["wrist"]], [round(float(v), 2) for v in an["elbow"]]],
                            "f": [[round(float(v), 2) for v in af["wrist"]], [round(float(v), 2) for v in af["elbow"]]]},
                  layers=ordered, chains=chains, source="source.png")
    if weapon_len:
        puppet.update(weapon_length=round(weapon_len, 2), weapon_back=round(weapon_back, 2))
        body.update(weapon_front=round(weapon_len, 2), weapon_back=round(weapon_back, 2))
    return out, dict(puppet=puppet, body=body, gait=gait), dict(fits=fits, cover=round(cover, 3), spill=round(spill, 3), px_per_unit=round(float(ppu), 3))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="check the reference and write each layer's prompt")
    p.add_argument("--image", required=True)
    p.add_argument("--out", required=True)
    b = sub.add_parser("bind", help="place the layers and write the puppet")
    b.add_argument("--image", required=True)
    b.add_argument("--layers", required=True, help="folder with <slot>.png for each layer")
    b.add_argument("--name", default="character")
    b.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        ref = reference(a.image)
        os.makedirs(a.out, exist_ok=True)
        if a.cmd == "plan":
            folder = os.path.join(a.out, "prompts")
            os.makedirs(folder, exist_ok=True)
            os.makedirs(os.path.join(a.out, "layers"), exist_ok=True)
            for slot in SLOTS:
                with open(os.path.join(folder, slot + ".txt"), "w", encoding="utf-8") as fh:
                    fh.write(prompt(slot))
            for slot in HAND_HINTS:
                with open(os.path.join(folder, slot + ".txt"), "w", encoding="utf-8") as fh:
                    fh.write(hand_prompt())
            print(f"[plan] {len(SLOTS)} art prompts + {len(HAND_HINTS)} optional hand hints -> {folder}. "
                  "Make art layers from the reference; make each hand hint from its finished arm layer.")
            return
        layers = {n: key_out(os.path.join(a.layers, n + ".png")) for n in (*SLOTS, *HAND_HINTS) if os.path.isfile(os.path.join(a.layers, n + ".png"))}
        out, spec, report = bind(ref, layers)
    except Rejected as e:
        sys.exit(f"[rejected] {e}")
    folder = os.path.join(a.out, "layers")
    os.makedirs(folder, exist_ok=True)
    for name, arr in out.items():
        box = Image.fromarray(arr[..., 3]).getbbox()
        Image.fromarray(arr, "RGBA").crop(box).save(os.path.join(folder, name + ".png"))
        spec["puppet"]["layers"][name].update(image=f"layers/{name}.png", offset=[box[0], box[1]])
    Image.fromarray(ref, "RGBA").save(os.path.join(a.out, "source.png"))
    spec.update(name=a.name, weapon="sword" if "weapon" in out else "none", cloth=[], style={"speed": 1.0, "bounce": 0.8})
    with open(os.path.join(a.out, "character.json"), "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "bind_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    canvas = Image.new("RGBA", (ref.shape[1], ref.shape[0]), (60, 62, 74, 255))
    for arr in out.values():
        canvas.alpha_composite(Image.fromarray(arr, "RGBA"))
    canvas.save(os.path.join(a.out, "layers_check.png"))
    print(f"[bind] {len(out)} layers, {report['px_per_unit']} px/unit, covers {report['cover']:.0%} of the reference, {report['spill']:.0%} outside -> {a.out}")
    for name, fit in report["fits"].items():
        print(f"  {name:<11} scale {fit['s']:.3f} turn {fit['deg']:+.1f} shift {fit['dx']:+.0f},{fit['dy']:+.0f} match {fit['match']:.0%}")


if __name__ == "__main__":
    main()
