#!/usr/bin/env python3
"""Find a side-view character's joints automatically (dev prototype), in cut_parts' joints.json form.

    python dev/auto_joints.py --image reference.png --model pose_landmarker_heavy.task --out joints.json [--weapon sword]

A pose model (MediaPipe Pose Landmarker, Apache-2.0) gives shoulders, elbows, wrists, hips, knees,
ankles, heels and toes; its depth says which side is near the camera. Head, neck, waist and hip
centre follow from those by fixed body proportions; the head's top is the silhouette's. Joints the
model puts off the art are pulled to the nearest drawn pixel. A sword's tip is the drawn point
farthest from the near hand along the blade's direction. Writes overlay.png for review. The model
is a measurement, not ground truth: inspect the overlay.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_layers as ll  # noqa: E402

HEAD_BASE = 0.45      # of the way from the ears' middle to the shoulders' middle: where head meets neck
NECK = 0.15           # of the way from the shoulders' middle back up toward the ears
WAIST = 0.35          # of the way from the hips' middle up to the shoulders' middle
ANKLE_SHARE = 5.0 / 37.0  # of the leg's length (hip-knee-ankle): ankle above the sole, as the rig builds feet
FOOT_SHARE = 0.4      # of the leg's length: farthest a toe can be from its heel
ARCH_SHARE = 0.08     # of the leg's length: widest gap in the sole line (a heeled shoe's arch)
SIDES = {"L": dict(sh=11, el=13, wr=15, hand=19, hip=23, kn=25, an=27, heel=29, toe=31),
         "R": dict(sh=12, el=14, wr=16, hand=20, hip=24, kn=26, an=28, heel=30, toe=32)}


def landmarks(rgb, model):
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions
    options = vision.PoseLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(model)),
                                           running_mode=vision.RunningMode.IMAGE, num_poses=1)
    with vision.PoseLandmarker.create_from_options(options) as detector:
        result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
    if not result.pose_landmarks:
        raise ValueError("no figure found by the pose model")
    h, w = rgb.shape[:2]
    return [(p.x * w, p.y * h, p.z, p.visibility) for p in result.pose_landmarks[0]]


def snap(point, fg):
    """The nearest drawn pixel to a point (itself when it is on the art)."""
    x, y = int(round(point[0])), int(round(point[1]))
    h, w = fg.shape
    if 0 <= x < w and 0 <= y < h and fg[y, x]:
        return [float(point[0]), float(point[1])]
    ys, xs = np.nonzero(fg)
    k = int(np.argmin((xs - point[0]) ** 2 + (ys - point[1]) ** 2))
    return [float(xs[k]), float(ys[k])]


def find(image, model, weapon="none"):
    rgba = ll.keyed(Image.open(image).convert("RGBA"))
    fg = rgba[..., 3] > 128
    flat = np.full(rgba.shape[:2] + (3,), 255, np.uint8)
    a = rgba[..., 3:4] / 255.0
    rgb = (rgba[..., :3] * a + flat * (1 - a)).astype(np.uint8)
    lm = landmarks(rgb, model)
    xy = lambda i: np.array(lm[i][:2])
    depth = {s: np.mean([lm[SIDES[s][k]][2] for k in ("sh", "hip", "kn")]) for s in SIDES}
    near = min(depth, key=depth.get)                      # smaller z: nearer the camera
    far = "R" if near == "L" else "L"
    faces_right = xy(0)[0] > (xy(7)[0] + xy(8)[0]) / 2
    J = {}
    for tag, side in (("n", near), ("f", far)):
        for k, i in SIDES[side].items():
            J[f"{k}_{tag}"] = xy(i)
    ears = (xy(7) + xy(8)) / 2
    shoulders = (xy(11) + xy(12)) / 2
    hips = (xy(23) + xy(24)) / 2
    J["head_base"] = ears + (shoulders - ears) * HEAD_BASE
    J["neck"] = shoulders + (ears - shoulders) * NECK
    J["hip"] = hips
    J["waist"] = hips + (shoulders - hips) * WAIST
    # The skull's top, not the silhouette's (a bun, a hat or a hair spike would pass it): the eyes sit
    # half way down the head, so the top is as far above them as the chin is below.
    eyes = (xy(2) + xy(5)) / 2
    axis = ears - J["head_base"]
    axis = axis / (np.linalg.norm(axis) or 1)              # the head's own up, from the chin past the ears
    J["head_top"] = J["head_base"] + axis * 2 * float((eyes - J["head_base"]) @ axis)
    out = {k: snap(v, fg) for k, v in J.items()}
    out["head_top"] = [float(J["head_top"][0]), float(J["head_top"][1])]
    # Feet: heel and toe on the sole (each foot's lowest drawn row); the toe is the shoe's front end
    # along that row, which pose models tend to place short of the tip.
    forward = 1 if faces_right else -1
    for tag in "nf":
        heel = np.array(out[f"heel_{tag}"])
        x = int(round(heel[0]))
        col = np.nonzero(fg[:, max(x - 2, 0):x + 3].any(1))[0]
        sole = int(col.max()) if len(col) else int(heel[1])
        out[f"heel_{tag}"] = [float(heel[0]), float(sole)]
        band = fg[max(sole - 6, 0):sole + 1].any(0)
        leg = np.linalg.norm(np.subtract(out[f"hip_{tag}"], out[f"kn_{tag}"])) + \
            np.linalg.norm(np.subtract(out[f"kn_{tag}"], out[f"an_{tag}"]))
        # Along the sole, over a heeled shoe's arch gap, no further than a foot's length.
        xs, gap = x, 0
        for step in range(1, int(FOOT_SHARE * leg)):
            px = x + forward * step
            if not 0 <= px < fg.shape[1]:
                break
            if band[px]:
                xs, gap = px, 0
            else:
                gap += 1
                if gap > ARCH_SHARE * leg:
                    break
        toe = np.array(out[f"toe_{tag}"])
        out[f"toe_{tag}"] = [float(xs if abs(xs - x) > abs(toe[0] - x) else toe[0]), float(sole)]
        # Both ankles at the rig's height above their soles: the rig gives both feet one ankle height,
        # and a pose model's ankle inside a boot is noisy. Kept on the shin's line.
        knee, ankle = np.array(out[f"kn_{tag}"]), np.array(out[f"an_{tag}"])
        height = ANKLE_SHARE * leg
        y = sole - height
        shin = ankle - knee
        t = (y - knee[1]) / shin[1] if abs(shin[1]) > 1e-6 else 1.0
        out[f"an_{tag}"] = snap(knee + shin * t, fg)
    if weapon != "none":
        grip = np.array(out["hand_n"])
        fore = grip - np.array(out["el_n"])
        ys, xs = np.nonzero(fg)
        v = np.column_stack([xs, ys]) - grip
        reach = v @ (fore / (np.linalg.norm(fore) or 1))
        k = int(np.argmax(reach))
        out["weapon_grip"] = grip.tolist()
        out["weapon_tip"] = [float(xs[k]), float(ys[k])]
    info = {"near_side": near, "faces_right": bool(faces_right),
            "visibility": {k: round(lm[i][3], 2) for side in SIDES.values() for k, i in side.items()}}
    return out, info, rgba


def overlay(rgba, J, path):
    im = Image.fromarray(rgba, "RGBA")
    bg = Image.new("RGBA", im.size, (236, 238, 242, 255))
    bg.alpha_composite(im)
    d = ImageDraw.Draw(bg)
    pairs = [("sh_n", "el_n"), ("el_n", "wr_n"), ("hip_n", "kn_n"), ("kn_n", "an_n"), ("heel_n", "toe_n"),
             ("sh_f", "el_f"), ("el_f", "wr_f"), ("hip_f", "kn_f"), ("kn_f", "an_f"), ("heel_f", "toe_f"),
             ("hip", "waist"), ("waist", "neck"), ("head_base", "head_top"), ("weapon_grip", "weapon_tip")]
    for a, b in pairs:
        if a in J and b in J:
            colour = "cyan" if a.endswith("_n") else "orange" if a.endswith("_f") else "magenta"
            d.line([tuple(J[a]), tuple(J[b])], fill=colour, width=4)
    for k, (x, y) in J.items():
        d.ellipse((x - 6, y - 6, x + 6, y + 6), fill="red", outline="white")
    bg.convert("RGB").save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--weapon", default="none", choices=["none", "sword"])
    a = ap.parse_args()
    J, info, rgba = find(a.image, a.model, a.weapon)
    Path(a.out).write_text(json.dumps(J, indent=1) + "\n")
    overlay(rgba, J, Path(a.out).with_name("joints_overlay.png"))
    print(json.dumps(info))


if __name__ == "__main__":
    main()
