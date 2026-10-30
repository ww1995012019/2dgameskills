#!/usr/bin/env python3
"""How closely a cut-out character re-creates the procedural one it was cut from.

    python dev/cutout_match.py <cut character.json> <procedural character.json> [--clips ...]

The self-test for cut_parts.py: render the procedural character's reference pose
(cut_parts.py template), cut it, then animate both. Per clip it prints the silhouette overlap
(IoU of alpha) and the mean colour error inside the shared silhouette, worst frame included.
The procedural side is drawn without cloth, since cut-outs carry none.
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "game-sprite-animator", "scripts"))

from sprite_anim.motions import build_clips  # noqa: E402
from sprite_anim.render import Renderer, frame_count, frame_time  # noqa: E402


def load(path):
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec["_dir"] = os.path.dirname(os.path.abspath(path))
    return spec


def compare(cut_spec, proc_spec, names, size=192, fps=15):
    proc_spec = dict(proc_spec, cloth=[])
    clips = build_clips(proc_spec.get("style"), proc_spec.get("custom_clips"))
    picked = {n: clips[n] for n in names}
    rc = Renderer(cut_spec, size, clips=picked)
    rp = Renderer(proc_spec, size, clips=picked)
    out = {}
    for n, c in picked.items():
        k = frame_count(c, fps)
        ious, errs = [], []
        for i in range(k):
            t = frame_time(c, i, k, fps)
            a, b = rc.render(c, t), rp.render(c, t)
            ma, mb = a[..., 3] > 0.5, b[..., 3] > 0.5
            ious.append((ma & mb).sum() / max((ma | mb).sum(), 1))
            both = ma & mb
            errs.append(float(np.abs(a[..., :3] - b[..., :3])[both].mean()) if both.any() else 1.0)
        out[n] = dict(iou=round(float(np.mean(ious)), 3), iou_min=round(float(np.min(ious)), 3),
                      color_err=round(float(np.mean(errs)), 3), frames=k)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cut")
    ap.add_argument("proc")
    ap.add_argument("--clips", default="idle,walk,run,attack_1,attack_3,roll,hurt,death")
    a = ap.parse_args()
    res = compare(load(a.cut), load(a.proc), a.clips.split(","))
    for n, r in res.items():
        print(f"{n:<12} iou {r['iou']:.3f} (worst {r['iou_min']:.3f})  colour error {r['color_err']:.3f}")
    print("mean iou", round(float(np.mean([r["iou"] for r in res.values()])), 3))


if __name__ == "__main__":
    main()
