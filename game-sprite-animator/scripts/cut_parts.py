#!/usr/bin/env python3
"""Turn one full-body picture (AI-generated or drawn) into cut-out parts for the rig.

    python cut_parts.py template --out tpl/                    # pose reference + joints to copy
    python cut_parts.py cut --image knight.png --joints knight_joints.json --out knight/
    python cut_parts.py check --character knight/character.json
    python generate.py --character knight/character.json --preset hd --out out/knight

template  renders the reference pose: template.png (the pose to ask the image model for),
          template_joints.png (every joint labelled) and joints.json (their pixel positions).
cut       splits the picture into the rig's parts. joints.json lists each joint's pixel position
          in the picture; copy the template's file and move the points onto the new art. Writes
          parts/*.png, character.json (ready for generate.py), bind_report.json,
          bind_preview.png (each part tinted, joints marked) and motion_check.png (the cut-out
          through the clips that bend it most). Exits 1 if a joint opens while moving.
check     re-runs that motion check on a character.json, e.g. after editing a part by hand.

How parts are cut: every bone is a capsule between two joints. A pixel goes to the bone it lies
deepest inside; where capsules overlap, the part drawn in front wins unless the pixel's colour
matches the part behind much better. Each part keeps a round cap of its neighbours' pixels at
the joints, so bending never opens a gap, and pixels a front part hides are filled from the
part's own colours. Parts are then turned upright (limbs hanging down, feet flat) as the rig
expects, and the bone lengths measured from the picture go into character.json.

Far-side limbs are usually hidden behind the body. When less than half of one is visible it is
rebuilt from the near-side limb, darkened, and the report says so: ask for better art there.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sprite_anim.art import Canvas, CharacterArt, hand_grip  # noqa: E402
from sprite_anim.rig import Body, full_pose, heel_world, solve, toe_world  # noqa: E402
from sprite_anim.mathx import add, rot, scale  # noqa: E402
from sprite_anim.render import GROUND_FRAC, UNIT_PX  # noqa: E402

# Standing with every limb clear of the body: what template.png shows and the prompt asks for.
CUT_POSE = dict(pelvis=0.0, spine=0.0, head=0.0, arm_n_up=30.0, arm_n_lo=18.0, arm_f_up=-24.0,
                arm_f_lo=14.0, foot_n_x=9.0, foot_f_x=-9.0, wep=62.0)

# part: (from joint, to joint, radius in rig units, kind). Back to front, as Cutout draws them.
# kind says how the part is turned upright: limb = bone hangs down, up = bone points up,
# foot = heel->toe level, weapon = grip->tip points up.
PARTS = {
    "arm_f_up": ("sh_f", "el_f", 3.6, "limb"),
    "arm_f_lo": ("el_f", "wr_f", 3.3, "limb"),
    "hand_f": ("wr_f", "hand_f", 3.2, "hand"),
    "leg_f_up": ("hip_f", "kn_f", 4.8, "limb"),
    "leg_f_lo": ("kn_f", "an_f", 4.2, "limb"),
    "foot_f": ("heel_f", "toe_f", 3.2, "foot"),
    "leg_n_up": ("hip_n", "kn_n", 4.8, "limb"),
    "leg_n_lo": ("kn_n", "an_n", 4.2, "limb"),
    "foot_n": ("heel_n", "toe_n", 3.2, "foot"),
    "pelvis": ("hip", "waist", 8.5, "up"),
    "torso": ("waist", "neck", 9.5, "up"),
    "head": ("head_base", "head_top", 15.0, "up"),
    "weapon": ("weapon_grip", "weapon_tip", 2.6, "weapon"),
    "arm_n_up": ("sh_n", "el_n", 3.6, "limb"),
    "arm_n_lo": ("el_n", "wr_n", 3.3, "limb"),
    "hand_n": ("wr_n", "hand_n", 3.2, "hand"),
}
PIVOT = {"hand_f": "wr_f", "hand_n": "wr_n", "foot_f": "an_f", "foot_n": "an_n", "weapon": "weapon_grip"}
# Parts that share a joint: they trade a round cap of pixels there so bending can't open a gap.
NEIGHBOURS = [("arm_f_up", "arm_f_lo"), ("arm_f_lo", "hand_f"), ("leg_f_up", "leg_f_lo"), ("leg_f_lo", "foot_f"),
              ("leg_n_up", "leg_n_lo"), ("leg_n_lo", "foot_n"), ("arm_n_up", "arm_n_lo"), ("arm_n_lo", "hand_n"),
              ("pelvis", "torso"), ("torso", "head"), ("pelvis", "leg_n_up"), ("pelvis", "leg_f_up"),
              ("torso", "arm_n_up"), ("torso", "arm_f_up")]
CAP_MAX = 4.0     # rig units: largest round cap two parts share at a joint
FAR = {"arm_f_up": "arm_n_up", "arm_f_lo": "arm_n_lo", "hand_f": "hand_n",
       "leg_f_up": "leg_n_up", "leg_f_lo": "leg_n_lo", "foot_f": "foot_n"}
REQUIRED = ["head_top", "head_base", "neck", "waist", "hip", "sh_n", "el_n", "wr_n", "hip_n", "kn_n", "an_n",
            "heel_n", "toe_n"]


# -- geometry ------------------------------------------------------------------------------

def up(p):
    """Picture pixels (y down) -> y-up space, the rig's convention."""
    return (p[0], -p[1])


