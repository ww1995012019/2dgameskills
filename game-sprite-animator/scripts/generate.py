#!/usr/bin/env python3
"""Generate a full sprite-animation set for a character.

    python generate.py --character ../assets/characters/hero.json --preset hd --out out/hero
    python generate.py --character c.json --preset pixel --clips idle,walk,run --out out/c_px
    python generate.py --character c.json --size 384 --fps 60 --fps-override idle=30 --out out/c
"""
import argparse
import json
import math
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
from sprite_anim.motions import SEAMS, Gait, NaturalWalk, GroundedGaitHold, build_clips  # noqa: E402
from sprite_anim.integrity import HUMANOID_BONES, THIGH_DEFORMATION_LIMITS, GARMENT_EDGE_LIMITS, ORDINARY_RUN_LIMITS  # noqa: E402
from sprite_anim.part_check import check_parts  # noqa: E402
from sprite_anim.occlusion_review import clip_candidates, write_report as write_occlusion_report  # noqa: E402
from sprite_anim.puppet_check import check_core, check_hands, check_layers, check_motion, check_attachments, check_neck, check_connections  # noqa: E402
from sprite_anim.render import GROUND_FRAC, PRESETS, Renderer, frame_count, frame_time, playback_speed, walk_hold_phase, to_u8  # noqa: E402
from sprite_anim.rig import Body  # noqa: E402
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
    head_motion = dict(head_world_deg=[], chest_world_deg=[], relative_deg=[])
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
        for key, value in (('head_world_deg', sk['head_rot']), ('chest_world_deg', sk['chest_rot']),
                           ('relative_deg', sk['head_rot'] - sk['chest_rot'])):
            head_motion[key].append(round(float(value), 6))
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
                head_motion=head_motion,
                frame_dt=1.0 / fps)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--character", help="character JSON (see references/character-spec.md)")
    ap.add_argument("--preset", choices=PRESETS, default="hd")
    ap.add_argument("--size", type=int, help="square frame size, overrides preset")
    ap.add_argument("--fps", type=int, help="overrides preset")
    ap.add_argument("--fps-override", help="per-clip fps, e.g. idle=15,crouch_idle=15")
    ap.add_argument("--pixel", action="store_true", help="force pixel-art output")
    ap.add_argument("--clips", default="all", help="comma list; default all")
    ap.add_argument("--fit-selected-clips", action="store_true", help="frame only the exported clips; other clips retain simulation dependencies but are not included in the viewport guarantee")
    ap.add_argument("--motion-blur", type=int, default=1, help="temporal samples per frame (HD only)")
    ap.add_argument("--grounded-settle", action="store_true", help="bake contact-locked flat-foot standing banks for natural walk")
    ap.add_argument("--no-fx", action="store_true")
    ap.add_argument("--no-frames", action="store_true", help="skip loose per-frame PNGs")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    spec = {}
    if a.character:
        from character_workflow import check_render_input
        from layer_parts import Rejected
        try:
            check_render_input(a.character)
        except (Rejected, OSError, ValueError, KeyError, TypeError) as error:
            sys.exit(f'[rejected] {error}')
        with open(a.character, encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["_dir"] = os.path.dirname(os.path.abspath(a.character))   # for relative part images
    p = dict(PRESETS[a.preset])
    size = a.size or p["size"]
    fps = a.fps or p["fps"]
    pixel = a.pixel or p["pixel"]
    over = parse_overrides(a.fps_override)
    name = spec.get("name", "character")

    clips = build_clips(spec.get("style"), spec.get("custom_clips"), spec.get("clip_key_overrides"), spec.get("gait"),
                        Body.from_spec(spec["body"]) if spec.get("puppet") else None)
    names = list(clips) if a.clips == "all" else [c for c in a.clips.split(",") if c]
    if spec.get('gait', {}).get('carry') and not set(names) <= {'idle', 'run'}:
        sys.exit('source rifle carry is limited to reviewed idle/run; other actions require separate motion work')
    unknown = [c for c in names if c not in clips]
    if unknown:
        sys.exit(f"unknown clips: {unknown}\navailable: {list(clips)}")
    if fps <= 0 or any(value <= 0 for value in over.values()):
        sys.exit('FPS must be positive')
    if 'walk' in names and isinstance(clips['walk'], Gait):
        walk = clips['walk']
        count = frame_count(walk, over.get('walk', fps))
        try:
            walk_hold_phase(walk, count)
        except ValueError as error:
            sys.exit(str(error))

    settle_banks = []
    if a.grounded_settle:
        walk = clips.get('walk')
        if 'walk' not in names or not isinstance(walk, NaturalWalk):
            sys.exit('--grounded-settle requires selected natural_walk_v1 walk')
        count = frame_count(walk, over.get('walk', fps))
        centre = walk_hold_phase(walk, count) * walk.duration
        for side in range(2):
            clock_phase = centre + side * walk.duration / 2
            source_frame = int(math.floor(clock_phase / walk.duration * count + 1e-10))
            sample_time = source_frame * walk.duration / count
            bank_name = 'walk_settle_' + str(side)
            if bank_name in clips:
                sys.exit('reserved grounded settle clip already exists: ' + bank_name)
            bank = GroundedGaitHold(walk, sample_time).settle(.25)
            bank.name = bank_name
            clips[bank_name] = bank
            names.append(bank_name)
            settle_banks.append(dict(clip=bank_name, source_frame=source_frame,
                sample_time_s=sample_time, clock_phase_s=clock_phase, duration_s=bank.duration))

    root = a.out
    if os.path.isdir(root):
        for stale in ('occlusion_review.json', 'occlusion_decisions.json', 'occlusion_decisions_template.json'):
            stale_path = os.path.join(root, stale)
            if os.path.isfile(stale_path):
                os.remove(stale_path)
        for sub in ("frames", "sheets", "engine", "fx"):
            shutil.rmtree(os.path.join(root, sub), ignore_errors=True)
    for sub in ("engine/godot", "engine/cocos", "engine/web", "sheets"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)

    t0 = time.time()
    r = Renderer(spec, size, pixel, motion_blur=a.motion_blur, clips=clips,
                 fit_clips={n: clips[n] for n in names} if a.fit_selected_clips else None)
    print(f"[bake] cloth chains {[d.name for d in r.defs]} in {time.time() - t0:.1f}s")
    unit_px = r.unit
    fit_scope = "exported clips" if a.fit_selected_clips else "every available action"
    print(f"[fit] character scale {r.fit:.3f} to keep {fit_scope} inside the frame")
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
            fps=cfps, loop=c.loop, duration=n / cfps,
            source_duration=c.duration,
            speed_px_s=round(playback_speed(c, cfps, n) * unit_px, 2),
            events=[dict(frame=min(n - 1, int(round(t / step))), name=e) for t, e in c.events],
            next=c.next if not c.loop else None, prev=c.prev,
            chain_frame=int(round(c.chain_at / step)) if c.chain_at else None,
            tags=sorted(c.tags))
        if getattr(c,'frame_multiple',1)>1:
            meta[nm]['frame_multiple'] = c.frame_multiple
        if isinstance(c, Gait) and nm == 'walk':
            # Both the legacy and natural walking loop can retain their phase
            # while braking to a two-foot support frame. Use the baked clock.
            meta[nm]['locomotion'] = dict(profile='natural_walk_v1' if isinstance(c, NaturalWalk) else 'phase_walk_v1',
                period_s=n / cfps, duty=c.duty, speed_px_s=playback_speed(c, cfps, n) * unit_px,
                hold_phase=walk_hold_phase(c, n),
                idle_mode='held_double_support', contact_sampling='baked_frames')
            if settle_banks:
                meta[nm]['locomotion']['settle_banks'] = settle_banks
                meta[nm]['locomotion']['idle_mode'] = 'settled_double_support'
        traces[nm] = rig_trace(c, n, cfps, r.art, unit_px, size)
        print(f"[clip] {nm:<14} {n:>3}f @ {cfps}fps {'loop' if c.loop else 'once'}")

    for bank in settle_banks:
        # Pose-bank registration follows the same discrete clock as the walk;
        # source sample times above are retained only for rendering its pixels.
        walk_fps = meta['walk']['fps']
        bank['sample_time_s'] = bank['source_frame'] / walk_fps
        bank['clock_phase_s'] *= meta['walk']['locomotion']['period_s'] / clips['walk'].duration
        bank['duration_s'] = (len(rendered[bank['clip']]['frames']) - 1) / meta[bank['clip']]['fps']

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
    if any('locomotion' in m for m in meta.values()):
        shutil.copy(os.path.join(SKILL_ROOT, 'assets', 'engine', 'web', 'grounded-walk.html'),
                    os.path.join(root, 'engine', 'web', 'grounded-walk.html'))
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
    # What cut_parts.py found goes along, or a set can pass QA with the cut's warnings left behind.
    bind = {}
    bind_path = os.path.join(spec.get("_dir", ""), "bind_report.json")
    if spec.get("parts") and os.path.isfile(bind_path):
        with open(bind_path, encoding="utf-8") as fh:
            bind = json.load(fh)
    problems = check_parts(spec, r.art.body) if spec.get("parts") else []
    occlusion_candidates = []
    occlusion_summary = None
    if r.art.puppet:
        problems = check_layers(r.art.puppet)
        for nm in names:
            problems += check_motion(r, clips[nm], len(rendered[nm]["frames"]), over.get(nm, fps))
            problems += check_hands(r, spec, clips[nm], rendered[nm]["frames"], over.get(nm, fps))
            problems += check_core(r, clips[nm], rendered[nm]["frames"], over.get(nm, fps))
            problems += check_neck(r, clips[nm], len(rendered[nm]['frames']), over.get(nm, fps))
            if spec.get('puppet', {}).get('connection_skinning') == 'registered_garment_v3':
                problems += check_connections(r, clips[nm], len(rendered[nm]['frames']), over.get(nm, fps))
            if spec.get('puppet', {}).get('attachment_checks', False):
                problems += check_attachments(r, clips[nm], len(rendered[nm]['frames']), over.get(nm, fps))
                occlusion_candidates += clip_candidates(r, clips[nm], len(rendered[nm]['frames']), over.get(nm, fps))
        if spec.get('puppet', {}).get('attachment_checks', False):
            occlusion_summary = write_occlusion_report(root, occlusion_candidates,
                                                       {n:len(rendered[n]['frames']) for n in names})
            print(f"[review] {occlusion_summary['candidates']} occlusion candidates; {occlusion_summary['status']}")
            print(f"[review] {occlusion_summary['check_command']}")
    connection_data = {}
    if r.art.puppet and spec.get('puppet', {}).get('connection_skinning') == 'registered_garment_v3':
        import hashlib
        shutil.copyfile(os.path.join(spec['_dir'],spec['puppet']['source']),os.path.join(root,'binding_reference.png'))
        with open(os.path.join(root,'binding_reference.png'),'rb') as source:
            source_reference_sha256=hashlib.sha256(source.read()).hexdigest()
        connection_data = dict(connection_review_required=True, connections=dict(
            method='registered_garment_surfaces_v3',shape_limits=THIGH_DEFORMATION_LIMITS,
            edge_limits=GARMENT_EDGE_LIMITS,run_limits=ORDINARY_RUN_LIMITS,
            ordinary_run=getattr(r,'ordinary_run_checks',None),
            **({'draw_owners':{layer.name:layer.draw_owner for layer in r.art.puppet.layers if layer.draw_owner}}
               if spec.get('gait',{}).get('carry') else {}),
            source_reference_sha256=source_reference_sha256,
            bindings={name: report for name, (_, _, report) in
                      dict(r.art.puppet.pelvis_bindings,**r.art.puppet.socket_bindings,
                           **{name:(parent,weights,report) for name,(parent,weights,report,_)
                              in r.art.puppet.garment_bindings.items()}).items()},
            clips=r.connection_checks,
            frame_hashes={name: [hashlib.sha256(str((f.shape[1], f.shape[0])).encode()+f.tobytes()).hexdigest()
                                  for f in rendered[name]['frames']] for name in names}))
    with open(os.path.join(root, "rig_trace.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(traces=traces, seams=seams, bones=HUMANOID_BONES,
                       **({'neck_skinning': dict(source_bindings={name:report for name, (_, _, report) in r.art.puppet.neck_bindings.items()},
                                                 clips=getattr(r, 'neck_checks', {}))}
                          if r.art.puppet and r.art.puppet.neck_bindings else {}),
                       **({'portrait_review_required': True} if r.art.puppet else {}),
                       **({"framing_scope": names} if a.fit_selected_clips else {}),
                       part_problems=problems, **connection_data,
                       **({'hand_detail':r.hand_detail_checks} if hasattr(r,'hand_detail_checks') else {}),
                       **({'binding_profile':'side-rifle-carry-v1' if spec.get('gait',{}).get('carry')
                            else 'basic-side-v1'} if connection_data else {}),
                       **({"occlusion_review": occlusion_summary} if occlusion_summary is not None else {}),
                       bind_warnings=bind.get("warnings", []), bind_gaps=bind.get("gaps", {}), clips_total=len(clips),
                       head_size=r.art.body.head_size,
                       locomotion_required=[n for n in names if 'locomotion' in meta[n]],
                       unit_px=unit_px, speeds={n: meta[n]['speed_px_s'] for n in names}), fh)
    if r.art.puppet and spec.get('puppet', {}).get('attachment_checks', False):
        with open(os.path.join(root, 'attachment_scope.json'), 'w', encoding='utf-8') as fh:
            json.dump(dict(method='source_owned_alpha_v1' if spec.get('gait',{}).get('carry') else 'isolated_layer_alpha',
                           **({'draw_owners':{layer.name:layer.draw_owner for layer in r.art.puppet.layers if layer.draw_owner}}
                              if spec.get('gait',{}).get('carry') else {}),
                           parts=['arm_near','arm_far','leg_near','leg_far'],
                           frames={n:len(rendered[n]['frames']) for n in names},
                           scope='root/proximal continuity and parent contact; not semantic appearance'), fh, indent=2)

    export.preview_html(root, os.path.join(SKILL_ROOT, "assets", "preview_template.html"),
                        os.path.join(SKILL_ROOT, "assets", "engine", "web", "sprite-player.js"), doc, fx_doc, name)
    total = sum(len(v["frames"]) for v in rendered.values())
    pages = ", ".join(f"{p['file']} {p['w']}x{p['h']}" for p in files)
    print(f"[done] {len(names)} clips, {total} frames, {len(sprites)} unique, atlas: {pages}, {time.time() - t0:.1f}s")
    print(f"[done] open {os.path.join(root, 'preview.html')}")


if __name__ == "__main__":
    main()
