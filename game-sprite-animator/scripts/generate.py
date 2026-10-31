#!/usr/bin/env python3
"""Generate a full sprite-animation set for a character.

    python generate.py --character ../assets/characters/hero.json --preset hd --out out/hero
    python generate.py --character c.json --preset pixel --clips idle,walk,run --out out/c_px
    python generate.py --character c.json --size 384 --fps 60 --fps-override idle=30 --out out/c
"""
import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sprite_anim import export  # noqa: E402
from sprite_anim.art import Canvas  # noqa: E402
from sprite_anim.rig_data import JointRecorder  # noqa: E402
from sprite_anim.constraints import frame_metrics  # noqa: E402
from sprite_anim.fx import build_fx  # noqa: E402
from sprite_anim.motions import SEAMS, build_clips  # noqa: E402
from sprite_anim.integrity import HUMANOID_BONES  # noqa: E402
from sprite_anim.part_check import check_parts  # noqa: E402
from sprite_anim.render import GROUND_FRAC, PRESETS, Renderer, frame_time, to_u8  # noqa: E402
from sprite_anim.rig import full_pose, heel_world, solve, toe_world  # noqa: E402

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE_JOINTS = ["wr_n", "wr_f", "an_n", "an_f", "kn_n", "kn_f", "hip", "neck", "head_base"]


def parse_overrides(text):
    out = {}
    for item in (text or "").split(","):
        if "=" in item:
            k, v = item.split("=")
            out[k.strip()] = int(v)
    return out


