#!/usr/bin/env python3
"""Whole-picture skinned rig (prototype): one mesh over the reference, bones move it, no hidden art.

    python dev/skin_rig.py --image reference.png --joints joints.json --base rig/ --out skin-rig/
    python dev/skin_runtime.py --character skin-rig/character.json --clips idle,walk --preset hd512 --no-fx --out build/

The layered puppet needs every part complete, so art one part hides behind another must be invented.
Here the reference is one sheet: each mesh vertex follows the bone of the body part it lies on
(ownership from local_layers), blended across joints; where parts part, the sheet stretches instead
of revealing invented art. Cells draw back to front by part, so a near limb stays in front.

`--base` supplies the body proportions, gait and rest angles of a known-joint binding of the same
picture and joints. Experimental, dev only: not packaged, not user-approved.
"""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_layers as ll  # noqa: E402

GRID = 6              # source pixels between mesh vertices
SMOOTH_PASSES = 8     # neighbour averaging of the weights: spreads a part boundary's stretch over a band
JOINT_BLEND = 0.18    # of the shorter bone: half-width of the blend across a limb joint
ROOT_BLEND = 0.22     # of the first limb bone: how far into a limb its root follows the trunk too
DEPTH = ("arm_far", "hips", "leg_far", "leg_near", "head", "torso", "weapon", "arm_near")

# Bones: name -> (kind, data). "seg": a joint pair rotated as drawn; "rot": a pivot turned by a
# skeleton angle. Each body part lists its bones root to tip.
BONES = {
    "pelvis": ("seg", ("hip", "waist")),
    "chest": ("seg", ("waist", "neck")),
    "head": ("rot", ("head_base", "head_rot", 1)),
    "weapon": ("rot", ("weapon_grip", "wep_a", -1)),
    "arm_n_up": ("seg", ("sh_n", "el_n")), "arm_n_lo": ("seg", ("el_n", "wr_n")),
    "arm_f_up": ("seg", ("sh_f", "el_f")), "arm_f_lo": ("seg", ("el_f", "wr_f")),
    "leg_n_up": ("seg", ("hip_n", "kn_n")), "leg_n_lo": ("seg", ("kn_n", "an_n")),
    "foot_n": ("rot", ("an_n", "fr_n", 1)),
    "leg_f_up": ("seg", ("hip_f", "kn_f")), "leg_f_lo": ("seg", ("kn_f", "an_f")),
    "foot_f": ("rot", ("an_f", "fr_f", 1)),
}
PART_BONES = {
    "torso": ("pelvis", "chest"), "hips": ("pelvis",), "head": ("head",), "weapon": ("weapon",),
    "arm_near": ("arm_n_up", "arm_n_lo"), "arm_far": ("arm_f_up", "arm_f_lo"),
    "leg_near": ("leg_n_up", "leg_n_lo", "foot_n"), "leg_far": ("leg_f_up", "leg_f_lo", "foot_f"),
}
ROOT_PARENT = {"arm_near": "chest", "arm_far": "chest", "leg_near": "pelvis", "leg_far": "pelvis"}
NAMES = list(BONES)


