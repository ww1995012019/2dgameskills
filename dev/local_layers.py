#!/usr/bin/env python3
"""Split ONE side-view picture into the layered puppet's whole-limb layers, locally (no image model).

    python dev/local_layers.py --image reference.png --joints joints.json --out job/local
    python game-sprite-animator/scripts/bind_known_joints.py --manifest job/local/rig_input.json --out job/rig-v1

EXPERIMENTAL (dev only, not in the skill package): phase 1 of the local layering plan. Not yet
validated on real AI art or approved by the user; see docs/local-layering.md.

The picture's own pixels are kept in place on its canvas: nothing is redrawn, scaled or moved.
Pixel ownership comes from cut_parts.cut (capsules along the marked bones, front parts first,
colour tie-breaks); its sixteen parts are merged into the layers bind_known_joints expects:
whole arms and legs (upper, lower, hand/foot), torso, hips, head and an optional sword.

Art a layer in front hides (the torso behind the near arm, a limb's root under the torso, the
far leg behind the near one) is filled from the hidden layer's own colours, only inside the
picture's silhouette and only inside the layer's bone capsules. That fill is plain and is reported.
A far limb that is mostly hidden is refused, not invented: request a reference showing it.

joints.json uses cut_parts' names (see references/ai-art.md): head_top, head_base, neck, waist,
hip, sh/el/wr, hip/kn/an, heel/toe for both sides (_n near, _f far), and weapon_grip/weapon_tip
for a sword. Numerical output only: visual review and the user's motion approval stay pending.
"""
import argparse
import json
import math
import os
from pathlib import Path

import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "game-sprite-animator/scripts"))
import cut_parts as cp  # noqa: E402
import layer_parts as lp  # noqa: E402

# Layer: the cut_parts parts merged into it. Back to front, as the layered puppet draws them.
GROUPS = {
    "arm_far": ("arm_f_up", "arm_f_lo", "hand_f"),
    "hips": (),                       # hidden core, built from the trunk below (see split)
    "leg_far": ("leg_f_up", "leg_f_lo", "foot_f"),
    "leg_near": ("leg_n_up", "leg_n_lo", "foot_n"),
    "head": ("head",),
    "torso": ("torso", "pelvis"),     # the whole visible trunk, chest to hips
    "weapon": ("weapon",),
    "arm_near": ("arm_n_up", "arm_n_lo", "hand_n"),
}
FAR_LIMBS = ("arm_far", "leg_far")
MIN_VISIBLE = 0.5     # of a far limb's capsule over the art that must be its own visible pixels
NECK_REACH = 0.35     # of head_base->neck, past the neck joint: the head keeps its neck under the collar
BG_MARGIN = 6         # 0-255 past the backdrop's own noise that still counts as backdrop
SOLID_ALPHA = 200     # 0-255: art at least this opaque anchors the pixels joined to it
LIMB_BONES = ("arm_f_up", "arm_f_lo", "leg_f_up", "leg_f_lo", "leg_n_up", "leg_n_lo", "arm_n_up", "arm_n_lo")
WIDTH_PERCENTILE = 80  # of the half-widths measured along a bone
WIDTH_PAD = 1.15      # measured half-width times this: the capsule just covers the limb's outline
CORE_SHARE = 0.7      # of a bone's measured radius: inside this a layer drawn in front owns the pixel
FILL_WARN = 0.15      # of a layer's capsule area: more local fill than this is reported for review
INK_UNITS = 0.6       # rig units: a fill takes colour from this far inside the layer, past its outline
INK_LOCAL = 0.6       # of the neighbourhood's median brightness: darker is a drawn line
KEEP_HANGING = False  # True: a garment area mostly above the hip line keeps its part below it (layered
                      # puppet hems). A skinned sheet moves cloth over a thigh with the thigh instead.
SPAN_SHARE = 0.1      # of an area inside a limb's bone core for that limb to count as sharing it
REGION_MAJORITY = 0.6 # share of a painted region one layer must hold to take all of it
HIP_CORE_INSET = 0.5  # rig units the hidden hip core keeps inside the trunk's outline
FILL_MIN_PX = 50      # a painted region smaller than this never colours a hidden fill
FILL_MIN_SHARE = 0.02 # nor one under this share of the layer's visible pixels (trim, ornament)
INK_DARK = 0.5        # of the layer's median brightness: darker pixels are outline ink, not fill colour


def eroded(mask, steps):
    """The mask shrunk by steps pixels (4-neighbour)."""
    m = mask.copy()
    for _ in range(steps):
        inner = m.copy()
        inner[1:] &= m[:-1]
        inner[:-1] &= m[1:]
        inner[:, 1:] &= m[:, :-1]
        inner[:, :-1] &= m[:, 1:]
        m = inner
    return m


