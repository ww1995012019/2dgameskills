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
FILL_WARN = 0.15      # of a layer's capsule area: more local fill than this is reported for review
INK_UNITS = 0.6       # rig units: a fill takes colour from this far inside the layer, past its outline
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


def split(img, joints):
    """Returns (layers {name: RGBA array on the picture's canvas}, layer joints, order, report)."""
    _, _, cut_report, owner, order = cp.cut(img, joints)
    J = {k: tuple(map(float, v)) for k, v in joints.items() if not k.startswith("_")}
    if "hand_n" not in J:
        J["hand_n"] = tuple(np.add(J["wr_n"], np.subtract(J["wr_n"], J["el_n"]) * 0.42))
    if "hand_f" not in J and "wr_f" in J:
        J["hand_f"] = tuple(np.add(J["wr_f"], np.subtract(J["wr_f"], J["el_f"]) * 0.42))
    missing = [k for k in ("sh_f", "el_f", "wr_f", "hip_f", "kn_f", "an_f", "heel_f", "toe_f") if k not in J]
    if missing:
        raise ValueError(f"far limbs need joints {missing}; the layered puppet binds both sides")
    radius = {k: float(v) for k, v in joints.get("_radius", {}).items()}
    rgba = cp.foreground(img)
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
    report = {"px_per_unit": round(ppu, 3), "layers": {}, "warnings": list(cut_report["warnings"]),
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
