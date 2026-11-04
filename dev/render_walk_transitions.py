#!/usr/bin/env python3
"""Render a phase-aware locomotion proof; report drift rather than imply foot locking."""
import argparse
import bisect
import json
import math
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game-sprite-animator/scripts'))
from sprite_anim.motions import GroundedGaitRamp, GroundedGaitHold, GroundedGaitSettle, Proc, build_clips
from sprite_anim.render import Renderer, to_u8
from sprite_anim.rig import Body, solve, heel_world, toe_world
from walk_transition_diagnostic import PhaseTransition, bind_idle, transition_from, transition_to


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--character', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--mode', choices=('grounded', 'settled', 'blend'), default='grounded')
    args = ap.parse_args()
    path = Path(args.character).resolve()
    spec = json.loads(path.read_text()); spec['_dir'] = str(path.parent)
    spec.setdefault('gait', {}).setdefault('walk', {})['profile'] = 'natural_walk_v1'
    body = Body.from_spec(spec['body'])
    clips = build_clips(spec.get('style'), spec.get('custom_clips'), spec.get('clip_key_overrides'), spec['gait'], body)
    idle, walk = clips['idle'], clips['walk']
    segments = []
    def add(label, duration, clip, offset):
        segments.append(dict(label=label, duration=duration, clip=clip, offset=offset))
    if args.mode == 'blend':
        bind_idle(idle, body)
        add('idle', .4, idle, .27)
        start = transition_from(walk, idle, .67, .17, .3)
        add('start', .3, start, 0.)
        add('walk', .7, walk, .47)
        stop = transition_to(walk, idle, 1.17, .11, .3)
        add('stop', .3, stop, 0.)
        add('idle', .45, idle, .41)
        restart = transition_from(walk, idle, .86, .39, .3)
        add('restart', .12, restart, 0.)
        reverse = PhaseTransition(restart, idle, body, .12, .98, .3)
        add('reverse command', .3, reverse, 0.)
        add('idle', .4, idle, 1.28)
    else:
        hold = walk.standing()
        if args.mode == 'settled':
            flat = hold.settle().hold()
            add('settled locomotion idle', .4, flat, 0.)
            unsettle = flat.resume()
            add('restore gait stance', unsettle.duration, unsettle, 0.)
            start = unsettle.resume(.3)
        else:
            add('locomotion idle', .4, hold, 0.)
            start = hold.resume(.3)
        add('grounded start', start.duration, start, 0.)
        phase = start.phase_time(start.duration)
        add('walk', .73, walk, phase)
        stop = walk.stop(phase+.73)
        add('grounded stop', stop.duration, stop, 0.)
        if args.mode == 'settled':
            settle = stop.hold().settle()
            add('settle heels', settle.duration, settle, 0.)
            flat = settle.hold()
            add('settled locomotion idle', .45, flat, 0.)
            unsettle = flat.resume()
            add('restore gait stance', unsettle.duration, unsettle, 0.)
            restart = unsettle.resume(.3)
        else:
            add('locomotion idle', .45, stop.hold(), 0.)
            restart = stop.resume(.3)
        add('grounded resume', restart.duration, restart, 0.)
        phase = restart.phase_time(restart.duration)
        add('walk', .37, walk, phase)
        stop2 = walk.stop(phase+.37)
        add('grounded stop again', stop2.duration, stop2, 0.)
        if args.mode == 'settled':
            settle = stop2.hold().settle()
            add('settle heels again', settle.duration, settle, 0.)
            add('settled locomotion idle', .4, settle.hold(), 0.)
        else:
            add('locomotion idle', .4, stop2.hold(), 0.)
    edges = np.cumsum([0.] + [s['duration'] for s in segments]).tolist()
    def at(t):
        i = max(0, min(len(segments)-1, bisect.bisect_right(edges, t)-1))
        s = segments[i]
        return s, t-edges[i]+s['offset']
    def travel(clip, t):
        return clip.displacement(t) if isinstance(clip, GroundedGaitRamp) else clip.speed*t
    roots = [0.]
    for s in segments:
        roots.append(roots[-1]+travel(s['clip'], s['offset']+s['duration'])-travel(s['clip'], s['offset']))
    def root_at(t):
        i = max(0, min(len(segments)-1, bisect.bisect_right(edges, t)-1))
        s = segments[i]
        return roots[i]+travel(s['clip'], t-edges[i]+s['offset'])-travel(s['clip'], s['offset'])
    seq = Proc('transition_proof', edges[-1], lambda t: at(t)[0]['clip'].sample(at(t)[1]), loop=False, tags=('ground',))
    seq.vel = lambda t: at(t)[0]['clip'].vel(at(t)[1])
    renderer = Renderer(spec, 512, clips={seq.name: seq})
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out/'frames').mkdir(exist_ok=True)
    frames, records = [], []
    root = 0.; previous_vel = seq.vel(0)[0]; previous_t = 0.
    for frame, t in enumerate(np.linspace(0, seq.duration, round(seq.duration*args.fps)+1)):
        t = float(t); segment, elapsed = at(t); clip = segment['clip']
        velocity = seq.vel(t)[0]
        root += .5*(previous_vel+velocity)*(t-previous_t)
        previous_vel, previous_t = velocity, t
        if args.mode != 'blend': root = root_at(t)
        sk = solve(seq.sample(t), body)
        feet = {}
        for side in 'nf':
            heel, toe = heel_world(sk, side), toe_world(sk, side)
            feet[side] = dict(heel_world=[heel[0]+root, heel[1]], toe_world=[toe[0]+root, toe[1]],
                              sole_height=min(heel[1], toe[1]))
        contact = clip.contacts(elapsed)
        record = dict(contact_validation='analytic' if args.mode != 'blend' else 'not_applicable_pose_blend', contacts=contact, frame=frame, time=t, stage=segment['label'], root_displacement=root,
                      root_speed=velocity, feet=feet)
        if isinstance(clip, PhaseTransition):
            record.update(source=clip.source.name, target=clip.target.name,
                          source_time=clip.source_time+elapsed, target_time=clip.target_time+elapsed,
                          source_phase=(clip.source_time+elapsed)/clip.source.duration%1,
                          target_phase=(clip.target_time+elapsed)/clip.target.duration%1,
                          target_weight=clip._weight(elapsed))
        elif isinstance(clip, GroundedGaitRamp):
            record.update(source='walk', source_time=clip.phase_time(elapsed),
                          source_phase=clip.phase_time(elapsed)/walk.duration%1, phase_rate=clip.phase_rate(elapsed))
        elif isinstance(clip, (GroundedGaitHold, GroundedGaitSettle)):
            record.update(source='walk', source_time=clip.phase_time,
                          source_phase=clip.phase_time/walk.duration%1, phase_rate=0.)
        else:
            record.update(source=clip.name, source_time=elapsed, source_phase=elapsed/clip.duration%1)
        if args.mode != 'blend':
            eps = 1e-6
            after = solve(seq.sample(t+eps), body)
            segment_after, elapsed_after = at(t+eps)
            after_contacts = segment_after['clip'].contacts(elapsed_after)
            drift = []
            for side in 'nf':
                if contact.get(side) and after_contacts.get(side):
                    point = min((heel_world,toe_world),key=lambda fn:fn(sk,side)[1])
                    p,q=point(sk,side),point(after,side)
                    drift.append(abs(q[0]+root_at(t+eps)-p[0]-root_at(t))/eps)
            record['max_planted_drift_units_per_s']=max(drift,default=None)
        records.append(record)
        image = Image.fromarray(to_u8(renderer.render(seq, t)))
        image.save(out/'frames'/f'{frame:03d}.png')
        # Scrolling ground grid shows actual integrated root travel while the
        # camera follows the character. No image crossfade or optical flow.
        canvas = Image.new('RGBA', (512, 552), '#e3e7ec')
        draw = ImageDraw.Draw(canvas); y = round(512*.86)
        for x in range(-512, 1024, 40):
            gx = int(x-root*renderer.unit)%552-20
            draw.line((gx,y,gx+18,y+10), fill='#8e97a3')
        draw.line((0,y,512,y), fill='#8e97a3')
        canvas.alpha_composite(image)
        draw.text((12,516), f'{segment["label"]} | t={t:.2f}s | root={root:.2f}', fill='black')
        draw.text((12,534), ('Grounded phase clock; '+('settled flat feet' if args.mode == 'settled' else 'held gait idle') if args.mode != 'blend' else 'Pose blend: continuous seams; foot locking NOT guaranteed'), fill='black')
        frames.append(canvas.convert('RGB'))
    frames[0].save(out/'proof.gif', save_all=True, append_images=frames[1:], duration=round(1000/args.fps), loop=0)
    metrics = {}
    for stage in dict.fromkeys(r['stage'] for r in records):
        rows = [r for r in records if r['stage']==stage]
        grounded_drift = []
        for a,b in zip(records, records[1:]):
            if a['stage'] != stage or b['stage'] != stage: continue
            for side in 'nf':
                for point in ('heel_world','toe_world'):
                    p,q = a['feet'][side][point],b['feet'][side][point]
                    if abs(p[1]) <= .05 and abs(q[1]) <= .05:
                        grounded_drift.append(abs(q[0]-p[0])/(b['time']-a['time']))
        metrics[stage] = dict(min_sole_height=min(r['feet'][s]['sole_height'] for r in rows for s in 'nf'),
                             max_sole_height=max(r['feet'][s]['sole_height'] for r in rows for s in 'nf'),
                             max_near_ground_drift_units_per_s=max(grounded_drift,default=None),
                             near_ground_intervals=len(grounded_drift),
                             max_planted_drift_units_per_s=max((r.get('max_planted_drift_units_per_s') or 0. for r in rows),default=None) if args.mode != 'blend' else None)
    (out/'trace.json').write_text(json.dumps(dict(mode=args.mode, contact_validation='analytic' if args.mode != 'blend' else 'not_applicable_pose_blend', unit_px=renderer.unit, records=records, metrics=metrics), indent=2))
    contact = Image.new('RGB',(512*4,552*2),'white')
    for i,t in enumerate(np.linspace(0, seq.duration, 8)):
        contact.paste(frames[min(len(frames)-1,round(t*args.fps))],(i%4*512,i//4*552))
    contact.save(out/'contact-sheet.jpg')
    print(json.dumps(metrics,indent=2))


if __name__ == '__main__': main()
