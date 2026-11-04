#!/usr/bin/env python3
"""Opt-in carriage comparison, not automatic visual approval or a default rig fix.

Search normalized wrist reaches on existing isolated-layer humanoid rigs. Preserve
source art, layer depth, chain lengths, weapon hand, gait timing and swing. Report
walk and both final held poses separately: minimizing detector flags alone can
hide the whole arm or select an unnatural backwards reach. A human must inspect
ordered frames before choosing any candidate. No existing spec is overwritten.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game-sprite-animator/scripts'))
from sprite_anim.motions import build_clips, GroundedGaitSettle
from sprite_anim.rig import Body
from sprite_anim.render import Renderer
from sprite_anim.occlusion_review import frame_metrics, is_candidate

REACHES = (-.45, -.30, -.15, 0., .15, .30, .45)


def clips_for(spec):
    return build_clips(spec.get('style'), spec.get('custom_clips'),
                       spec.get('clip_key_overrides'), spec.get('gait'),
                       Body.from_spec(spec['body']))


def candidate_specs(spec, elbow_mode='source'):
    if spec.get('gait', {}).get('walk', {}).get('profile') != 'natural_walk_v1':
        raise ValueError('requires explicitly selected natural_walk_v1')
    if elbow_mode not in ('source', 'relaxed'):
        raise ValueError('elbow_mode must be source or relaxed')
    walk = clips_for(spec)['walk']
    # Same relaxed elbow cap used by NaturalWalk before explicit overrides.
    elbow = walk.arm_f[2] if elbow_mode == 'source' else min(20., walk.arm_f[2])
    results = []
    for reach in REACHES:
        candidate = copy.deepcopy(spec)
        arm = list(walk._carriage('f', elbow, walk.arm_f[1], walk.arm_f[3], reach))
        candidate['gait']['walk'].update(arm_f=arm, settle_relax_free_arm=True)
        results.append((reach, candidate))
    return results


def summarize(rows):
    if not rows:
        raise ValueError('no far-arm measurements; unsupported or missing art')
    paired = []
    for row in rows:
        values = [row.get('hand_visible_fraction'), row.get('forearm_visible_fraction')]
        if any(v is None or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
            raise ValueError('missing or invalid hand/forearm support')
        paired.append(min(values))
    return dict(frames=len(rows), disconnected_review_candidates=sum(is_candidate(r) for r in rows),
                min_paired_visibility=min(paired), mean_paired_visibility=sum(paired)/len(paired),
                hand_or_forearm_hidden_frames=sum(v < .01 for v in paired), visual_approval='pending')


def evaluate(spec, size=256, samples=20, elbow_mode='source'):
    if type(samples) is not int or samples < 8:
        raise ValueError('at least eight whole-cycle samples required')
    if type(size) is not int or size < 64:
        raise ValueError('size must be an integer of at least 64')
    candidates = candidate_specs(spec, elbow_mode)
    registry, trials = {}, []
    for number, (reach, candidate) in enumerate(candidates):
        walk = clips_for(candidate)['walk']; walk.name = f'carriage_{number}'
        registry[walk.name] = walk
        holds = []
        for bank, phase in enumerate((.05, .55)):
            hold = GroundedGaitSettle(walk, phase*walk.duration).hold()
            hold.name = f'carriage_{number}_hold_{bank}'
            registry[hold.name] = hold; holds.append(hold)
        trials.append((reach, candidate, walk, holds))
    # All candidates share one fit and render resolution for fair pixel comparison.
    renderer = Renderer(spec, size, clips=registry)
    if not renderer.art.puppet:
        raise ValueError('requires an isolated-layer puppet')
    output = []
    for reach, candidate, walk, holds in trials:
        rows = [r for i in range(samples) for r in frame_metrics(renderer,walk,i,samples,24)
                if r['arm'] == 'arm_far']
        hold_rows = [r for hold in holds for r in frame_metrics(renderer,hold,0,2,24)
                     if r['arm'] == 'arm_far']
        output.append(dict(reach_fraction=reach, arm_f=candidate['gait']['walk']['arm_f'],
                           walk=summarize(rows), final_holds=summarize(hold_rows),
                           walk_rows=rows, hold_rows=hold_rows))
    return dict(method='bounded_normalized_reach_comparison', elbow_mode=elbow_mode,
                resolution=size, samples=samples, candidates=output,
                visual_approval='pending', automatic_selection=False,
                limitations='Not identity fitting, semantic hand recognition, motion acceptance or browser playback. Inspect full ordered frames and hold poses; fewer flags can mean a hidden limb or an unnatural reach.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--character',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--elbow',choices=('source','relaxed'),default='source')
    parser.add_argument('--samples',type=int,default=20)
    args=parser.parse_args()
    if args.out.exists():raise ValueError('refusing to overwrite existing comparison')
    source=args.character.resolve(); spec=json.loads(source.read_text());spec['_dir']=str(source.parent)
    report=evaluate(spec,samples=args.samples,elbow_mode=args.elbow)
    report.update(source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x') as f:json.dump(report,f,indent=2)
    print(args.out)


if __name__ == '__main__':main()
