#!/usr/bin/env python3
"""Top-down QA: direction integrity, phase alignment, ground-plane stance and articulated bones.

Frame hashes bind source pixels to a labelled trace. They detect swapped/edited frames,
not semantic art correctness; front/back appearance still requires visual review.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sprite_anim.integrity import frame_problems
from sprite_anim.topdown import DIRECTIONS, LOOPS, BONES

CHECKS = ("structure", "direction", "phase", "hold", "seam", "slide", "limits", "float", "bones", "bounds")


def distance(a, b):
    return float(np.sqrt(np.mean(np.sum((a - b) ** 2, axis=-1))))


def run(root):
    root = Path(root)
    doc = json.loads((root / "animations.json").read_text())
    trace = json.loads((root / "rig_trace.json").read_text())
    height = 90 * trace["unit_px"]
    report = {}
    transitions = []
    for name, c in doc["clips"].items():
        tr = trace["traces"][name]
        files = sorted((root / "frames" / name).glob("*.png"))
        frames = [np.asarray(Image.open(f).convert("RGBA")) for f in files]
        r = {k: "PASS" for k in CHECKS}
        r.update(frames=len(frames), flags={})

        def flag(check, i, message):
            r[check] = "FAIL"
            r["flags"].setdefault(str(i), []).append(message)

        n = len(frames)
        if n != len(c["frames"]) or n != len(tr["frame_hashes"]) or n < 2:
            flag("structure", 0, "frame/manifest/trace count mismatch")
        if any(not isinstance(e.get("frame"), int) or not 0 <= e["frame"] < n for e in c["events"]):
            flag("structure", 0, "event outside clip frame range")
        action = c["action"]
        direction = c["direction"]
        if (
            direction not in DIRECTIONS
            or name != action + "_" + direction
            or tr["direction"] != direction
            or tr["action"] != action
        ):
            flag("direction", 0, "action/direction label mismatch")
        elif not np.allclose(
            c["velocity_px_s"], np.array(DIRECTIONS[direction]) * c["speed_px_s"], atol=1e-5
        ):
            flag("direction", 0, "velocity does not follow the declared direction")
        for i, f in enumerate(frames):
            if f.shape != (doc["frame_size"], doc["frame_size"], 4):
                flag("structure", i, "frame dimensions differ")
            if (
                i < len(tr["frame_hashes"])
                and hashlib.sha256(f.tobytes()).hexdigest() != tr["frame_hashes"][i]
            ):
                flag("direction", i, "pixels do not match this labelled direction/phase trace")
            if any((f[0, :, 3].any(), f[-1, :, 3].any(), f[:, 0, 3].any(), f[:, -1, 3].any())):
                flag("bounds", i, "cut off at frame edge")
            if action in ("walk", "run") and i > 0 and np.array_equal(f, frames[i - 1]):
                flag("hold", i, "repeated locomotion frame")
        joints = np.stack([tr["joints"][j] for j in sorted(tr["joints"])], axis=1)
        if len(joints) != n:
            flag("structure", 0, "joint frame count mismatch")
        px, py = doc["pivot"]
        skeleton = {j: [[px + x, py + y] for x, y in track] for j, track in tr["joints"].items()}
        floating, empty = frame_problems(frames, trace["unit_px"], skeleton, BONES)
        for check, found in (("float", floating), ("bones", empty)):
            for i, messages in found.items():
                for message in messages:
                    flag(check, i, message)
        if c["loop"] and len(joints) > 2:
            step = np.mean([distance(a, b) for a, b in zip(joints, joints[1:])])
            ratio = distance(joints[-1], joints[0]) / max(float(step), height * 0.002)
            r["joint_seam_ratio"] = round(ratio, 4)
            if ratio > 2.6:
                flag("seam", 0, "joint loop seam is too large")
                flag("seam", n - 1, "joint loop seam is too large")
        world = tr["world"]
        bone_err = 0.0
        for a, b in BONES:
            lengths = np.linalg.norm(np.array(world[a]) - world[b], axis=1)
            target = 18 if a.startswith(("hip", "knee")) else 14
            error = np.abs(lengths - target)
            bone_err = max(bone_err, float(error.max()))
            for i in np.flatnonzero(error > 0.05):
                flag("limits", int(i), f"{a}->{b} length changed")
        weapon_length = np.linalg.norm(np.array(world["blade_tip"]) - world["hand_r"], axis=1)
        for i in np.flatnonzero(np.abs(weapon_length - 23) > 0.05):
            flag("limits", int(i), "weapon length changed")
        for joint, points in world.items():
            values = np.asarray(points)
            for i in np.flatnonzero(~np.isfinite(values).all(axis=1)):
                flag("structure", int(i), "non-finite joint: " + joint)
        r["bone_err"] = round(bone_err, 6)
        for leg in ("r", "l"):
            for i, z in enumerate(np.array(world["foot_" + leg])[:, 2]):
                if z < 0:
                    flag("limits", i, "foot penetrates ground plane")
        if action in ("walk", "run"):
            errors = []
            expected = -np.array(c["velocity_px_s"]) / c["fps"]
            for leg in ("r", "l"):
                points = np.array(tr["feet"][leg])
                contacts = tr["contacts"][leg]
                for i in range(len(points)):
                    j = (i + 1) % len(points)
                    if contacts[i] and contacts[j]:
                        err = float(np.linalg.norm(points[j] - points[i] - expected))
                        errors.append(err)
                        if err > 0.25:
                            flag("slide", i, "stance foot disagrees with declared ground velocity")
            r["slide_px"] = round(max(errors, default=0), 6)
        report[name] = r
    # All directions share timing and events. Foot lift and body height are phase-locked.
    for action in {c["action"] for c in doc["clips"].values()}:
        names = [action + "_" + d for d in DIRECTIONS]
        reference = doc["clips"].get(names[0])
        for name in names:
            if name not in report:
                raise ValueError(f"missing required direction: {name}")
            c = doc["clips"][name]
            r = report[name]
            if len(c["frames"]) != len(reference["frames"]):
                r["phase"] = "FAIL"
                r["flags"].setdefault("0", []).append("direction frame count mismatch")
            for key in ("fps", "duration", "loop", "events", "speed_px_s"):
                if c[key] != reference[key]:
                    r["phase"] = "FAIL"
                    r["flags"].setdefault("0", []).append(
                        "direction timing/speed/event mismatch: " + key
                    )
            a = trace["traces"][names[0]]
            b = trace["traces"][name]
            for joint in ("root", "foot_r", "foot_l"):
                if not np.allclose(
                    np.array(a["world"][joint])[:, 2], np.array(b["world"][joint])[:, 2], atol=1e-6
                ):
                    r["phase"] = "FAIL"
                    r["flags"].setdefault("0", []).append("direction gait phase mismatch: " + joint)
    for name, c in doc["clips"].items():
        target = c["next"]
        if target not in doc["clips"]:
            continue
        a = trace["traces"][name]
        b = trace["traces"][target]
        ja = np.array([a["joints"][j][-1] for j in sorted(a["joints"])])
        jb = np.array([b["joints"][j][0] for j in sorted(b["joints"])])
        ratio = distance(ja, jb) / height
        status = "FAIL" if ratio > 0.1 else "PASS"
        transitions.append(
            dict(
                a=name,
                b=target,
                status=status,
                ratio=round(ratio, 5),
                a_frame=report[name]["frames"] - 1,
                b_frame=0,
            )
        )
        if status == "FAIL":
            report[name]["flags"].setdefault(str(report[name]["frames"] - 1), []).append(
                "handover pose discontinuity"
            )
    fails = sum(r[k] == "FAIL" for r in report.values() for k in CHECKS) + sum(
        t["status"] == "FAIL" for t in transitions
    )
    for name, r in report.items():
        print(name, " ".join(k + "=" + r[k] for k in CHECKS))
    (root / "qa_report.json").write_text(
        json.dumps(dict(clips=report, transitions=transitions), indent=1)
    )
    print(f"result: {fails} FAIL, 0 WARN")
    return bool(fails)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path")
    a = p.parse_args()
    sys.exit(run(a.path))