def capsule(J, part, ppu, radius, xx, yy, share=1.0):
    """The part's capsule over the picture, as cut_parts measures it (share scales its radius)."""
    a, b, r, _ = cp.PARTS[part]
    if a not in J or b not in J:
        return np.zeros(xx.shape, bool)
    pa, pb, rad = J[a], J[b], radius.get(part, r) * ppu
    if part == "head":
        v = np.subtract(J[b], J[a])
        pa, pb, rad = tuple(J[a] + v * 0.45), tuple(J[a] + v * 0.6), 0.55 * float(np.hypot(*v))
    if part == "weapon":
        v = np.subtract(J[b], J[a])
        pa = tuple(J[a] - v * 0.28)
    return cp.seg_dist(xx, yy, pa, pb) < rad * share


def keyed(img):
    """Straight RGBA. A solid magenta background (the workflow's contract) is keyed out with the
    background unmixed from edge pixels; anything else uses cut_parts' border flood."""
    a = np.asarray(img.convert("RGBA"))
    border = np.concatenate([a[0, :, :3], a[-1, :, :3], a[:, 0, :3], a[:, -1, :3]]).astype(int)
    if a[..., 3].min() >= 250 and (np.abs(border - lp.KEY_COLOR).max(axis=1) < 40).mean() > 0.9:
        rgb = a[..., :3].astype(np.float32)
        k = np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1]
        alpha = np.clip(1 - (k - 22) / 70, 0, 1)
        mix = np.clip(k / 255, 0, 0.92)[..., None]
        fg = (rgb - mix * np.array(lp.KEY_COLOR, np.float32)) / (1 - mix)
        out = np.dstack([np.clip(fg, 0, 255), alpha * 255]).astype(np.uint8)
        out[alpha < 0.02] = 0
        return attached(out)
    return attached(flat_background(a))


def flat_background(a):
    """Remove a flat backdrop of any colour: pixels joined to the border within the backdrop's own
    noise. A fixed tolerance eats pale skin or white cloth next to a light grey backdrop."""
    from scipy import ndimage as ndi
    rgb = a[..., :3].astype(np.int16)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    noise = float(np.percentile(np.abs(border - bg).max(axis=1), 99))
    near = np.abs(rgb - bg).max(axis=2) <= noise + BG_MARGIN
    labels, _ = ndi.label(near)
    edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    out = a.copy()
    out[np.isin(labels, edge[edge > 0])] = 0
    return out


def attached(rgba):
    """Drop specks not joined to solid art: compression noise in a flat background keys out as
    faint islands, invisible on magenta and plain dots on any other background."""
    from scipy import ndimage as ndi
    labels, count = ndi.label(rgba[..., 3] > 0)
    if not count:
        return rgba
    solid = np.bincount(labels[rgba[..., 3] > SOLID_ALPHA], minlength=count + 1)
    solid[0] = 0
    out = rgba.copy()
    out[~(solid > 0)[labels]] = 0
    return out


