#!/usr/bin/env python3
"""Generate a side-view shooter character: lower body, upper body per weapon, full-body clips
and baked combos.

    python generate.py --character ../assets/characters/commando.json --preset hd --out out/commando
    python generate.py --character c.json --preset pixel --weapons pistol,smg --out out/c_px
    python generate.py --character c.json --combos run:fire_0,idle:fire_p45 --out out/c
"""
import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sprite_anim import export  # noqa: E402
from sprite_anim.constraints import frame_metrics  # noqa: E402
from sprite_anim.fx import build_fx  # noqa: E402
from sprite_anim.motions import AIMS_9, DEFAULT_COMBOS, SEAMS, aim_tag, build_clips  # noqa: E402
from sprite_anim.render import GROUND_FRAC, PRESETS, Renderer, frame_time, to_u8  # noqa: E402
from sprite_anim.rig import full_pose, heel_world, solve, toe_world  # noqa: E402
from sprite_anim.weapons import WEAPONS  # noqa: E402

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_overrides(text):
    out = {}
    for item in (text or "").split(","):
        if "=" in item:
            k, v = item.split("=")
            out[k.strip()] = int(v)
    return out


def trace_clip(clip, n, fps, art, unit_px, rest_waist, pixel):
    """Per-frame data the game needs (anchors, muzzle) and the QA pass reads (hands, feet)."""
    feet = {"n": dict(heel=[], ball=[]), "f": dict(heel=[], ball=[])}
    contacts = {"n": [], "f": []}
    anchors, muzzle, gaps, flash, metrics = [], [], [], [], []
    art.active = clip.weapon or art.spec["weapons"][0]
    round_px = (lambda v: int(round(v))) if pixel else (lambda v: round(v, 2))
    for i in range(n):
        t = frame_time(clip, i, n, fps)
        pose = full_pose(clip.sample(t))
        sk = solve(pose, art.body)
        metrics.append(frame_metrics(sk, art.body, art.weapon_span(sk)))
        c = clip.contacts(t)
        for s in "nf":
            for key, pt in (("heel", heel_world(sk, s)), ("ball", toe_world(sk, s))):
                feet[s][key].append([round(pt[0] * unit_px, 3), round(pt[1] * unit_px, 3)])
            contacts[s].append(bool(c.get(s, False)))
        anchors.append([round_px((sk["waist"][0] - rest_waist[0]) * unit_px), round_px(-(sk["waist"][1] - rest_waist[1]) * unit_px)])
        weapon = clip.weapon or art.spec["weapons"][0]
        m = art.muzzle(sk, weapon)
        muzzle.append([round(m[0] * unit_px, 2), round(-m[1] * unit_px, 2)])
        gaps.append([round(g * unit_px, 3) * (1 if pose["gun_ik"] >= 0.999 else 0) for g in sk["hand_gaps"]])
        flash.append(pose["flash"])
    step = clip.duration / n if clip.loop else clip.duration / (n - 1)
    shots = sorted(int(round(t / step)) for t, e in clip.events if e == "shot")
    return dict(feet=feet, contacts=contacts, gaps=gaps, flash=flash, shots=shots, metrics=metrics, frame_dt=step), anchors, muzzle


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--character", help="character JSON (see references/character-spec.md)")
    ap.add_argument("--preset", choices=PRESETS, default="hd")
    ap.add_argument("--size", type=int, help="square frame size, overrides preset")
    ap.add_argument("--fps", type=int, help="overrides preset")
    ap.add_argument("--fps-override", help="per-clip fps, e.g. idle=15,crouch_idle=15")
    ap.add_argument("--pixel", action="store_true", help="force pixel-art output")
    ap.add_argument("--weapons", help="comma list, overrides the spec. first = primary")
    ap.add_argument("--aim-steps", type=int, choices=[5, 9], default=9, help="aim angles per weapon")
    ap.add_argument("--combos", help="baked lower:upper pairs, or 'none'")
    ap.add_argument("--clips", default="all", help="comma list; default all")
    ap.add_argument("--no-fx", action="store_true")
    ap.add_argument("--no-frames", action="store_true", help="skip loose per-frame PNGs")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    spec = {}
    if a.character:
        with open(a.character, encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["_dir"] = os.path.dirname(os.path.abspath(a.character))
    if a.weapons:
        spec["weapons"] = [w for w in a.weapons.split(",") if w]
    bad = [w for w in spec.get("weapons", []) if w not in WEAPONS]
    if bad:
        sys.exit(f"unknown weapons: {bad}\navailable: {list(WEAPONS)}")
    p = dict(PRESETS[a.preset])
    size = a.size or p["size"]
    fps = a.fps or p["fps"]
    pixel = a.pixel or p["pixel"]
    over = parse_overrides(a.fps_override)
    name = spec.get("name", "soldier")
    aims = AIMS_9 if a.aim_steps == 9 else AIMS_9[::2]
    combos = DEFAULT_COMBOS if a.combos is None else ([] if a.combos == "none" else a.combos.split(","))

    clips = build_clips(spec, fps, aims, combos)
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
    r = Renderer(spec, size, pixel, clips=clips)
    print(f"[bake] cloth chains {[d.name for d in r.defs]} in {time.time() - t0:.1f}s")
    unit_px = r.unit
    print(f"[fit] character scale {r.fit:.3f} to keep every action inside the frame")
    pivot = (size // 2, int(size * GROUND_FRAC))
    rest_waist = solve(full_pose({}), r.art.body)["waist"]

    rendered, meta, sheets, traces = {}, {}, {}, {}
    for nm in names:
        c = clips[nm]
        cfps = over.get(nm, c.fps or fps)
        frames = [to_u8(f) for f in r.render_clip(c, cfps)]
        n = len(frames)
        rendered[nm] = dict(frames=frames)
        if not a.no_frames:
            export.write_frames(root, nm, frames)
        sheets[nm] = export.write_sheet(root, nm, frames, size)
        step = c.duration / n if c.loop else c.duration / (n - 1)
        trace, anchors, muzzle = trace_clip(c, n, cfps, r.art, unit_px, rest_waist, pixel)
        m = dict(fps=cfps, loop=c.loop, duration=round(c.duration, 4), speed_px_s=round(c.speed * unit_px, 2),
                 events=[dict(frame=min(n - 1, int(round(t / step))), name=e) for t, e in c.events],
                 next=c.next if not c.loop else None, tags=sorted(c.tags), layer=c.layer)
        if c.weapon:
            m["weapon"] = c.weapon
        if c.aim is not None:
            m["aim"] = c.aim
        if c.layer == "lower":
            m["anchors"] = anchors
        if c.layer != "lower":
            m["muzzle"] = muzzle
        meta[nm] = m
        traces[nm] = trace
        print(f"[clip] {nm:<22} {n:>3}f @ {cfps}fps {c.layer}")

    sprites, refs, files = export.build_atlas(root, rendered, size)
    export.texturepacker_json(root, sprites, refs, files, size, pivot)
    doc = export.manifest(sprites, refs, files, meta, size, pivot, name)
    doc["weapons"] = {w: {k: WEAPONS[w][k] for k in ("period", "kind", "reload")} for w in spec.get("weapons", ["rifle"])}
    doc["aims"] = {str(x): aim_tag(x) for x in aims}
    doc["unit_px"] = unit_px
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

    with open(os.path.join(root, "rig_trace.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(traces=traces, seams=[s for s in SEAMS if s[0] in names and s[1] in names],
                       unit_px=unit_px, speeds={n: clips[n].speed * unit_px for n in names}), fh)

    export.preview_html(root, os.path.join(SKILL_ROOT, "assets", "preview_template.html"),
                        os.path.join(SKILL_ROOT, "assets", "engine", "web", "sprite-player.js"), doc, fx_doc, name)
    total = sum(len(v["frames"]) for v in rendered.values())
    pages = ", ".join(f"{p['file']} {p['w']}x{p['h']}" for p in files)
    print(f"[done] {len(names)} clips, {total} frames, {len(sprites)} unique, atlas: {pages}, {time.time() - t0:.1f}s")
    print(f"[done] open {os.path.join(root, 'preview.html')}")


if __name__ == "__main__":
    main()