def part_angle(kind, a, b):
    """Clockwise degrees the part is turned in the picture, in Cutout's convention for that part."""
    dx, dy = b[0] - a[0], -(b[1] - a[1])
    if kind in ("limb", "hand"):
        return -math.degrees(math.atan2(dx, -dy))
    if kind == "up":
        return math.degrees(math.atan2(dx, dy))
    if kind == "foot":
        return math.degrees(math.atan2(-dy, dx))
    return 180 - math.degrees(math.atan2(dx, -dy))     # weapon: Cutout turns it by 180 - wep_a


def seg_dist(px, py, a, b):
    ax, ay = a
    vx, vy = b[0] - ax, b[1] - ay
    L2 = vx * vx + vy * vy or 1e-9
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / L2, 0, 1)
    return np.hypot(px - (ax + t * vx), py - (ay + t * vy))


def palette(pixels, k=4, iters=8):
    """A few representative colours (tiny k-means), enough to tell a sleeve from a tunic."""
    if len(pixels) > 4000:
        pixels = pixels[np.linspace(0, len(pixels) - 1, 4000).astype(int)]
    lum = pixels.sum(1)
    cent = np.stack([pixels[np.argsort(lum)[int(q * (len(pixels) - 1))]] for q in np.linspace(0.1, 0.9, k)])
    for _ in range(iters):
        lab = np.abs(pixels[:, None, :] - cent[None]).sum(2).argmin(1)
        for j in range(k):
            if (lab == j).any():
                cent[j] = pixels[lab == j].mean(0)
    return cent


def colour_distance(pixels, cent):
    """0 = one of the part's colours, 1 = as far as colours go (mean channel difference)."""
    if cent is None:
        return np.full(len(pixels), 0.35, np.float32)
    return np.abs(pixels[:, None, :] - cent[None]).sum(2).min(1) / (3 * 255)


def reached(mask, seeds):
    """Pixels of mask connected to any seed pixel (4-neighbour flood, in C via PIL)."""
    im = Image.fromarray(mask.astype(np.uint8)).copy()   # fromarray shares a read-only buffer
    ys, xs = np.nonzero(seeds & mask)
    for y, x in zip(ys[::97], xs[::97]):       # a sparse set of seeds is plenty for one region
        if im.getpixel((int(x), int(y))) == 1:
            ImageDraw.floodfill(im, (int(x), int(y)), 2)
    return np.asarray(im) == 2