def hull(mask):
    """The convex hull of a mask's pixels, as a mask (monotone chain over the pixel corners)."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 3:
        return mask.copy()
    pts = sorted(set(zip(xs.tolist(), ys.tolist())))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    poly = lower[:-1] + upper[:-1]
    im = Image.new("1", (mask.shape[1], mask.shape[0]))
    ImageDraw.Draw(im).polygon(poly, fill=1, outline=1)
    return np.asarray(im, dtype=bool)


def ink_regions(rgba, fg):
    """Label the areas of the figure that outline ink encloses: (labels, count). Ink is a pixel far
    darker than its neighbourhood or plain dark; it belongs to no region."""
    from scipy import ndimage as ndi
    luma = rgba[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    local = ndi.median_filter(np.where(fg, luma, 255), size=9)
    # Relative darkness only: an absolute threshold would call black clothing ink and merge both legs
    # of black trousers into one unbroken area.
    ink = fg & (luma < INK_LOCAL * local)
    labels, count = ndi.label(fg & ~ink)
    return labels, count, ink


OUTLINE_BONES = {
    "torso": (("hip", "waist"), ("waist", "neck")),
    "leg_near": (("hip_n", "kn_n"), ("kn_n", "an_n")),
    "leg_far": (("hip_f", "kn_f"), ("kn_f", "an_f")),
    "arm_near": (("sh_n", "el_n"), ("el_n", "wr_n")),
    "arm_far": (("sh_f", "el_f"), ("el_f", "wr_f")),
}
OUTLINE_BINS = 24     # stations along each bone where a layer's two edges are read


def outline_limit(own, free, bones):
    """Where hidden art may go: within the layer's own two edges along its bones. An edge station
    counts where the pixel just past it is background or art behind (free); covered stations take
    the edge interpolated from counted ones, held constant past the last."""
    h, w = own.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    best = np.full((h, w), np.inf, np.float32)
    allowed = np.zeros((h, w), bool)
    which = np.full((h, w), -1, int)
    frames = []
    for i, (a, b) in enumerate(bones):
        a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
        v = b - a
        length = float(np.hypot(*v)) or 1.0
        u = v / length
        t = ((xx - a[0]) * u[0] + (yy - a[1]) * u[1]) / length
        d = (xx - a[0]) * -u[1] + (yy - a[1]) * u[0]
        dist = np.abs(d) + np.maximum(-t, 0) * length + np.maximum(t - 1, 0) * length
        closer = dist < best
        best[closer] = dist[closer]
        which[closer] = i
        frames.append((t, d, u))
    for i, (t, d, u) in enumerate(frames):
        mine = which == i
        sel = own & mine
        if sel.sum() < 10:
            allowed |= mine
            continue
        bins = np.clip(((t + 0.25) / 1.5 * OUTLINE_BINS).astype(int), 0, OUTLINE_BINS - 1)
        centres, hi, lo, hi_ok, lo_ok = [], [], [], [], []
        normal = np.array([-u[1], u[0]])
        for k in range(OUTLINE_BINS):
            m = sel & (bins == k)
            if not m.any():
                continue
            dd = d[m]
            ys, xs = np.nonzero(m)
            top, bot = int(dd.argmax()), int(dd.argmin())
            centres.append(k)
            hi.append(float(dd[top]))
            lo.append(float(dd[bot]))
            for edge, sign, ok in ((top, 1, hi_ok), (bot, -1, lo_ok)):
                x, y = np.round(np.array([xs[edge], ys[edge]]) + normal * sign * 3).astype(int)
                ok.append(not (0 <= x < w and 0 <= y < h) or bool(free[y, x]))
        centres = np.array(centres, float)
        grid = np.arange(OUTLINE_BINS, dtype=float)

        def side(values, ok):
            values, ok = np.array(values), np.array(ok, bool)
            if not ok.any():
                return np.interp(grid, centres, values)
            return np.interp(grid, centres[ok], values[ok])
        top_edge, bottom_edge = side(hi, hi_ok), side(lo, lo_ok)
        allowed |= mine & (d <= top_edge[bins] + 1) & (d >= bottom_edge[bins] - 1)
    return allowed


TWINS = {
    "arm_far": ("arm_near", (("sh_f", "el_f"), ("el_f", "wr_f"), ("wr_f", "hand_f")),
                (("sh_n", "el_n"), ("el_n", "wr_n"), ("wr_n", "hand_n"))),
    "leg_far": ("leg_near", (("hip_f", "kn_f"), ("kn_f", "an_f")), (("hip_n", "kn_n"), ("kn_n", "an_n"))),
}


def twin_points(J, pts, far_bones, near_bones):
    """Each point near a far limb, carried to the same place on the near limb: nearest far bone,
    the share along it and the distance across it, laid on the matching near bone."""
    best = np.full(len(pts), np.inf)
    out = np.zeros_like(pts)
    for (fa, fb), (na, nb) in zip(far_bones, near_bones):
        a, b = np.array(J[fa]), np.array(J[fb])
        v = b - a
        length = np.hypot(*v) or 1.0
        u = v / length
        t = np.clip((pts - a) @ u / length, 0, 1)
        across = (pts - a) @ np.array([-u[1], u[0]])
        dist = np.hypot(*(pts - (a + np.outer(t * length, u))).T)
        c, d = np.array(J[na]), np.array(J[nb])
        vn = d - c
        ln = np.hypot(*vn) or 1.0
        un = vn / ln
        target = c + np.outer(t * ln, un) + np.outer(across, np.array([-un[1], un[0]]))
        closer = dist < best
        best[closer] = dist[closer]
        out[closer] = target[closer]
    return out


def region_fill(rgba, source, regions, target, own_px):
    """Colours for target pixels: the mean colour of the nearest sizeable painted region of the layer."""
    from scipy import ndimage as ndi
    labels = regions * source
    sizes = np.bincount(labels.ravel(), minlength=regions.max() + 1)
    big = sizes >= max(FILL_MIN_PX, FILL_MIN_SHARE * own_px)
    big[0] = False
    seed = big[labels]
    if not seed.any():
        seed = source
        labels = np.where(source, 1, 0)
        sizes = np.bincount(labels.ravel(), minlength=2)
    rgb = rgba[..., :3].astype(np.float64)
    means = np.stack([np.bincount(labels[seed], weights=rgb[seed][:, c], minlength=len(sizes))
                      for c in range(3)], 1) / np.maximum(np.bincount(labels[seed], minlength=len(sizes)), 1)[:, None]
    _, (iy, ix) = ndi.distance_transform_edt(~seed, return_indices=True)
    return np.clip(means[labels[iy[target], ix[target]]], 0, 255).astype(np.uint8)


def measured_radii(fg, J, ppu):
    """Each limb bone's half-width in rig units, measured on the silhouette: from points along the
    bone's middle, half the width across it (one side's distance where the other meets other art). A bone with no clear edge
    (an arm laid over the chest) takes its limb's other bone. Defaults stay for unmeasurable limbs."""
    h, w = fg.shape
    out = {}
    for name in LIMB_BONES:
        a, b = (np.array(J[k]) for k in cp.PARTS[name][:2])
        v = b - a
        across = np.array([-v[1], v[0]]) / (np.hypot(*v) or 1)
        limit = int(2 * cp.PARTS[name][2] * ppu)
        found = []
        # Away from the root, which sits under the trunk's clothes: a scan there runs through the
        # hem and would count it as limb.
        for t in np.linspace(0.35, 0.9, 12):
            sides = []
            for side in (1, -1):
                for d in range(1, limit):
                    x, y = np.round(a + v * t + across * side * d).astype(int)
                    if not (0 <= x < w and 0 <= y < h) or not fg[y, x]:
                        sides.append(d)
                        break
            if len(sides) == 2:
                found.append(sum(sides) / 2)       # the limb's own half-width, wherever the bone sits
            elif sides:
                found.append(sides[0])
        if len(found) >= 3:
            # The wide end of the limb (a sleeve gathered at the elbow), not its middle: cloth past
            # the capsule would be left on the trunk when the limb moves.
            out[name] = float(np.percentile(found, WIDTH_PERCENTILE)) / ppu * WIDTH_PAD
    # The trunk, measured at the waist and over the hips, where the arms hang clear of it. A chibi
    # default would take in a sleeve hanging beside the body.
    spine, pelvis = np.array(J["neck"]) - np.array(J["waist"]), np.array(J["waist"]) - np.array(J["hip"])
    trunk = []
    for base, v, ts in ((np.array(J["waist"]), spine, np.linspace(0.0, 0.15, 4)),
                        (np.array(J["hip"]), pelvis, np.linspace(0.3, 0.9, 5))):
        across = np.array([-v[1], v[0]]) / (np.hypot(*v) or 1)
        for t in ts:
            sides = []
            for side in (1, -1):
                for d in range(1, int(2 * cp.PARTS["torso"][2] * ppu)):
                    x, y = np.round(base + v * t + across * side * d).astype(int)
                    if not (0 <= x < w and 0 <= y < h) or not fg[y, x]:
                        sides.append(d)
                        break
            if len(sides) == 2:
                trunk.append(sum(sides) / 2)
    if len(trunk) >= 3:
        out["torso"] = out["pelvis"] = float(np.median(trunk)) / ppu * WIDTH_PAD
    for name in LIMB_BONES:
        twin = name[:-2] + ("lo" if name.endswith("up") else "up")
        if name not in out and twin in out:
            out[name] = out[twin]
    return {k: round(min(v, cp.PARTS[k][2]), 2) for k, v in out.items()}


