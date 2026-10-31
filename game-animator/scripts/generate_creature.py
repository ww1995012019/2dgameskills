#!/usr/bin/env python3
"""Experimental configuration-driven flight sprite generator."""
import argparse
import base64
import hashlib
import html
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modes/game-sprite-animator/scripts"))
from sprite_anim import export
from creature_render import CreatureRenderer
from creature_rig import CreatureRig, FLIGHT_ACTIONS, LOOPS


def write_preview(out, doc, player, title):
    images = ["data:image/png;base64," + base64.b64encode((out / page["file"]).read_bytes()).decode("ascii")
              for page in doc["pages"]]
    data = json.dumps(dict(doc=doc, images=images, fx=None, fx_images=[], title=title), ensure_ascii=False)
    # JSON is embedded in a script element: escape HTML delimiters before insertion.
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = (ROOT / "assets/creature_preview.html").read_text(encoding="utf-8")
    template = template.replace("__TITLE__", html.escape(title))
    template = template.replace("/*__PLAYER__*/", player.read_text(encoding="utf-8"))
    template = template.replace("/*__DATA__*/null", data)
    (out / "preview.html").write_text(template, encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True, help="creature JSON and relative PNG part paths")
    p.add_argument("--out", required=True, help="new or empty output directory")
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--clips", default=",".join(FLIGHT_ACTIONS))
    a = p.parse_args()
    names = a.clips.split(",")
    if not names or len(set(names)) != len(names) or any(n not in FLIGHT_ACTIONS for n in names):
        p.error("--clips must be unique names from " + ", ".join(FLIGHT_ACTIONS))
    if not 8 <= a.fps <= 60:
        p.error("--fps must be in 8..60")
    config_path = Path(a.config).resolve()
    spec = json.loads(config_path.read_text(encoding="utf-8"))
    rig = CreatureRig(spec)
    renderer = CreatureRenderer(rig, spec, config_path.parent, a.size)
    count = max(2, round(rig.period * a.fps))
    total_frames = sum(count + (name not in LOOPS) for name in names)
    if total_frames > 512:
        p.error("requested animations exceed 512 frames; reduce FPS, period or clips")
    if total_frames * a.size * a.size * 4 > 512 * 1024 * 1024:
        p.error("raw frames would exceed 512 MiB; reduce size, FPS, period or clips")
    out = Path(a.out).resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        p.error("--out must be a new or empty directory")
    out.mkdir(parents=True, exist_ok=True)
    for folder in ("frames", "sheets", "engine/godot", "engine/cocos", "engine/web"):
        (out / folder).mkdir(parents=True, exist_ok=True)
    rendered, metadata, sheets, traces = {}, {}, {}, {}
    for name in names:
        is_loop = name in LOOPS
        total = count if is_loop else count + 1
        times = [rig.period * i / count for i in range(total)]
        poses = [rig.pose(t, name) for t in times]
        frames = [np.asarray(renderer.render(pose)) for pose in poses]
        rendered[name] = {"frames": frames}
        metadata[name] = dict(fps=count / rig.period, loop=is_loop, duration=rig.period,
                              speed_px_s=0, events=[], next=None, tags=["air"])
        traces[name] = dict(times=times, poses=poses, frame_hashes=[hashlib.sha256(frame.tobytes()).hexdigest() for frame in frames],
                            loop_reference=rig.pose(rig.period, name) if is_loop else None)
        export.write_frames(str(out), name, frames)
        sheets[name] = export.write_sheet(str(out), name, frames, a.size)
        print(f"[clip] {name}: {total} frames", flush=True)
    sprites, refs, pages = export.build_atlas(str(out), rendered, a.size)
    pivot = tuple(round(x) for x in renderer.pivot)
    doc = export.manifest(sprites, refs, pages, metadata, a.size, pivot, str(spec.get("name", "creature")))
    (out / "animations.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "rig_trace.json").write_text(json.dumps({"bones": rig.bones, "wing_pairs": rig.wing_pairs,
                                                    "motion": {"period": rig.period, "bob": rig.bob, "pitch": rig.pitch},
                                                    "unit_px": renderer.unit, "clips": traces}, ensure_ascii=False), encoding="utf-8")
    export.texturepacker_json(str(out), sprites, refs, pages, a.size, pivot)
    export.godot_tres(str(out), doc)
    export.cocos_plist(str(out), doc)
    export.css_keyframes(str(out), doc, sheets)
    player = ROOT / "modes/game-sprite-animator/assets/engine/web/sprite-player.js"
    (out / "engine/web/sprite-player.js").write_bytes(player.read_bytes())
    write_preview(out, doc, player, str(spec.get("name", "creature")))
    print(f"[done] {len(names)} clips; generated files only, engine imports not yet verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
