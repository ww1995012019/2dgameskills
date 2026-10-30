#!/usr/bin/env python3
"""Bake a complete eight-direction 3/4 top-down character, with engine exports."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sprite_anim import export
from sprite_anim.art import TopDownArt
from sprite_anim.topdown import (
    DIRECTIONS,
    MIRRORS,
    DURATIONS,
    LOOPS,
    BONES,
    sample,
    project,
    frame_count,
    phase_at,
    events,
)

ROOT = Path(__file__).resolve().parents[1]
PRESETS = {
    "hd": (256, 30, False),
    "hd60": (256, 60, False),
    "hd512": (512, 30, False),
    "pixel48": (48, 12, True),
    "pixel": (64, 15, True),
    "pixel96": (96, 15, True),
}


def digest(frame):
    return hashlib.sha256(frame.tobytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--character", default=str(ROOT / "assets/characters/wanderer.json"))
    ap.add_argument("--preset", choices=PRESETS, default="hd")
    ap.add_argument("--size", type=int)
    ap.add_argument("--fps", type=int)
    ap.add_argument(
        "--clips", default="all", help="comma-separated actions, all eight directions per action"
    )
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    size, fps, pixel = PRESETS[a.preset]
    size = a.size or size
    fps = a.fps or fps
    if not 32 <= size <= 1024 or not 8 <= fps <= 120:
        ap.error("size must be 32..1024 and fps 8..120")
    actions = list(DURATIONS) if a.clips == "all" else a.clips.split(",")
    if not actions or len(set(actions)) != len(actions) or any(x not in DURATIONS for x in actions):
        ap.error("unknown or duplicate action")
    if "idle" not in actions:
        actions.insert(0, "idle")
    spec = json.loads(Path(a.character).read_text(encoding="utf-8"))
    art = TopDownArt(spec, size, pixel)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("frames", "sheets", "engine"):
        if (out / sub).exists():
            shutil.rmtree(out / sub)
        (out / sub).mkdir()
    for sub in ("godot", "cocos", "web", "unity"):
        (out / "engine" / sub).mkdir()
    rendered = {}
    meta = {}
    traces = {}
    sheets = {}
    for action in actions:
        count = frame_count(action, fps)
        loop = action in LOOPS
        duration = (count if loop else count - 1) / fps
        stride = 10 if action == "run" else 8
        duty = 0.55 if action == "run" else 0.6
        speed = 2 * stride / (duty * duration) * art.unit if action in ("walk", "run") else 0.0
        frames_by_direction = {}
        poses_by_direction = {}
        for direction in DIRECTIONS:
            if direction in MIRRORS:
                continue
            poses = [sample(action, direction, phase_at(action, i, count)) for i in range(count)]
            frames_by_direction[direction] = [art.render(p) for p in poses]
            poses_by_direction[direction] = poses
        for direction, canonical in MIRRORS.items():
            # Mirror about the shared integer feet pivot, not about (size-1)/2.
            frames = []
            for original in frames_by_direction[canonical]:
                mirrored = np.zeros_like(original)
                mirrored[:, 1:] = original[:, ::-1][:, :-1]
                frames.append(mirrored)
            frames_by_direction[direction] = frames
            poses = []
            for pose in poses_by_direction[canonical]:
                mirrored = dict(pose)
                mirrored["points"] = {
                    j: v * np.array([-1, 1, 1]) for j, v in pose["points"].items()
                }
                poses.append(mirrored)
            poses_by_direction[direction] = poses
        for direction, vector in DIRECTIONS.items():
            name = action + "_" + direction
            frames = frames_by_direction[direction]
            poses = poses_by_direction[direction]
            rendered[name] = {"frames": frames}
            export.write_frames(str(out), name, frames)
            sheets[name] = export.write_sheet(str(out), name, frames, size)
            ev = events(action, count)
            meta[name] = dict(
                fps=fps,
                loop=loop,
                duration=duration,
                speed_px_s=round(speed, 6),
                velocity_px_s=[round(speed * v, 6) for v in vector],
                events=ev,
                next=None if action in LOOPS or action == "death" else "idle_" + direction,
                tags=["ground"] + (["attack"] if action == "attack" else []),
                action=action,
                direction=direction,
                mirror_of=(action + "_" + MIRRORS[direction]) if direction in MIRRORS else None,
            )
            joints = {j: [] for j in poses[0]["points"]}
            world = {j: [] for j in joints}
            feet = {k: [] for k in ("r", "l")}
            contacts = {k: [] for k in feet}
            for pose in poses:
                for j, v in pose["points"].items():
                    joints[j].append((project(v) * art.unit).tolist())
                    world[j].append(v.tolist())
                for leg in feet:
                    v = pose["points"]["foot_" + leg]
                    ground = v.copy()
                    ground[2] = 0
                    feet[leg].append((project(ground) * art.unit).tolist())
                    contacts[leg].append(pose["contacts"][leg])
            traces[name] = dict(
                action=action,
                direction=direction,
                joints=joints,
                world=world,
                feet=feet,
                contacts=contacts,
                frame_dt=1 / fps,
                frame_hashes=[digest(f) for f in frames],
            )
            print(f"[clip] {name:<20} {count}f @ {fps}fps", flush=True)
    sprites, refs, pages = export.build_atlas(str(out), rendered, size)
    export.texturepacker_json(str(out), sprites, refs, pages, size, art.pivot)
    doc = export.manifest(sprites, refs, pages, meta, size, art.pivot, spec.get("name", "topdown"))
    doc.update(
        view="three_quarter_topdown",
        direction_order=list(DIRECTIONS),
        directions={
            k: dict(vector=list(v), mirror_of=MIRRORS.get(k)) for k, v in DIRECTIONS.items()
        },
        mirror_rule="baked screen reflection; mirrored equipment changes handedness",
        unit_px=art.unit,
    )
    (out / "animations.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "rig_trace.json").write_text(
        json.dumps(dict(traces=traces, unit_px=art.unit, bones=BONES)), encoding="utf-8"
    )
    export.godot_tres(str(out), doc)
    export.cocos_plist(str(out), doc)
    export.css_keyframes(str(out), doc, sheets)
    shutil.copy(ROOT / "assets/engine/web/sprite-player.js", out / "engine/web/sprite-player.js")
    shutil.copy(
        ROOT / "assets/engine/unity/SpriteSetImporter.cs", out / "engine/unity/SpriteSetImporter.cs"
    )
    export.preview_html(
        str(out),
        str(ROOT / "assets/preview_template.html"),
        str(ROOT / "assets/engine/web/sprite-player.js"),
        doc,
        None,
        doc["character"],
    )
    print(
        f'[done] {len(meta)} clips, {sum(len(x["frames"]) for x in rendered.values())} frames',
        flush=True,
    )


if __name__ == "__main__":
    main()