class Inpainter:
    """Optional local inpainting (a TorchScript LaMa model): fills only masked pixels of a picture.
    Experimental: the public LaMa weights were trained on Places2, whose terms are non-commercial;
    clear the licence before shipping anything made with them."""

    def __init__(self, path):
        import torch
        self.torch = torch
        torch.set_num_threads(max(1, os.cpu_count() or 1))
        self.model = torch.jit.load(str(path), map_location="cpu").eval()
        self.calls = 0

    def __call__(self, rgb, mask, pad=48):
        """rgb uint8 (h, w, 3), mask bool (h, w): returns rgb with masked pixels painted."""
        torch = self.torch
        ys, xs = np.nonzero(mask)
        h, w = mask.shape
        y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, h)
        x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, w)
        crop, m = rgb[y0:y1, x0:x1], mask[y0:y1, x0:x1]
        ch, cw = crop.shape[:2]
        ph, pw = (-ch) % 8, (-cw) % 8
        image = np.pad(crop, ((0, ph), (0, pw), (0, 0)), mode="edge").astype(np.float32) / 255
        hole = np.pad(m, ((0, ph), (0, pw))).astype(np.float32)
        with torch.no_grad():
            out = self.model(torch.from_numpy(image).permute(2, 0, 1)[None],
                             torch.from_numpy(hole)[None, None])
        self.calls += 1
        painted = (out[0].permute(1, 2, 0).numpy()[:ch, :cw] * 255).clip(0, 255).astype(np.uint8)
        result = rgb.copy()
        result[y0:y1, x0:x1][m] = painted[m]
        return result


# Layers whose hidden art is worth an AI completion, with what the hidden part is, for the prompt.
COMPLETE = {
    "torso": "the side of the upper-body garment (the same panels, colours, trim and pattern) where the arm covered it",
    "arm_far": "the shoulder end of the same rear sleeve, where the body covered it",
    "leg_far": "the top of the same rear trouser leg, where the front leg and the tunic covered it",
    "leg_near": "the top of the same front trouser leg, where the tunic covered it",
}


