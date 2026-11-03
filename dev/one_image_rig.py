#!/usr/bin/env python3
"""One side-view picture in, a skinned rig with idle/walk out, with no manual step (dev prototype).

    python dev/one_image_rig.py --image hero.png --pose-model pose_landmarker_heavy.task --out job/ [--weapon sword]

1. joints: dev/auto_joints.py (pose model + silhouette), overlay saved for review;
2. skin: dev/skin_rig.py, one mesh over the whole picture, nothing hidden is invented; proportions
   and gait measured from the joints and the figure;
3. idle and walk rendered with dev/skin_runtime.py, then motion QA.

Each stage writes into its own folder under --out; an existing --out is refused. Numerical QA is not
visual approval: review the frames and the joint overlay.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "game-sprite-animator/scripts"))
import auto_joints  # noqa: E402
import skin_rig  # noqa: E402


def run(image, pose_model, out, weapon="none", clips="idle,walk", preset="hd512"):
    out = Path(out)
    if out.exists():
        raise ValueError("output exists; choose a new folder")
    out.mkdir(parents=True)
    joints, info, rgba = auto_joints.find(image, pose_model, weapon)
    (out / "joints.json").write_text(json.dumps(joints, indent=1) + "\n")
    auto_joints.overlay(rgba, joints, out / "joints_overlay.png")
    skin_rig.build(image, out / "joints.json", out / "rig", out.name)
    runtime = [sys.executable, str(HERE / "skin_runtime.py")]
    subprocess.run(runtime + ["generate", "--character", str(out / "rig/character.json"), "--clips", clips,
                              "--preset", preset, "--no-fx", "--out", str(out / "build")], check=True)
    qa = subprocess.run(runtime + ["qa", str(out / "build")], capture_output=True, text=True)
    (out / "qa.txt").write_text(qa.stdout + qa.stderr)
    summary = dict(pose=info, qa_exit=qa.returncode, image_generation_calls=0,
                   qa_result=[line for line in qa.stdout.splitlines() if line.startswith("result:")])
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True)
    ap.add_argument("--pose-model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--weapon", default="none", choices=["none", "sword"])
    ap.add_argument("--clips", default="idle,walk")
    ap.add_argument("--preset", default="hd512")
    a = ap.parse_args()
    print(json.dumps(run(a.image, a.pose_model, a.out, a.weapon, a.clips, a.preset), indent=1))


if __name__ == "__main__":
    main()
