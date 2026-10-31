#!/usr/bin/env python3
"""Four-paw stance, digitigrade bones, tail continuity, support pattern and export QA."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sprite_anim.integrity import frame_problems
from sprite_anim.rig import LEGS, LENGTHS, GAITS, ACTIONS

CHECKS = (
    "structure",
    "integrity",
    "hold",
    "seam",
    "spike",
    "slide",
    "limits",
    "tail",
    "gait",
    "float",
    "bones",
    "bounds",
)


def rms(a, b):
    return float(np.sqrt(np.mean(np.sum((a - b) ** 2, axis=-1))))


def run(root):
    root = Path(root)
    doc = json.loads((root / "animations.json").read_text())
    trace = json.loads((root / "rig_trace.json").read_text())
    unit = trace["unit_px"]
    if doc["rig"] != "canine_side" or doc["legs"] != list(LEGS):
        raise ValueError("wrong quadruped rig or missing legs")
    reports = {}
    for name, c in doc["clips"].items():
        tr = trace["traces"][name]
        paths = sorted((root / "frames" / name).glob("*.png"))
        frames = [np.asarray(Image.open(p).convert("RGBA")) for p in paths]
        n = len(frames)
        r = {k: "PASS" for k in CHECKS}
        r.update(frames=n, flags={})

        def flag(check, i, reason):
            r[check] = "FAIL"
            r["flags"].setdefault(str(i), []).append(reason)

        if n != len(c["frames"]) or n != len(tr["frame_hashes"]) or n < 2:
            flag("structure", 0, "frame/trace/manifest count mismatch")
        if name not in ACTIONS and (
            name not in GAITS
            or c["gait"] != dict(duty=GAITS[name]["duty"], phases=GAITS[name]["phases"])
        ):
            flag("gait", 0, "incorrect gait phase declaration")
        if c["loop"] != (name in GAITS) or c["duration"] != (n if c["loop"] else n - 1) / c["fps"]:
            flag("structure", 0, "invalid loop timing")
        for i, f in enumerate(frames):
            if f.shape != (doc["frame_size"], doc["frame_size"], 4):
                flag("structure", i, "invalid frame size")
            if (
                i < len(tr["frame_hashes"])
                and hashlib.sha256(f.tobytes()).hexdigest() != tr["frame_hashes"][i]
            ):
                flag("integrity", i, "frame differs from its rig-labelled export")
            if any((f[0, :, 3].any(), f[-1, :, 3].any(), f[:, 0, 3].any(), f[:, -1, 3].any())):
                flag("bounds", i, "frame cut off at edge")
            if name in ("walk", "trot", "run") and i > 0 and np.array_equal(f, frames[i - 1]):
                flag("hold", i, "duplicate locomotion frame")
        joints = np.stack([tr["joints"][j] for j in sorted(tr["joints"])], axis=1)
        if len(joints) != n:
            flag("structure", 0, "joint count mismatch")
        for i in np.flatnonzero(~np.isfinite(joints).all(axis=(1, 2))):
            flag("structure", int(i), "non-finite joint position")
        px, py = doc["pivot"]
        skeleton = {j: [[px + x, py - y] for x, y in track] for j, track in tr["joints"].items()}
        bones = [bone.split("->") for bone in LENGTHS]
        floating, empty = frame_problems(frames, unit, skeleton, bones)
        for check, found in (("float", floating), ("bones", empty)):
            for i, messages in found.items():
                for message in messages:
                    flag(check, i, message)
        deltas = [rms(a, b) for a, b in zip(joints, joints[1:])]
        typical = float(np.mean(deltas))
        seam = rms(joints[-1], joints[0])
        ratio = seam / max(typical, 60 * unit * 0.002)
        r["joint_seam_ratio"] = round(ratio, 5)
        if c["loop"] and ratio > 2.6:
            flag("seam", 0, "joint loop does not close")
            flag("seam", n - 1, "joint loop does not close")
        steps = deltas + ([seam] if c["loop"] else [])
        peak = 0.0
        for i, step in enumerate(steps):
            value = step / max(
                steps[i - 1], steps[(i + 1) % len(steps)], typical * 0.5, 60 * unit * 0.002
            )
            peak = max(peak, value)
            if value > 4 and (c["loop"] or 0 < i < len(steps) - 1):
                flag("spike", i, "joint step exceeds its neighbours")
        r["spike_ratio"] = round(peak, 5)
        world = tr["world"]
        bone_error = 0.0
        for joint, values in world.items():
            for i in np.flatnonzero(~np.isfinite(np.asarray(values)).all(axis=1)):
                flag("structure", int(i), "non-finite world joint: " + joint)
        for i in range(n):
            if (
                min(world["head"][i][1] - 7, world["muzzle"][i][1] - 4, world["spine_3"][i][1] - 17)
                < -0.1
            ):
                flag("limits", i, "body or jaw penetrates floor")
        expected_speed = (
            0.0
            if name == "idle" or name in ACTIONS
            else 2 * GAITS[name]["stride"] / (GAITS[name]["duty"] * c["duration"]) * unit
        )
        if not np.isclose(c["speed_px_s"], expected_speed, atol=1e-6):
            flag("gait", 0, "speed disagrees with stride and stance duration")
        for bone, target in LENGTHS.items():
            a, b = bone.split("->")
            err = np.abs(np.linalg.norm(np.array(world[a]) - world[b], axis=1) - target)
            bone_error = max(bone_error, float(err.max()))
            for i in np.flatnonzero(err > 1e-5):
                flag("limits", int(i), "bone length changed: " + bone)
        r["bone_err"] = round(bone_error, 7)
        errors = []
        expected_events = []
        for leg in LEGS:
            root_joint = np.asarray(world[leg + "_root"])
            upper = np.asarray(world[leg + "_bend"]) - root_joint
            target = np.asarray(world[leg + "_ankle"]) - root_joint
            bend = target[:, 0] * upper[:, 1] - target[:, 1] * upper[:, 0]
            for i in np.flatnonzero(bend * (1 if leg.startswith("hind") else -1) < -1e-6):
                flag("limits", int(i), "inverted knee/elbow: " + leg)
            points = np.array(tr["feet"][leg])
            contact = tr["contacts"][leg]
            phases = (np.arange(n) / n - c["gait"]["phases"][leg]) % 1
            expected_contact = phases < c["gait"]["duty"]
            if len(points) != n or len(contact) != n:
                flag("structure", 0, "missing foot samples: " + leg)
                continue
            for i in range(n):
                if bool(contact[i]) != bool(expected_contact[i]):
                    flag("gait", i, "incorrect contact phase: " + leg)
                if points[i, 1] < 2 * unit - 1e-5:
                    flag("limits", i, "paw below floor: " + leg)
                if contact[i]:
                    if abs(points[i, 1] - 2 * unit) > 0.1 * unit:
                        flag("slide", i, "planted paw hovers: " + leg)
                    j = (i + 1) % n
                    if contact[j] and name in ("walk", "trot", "run"):
                        err = float(
                            np.linalg.norm(
                                points[j] - points[i] - [-c["speed_px_s"] / c["fps"], 0.0]
                            )
                        )
                        errors.append(err)
                        if err > 0.25:
                            flag("slide", i, "stance foot slides: " + leg)
                if name in ("walk", "trot", "run") and contact[i] and not contact[i - 1]:
                    expected_events.append((i, "footstep_" + leg))
            # The ankle-paw bone must agree with the separately exported contact data.
            paw = np.array(world[leg + "_paw"]) * unit
            for i in np.flatnonzero(np.linalg.norm(paw - points, axis=1) > 1e-5):
                flag("structure", int(i), "foot/contact traces disagree: " + leg)
        r["slide_px"] = round(max(errors, default=0), 6)
        actual_events = [(e["frame"], e["name"]) for e in c["events"]]
        if name == "attack":
            expected_events = [(round((n - 1) * 0.3), "hit_on"), (round((n - 1) * 0.58), "hit_off")]
        elif name == "death":
            expected_events = [(round((n - 1) * 0.9), "body_thud")]
        if sorted(actual_events) != sorted(expected_events):
            flag("gait", 0, "footstep events do not match touchdowns")
        if name == "trot":
            if (
                tr["contacts"]["front_near"] != tr["contacts"]["hind_far"]
                or tr["contacts"]["front_far"] != tr["contacts"]["hind_near"]
            ):
                flag("gait", 0, "trot must pair diagonal legs")
        if name == "run" and all(any(tr["contacts"][leg][i] for leg in LEGS) for i in range(n)):
            flag("gait", 0, "gallop has no suspension phase")
        tail = np.stack([world["tail_" + str(k)] for k in range(6)], axis=1)
        anchor = np.array(world["tail_base"])
        for i in np.flatnonzero(np.linalg.norm(tail[:, 0] - anchor, axis=1) > 1e-5):
            flag("tail", int(i), "tail root detached")
        segments = np.linalg.norm(np.diff(tail, axis=1), axis=2)
        r["tail_length_error"] = round(float(np.max(np.abs(segments - 6))), 6)
        for i in np.flatnonzero(np.any(np.abs(segments - 6) > 0.08, axis=1)):
            flag("tail", int(i), "tail segment length changed")
        widths = np.linspace(7, 1.2, 6) / 2
        for i, chain in enumerate(tail):
            tangent = np.gradient(chain, axis=0)
            flat = np.abs(tangent[:, 0]) / np.maximum(np.linalg.norm(tangent, axis=1), 1e-8)
            if np.any(chain[1:, 1] - widths[1:] * flat[1:] < -0.1):
                flag("tail", i, "drawn tail crosses ground")
        reports[name] = r
        print(name, " ".join(k + "=" + r[k] for k in CHECKS))
    transitions = []
    if "idle" in reports:
        idle = trace["traces"]["idle"]["joints"]
        for name in ("attack", "hurt"):
            if name not in reports:
                continue
            tr = trace["traces"][name]["joints"]
            # Body and tail are evaluated independently so a large tail cannot hide a body jump.
            for group in ("body", "tail"):
                keys = [k for k in idle if k.startswith("tail_") == (group == "tail")]
                value = rms(
                    np.array([tr[k][-1] for k in keys]), np.array([idle[k][0] for k in keys])
                ) / (60 * unit)
                status = "PASS" if value <= 0.1 else "FAIL"
                transitions.append(dict(a=name, b="idle", group=group, ratio=value, status=status))
    fails = sum(r[k] == "FAIL" for r in reports.values() for k in CHECKS)
    fails += sum(t["status"] == "FAIL" for t in transitions)
    (root / "qa_report.json").write_text(
        json.dumps(dict(clips=reports, transitions=transitions), indent=1)
    )
    print(f"result: {fails} FAIL, 0 WARN")
    return bool(fails)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path")
    a = p.parse_args()
    sys.exit(run(a.path))
