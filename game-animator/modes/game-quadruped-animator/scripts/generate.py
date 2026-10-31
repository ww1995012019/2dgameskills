#!/usr/bin/env python3
"""Generate a side-view wolf: four gaits plus bite, hurt and terminal death."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sprite_anim import export
from sprite_anim.rig import Clip, GAITS, LEGS, LENGTHS, ACTIONS
from sprite_anim.rig_data import JointRecorder
from sprite_anim.render import Renderer, TAIL

ROOT = Path(__file__).resolve().parents[1]
PRESETS = {
    "hd": (256, 30, False),
    "hd60": (256, 60, False),
    "hd512": (512, 30, False),
    "pixel48": (48, 12, True),
    "pixel": (64, 15, True),
    "pixel96": (96, 15, True),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--character", default=str(ROOT / "assets/characters/wolf.json"))
    p.add_argument("--preset", choices=PRESETS, default="hd")
    p.add_argument("--size", type=int)
    p.add_argument("--fps", type=int)
    p.add_argument(
        "--clips", default="all", help="idle,walk,trot,run; idle is included for the preview"
    )
    p.add_argument("--out", required=True)
    a = p.parse_args()
    size, fps, pixel = PRESETS[a.preset]
    size = a.size or size
    fps = a.fps or fps
    if not 32 <= size <= 1024 or not 8 <= fps <= 120:
        p.error("size must be 32..1024, fps 8..120")
    names = list(GAITS) + list(ACTIONS) if a.clips == "all" else a.clips.split(",")
    if (
        not names
        or len(set(names)) != len(names)
        or any(n not in GAITS and n not in ACTIONS for n in names)
    ):
        p.error("unknown or duplicate clip")
    if "idle" not in names:
        names.insert(0, "idle")
    spec = json.loads(Path(a.character).read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("frames", "sheets", "engine"):
        if (out / sub).exists():
            shutil.rmtree(out / sub)
        (out / sub).mkdir()
    for sub in ("godot", "cocos", "unity", "web"):
        (out / "engine" / sub).mkdir()
    r = Renderer(spec, size, pixel)
    art = r.art
    rendered = {}
    meta = {}
    traces = {}
    sheets = {}
    for name in names:
        clip = Clip(name, fps)
        tail = r.bake(clip)
        frames = []
        contacts = {leg: [] for leg in LEGS}
        recorder = None
        world = {}
        feet = {leg: [] for leg in LEGS}
        for i in range(clip.count):
            frame, pose = r.frame(clip, tail, i)
            frames.append(frame)
            if recorder is None:
                recorder = JointRecorder(pose["joints"], art.unit)
                world = {j: [] for j in pose["joints"]}
            recorder.append(pose["joints"])
            for j, v in pose["joints"].items():
                world[j].append([float(x) for x in v])
            for leg in LEGS:
                contacts[leg].append(pose["contacts"][leg])
                feet[leg].append((pose["joints"][leg + "_paw"] * art.unit).tolist())
        events = []
        if name in GAITS and name != "idle":
            for leg in LEGS:
                c = contacts[leg]
                for i in range(clip.count):
                    if c[i] and not c[i - 1]:
                        events.append(dict(frame=i, name="footstep_" + leg))
        if name == "attack":
            events = [
                dict(frame=round((clip.count - 1) * 0.3), name="hit_on"),
                dict(frame=round((clip.count - 1) * 0.58), name="hit_off"),
            ]
        elif name == "death":
            events = [dict(frame=round((clip.count - 1) * 0.9), name="body_thud")]
        events.sort(key=lambda e: (e["frame"], e["name"]))
        meta[name] = dict(
            fps=fps,
            loop=clip.loop,
            duration=clip.duration,
            speed_px_s=round(clip.speed * art.unit, 6),
            events=events,
            next="idle" if name in ("attack", "hurt") else None,
            tags=["ground"],
            gait=dict(duty=clip.gait["duty"], phases=clip.gait["phases"]),
        )
        traces[name] = dict(
            joints=recorder.joints,
            world=world,
            feet=feet,
            contacts=contacts,
            frame_dt=1 / fps,
            frame_hashes=[hashlib.sha256(f.tobytes()).hexdigest() for f in frames],
        )
        rendered[name] = dict(frames=frames)
        export.write_frames(str(out), name, frames)
        sheets[name] = export.write_sheet(str(out), name, frames, size)
        print(f"[clip] {name} {clip.count}f @ {fps}fps, {clip.speed:.3f} rig units/s", flush=True)
    sprites, refs, pages = export.build_atlas(str(out), rendered, size)
    export.texturepacker_json(str(out), sprites, refs, pages, size, art.pivot)
    doc = export.manifest(sprites, refs, pages, meta, size, art.pivot, spec.get("name", "wolf"))
    doc.update(
        rig="canine_side",
        unit_px=art.unit,
        legs=list(LEGS),
        facing="right",
        mirror_rule="flip in the engine for left",
    )
    (out / "animations.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "rig_trace.json").write_text(
        json.dumps(
            dict(
                traces=traces,
                unit_px=art.unit,
                bones=LENGTHS,
                tail=dict(segments=TAIL["n"] - 1, length=TAIL["seg"], width=list(TAIL["width"])),
            )
        ),
        encoding="utf-8",
    )
    export.godot_tres(str(out), doc)
    export.cocos_plist(str(out), doc)
    export.css_keyframes(str(out), doc, sheets)
    for kind, file in (("web", "sprite-player.js"), ("unity", "SpriteSetImporter.cs")):
        shutil.copy(ROOT / "assets/engine" / kind / file, out / "engine" / kind / file)
    export.preview_html(
        str(out),
        str(ROOT / "assets/preview_template.html"),
        str(ROOT / "assets/engine/web/sprite-player.js"),
        doc,
        None,
        doc["character"],
    )
    print(f'[done] {len(meta)} clips, {sum(len(x["frames"]) for x in rendered.values())} frames')


if __name__ == "__main__":
    main()