def split(img, joints, inpaint=None, completions=None, masks_out=None, ownership_out=None):
    """Returns (layers {name: RGBA array on the picture's canvas}, layer joints, order, report)."""
    rgba = keyed(img)
    J = {k: tuple(map(float, v)) for k, v in joints.items() if not k.startswith("_")}
    leg_px = math.dist(J["hip_n"], J["kn_n"]) + math.dist(J["kn_n"], J["an_n"])
    ppu0 = leg_px / (cp.Body().thigh + cp.Body().shin)
    joints = dict(joints)
    # Measured limb widths unless the joints file states them.
    joints["_radius"] = {**measured_radii(rgba[..., 3] > 24, J, ppu0), **joints.get("_radius", {})}
    _, _, cut_report, owner, order = cp.cut(Image.fromarray(rgba, "RGBA"), joints)
    if "hand_n" not in J:
        J["hand_n"] = tuple(np.add(J["wr_n"], np.subtract(J["wr_n"], J["el_n"]) * 0.42))
    if "hand_f" not in J and "wr_f" in J:
        J["hand_f"] = tuple(np.add(J["wr_f"], np.subtract(J["wr_f"], J["el_f"]) * 0.42))
    missing = [k for k in ("sh_f", "el_f", "wr_f", "hip_f", "kn_f", "an_f", "heel_f", "toe_f") if k not in J]
    if missing:
        raise ValueError(f"far limbs need joints {missing}; the layered puppet binds both sides")
    radius = {k: float(v) for k, v in joints.get("_radius", {}).items()}
    h, w = rgba.shape[:2]
    fg = rgba[..., 3] > 24
    ppu = float(cut_report["px_per_unit"])
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    has_weapon = "weapon" in order
    names = [n for n in GROUPS if has_weapon or n != "weapon"]
    part_layer = {p: n for n in names for p in GROUPS[n]}
    rank = {n: i for i, n in enumerate(names)}
    # Which layer owns each pixel, and how far forward it is drawn.
    layer_of = np.full((h, w), -1, int)
    for i, p in enumerate(order):
        if p in part_layer:
            layer_of[owner == i] = rank[part_layer[p]]
    # The trunk starts at the neck joint: what the torso was given above it (hair ends, the chin,
    # the throat) is the head's, so it turns with the head and the head seats over the collar.
    up_axis = np.subtract(J["neck"], J["waist"])
    up_axis = up_axis / (np.hypot(*up_axis) or 1)
    above = (xx - J["neck"][0]) * up_axis[0] + (yy - J["neck"][1]) * up_axis[1] > 0
    layer_of[above & (layer_of == rank["torso"])] = rank["head"]
    # Painted regions stay whole: an area enclosed by outline ink (a hem panel, a sleeve, a trouser
    # leg) goes entirely to the layer holding most of it, instead of being sliced by capsules into
    # flaps that swing loose with the wrong part.
    regions, count, ink = ink_regions(rgba, fg)
    if count:
        valid = (regions > 0) & (layer_of >= 0)
        votes = np.bincount(regions[valid] * len(names) + layer_of[valid],
                            minlength=(count + 1) * len(names)).reshape(count + 1, len(names))
        total = votes.sum(1)
        winner = votes.argmax(1)
        sure = (total > 0) & (votes.max(1) >= REGION_MAJORITY * np.maximum(total, 1))
        # An area across the bone cores of two layers (one dark cloth over both legs, no line between)
        # is ambiguous: it keeps the per-pixel bone assignment instead of going whole to one side.
        cores = np.zeros((count + 1, len(names)), np.int64)
        for n in names:
            core_n = np.zeros((h, w), bool)
            for p_ in GROUPS[n]:
                if p_ in LIMB_BONES:
                    core_n |= capsule(J, p_, ppu, radius, xx, yy, CORE_SHARE)
            if core_n.any():
                cores[:, rank[n]] = np.bincount(regions[core_n & (regions > 0)], minlength=count + 1)
        straddles = ((cores >= SPAN_SHARE * np.maximum(total, 1)[:, None]) & (cores > 0)).sum(1) >= 2
        sure &= ~straddles
        pick = sure[regions] & (regions > 0)
        report_regions = int(sure.sum())
        layer_of[pick] = winner[regions[pick]]
        # A painted region lying mostly below the hip joint is a leg's (trouser tops under a hem),
        # not the trunk's: left on the trunk it hangs below the hem when the legs swing.
        down = np.subtract(J["hip"], J["waist"])
        below = ((xx - J["waist"][0]) * down[0] + (yy - J["waist"][1]) * down[1]) / float(down @ down) > 1.0
        trunk = (layer_of == rank["torso"]) & (regions > 0)
        low = np.bincount(regions[trunk & below], minlength=count + 1)
        all_ = np.bincount(regions[trunk], minlength=count + 1)
        # ...and mostly over a thigh: a hem panel hanging below the hip beside the legs stays.
        thighs = (capsule(J, "leg_n_up", ppu, radius, xx, yy) | capsule(J, "leg_f_up", ppu, radius, xx, yy))
        over = np.bincount(regions[trunk & thighs], minlength=count + 1)
        leggy = (all_ > 0) & (low > 0.5 * all_) & (over > 0.5 * all_)
        leggy[0] = False
        move = trunk & leggy[regions]
        if move.any():
            near = cp.seg_dist(xx, yy, J["hip_n"], J["kn_n"])
            far = cp.seg_dist(xx, yy, J["hip_f"], J["kn_f"])
            layer_of[move & (near <= far)] = rank["leg_near"]
            layer_of[move & (near > far)] = rank["leg_far"]
        # Below the hip joint the trunk keeps only garments hanging from above it (a tunic hem): an
        # area mostly above the hip line. The rest (dark trousers no line splits into two legs) goes
        # pixel by pixel to the nearer leg, or the thigh tops would stay behind when a leg lifts.
        loose = (layer_of == rank["torso"]) & below
        if KEEP_HANGING:
            above = np.bincount(regions[(regions > 0) & ~below], minlength=count + 1)
            sized = np.bincount(regions[regions > 0], minlength=count + 1)
            hanging = (sized > 0) & (above > 0.5 * sized)
            loose &= ~(hanging[regions] & (regions > 0))
        if loose.any():
            near = cp.seg_dist(xx, yy, J["hip_n"], J["kn_n"])
            far = cp.seg_dist(xx, yy, J["hip_f"], J["kn_f"])
            layer_of[loose & (near <= far)] = rank["leg_near"]
            layer_of[loose & (near > far)] = rank["leg_far"]
        # Outline ink goes with the nearest painted region, so a line stays on the shape it draws
        # instead of being cut into loose strokes on other layers.
        from scipy import ndimage as ndi
        painted = (regions > 0) & (layer_of >= 0)
        if painted.any():
            _, (iy, ix) = ndi.distance_transform_edt(~painted, return_indices=True)
            line = ink & fg
            layer_of[line] = layer_of[iy[line], ix[line]]
    # A layer drawn in front owns the core of its own bones. cut_parts' colour tie-break can hand a
    # sleeve's middle to a same-coloured part behind it, which would punch a hole in the limb.
    for n in names:
        for p in GROUPS[n]:
            if p in LIMB_BONES:
                core = capsule(J, p, ppu, radius, xx, yy, CORE_SHARE) & fg
                layer_of[core & (layer_of < rank[n])] = rank[n]
    if ownership_out is not None:
        ownership_out.update(layer_of=layer_of.copy(), names=list(names), rgba=rgba, J=J, ppu=ppu)
    report = {"px_per_unit": round(ppu, 3), "measured_radius": radius, "layers": {}, "warnings": list(cut_report["warnings"]),
              "blockers": [], "image_generation_calls": 0}
    layers = {}
    # Near limbs first: a far limb's hidden part is rebuilt from its finished twin. The torso before
    # the hidden hip core, which must stay inside it.
    later = ("hips",) + FAR_LIMBS
    for n in [m for m in names if m not in later] + [m for m in names if m in later]:
        parts = GROUPS[n] or ("pelvis",)
        own = layer_of == rank[n]
        area = np.zeros((h, w), bool)
        core = np.zeros((h, w), bool)
        for p in parts:
            area |= capsule(J, p, ppu, radius, xx, yy)
            core |= capsule(J, p, ppu, radius, xx, yy, 0.5)
        area &= fg
        if n == "hips":
            # Hidden core under the legs: a copy of the visible trunk over the pelvis, with what the
            # legs cover filled in. Never shown at rest; it keeps the body closed when legs swing.
            # Only between the waist and the hip joint: below it the legs part, and anything the core
            # carried there (a hem slit, trouser tops) would show between them.
            down = np.subtract(J["hip"], J["waist"])
            along = ((xx - J["waist"][0]) * down[0] + (yy - J["waist"][1]) * down[1]) / float(down @ down)
            area &= along <= 1.0
            # Inside the finished trunk, short of its hem: never seen at rest or between the legs.
            if "torso" in layers:
                area &= eroded(layers["torso"][..., 3] > 0, max(1, round(HIP_CORE_INSET * ppu)))
            own = area & (layer_of == rank["torso"])
        if n == "head":
            # The head keeps its own neck down past the collar, so it stays seated under the torso.
            v = np.subtract(J["neck"], J["head_base"])
            end = tuple(np.add(J["neck"], v * NECK_REACH))
            neck_w = cp.PARTS["torso"][2] * ppu * 0.45
            own |= fg & (cp.seg_dist(xx, yy, J["head_base"], end) < neck_w) & (layer_of == rank["torso"])
        # Pixels a layer in front hides inside this layer's capsules; the head never hides another.
        hidden = area & ~own & ((layer_of > rank[n]) | (n == "hips"))
        if n != "head":
            hidden &= layer_of != rank["head"]
        if n in OUTLINE_BONES:
            # Hidden outline continues the visible one along the bones: where a layer in front
            # covers this layer's edge, the edge runs on from the uncovered edge above and below.
            # Guessing a shape there (a hull, a capsule, a neighbour's outline) leaves a flap where
            # the cover moves away.
            free = ~fg | (layer_of < rank[n])
            hidden &= outline_limit(own, free, [(J[a], J[b]) for a, b in OUTLINE_BONES[n] if a in J and b in J])
        visible = float(own[area].mean()) if area.any() else 0.0
        info = {"visible": round(visible, 3), "own_px": int(own.sum()), "filled_px": int(hidden.sum())}
        report["layers"][n] = info
        if n in FAR_LIMBS and visible < MIN_VISIBLE:
            report["blockers"].append(f"{n}: only {visible:.0%} visible; a local fill would invent the limb. "
                                      "Request a reference with the far limb clear of the body.")
        if not own.any():
            report["blockers"].append(f"{n}: no pixels")
            continue
        # Grow from the layer's interior, not its edge: edge pixels are outline ink (its own, or a
        # neighbour's the cut gave it), which a fill would smear into dark stripes.
        seed = eroded(own, max(1, round(INK_UNITS * ppu)))
        # Outline ink thicker than that erosion: far darker than the layer's typical colour.
        luma = rgba[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
        if own.any():
            seed &= luma > INK_DARK * float(np.median(luma[own]))
        if seed.sum() < 0.1 * own.sum():
            seed = own
        steps = int(cp.PARTS[parts[0]][2] * ppu * 2) + 2
        pix, have = cp.fill_from(rgba, seed, own | hidden, steps + max(1, round(INK_UNITS * ppu)))
        keep = have & (own | hidden)
        # Hidden art continues the painted areas beside it, each in its own flat colour (a green
        # panel stays green, a white sleeve white). No blurred ramp (it reads as a smear when a limb
        # swings away) and no colour from small details such as trim, which would streak.
        filled = keep & ~own
        if filled.any():
            pix[filled, :3] = region_fill(rgba, own & ~ink, regions, filled, own.sum())
        if masks_out is not None and n in COMPLETE and filled.any():
            masks_out[n] = (own & (rgba[..., 3] == 255), filled.copy())
        done = completions and Path(completions, n, "completed.png").exists()
        if done and filled.any():
            # An approved masked completion: its pixels inside the recorded completion mask only.
            expected = np.asarray(Image.open(Path(completions, n, "completion_mask.png"))) > 0
            if not np.array_equal(expected, filled):
                raise ValueError(f"{n}: completion mask no longer matches this split; export again")
            completed = np.asarray(Image.open(Path(completions, n, "completed.png")).convert("RGBA"))
            pix[filled] = completed[filled]
            info["completed_by"] = "masked AI completion"
        elif inpaint is not None and filled.any():
            # Context is this layer alone: other layers' art (the arm in front) is flattened to the
            # layer's own colour so it is not continued into the hidden area. Only filled pixels change.
            context = rgba[..., :3].copy()
            context[~own] = np.median(rgba[own & ~ink][:, :3], axis=0).astype(np.uint8) if (own & ~ink).any() else 128
            painted = inpaint(context, filled)
            pix[filled, :3] = painted[filled]
        if n in TWINS and TWINS[n][0] in layers and filled.any():
            # A far arm or leg is drawn like its near twin: its hidden part takes the twin's art at
            # the same place along the same bone (shape, outline and shading), and nothing where the
            # twin has none, so the far limb never grows a flap past a limb's outline.
            twin, far_bones, near_bones = TWINS[n]
            ys, xs = np.nonzero(filled)
            mapped = twin_points(J, np.column_stack([xs, ys]).astype(float), far_bones, near_bones)
            mx, my = np.round(mapped).astype(int).T
            ok = (mx >= 0) & (mx < w) & (my >= 0) & (my < h)
            src = np.zeros((len(xs), 4), np.uint8)
            src[ok] = layers[twin][my[ok], mx[ok]]
            has = src[:, 3] > 0
            if inpaint is None and not done:
                pix[ys[has], xs[has]] = src[has]       # without an inpainter, the twin's art too
            keep[ys[~has], xs[~has]] = False
            info["from_twin_px"] = int(has.sum())
        # Only art joined to the layer's own bones: a stray sliver would float beside the limb.
        joined = cp.reached(keep, core & keep) if (core & keep).any() else keep
        if (keep & ~joined).any():
            info["dropped_px"] = int((keep & ~joined).sum())
        keep = joined
        pix[~keep] = 0
        pix[own & keep] = rgba[own & keep]         # visible pixels stay exactly as painted
        if hidden.sum() > FILL_WARN * max(area.sum(), 1):
            report["warnings"].append(f"{n}: {int(hidden.sum())} hidden pixels filled locally from its own "
                                      "colours; check layers_overview.png")
        layers[n] = pix
    lj = {
        "head": {"head_base": J["head_base"]},
        "hips": {"hip": J["hip"], "waist": J["waist"]},
        "arm_near": {"shoulder": J["sh_n"], "elbow": J["el_n"], "wrist": J["wr_n"]},
        "arm_far": {"shoulder": J["sh_f"], "elbow": J["el_f"], "wrist": J["wr_f"]},
        "leg_near": {"hip": J["hip_n"], "knee": J["kn_n"], "ankle": J["an_n"]},
        "leg_far": {"hip": J["hip_f"], "knee": J["kn_f"], "ankle": J["an_f"]},
    }
    if has_weapon:
        lj["weapon"] = {"grip": J["weapon_grip"]}
    lj = {n: {k: [round(float(c), 2) for c in p] for k, p in row.items()} for n, row in lj.items()}
    return layers, lj, names, report


def overview(layers, order, size):
    """Each layer alone on grey, back to front, for visual review of the local fill."""
    w, h = size
    cols = 4
    rows = math.ceil(len(order) / cols)
    sheet = Image.new("RGBA", (cols * w, rows * h + 0), (96, 96, 96, 255))
    d = ImageDraw.Draw(sheet)
    for i, n in enumerate(order):
        x, y = (i % cols) * w, (i // cols) * h
        sheet.alpha_composite(Image.fromarray(layers[n], "RGBA"), (x, y))
        d.text((x + 6, y + 6), n, fill=(255, 255, 255, 255))
    return sheet


def export_completions(rgba, masks, folder):
    """One masked-completion request per layer: plate.png (visible art on grey, the area to paint in
    pure green), the masks, and the prompt. Generated plates go back through compose()."""
    import masked_completion as mc
    folder = Path(folder)
    keyed_path = folder / "keyed.png"
    folder.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(keyed_path)
    for n, (visible, completion) in masks.items():
        d = folder / n
        d.mkdir()
        Image.fromarray((visible & ~completion).astype(np.uint8) * 255, "L").save(d / "visible_mask.png")
        Image.fromarray(completion.astype(np.uint8) * 255, "L").save(d / "completion_mask.png")
        mc.prepare(keyed_path, d / "visible_mask.png", d / "completion_mask.png", d / "request")
        (d / "prompt.txt").write_text(
            "Edit the attached image. Paint ONLY the pure bright green (#00FF00) area. Fill it with "
            f"{COMPLETE[n]}, continuing the surrounding artwork seamlessly: same linework, colours, "
            "shading and painting style. Keep every non-green pixel exactly as it is: do not move, "
            "redraw, recolour or extend anything else, and keep the light grey background grey. "
            "No green may remain. Output one square image, same framing and size as the input.\n",
            encoding="utf-8")


def run(image, joints_path, out, name="character", inpaint_model=None, completions=None,
        export=None):
    out = Path(out)
    if out.exists():
        raise ValueError("output exists; choose a new version folder")
    img = Image.open(image).convert("RGBA")
    joints = json.loads(Path(joints_path).read_text(encoding="utf-8"))
    inpaint = Inpainter(inpaint_model) if inpaint_model else None
    masks = {} if export else None
    layers, lj, order, report = split(img, joints, inpaint, completions, masks)
    if export:
        export_completions(keyed(img), masks, export)
    if inpaint is not None:
        report["local_inpaint_calls"] = inpaint.calls
        report["inpaint_model"] = str(inpaint_model)
    out.mkdir(parents=True)
    (out / "layers").mkdir()
    for n, pix in layers.items():
        Image.fromarray(pix, "RGBA").save(out / "layers" / f"{n}.png")
    overview(layers, [n for n in order if n in layers], img.size).convert("RGB").save(out / "layers_overview.png")
    img.save(out / "reference.png")
    manifest = {"name": name, "layers": {n: f"layers/{n}.png" for n in order if n in layers},
                "joints": lj, "order": [n for n in order if n in layers]}
    (out / "rig_input.json").write_text(json.dumps(manifest, indent=1) + "\n")
    report["scope"] = "local split and fill only; visual review and user motion approval pending"
    (out / "local_report.json").write_text(json.dumps(report, indent=1) + "\n")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True)
    ap.add_argument("--joints", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="character")
    ap.add_argument("--inpaint-model", help="TorchScript LaMa model for hidden areas (experimental, check licence)")
    ap.add_argument("--export-completion", help="folder: write one masked AI-completion request per layer")
    ap.add_argument("--completions", help="folder of composed completions (completed.png per layer) to use")
    a = ap.parse_args()
    report = run(a.image, a.joints, a.out, a.name, a.inpaint_model, a.completions, a.export_completion)
    for line in report["warnings"]:
        print("warning:", line)
    for line in report["blockers"]:
        print("BLOCKED:", line)
    print(f"[local] {len(report['layers'])} layers -> {a.out}; image generation calls: 0")
    if report["blockers"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
