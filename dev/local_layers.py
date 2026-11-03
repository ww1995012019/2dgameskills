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
LIMB_BONES = ("arm_f_up", "arm_f_lo", "leg_f_up", "leg_f_lo", "leg_n_up", "leg_n_lo", "arm_n_up", "arm_n_lo")
WIDTH_PERCENTILE = 80  # of the half-widths measured along a bone
WIDTH_PAD = 1.15      # measured half-width times this: the capsule just covers the limb's outline
CORE_SHARE = 0.7      # of a bone's measured radius: inside this a layer drawn in front owns the pixel
FILL_WARN = 0.15      # of a layer's capsule area: more local fill than this is reported for review
INK_UNITS = 0.6       # rig units: a fill takes colour from this far inside the layer, past its outline
FILL_COLOURS = 4      # main colours of a layer a hidden fill is painted with
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
        return out
    return cp.foreground(img)


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


def split(img, joints):
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
    # A layer drawn in front owns the core of its own bones. cut_parts' colour tie-break can hand a
    # sleeve's middle to a same-coloured part behind it, which would punch a hole in the limb.
    for n in names:
        for p in GROUPS[n]:
            if p in LIMB_BONES:
                core = capsule(J, p, ppu, radius, xx, yy, CORE_SHARE) & fg
                layer_of[core & (layer_of < rank[n])] = rank[n]
    report = {"px_per_unit": round(ppu, 3), "measured_radius": radius, "layers": {}, "warnings": list(cut_report["warnings"]),
              "blockers": [], "image_generation_calls": 0}
    layers = {}
    for n in names:
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
        if n == "torso":
            # A trunk is never wider than its own visible outline: a sleeve that crossed it is not
            # hidden trunk, and filling it would leave a flap where the arm swings away.
            hidden &= hull(own)
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
        # Flat colours, not a blurred ramp: each filled pixel takes the nearest of the layer's own
        # main colours, as cel art is painted. A soft ramp reads as a smear when a limb swings away.
        filled = keep & ~own
        if filled.any() and seed.sum() > 8:
            cent = cp.palette(rgba[seed][:, :3].astype(np.float32), k=FILL_COLOURS)
            rgb = pix[filled][:, :3].astype(np.float32)
            nearest = ((rgb[:, None, :] - cent[None]) ** 2).sum(-1).argmin(1)
            pix[filled, :3] = np.clip(cent[nearest], 0, 255).astype(np.uint8)
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


def run(image, joints_path, out, name="character"):
    out = Path(out)
    if out.exists():
        raise ValueError("output exists; choose a new version folder")
    img = Image.open(image).convert("RGBA")
    joints = json.loads(Path(joints_path).read_text(encoding="utf-8"))
    layers, lj, order, report = split(img, joints)
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
    a = ap.parse_args()
    report = run(a.image, a.joints, a.out, a.name)
    for line in report["warnings"]:
        print("warning:", line)
    for line in report["blockers"]:
        print("BLOCKED:", line)
    print(f"[local] {len(report['layers'])} layers -> {a.out}; image generation calls: 0")
    if report["blockers"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
