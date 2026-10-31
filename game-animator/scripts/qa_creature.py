#!/usr/bin/env python3
"""Check generated flight frames and configured bone invariants, not visual anatomy."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modes/game-sprite-animator/scripts"))
from sprite_anim.integrity import frame_problems


def rotate(point, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return (point[0] * c - point[1] * s, point[0] * s + point[1] * c)


def speed_bounds(bones, motion):
    """Conservative endpoint speeds derived from the rig's actual sinusoidal drivers."""
    period = motion["period"]
    root_speed = max(2 * math.pi, 3) * abs(motion["bob"]) / period
    root_angular = math.radians(max(2 * math.pi * abs(motion["pitch"]), 70, 15 * math.pi) / period)
    bounds = {}

    def bone_speed(name):
        if name in bounds:
            return bounds[name]
        bone = bones[name]
        parent = bone["parent"]
        if parent is None:
            anchor_speed, parent_angular = root_speed, root_angular
        else:
            start_speed, end_speed, parent_angular = bone_speed(parent)
            anchor_speed = start_speed if bone["anchor"] == "start" else end_speed
        start_speed = anchor_speed + math.hypot(*bone["offset"]) * parent_angular
        angular = parent_angular + math.radians(2 * math.pi * abs(bone["flap_amplitude"]) / period)
        bounds[name] = (start_speed, start_speed + bone["length"] * angular, angular)
        return bounds[name]

    for name in bones:
        bone_speed(name)
    return bounds