def drop_strays(owner, stack, order, fg):
    """A part keeps only pixels joined to its own core. Specks cut off from it (a stray outline,
    a sliver of a sword guard beside the hand) go to the next-closest part, if they touch it, or
    are dropped: left as they are they would float beside the limb when it moves."""
    for _ in range(2):
        moved = False
        for i in range(len(order)):
            own = owner == i
            if not own.any():
                continue
            core = own & (stack[i] < 0)
            keep = reached(own, core) if core.any() else own
            stray = own & ~keep
            if not stray.any():
                continue
            alt = stack.copy()
            alt[i] = np.inf
            owner[stray] = np.argmin(alt, axis=0)[stray]
            moved = True
        if not moved:
            break
    for i in range(len(order)):     # whatever still floats free after that is dropped
        own = owner == i
        core = own & (stack[i] < 0)
        if own.any() and core.any():
            owner[own & ~reached(own, core)] = -1
    return owner


def fill_from(rgba, own, region, steps):
    """Grow own pixels' colours into region (pixels a front part hid), nearest first."""
    out = rgba.copy()
    have = own.copy()
    todo = region & ~have
    for _ in range(steps):
        if not todo.any():
            break
        acc = np.zeros(rgba.shape[:2] + (4,), np.float32)
        cnt = np.zeros(rgba.shape[:2], np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            src = np.roll(np.roll(have, dy, 0), dx, 1)
            col = np.roll(np.roll(out, dy, 0), dx, 1).astype(np.float32)
            acc[src] += col[src]
            cnt += src
        grow = todo & (cnt > 0)
        out[grow] = (acc[grow] / cnt[grow, None]).astype(np.uint8)
        out[grow, 3] = 255
        have |= grow
        todo &= ~grow
    return out, have


# -- template ------------------------------------------------------------------------------

def template(spec, size):
    """Reference pose: the picture, its joints in picture pixels, and the labelled version."""
    spec = dict(spec, cloth=[])
    art = CharacterArt(spec)
    pose = full_pose(CUT_POSE)
    sk = solve(pose, art.body)
    unit = size * UNIT_PX
    cv = Canvas(size, 4, unit, GROUND_FRAC, max(1.0, size / 256 * 1.5), False, art.ink)
    art.draw(cv, sk, pose, {}, None)
    img = Image.fromarray((np.clip(cv.resolve(), 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")

    def px(p):
        x, y = cv.T(p)
        return [round(x / cv.ss, 2), round(y / cv.ss, 2)]

    hs = art.body.head_size
    j = {k: sk[k] for k in ("head_base", "neck", "waist", "hip", "sh_n", "el_n", "wr_n", "sh_f", "el_f", "wr_f",
                             "hip_n", "kn_n", "an_n", "hip_f", "kn_f", "an_f")}
    j["head_top"] = add(sk["head_base"], rot((0, 30 * hs), sk["head_rot"]))
    for s in "nf":
        j["hand_" + s] = add(sk["wr_" + s], scale((sk["wr_" + s][0] - sk["el_" + s][0], sk["wr_" + s][1] - sk["el_" + s][1]), 0.42))
        j["heel_" + s], j["toe_" + s] = heel_world(sk, s), toe_world(sk, s)
    if spec.get("weapon", "sword") != "none":
        hilt, tip = art.blade_points(sk)
        j["weapon_grip"], j["weapon_tip"] = hand_grip(sk), tip     # the fist, on the blade's line
    joints = {k: px(v) for k, v in j.items()}
    labelled = img.copy()
    d = ImageDraw.Draw(labelled)
    for k, (x, y) in joints.items():
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 40, 90, 255), outline=(255, 255, 255, 255))
        d.text((x + 4, y - 6), k, fill=(255, 255, 255, 255))
    return img, labelled, joints


# -- cut -----------------------------------------------------------------------------------

def foreground(img, tol=28):
    """Alpha if the picture has it, else flood the border colour away (plain backgrounds)."""
    a = np.asarray(img.convert("RGBA")).copy()
    if a[..., 3].min() < 250:
        return a
    rgb = a[..., :3].astype(int)
    h, w = rgb.shape[:2]
    corners = np.array([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
    bg = np.median(corners, axis=0)
    near = np.abs(rgb - bg).max(axis=2) <= tol
    seen = np.zeros((h, w), bool)
    seen[0, :], seen[-1, :], seen[:, 0], seen[:, -1] = near[0, :], near[-1, :], near[:, 0], near[:, -1]
    while True:     # flood from the border through background-coloured pixels only
        grow = seen.copy()
        grow[1:] |= seen[:-1]
        grow[:-1] |= seen[1:]
        grow[:, 1:] |= seen[:, :-1]
        grow[:, :-1] |= seen[:, 1:]
        grow &= near
        if (grow == seen).all():
            break
        seen = grow
    a[seen, 3] = 0
    return a


def cut(img, joints, base=None):
    """Returns (parts {name: (canonical RGBA image, pivot)}, character spec, report)."""
    base = dict(base or {})
    missing = [k for k in REQUIRED if k not in joints]
    if missing:
        raise ValueError(f"joints.json is missing {missing}")
    J = {k: tuple(map(float, v)) for k, v in joints.items() if not k.startswith("_")}
    # The picture's own layering, when it differs from the rig's. Side views often hold the weapon
    # in the far hand: that arm is behind the chest in the picture, though the rig draws the weapon
    # arm in front. "_behind" / "_front" list parts to treat as behind / in front of the body while
    # cutting; the animation still layers parts the rig's way.
    behind, front_parts = set(joints.get("_behind", [])), set(joints.get("_front", []))
    # "_radius": a part's half-width in rig units where the art is much slimmer or bulkier than the
    # defaults in PARTS (a wide armoured skirt, a thin staff).
    radius = {k: float(v) for k, v in joints.get("_radius", {}).items()}
    unknown = (behind | front_parts | set(radius)) - set(PARTS)
    if unknown:
        raise ValueError(f"_behind/_front/_radius name unknown parts {sorted(unknown)}")
    has_weapon = "weapon_grip" in J and "weapon_tip" in J
    rgba = foreground(img)
    h, w = rgba.shape[:2]
    fg = rgba[..., 3] > 24
    body = Body.from_spec(base.get("body"))

    # Scale from the legs, whose length the motions are built around; the rest is measured.
    def length(a, b):
        return math.dist(J[a], J[b])

    leg_px = length("hip_n", "kn_n") + length("kn_n", "an_n")
    ppu = leg_px / (body.thigh + body.shin)
    measured = {
        "thigh": length("hip_n", "kn_n") / ppu, "shin": length("kn_n", "an_n") / ppu,
        "up_arm": length("sh_n", "el_n") / ppu, "lo_arm": length("el_n", "wr_n") / ppu,
        "pelvis_len": length("hip", "waist") / ppu, "chest_len": length("waist", "neck") / ppu,
    }
    # Where the rig hangs arms, legs and head comes from these lengths, not from the marks, so fit
    # them to the marks: measured along the torso's own axis, the shoulder sets chest_len (the rig
    # hangs it 3 units below the chest top), the head base sets neck_len, and the near hip's
    # offset sets hip_w. Otherwise a part sits a little off its neighbour and bending opens a gap.
    spine = np.subtract(up(J["neck"]), up(J["waist"]))
    u = spine / (np.hypot(*spine) or 1)
    fwd = np.array([u[1], -u[0]])

    def local(name):
        v = np.subtract(up(J[name]), up(J["waist"])) / ppu
        return float(v @ fwd), float(v @ u)

    def width(near_off, near_k, far_off, far_k):
        """One width sets both sides (near at near_k * w, far at far_k * w): least squares over the
        sides that are marked. Fitting the near side alone can throw the far limb far off."""
        pairs = [(near_off, near_k)] + ([(far_off, far_k)] if far_off is not None else [])
        w = sum(o * k for o, k in pairs) / sum(k * k for _, k in pairs)
        return min(max(w, 0.0), 6.0)

    sh_x, sh_y = local("sh_n")
    measured["chest_len"] = max(sh_y + 3.0, 6.0)
    measured["neck_len"] = max(local("head_base")[1] - measured["chest_len"], 0.0)
    # The rig puts the near shoulder 0.4 * sh_w behind the spine and the far one sh_w in front.
    measured["sh_w"] = width(sh_x, -0.4, local("sh_f")[0] if "sh_f" in J else None, 1.0)
    pel = np.subtract(up(J["waist"]), up(J["hip"]))
    pfwd = np.array([pel[1], -pel[0]]) / (np.hypot(*pel) or 1)

    def hip_off(name):
        return float(np.subtract(up(J[name]), up(J["hip"])) @ pfwd) / ppu

    # And the near hip joint 0.3 * hip_w in front of the hip centre, the far one hip_w behind.
    measured["hip_w"] = width(hip_off("hip_n"), 0.3, hip_off("hip_f") if "hip_f" in J else None, -1.0)
    if "hand_n" not in J:
        J["hand_n"] = tuple(np.add(J["wr_n"], np.subtract(J["wr_n"], J["el_n"]) * 0.42))
    names = [n for n in PARTS if has_weapon or n != "weapon"]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sd = {}
    for n in names:
        a, b, r, _ = PARTS[n]
        if a not in J or b not in J:
            continue
        pa, pb, rad = J[a], J[b], radius.get(n, r) * ppu
        if n == "head":     # a disc around the skull, not a capsule reaching down the neck
            v = np.subtract(J[b], J[a])
            pa, pb, rad = tuple(J[a] + v * 0.45), tuple(J[a] + v * 0.6), 0.55 * float(np.hypot(*v))
        if n == "weapon":   # grip and pommel run back past the fist, along the same line
            v = np.subtract(J[b], J[a])
            pa = tuple(J[a] - v * 0.28)
        sd[n] = seg_dist(xx, yy, pa, pb) - rad
    order = [n for n in names if n in sd]
    order = [n for n in order if n in behind] + [n for n in order if n not in behind and n not in front_parts] \
        + [n for n in order if n in front_parts]
    z = {n: i for i, n in enumerate(order)}
    rad = np.array([radius.get(n, PARTS[n][2]) * ppu for n in order])[:, None, None]
    stack = np.stack([sd[n] for n in order])
    inside = stack < 0
    rgb = rgba[..., :3].astype(np.float32)
    # Each part's own colours: a few clusters from pixels deep inside it and no other part.
    palettes = []
    for i, n in enumerate(order):
        core = fg & (stack[i] < -0.4 * rad[i]) & (inside.sum(0) == 1)
        palettes.append(palette(rgb[core]) if core.sum() > 8 else None)
    # Geometry first: the front-most capsule a pixel is inside owns it, else the one it is
    # deepest in. Colours share a lot between parts (sleeve and tunic), so they only overrule
    # that when a pixel clearly matches a neighbouring part instead, such as a sword guard
    # sticking out of the blade's capsule over the belt.
    front = np.where(inside, np.arange(len(order))[:, None, None], -1).max(axis=0)
    owner = np.where(fg, np.argmin(stack, axis=0), -1)
    claim = fg & (front >= 0)
    owner[claim] = front[claim]
    reach = fg[None] & (stack < 0.6 * rad)
    cds = np.full(stack.shape, np.inf, np.float32)
    for i in range(len(order)):
        if reach[i].any() and palettes[i] is not None:
            cds[i][reach[i]] = colour_distance(rgb[reach[i]], palettes[i])
    best = np.argmin(cds, axis=0)
    ys, xs = np.nonzero(fg)
    cur = owner[ys, xs]
    own_cd = cds[cur, ys, xs]
    alt = best[ys, xs]
    better = (alt != cur) & (cds[alt, ys, xs] + 0.12 < own_cd)
    owner[ys[better], xs[better]] = alt[better]

    owner = drop_strays(owner, stack, order, fg)

    report = {"px_per_unit": round(ppu, 3), "parts": {}, "warnings": []}
    masks = {n: (owner == z[n]) for n in order}
    for a_, b_ in NEIGHBOURS:     # round caps at shared joints
        if a_ not in masks or b_ not in masks:
            continue
        jx, jy = J[PIVOT.get(b_, PARTS[b_][0])]
        # Enough to bridge the joint while it bends, never a big shared patch: a cap the size of
        # the torso's would copy the face onto the chest, showing when the head turns.
        cap = np.hypot(xx - jx, yy - jy) < min(radius.get(a_, PARTS[a_][2]), radius.get(b_, PARTS[b_][2]), CAP_MAX) * ppu
        both = cap & (masks[a_] | masks[b_])
        masks[a_] = masks[a_] | both
        masks[b_] = masks[b_] | both

    parts = {}
    for n in order:
        a, b, r, kind = PARTS[n]
        own = masks[n]
        capsule = (sd[n] < 0) & fg
        cover = own.sum() / max(capsule.sum(), 1)
        r = radius.get(n, r)
        info = {"coverage": round(float(cover), 2)}
        if n in FAR and cover < 0.5:
            info["source"] = "near limb, darkened"
            report["warnings"].append(f"{n}: only {cover:.0%} visible, rebuilt from {FAR[n]}; better art would help")
            report["parts"][n] = info
            continue
        # Fill what parts in front hide (an arm across the chest, the head over the collar):
        # when they move away, the part underneath must not show a hole.
        hidden = capsule & ~own & fg & (owner > z[n])
        if "head" in z and n != "head":
            hidden &= owner != z["head"]     # the head always covers its own patch; filling it would paint skin under the chin
        pivot = J[PIVOT.get(n, a)]
        region = hidden | own
        if kind in ("limb", "hand", "foot"):
            # A limb ends in a full round cap at its pivot, as cut-out puppets do: if the mark sits
            # near the body's edge, turning the limb would otherwise show its flat cut end.
            region |= np.hypot(xx - pivot[0], yy - pivot[1]) < 0.9 * r * ppu
        pix, have = fill_from(rgba, own, region, int(r * ppu) + 2)
        if hidden.sum() > 0.15 * max(capsule.sum(), 1):
            info["filled_px"] = int(hidden.sum())
            report["warnings"].append(f"{n}: {hidden.sum()} hidden pixels filled from its own colours; check bind_preview.png")
        pix[~have] = 0
        # Cutout turns a hand with the forearm, so it is set upright along the forearm too.
        ang = part_angle(kind, *((J["el_" + n[-1]], J["wr_" + n[-1]]) if kind == "hand" else (J[a], J[b])))
        im = Image.fromarray(pix, "RGBA").rotate(ang, resample=Image.BICUBIC, center=pivot)
        box = im.getbbox()
        if not box:
            report["warnings"].append(f"{n}: no pixels")
            continue
        pad = 2
        box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, w), min(box[3] + pad, h))
        parts[n] = (im.crop(box), (round(pivot[0] - box[0], 2), round(pivot[1] - box[1], 2)))
        info["angle"] = round(ang, 1)
        report["parts"][n] = info
    for n, src in FAR.items():
        if n in order and n not in parts and src in parts:
            im, pv = parts[src]
            a = np.asarray(im).copy()
            a[..., :3] = (a[..., :3] * 0.72).astype(np.uint8)    # the procedural art's far shade
            parts[n] = (Image.fromarray(a, "RGBA"), pv)

    # How far the rig's own joints land from the picture's, once lengths are measured: a big gap
    # means a part will hang off its neighbour. Compared in the reference pose's angles.
    spec = {k: v for k, v in base.items() if k not in ("parts", "body", "_dir")}
    spec.update(name=base.get("name", "cutout"), cloth=[], px_per_unit=round(ppu, 4),
                body={**base.get("body", {}), **{k: round(v, 3) for k, v in measured.items()}})
    spec.setdefault("weapon", "sword" if has_weapon else "none")
    spec["parts"] = {n: {"image": f"parts/{n}.png", "pivot": list(pv)} for n, (_, pv) in parts.items()}
    if behind or front_parts:     # animate with the picture's layering, as it was cut
        spec["layers"] = {k: sorted(v) for k, v in (("behind", behind), ("front", front_parts)) if v}
    # Marking checks: a joint off the character, limbs that don't match, a foot of the wrong size.
    for k, (x, y) in J.items():
        if not (0 <= x < w and 0 <= y < h):
            raise ValueError(f"joint {k} at {x:.0f},{y:.0f} is outside the {w}x{h} picture")
        y0, y1, x0, x1 = int(max(y - 3 * ppu, 0)), int(min(y + 3 * ppu, h)), int(max(x - 3 * ppu, 0)), int(min(x + 3 * ppu, w))
        if not fg[y0:y1, x0:x1].any():
            report["warnings"].append(f"joint {k} is not on the character; check its position")
    for a_, b_ in (("sh", "el"), ("el", "wr"), ("hip", "kn"), ("kn", "an")):
        if f"{a_}_f" in J and f"{b_}_f" in J:
            ln, lf = length(f"{a_}_n", f"{b_}_n"), length(f"{a_}_f", f"{b_}_f")
            if abs(lf - ln) > 0.2 * ln:
                report["warnings"].append(f"{a_}->{b_}: far side is {lf / ln:.0%} of the near side; one of them is marked wrong")
    foot = length("heel_n", "toe_n") / ppu
    if not 6 <= foot <= 18:
        report["warnings"].append(f"foot is {foot:.1f} units heel to toe, the rig expects about 11; check heel_n and toe_n")
    for s_ in "nf":
        if all(k in J for k in (f"an_{s_}", f"heel_{s_}", f"toe_{s_}")):
            # The rig plants the sole 5 units under the ankle; off by much and the foot sinks or floats.
            h, t, a_ = (np.array(up(J[f"{k}_{s_}"])) for k in ("heel", "toe", "an"))
            line = (t - h) / (np.hypot(*(t - h)) or 1)
            d_ = a_ - h
            height = float(line[0] * d_[1] - line[1] * d_[0]) / ppu
            if abs(height - 5.0) > 2.0:
                report["warnings"].append(f"an_{s_} is {height:.1f} units above the sole, the rig expects 5; "
                                          f"move it {'up' if height < 5 else 'down'} or the foot will {'sink' if height < 5 else 'float'}")
    return parts, spec, report, owner, order


CHECK_CLIPS = ["idle", "walk", "run", "attack_1", "attack_3", "roll", "hurt", "death"]
GAP_JOINTS = ("sh_n", "el_n", "wr_n", "sh_f", "el_f", "hip_n", "kn_n", "an_n", "hip_f", "kn_f", "an_f", "waist", "neck")


def check(spec, size=192, fps=15, clips=CHECK_CLIPS):
    """Animate the cut-out through the clips that bend it most. Returns (sheet image, gaps):
    gaps maps clip -> {joint: worst see-through share of a small disc on that joint}, listing
    only joints that open. A part sitting off its neighbour shows through right at the joint."""
    from sprite_anim.motions import build_clips
    from sprite_anim.render import Renderer, frame_count, frame_time
    lib = build_clips(spec.get("style"), spec.get("custom_clips"))
    picked = {n: lib[n] for n in clips if n in lib}
    r = Renderer(spec, size, clips=picked)
    yy, xx = np.mgrid[0:size, 0:size]
    cols = 6
    sheet = Image.new("RGBA", (cols * size, len(picked) * (size + 14)), (58, 62, 74, 255))
    d = ImageDraw.Draw(sheet)
    gaps = {}
    for row, (n, c) in enumerate(picked.items()):
        k = frame_count(c, fps)
        shown = {round(q * (k - 1) / (cols - 1)) for q in range(cols)}
        d.text((3, row * (size + 14) + 1), n, fill=(255, 255, 255, 255))
        for i in range(k):
            t = frame_time(c, i, k, fps)
            f = r.render(c, t)
            a = f[..., 3] > 0.5
            pose = full_pose(c.sample(t))
            sk = solve(pose, r.art.body)
            cv = Canvas(size, 1, r.unit, GROUND_FRAC, 1, False, (0, 0, 0))
            cv.set_squash(pose["squash"], 0.0)
            for j in GAP_JOINTS:
                x, y = cv.T(sk[j])
                disc = (xx - x) ** 2 + (yy - y) ** 2 <= (1.2 * r.unit) ** 2
                v = float((disc & ~a).sum() / max(disc.sum(), 1))
                if v > 0.05:
                    gaps.setdefault(n, {})[j] = round(max(v, gaps.get(n, {}).get(j, 0)), 2)
            if i in shown:
                im = Image.fromarray((np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")
                sheet.alpha_composite(im, (sorted(shown).index(i) * size, row * (size + 14) + 14))
    return sheet, gaps


def preview(img, joints, owner, order):
    rgba = np.asarray(img.convert("RGBA")).astype(np.float32)
    tint = rgba.copy()
    rng = np.random.default_rng(3)
    for i, _ in enumerate(order):
        col = rng.integers(60, 255, 3)
        m = owner == i
        tint[m, :3] = tint[m, :3] * 0.45 + col * 0.55
    out = Image.fromarray(tint.astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(out)
    for k, (x, y) in ((k, v) for k, v in joints.items() if not k.startswith("_")):
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
        d.text((x + 4, y - 6), k, fill=(0, 0, 0, 255))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("template", help="write the reference pose and its joints")
    t.add_argument("--character", help="character JSON whose proportions to show (default hero)")
    t.add_argument("--size", type=int, default=512)
    t.add_argument("--out", required=True)
    c = sub.add_parser("cut", help="cut a full-body picture into parts")
    c.add_argument("--image", required=True)
    c.add_argument("--joints", required=True, help="joints.json in the picture's pixels")
    c.add_argument("--base", help="character JSON to carry over: name, weapon, style, colors")
    c.add_argument("--out", required=True)
    k = sub.add_parser("check", help="animate a cut-out and report joints that open")
    k.add_argument("--character", required=True)
    k.add_argument("--out", help="motion sheet path (default: motion_check.png next to it)")
    a = ap.parse_args()
    if a.cmd == "check":
        with open(a.character, encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["_dir"] = os.path.dirname(os.path.abspath(a.character))
        sys.exit(run_check(spec, a.out or os.path.join(spec["_dir"], "motion_check.png")))
    os.makedirs(a.out, exist_ok=True)
    if a.cmd == "template":
        spec = json.load(open(a.character, encoding="utf-8")) if a.character else {}
        img, labelled, joints = template(spec, a.size)
        img.save(os.path.join(a.out, "template.png"))
        labelled.save(os.path.join(a.out, "template_joints.png"))
        with open(os.path.join(a.out, "joints.json"), "w", encoding="utf-8") as fh:
            json.dump(joints, fh, indent=1)
        print(f"[template] {a.out}: template.png, template_joints.png, joints.json ({len(joints)} joints)")
        return
    img = Image.open(a.image)
    with open(a.joints, encoding="utf-8") as fh:
        joints = json.load(fh)
    base = json.load(open(a.base, encoding="utf-8")) if a.base else {}
    parts, spec, report, owner, order = cut(img, joints, base)
    os.makedirs(os.path.join(a.out, "parts"), exist_ok=True)
    for n, (im, _) in parts.items():
        im.save(os.path.join(a.out, "parts", n + ".png"))
    with open(os.path.join(a.out, "character.json"), "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "bind_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    preview(img, joints, owner, order).save(os.path.join(a.out, "bind_preview.png"))
    print(f"[cut] {len(parts)} parts, {report['px_per_unit']} px/unit -> {a.out}")
    for wmsg in report["warnings"]:
        print("  warning:", wmsg)
    spec["_dir"] = os.path.abspath(a.out)
    sys.exit(run_check(spec, os.path.join(a.out, "motion_check.png"), report, os.path.join(a.out, "bind_report.json")))


def run_check(spec, sheet_path, report=None, report_path=None):
    """Animate, save the sheet, print gaps; non-zero exit when a joint opens."""
    sheet, gaps = check(spec)
    sheet.save(sheet_path)
    print(f"[check] motion sheet -> {sheet_path}")
    for clip, js in gaps.items():
        print(f"  gap: {clip}: " + ", ".join(f"{j} {v:.0%}" for j, v in js.items()))
    if report is not None:
        report["gaps"] = gaps
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
    if gaps:
        print("  joints open while moving: move those joints' marks onto the joint centres and cut again")
    return 1 if gaps else 0


if __name__ == "__main__":
    main()