def rig_trace(clip, n, fps, art, unit_px, size):
    """Per-frame joint positions (in output pixels) for the QA pass."""
    body = art.body
    recorder = JointRecorder(TRACE_JOINTS, unit_px)
    tr = recorder.joints
    metrics = []
    feet = {"n": dict(heel=[], ball=[]), "f": dict(heel=[], ball=[])}
    contacts = {"n": [], "f": []}
    # Where each joint lands in the frame, squash included, for the bone-coverage check.
    skeleton = {j: [] for bone in HUMANOID_BONES for j in bone}
    smear = []
    cv = Canvas(size, 1, unit_px, GROUND_FRAC, 1, False, (0, 0, 0))
    for i in range(n):
        t = frame_time(clip, i, n, fps)
        pose = full_pose(clip.sample(t))
        sk = solve(pose, body)
        recorder.append(sk)
        cv.set_squash(pose["squash"], 0.0)
        for j, track in skeleton.items():
            track.append([round(v, 2) for v in cv.T(sk[j])])
        smear.append(pose["smear"] > 0.02)
        metrics.append(frame_metrics(sk, body, art.weapon_span(sk)))
        c = clip.contacts(t)
        for s in "nf":
            for key, pt in (("heel", heel_world(sk, s)), ("ball", toe_world(sk, s))):
                feet[s][key].append([round(pt[0] * unit_px, 3), round(pt[1] * unit_px, 3)])
            contacts[s].append(bool(c.get(s, False)))
    return dict(joints=tr, skeleton=skeleton, smear=smear, feet=feet, contacts=contacts, metrics=metrics,
                frame_dt=clip.duration / (n if clip.loop else n - 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--character", help="character JSON (see references/character-spec.md)")
    ap.add_argument("--preset", choices=PRESETS, default="hd")
    ap.add_argument("--size", type=int, help="square frame size, overrides preset")
    ap.add_argument("--fps", type=int, help="overrides preset")
    ap.add_argument("--fps-override", help="per-clip fps, e.g. idle=15,crouch_idle=15")
    ap.add_argument("--pixel", action="store_true", help="force pixel-art output")
    ap.add_argument("--clips", default="all", help="comma list; default all")
    ap.add_argument("--motion-blur", type=int, default=1, help="temporal samples per frame (HD only)")
    ap.add_argument("--no-fx", action="store_true")
    ap.add_argument("--no-frames", action="store_true", help="skip loose per-frame PNGs")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    spec = {}
    if a.character:
        with open(a.character, encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["_dir"] = os.path.dirname(os.path.abspath(a.character))   # for relative part images
    p = dict(PRESETS[a.preset])
    size = a.size or p["size"]
    fps = a.fps or p["fps"]
    pixel = a.pixel or p["pixel"]
    over = parse_overrides(a.fps_override)
    name = spec.get("name", "character")

    clips = build_clips(spec.get("style"), spec.get("custom_clips"), spec.get("clip_key_overrides"))
    names = list(clips) if a.clips == "all" else [c for c in a.clips.split(",") if c]
    unknown = [c for c in names if c not in clips]
    if unknown:
        sys.exit(f"unknown clips: {unknown}\navailable: {list(clips)}")

    root = a.out
    if os.path.isdir(root):
        for sub in ("frames", "sheets", "engine", "fx"):
            shutil.rmtree(os.path.join(root, sub), ignore_errors=True)
    for sub in ("engine/godot", "engine/cocos", "engine/web", "sheets"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)

    t0 = time.time()
    r = Renderer(spec, size, pixel, motion_blur=a.motion_blur, clips=clips)
    print(f"[bake] cloth chains {[d.name for d in r.defs]} in {time.time() - t0:.1f}s")
    unit_px = r.unit
    print(f"[fit] character scale {r.fit:.3f} to keep every action inside the frame")
    pivot = (size // 2, int(size * GROUND_FRAC))

    rendered, meta, sheets, traces = {}, {}, {}, {}
    for nm in names:
        c = clips[nm]
        cfps = over.get(nm, fps)
        frames = [to_u8(f) for f in r.render_clip(c, cfps)]
        n = len(frames)
        rendered[nm] = dict(frames=frames)
        if not a.no_frames:
            export.write_frames(root, nm, frames)
        sheets[nm] = export.write_sheet(root, nm, frames, size)
        step = c.duration / n if c.loop else c.duration / (n - 1)
        meta[nm] = dict(
            fps=cfps, loop=c.loop, duration=round(c.duration, 4),
            speed_px_s=round(c.speed * unit_px, 2),
            events=[dict(frame=min(n - 1, int(round(t / step))), name=e) for t, e in c.events],
            next=c.next if not c.loop else None, prev=c.prev,
            chain_frame=int(round(c.chain_at / step)) if c.chain_at else None,
            tags=sorted(c.tags))
        traces[nm] = rig_trace(c, n, cfps, r.art, unit_px, size)
        print(f"[clip] {nm:<14} {n:>3}f @ {cfps}fps {'loop' if c.loop else 'once'}")

    for nm in names:
        c = clips[nm]
        if c.next_at and c.next in rendered:
            meta[nm]["next_frame"] = int(round(c.next_at * (len(rendered[c.next]["frames"]) - 1)))

    sprites, refs, files = export.build_atlas(root, rendered, size)
    export.texturepacker_json(root, sprites, refs, files, size, pivot)
    doc = export.manifest(sprites, refs, files, meta, size, pivot, name)
    with open(os.path.join(root, "animations.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    export.godot_tres(root, doc)
    export.cocos_plist(root, doc)
    export.css_keyframes(root, doc, sheets)
    shutil.copy(os.path.join(SKILL_ROOT, "assets", "engine", "web", "sprite-player.js"), os.path.join(root, "engine", "web"))
    os.makedirs(os.path.join(root, "engine", "unity"), exist_ok=True)
    shutil.copy(os.path.join(SKILL_ROOT, "assets", "engine", "unity", "SpriteSetImporter.cs"), os.path.join(root, "engine", "unity"))

    fx_doc = None
    if not a.no_fx:
        fx = build_fx(size, fps, pixel, spec)
        fx_rendered = {k: dict(frames=v["frames"]) for k, v in fx.items()}
        os.makedirs(os.path.join(root, "fx"), exist_ok=True)
        s2, r2, f2 = export.build_atlas(root, fx_rendered, size, prefix="fx")
        export.texturepacker_json(root, s2, r2, f2, size, pivot, prefix="fx")
        fm = {k: dict(fps=v["fps"], loop=v["loop"], duration=v["duration"], events=[], tags=[], next=None) for k, v in fx.items()}
        fx_doc = export.manifest(s2, r2, f2, fm, size, pivot, name + "_fx")
        with open(os.path.join(root, "fx.json"), "w", encoding="utf-8") as fh:
            json.dump(fx_doc, fh, ensure_ascii=False, indent=1)
        for k, v in fx.items():
            export.write_sheet(os.path.join(root, "fx"), k, v["frames"], size)

    seams = [s for s in SEAMS if s[0] in names and s[1] in names]
    # Custom clips declare their own neighbors; include them in the same transition QA.
    for name in spec.get("custom_clips", {}):
        if name not in names:
            continue
        clip = clips[name]
        for pair in ((clip.prev, name), (name, clip.next)):
            if pair[0] in names and pair[1] in names and pair[0] != pair[1] and pair not in seams:
                seams.append(pair)
    with open(os.path.join(root, "rig_trace.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(traces=traces, seams=seams, bones=HUMANOID_BONES,
                       part_problems=check_parts(spec, r.art.body) if spec.get("parts") else [],
                       unit_px=unit_px, speeds={n: clips[n].speed * unit_px for n in names}), fh)

    export.preview_html(root, os.path.join(SKILL_ROOT, "assets", "preview_template.html"),
                        os.path.join(SKILL_ROOT, "assets", "engine", "web", "sprite-player.js"), doc, fx_doc, name)
    total = sum(len(v["frames"]) for v in rendered.values())
    pages = ", ".join(f"{p['file']} {p['w']}x{p['h']}" for p in files)
    print(f"[done] {len(names)} clips, {total} frames, {len(sprites)} unique, atlas: {pages}, {time.time() - t0:.1f}s")
    print(f"[done] open {os.path.join(root, 'preview.html')}")


if __name__ == "__main__":
    main()