def seg_param(p, a, b):
    """(share along a->b, clamped 0..1; distance to the segment) for points p (n, 2)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    v = b - a
    t = np.clip(((p - a) @ v) / max(float(v @ v), 1e-9), 0, 1)
    d = np.hypot(*(p - (a + np.outer(t, v))).T)
    return t, d


def chain_weights(p, J, part):
    """Weights (n, len(NAMES)) for points of one part: blended along its chain and into its root."""
    w = np.zeros((len(p), len(NAMES)))
    bones = PART_BONES[part]
    if len(bones) == 1:
        w[:, NAMES.index(bones[0])] = 1
        return w
    # Position along the chain: nearest segment, then arc length from the root.
    segs = []
    for b in bones:
        kind, data = BONES[b]
        if kind == "seg":
            segs.append((b, J[data[0]], J[data[1]]))
        else:                                   # a foot: a short segment from the ankle forward
            heel = J["heel_" + data[0][-1]]
            toe = J["toe_" + data[0][-1]]
            segs.append((b, J[data[0]], tuple(np.add(J[data[0]], np.subtract(toe, heel)))))
    lengths = [math.dist(a, b) for _, a, b in segs]
    starts = np.concatenate([[0], np.cumsum(lengths)[:-1]])
    best = np.full(len(p), np.inf)
    arc = np.zeros(len(p))
    for (name, a, b), s0, ln in zip(segs, starts, lengths):
        t, d = seg_param(p, a, b)
        closer = d < best
        best[closer] = d[closer]
        arc[closer] = s0 + t[closer] * ln
    for i, (name, _, _) in enumerate(segs):
        lo = starts[i] if i else -np.inf
        hi = starts[i] + lengths[i] if i < len(segs) - 1 else np.inf
        r_lo = JOINT_BLEND * min(lengths[i - 1], lengths[i]) if i else 0
        r_hi = JOINT_BLEND * min(lengths[i], lengths[i + 1]) if i < len(segs) - 1 else 0
        up = np.clip((arc - (lo - r_lo)) / max(2 * r_lo, 1e-9), 0, 1) if i else np.ones(len(p))
        down = np.clip(((hi + r_hi) - arc) / max(2 * r_hi, 1e-9), 0, 1) if i < len(segs) - 1 else np.ones(len(p))
        w[:, NAMES.index(name)] = np.minimum(up, down)
    if part in ROOT_PARENT:                     # the limb's root follows the trunk into the joint
        root = ROOT_BLEND * lengths[0]
        share = np.clip(1 - arc / max(root, 1e-9), 0, 1) * 0.5
        w *= (1 - share)[:, None]
        w[:, NAMES.index(ROOT_PARENT[part])] += share
    w /= np.maximum(w.sum(1, keepdims=True), 1e-9)
    return w


def build(image, joints_path, base, out):
    out, base = Path(out), Path(base)
    if out.exists():
        raise ValueError("output exists; choose a new version folder")
    joints = json.loads(Path(joints_path).read_text(encoding="utf-8"))
    own = {}
    ll.split(Image.open(image).convert("RGBA"), joints, ownership_out=own)
    rgba, layer_of, names, J = own["rgba"], own["layer_of"], own["names"], dict(own["J"])
    alpha = rgba[..., 3] > 0
    ys, xs = np.nonzero(alpha)
    pad = 2 * GRID
    x0, y0 = max(int(xs.min()) - pad, 0), max(int(ys.min()) - pad, 0)
    x1, y1 = min(int(xs.max()) + pad, rgba.shape[1]), min(int(ys.max()) + pad, rgba.shape[0])
    crop = rgba[y0:y1, x0:x1]
    labels = layer_of[y0:y1, x0:x1]
    h, w = crop.shape[:2]
    gx = np.arange(0, w + GRID, GRID, dtype=float)
    gy = np.arange(0, h + GRID, GRID, dtype=float)
    vx, vy = np.meshgrid(gx, gy)
    # Each vertex belongs to the part owning the nearest drawn pixel.
    from scipy import ndimage as ndi
    owned = labels >= 0
    _, (iy, ix) = ndi.distance_transform_edt(~owned, return_indices=True)
    cy, cx = np.clip(vy.astype(int), 0, h - 1), np.clip(vx.astype(int), 0, w - 1)
    vlabel = labels[iy[cy, cx], ix[cy, cx]]
    pts = np.column_stack([vx.ravel() + x0, vy.ravel() + y0])
    weights = np.zeros((pts.shape[0], len(NAMES)))
    flat = vlabel.ravel()
    for k, part in enumerate(names):
        sel = flat == k
        if sel.any():
            weights[sel] = chain_weights(pts[sel], J, part)
    # Where two parts meet, a hard switch puts all their relative motion into one row of cells, which
    # tears into a sawtooth. Averaging the weights with neighbours spreads it over a band. The sword
    # keeps hard weights: it is rigid.
    field = weights.reshape(vx.shape + (len(NAMES),))
    rigid_mask = (vlabel == names.index("weapon")) if "weapon" in names else np.zeros(vx.shape, bool)
    for _ in range(SMOOTH_PASSES):
        avg = field.copy()
        avg[1:-1, 1:-1] = (field[1:-1, 1:-1] * 2 + field[:-2, 1:-1] + field[2:, 1:-1]
                           + field[1:-1, :-2] + field[1:-1, 2:]) / 6
        avg[rigid_mask] = field[rigid_mask]
        field = avg
    weights = (field / np.maximum(field.sum(-1, keepdims=True), 1e-9)).reshape(weights.shape)
    # Cells with art, drawn back to front by the part most of their pixels belong to.
    cells, depth = [], []
    for j in range(len(gy) - 1):
        for i in range(len(gx) - 1):
            sy, sx = slice(int(gy[j]), min(int(gy[j + 1]) + 1, h)), slice(int(gx[i]), min(int(gx[i + 1]) + 1, w))
            a = crop[sy, sx, 3] > 0
            if a.any():
                lab = labels[sy, sx][a]
                lab = lab[lab >= 0]
                part = names[np.bincount(lab).argmax()] if len(lab) else "torso"
                cells.append((j, i))
                depth.append(DEPTH.index(part))
    order = np.argsort(np.array(depth), kind="stable")
    cells = np.array(cells)[order]
    shutil.copytree(base, out)
    Image.fromarray(crop, "RGBA").save(out / "body.png")
    rest = {}
    for name, (kind, data) in BONES.items():
        if kind == "seg":
            rest[name] = [list(map(float, J[data[0]])), list(map(float, J[data[1]]))]
        else:
            pivot = J[data[0]] if data[0] != "weapon_grip" else J["weapon_grip"]
            rest[name] = [list(map(float, pivot))]
    np.savez_compressed(out / "skin.npz", cells=cells, weights=weights.reshape(vx.shape + (len(NAMES),)),
                        gx=gx, gy=gy)
    spec = json.loads((out / "character.json").read_text(encoding="utf-8"))
    spec["puppet"]["layers"] = {"body": {"kind": "skin", "image": "body.png", "offset": [x0, y0],
                                         "skin": "skin.npz", "bones": NAMES, "rest": rest,
                                         "bone_defs": {n: [k, list(d)] for n, (k, d) in BONES.items()}}}
    spec["skin_rig"] = {"prototype": True, "image_generation_calls": 0, "grid_px": GRID}
    (out / "character.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True)
    ap.add_argument("--joints", required=True)
    ap.add_argument("--base", required=True, help="a known-joint binding of the same picture (proportions, gait)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    print("[skin]", build(a.image, a.joints, a.base, a.out), "image generation calls: 0")


if __name__ == "__main__":
    main()