def inspect(out):
    doc = json.loads((out / "animations.json").read_text(encoding="utf-8"))
    trace = json.loads((out / "rig_trace.json").read_text(encoding="utf-8"))
    bones, pairs = trace["bones"], trace["wing_pairs"]
    bounds = speed_bounds(bones, trace["motion"])
    pages = []
    for page in doc["pages"]:
        with Image.open(out / page["file"]) as atlas:
            pages.append(np.asarray(atlas.convert("RGBA")))
    reports = {}
    for name, clip in doc["clips"].items():
        entry = trace["clips"][name]
        poses = entry["poses"]
        flags = {}
        images = []

        def mark(frame, message):
            flags.setdefault(str(frame), []).append(message)

        if len(poses) != len(clip["frames"]):
            mark(0, "pose and animation frame counts differ")
        if len(entry.get("frame_hashes", [])) != len(poses):
            mark(0, "frame hash count differs")
        times = entry.get("times", [])
        duration = clip.get("duration")
        valid_times = (isinstance(times, list) and len(times) == len(poses) and bool(times)
                       and isinstance(duration, (int, float)) and not isinstance(duration, bool)
                       and math.isfinite(duration) and duration > 0
                       and all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in times)
                       and times[0] >= 0 and all(a < b for a, b in zip(times, times[1:]))
                       and (times[-1] < duration if clip["loop"] else times[-1] <= duration + 1e-9))
        if not valid_times:
            mark(0, "invalid frame times")
        for index, pose in enumerate(poses):
            path = out / "frames" / name / f"{name}_{index:03d}.png"
            if not path.is_file():
                mark(index, "frame file missing")
            else:
                with Image.open(path) as img:
                    rgba = img.convert("RGBA")
                    images.append(np.asarray(rgba))
                    bbox = rgba.getchannel("A").getbbox()
                    if index < len(entry.get("frame_hashes", [])) and hashlib.sha256(rgba.tobytes()).hexdigest() != entry["frame_hashes"][index]:
                        mark(index, "frame pixels differ from recorded frame hash")
                    if img.size != (doc["frame_size"], doc["frame_size"]):
                        mark(index, "wrong frame size")
                    if bbox is None:
                        mark(index, "empty frame")
                    elif bbox[0] == 0 or bbox[1] == 0 or bbox[2] == img.width or bbox[3] == img.height:
                        mark(index, "art touches frame edge")
                    if index < len(clip["frames"]):
                        try:
                            ref = clip["frames"][index]
                            if not isinstance(ref, int) or isinstance(ref, bool) or not 0 <= ref < len(doc["regions"]):
                                raise ValueError("invalid region")
                            r = doc["regions"][ref]
                            if not isinstance(r["page"], int) or not 0 <= r["page"] < len(pages):
                                raise ValueError("invalid atlas page")
                            page = pages[r["page"]]
                            x, y, w, h, ox, oy = (r[k] for k in ("x", "y", "w", "h", "ox", "oy"))
                            if any(not isinstance(v, int) or isinstance(v, bool) for v in (x, y, w, h, ox, oy)):
                                raise ValueError("invalid region coordinates")
                            if min(x, y, ox, oy) < 0 or w <= 0 or h <= 0 or x + w > page.shape[1] or y + h > page.shape[0] or ox + w > img.width or oy + h > img.height:
                                raise ValueError("out-of-range atlas region")
                            pixels = np.asarray(rgba)
                            source = pixels[oy:oy+h, ox:ox+w]
                            crop = page[y:y+h, x:x+w]
                            visible = source[:, :, 3] > 0
                            if (bbox != (ox, oy, ox+w, oy+h) or not np.array_equal(source[:, :, 3], crop[:, :, 3])
                                    or not np.array_equal(source[:, :, :3][visible], crop[:, :, :3][visible])):
                                mark(index, "atlas frame differs from source pixels")
                        except (KeyError, TypeError, ValueError, IndexError):
                            mark(index, "invalid atlas frame reference")
            for bone_name, bone in bones.items():
                if bone_name not in pose:
                    mark(index, f"{bone_name}: missing pose")
                    continue
                start, end, angle = pose[bone_name]
                if any(not math.isfinite(x) for x in (*start, *end, angle)):
                    mark(index, f"{bone_name}: non-finite coordinates")
                    continue
                if abs(math.dist(start, end) - bone["length"]) > max(1e-6, bone["length"] * 1e-5):
                    mark(index, f"{bone_name}: bone length changed")
                expected = rotate((bone["length"], 0), angle)
                if math.dist(end, (start[0] + expected[0], start[1] + expected[1])) > 1e-5:
                    mark(index, f"{bone_name}: endpoint disagrees with angle")
                parent = bone["parent"]
                if parent is not None and parent in pose:
                    pstart, pend, pangle = pose[parent]
                    if any(not math.isfinite(x) for x in (*pstart, *pend, pangle)):
                        mark(index, f"{bone_name}: parent has non-finite coordinates")
                        continue
                    anchor = pstart if bone["anchor"] == "start" else pend
                    off = rotate(bone["offset"], pangle)
                    if math.dist(start, (anchor[0] + off[0], anchor[1] + off[1])) > 1e-5:
                        mark(index, f"{bone_name}: joint detached")
                    local = angle - pangle
                    if not bone["limits"][0] - 1e-6 <= local <= bone["limits"][1] + 1e-6:
                        mark(index, f"{bone_name}: joint limit exceeded")
            for left, right in pairs:
                if left not in pose or right not in pose:
                    continue
                def local_angle(name):
                    parent = bones[name]["parent"]
                    return pose[name][2] - (pose[parent][2] if parent is not None else 0)
                if abs(local_angle(left) - local_angle(right)) > 2.0:
                    mark(index, f"{left}/{right}: configured wing pair out of phase")
        # Older traces have no pivot, so their pixels can't be matched to bones.
        if "pivot" in trace and len(images) == len(poses) and not any(b not in p for p in poses for b in bones):
            ox, oy = trace["pivot"]
            unit = trace["unit_px"]
            skeleton = {}
            segments = []
            for bone in bones:
                skeleton[bone + ".start"] = [[ox + p[bone][0][0] * unit, oy + p[bone][0][1] * unit] for p in poses]
                skeleton[bone + ".end"] = [[ox + p[bone][1][0] * unit, oy + p[bone][1][1] * unit] for p in poses]
                segments.append((bone + ".start", bone + ".end"))
            for found in frame_problems(images, unit, skeleton, segments):
                for index, messages in found.items():
                    for message in messages:
                        mark(index, message)
        # A driver-derived upper bound avoids treating a normal turning point as a jump.
        if len(poses) >= 2 and valid_times:
            for bone_name, bone in bones.items():
                if any(bone_name not in pose or any(not math.isfinite(v) for v in pose[bone_name][1]) for pose in poses):
                    continue
                points = [pose[bone_name][1] for pose in poses]
                for index in range(len(points) if clip["loop"] else len(points) - 1):
                    next_index = (index + 1) % len(points)
                    dt = times[next_index] - times[index] if next_index else clip["duration"] - times[index] + times[0]
                    if dt <= 0 or math.dist(points[index], points[next_index]) > bounds[bone_name][1] * dt + 1e-5:
                        mark((index + 1) % len(points), f"{bone_name}: abrupt endpoint movement")
        if clip["loop"] and poses:
            reference = entry.get("loop_reference")
            if not reference:
                mark(0, "loop reference missing")
            else:
                for bone in bones:
                    if (bone not in reference or bone not in poses[0]
                            or any(not math.isfinite(x) for x in reference[bone][1])
                            or math.dist(reference[bone][1], poses[0][bone][1]) > 1e-5):
                        mark(len(poses) - 1, f"{bone}: loop endpoint does not close")
        reports[name] = {"status": "FAIL" if flags else "PASS", "flags": flags, "frames": len(poses)}
    problems = trace.get("part_problems", [])
    return {"clips": reports, "parts": {"status": "FAIL" if problems else "PASS", "problems": problems},
            "scope": "geometry, explicit wing pairs, endpoint speed bounds, loop closure, frame bounds, floating art, bare bones and PNG part continuity; not anatomy or visual quality"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    result = inspect(a.output)
    (a.output / "qa_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, report in result["clips"].items():
        print(f"{name}: {report['status']} ({len(report['flags'])} flagged frames)")
    for problem in result["parts"]["problems"]:
        print("part: " + problem)
    return int(any(x["status"] == "FAIL" for x in result["clips"].values()) or bool(result["parts"]["problems"]))


if __name__ == "__main__":
    raise SystemExit(main())
