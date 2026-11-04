"""Output-bound screen-space arm readability review gate for opted-in humanoids.

Physical layer continuity and human-readable overlap are different questions.
These measurements identify material for visual review; they never reject a pose,
change its depth order, or treat an intentionally hidden limb as broken.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from .integrity import components

# Conservative review-candidate selection, NOT physical failure thresholds.
MIN_HAND_SHARE = .20
MIN_VISIBLE_HAND_PIXELS = 4.
MIN_SOURCE_HAND_PIXELS = 8.
MAX_FOREARM_SHARE = .25
MIN_OPAQUE_FOREARM_SHARE = .65
OPAQUE_TRANSMITTANCE = .05
REPORT = 'occlusion_review.json'
DECISIONS = 'occlusion_decisions.json'


def visibility_metrics(layers, arm, hand_region, forearm_region):
    """layers is back-to-front [(name, normalized alpha)], using identical grids.

    Regions are supplied independently of colour. A source-tagged hand mask is
    preferable for unusual shapes; frame_metrics uses wrist-relative geometry for
    the supported humanoid hand/forearm setup and returns that limitation.
    """
    names = [name for name, _ in layers]
    index = names.index(arm)
    alpha = np.asarray(layers[index][1], float)
    if alpha.ndim != 2 or not np.isfinite(alpha).all() or np.any((alpha < 0) | (alpha > 1)):
        raise ValueError('arm alpha must be a finite normalized 2D array')
    hand, forearm = np.asarray(hand_region, bool), np.asarray(forearm_region, bool)
    if hand.shape != alpha.shape or forearm.shape != alpha.shape:
        raise ValueError('regions and layer alphas must use the same pixel grid')
    transmittance = np.ones_like(alpha)
    contributions = {}
    isolated_forearm = float(alpha[forearm].sum())
    # Attribute each hidden pixel to its frontmost covering material. This is
    # not a causal removal test: a duplicate torso underneath can still hide it.
    for name, cover in reversed(layers[index + 1:]):
        cover = np.asarray(cover, float)
        if cover.shape != alpha.shape or not np.isfinite(cover).all() or np.any((cover < 0) | (cover > 1)):
            raise ValueError('layer alpha must be finite, normalized and on the same grid')
        removed = alpha * transmittance * cover
        mass = float(removed[forearm].sum())
        if mass:
            contributions[name] = mass / max(isolated_forearm, 1e-12)
        transmittance *= 1 - cover
    visible = alpha * transmittance

    def connected(mask):
        labels = components(mask)
        h = set(np.unique(labels[hand])) - {0}
        f = set(np.unique(labels[forearm])) - {0}
        return bool(h & f)

    def fraction(region):
        mass = float(alpha[region].sum())
        return float(visible[region].sum()) / mass if mass else None

    return dict(arm=arm, isolated_hand_mass=float(alpha[hand].sum()),
                visible_hand_mass=float(visible[hand].sum()),
                visible_hand_pixels=int((hand & (visible > .5)).sum()),
                hand_visible_fraction=fraction(hand), forearm_visible_fraction=fraction(forearm),
                isolated_hand_forearm_connected=connected(alpha > .5),
                visible_hand_forearm_connected={str(cut): connected(visible > cut) for cut in (.1, .25, .5)},
                forearm_opaque_occlusion_fraction=float(alpha[forearm & (transmittance <= OPAQUE_TRANSMITTANCE)].sum()) / max(isolated_forearm, 1e-12),
                forearm_occluders=contributions)


def arm_regions(shape, wrist, elbow, radius):
    """Wrist-distal hand and middle forearm regions for ordinary humanoid limbs.

    This is not semantic hand segmentation. Wide sleeves, folded overlaps or
    unusual robot appendages require source-tagged material regions instead.
    """
    wrist, elbow = np.asarray(wrist, float), np.asarray(elbow, float)
    length = float(np.linalg.norm(wrist - elbow))
    if length <= 1e-8:
        raise ValueError('forearm needs distinct elbow and wrist')
    direction = (wrist - elbow) / length
    yy, xx = np.indices(shape)
    x, y = xx - wrist[0], yy - wrist[1]
    along = x * direction[0] + y * direction[1]
    across = -x * direction[1] + y * direction[0]
    hand = (along >= 0) & (x*x + y*y < (.65 * length)**2)
    forearm = (along >= -.65*length) & (along <= -.30*length) & (np.abs(across) <= radius*1.5)
    return hand, forearm


def frame_metrics(renderer, clip, index, count, fps):
    """Measure one frame at the renderer's actual supersampling, in its layer order."""
    from sprite_anim.art import Canvas
    from sprite_anim.rig import full_pose, solve
    from sprite_anim.render import GROUND_FRAC, frame_time
    from sprite_anim.puppet import raster
    puppet = renderer.art.puppet
    cv = Canvas(renderer.size, renderer.ss, renderer.unit, GROUND_FRAC, 1, False, (0,0,0))
    t = frame_time(clip, index, count, fps)
    pose = full_pose(clip.sample(t)); sk = solve(pose, renderer.art.body)
    cv.set_squash(pose['squash'], 0.)
    scale = cv.s / puppet.px_per_unit
    layers = list(puppet.meshes(cv, sk, renderer.cloth_at(clip,t), 'ground' in clip.tags))
    result = []
    for position, (layer, vertices) in enumerate(layers):
        if layer.name not in ('arm_near','arm_far'):
            continue
        # Preserve the entire arm alpha support, not merely the wrist ROI: a
        # visible sleeve path may leave the local wrist region and return.
        used = vertices[layer.used]
        lo = np.floor(used.min(0)).astype(int) - 2
        hi = np.ceil(used.max(0)).astype(int) + 3
        x0,y0 = max(0,int(lo[0])),max(0,int(lo[1]))
        x1,y1 = min(cv.w,int(hi[0])),min(cv.h,int(hi[1]))
        if x1 <= x0 or y1 <= y0:
            continue
        offset = np.array([x0,y0]); width,height=x1-x0,y1-y0
        alphas = [(part.name,raster(part,verts-offset,puppet.mip(part,scale),width,height)[...,3])
                  for part,verts in layers[position:]]
        side = 'n' if layer.name == 'arm_near' else 'f'
        hand,forearm=arm_regions((height,width),np.array(cv.T(sk['wr_'+side]))-offset,
                                np.array(cv.T(sk['el_'+side]))-offset,layer.radius*scale)
        row=visibility_metrics(alphas,layer.name,hand,forearm)
        row.update(clip=clip.name,frame=index,supersampling=renderer.ss,
                   region_method='wrist_relative_humanoid_geometry',
                   interpretation='review candidate only; occlusion is not a physical tear')
        result.append(row)
    return result


def is_candidate(row):
    """Material hand remains while opaque foreground hides most middle forearm.

    Neither a translucent cloth nor a nearly hidden/tiny hand is sufficient.
    Connectivity alone is insufficient: a one-pixel bridge can still read poorly.
    """
    scale = row.get('supersampling', 1) ** 2
    hand, forearm = row.get('hand_visible_fraction'), row.get('forearm_visible_fraction')
    return bool(row.get('isolated_hand_forearm_connected') and hand is not None and forearm is not None
                and hand >= MIN_HAND_SHARE and forearm <= MAX_FOREARM_SHARE
                and row.get('visible_hand_mass',0) / scale >= MIN_VISIBLE_HAND_PIXELS
                and row.get('isolated_hand_mass',0) / scale >= MIN_SOURCE_HAND_PIXELS
                and row.get('forearm_opaque_occlusion_fraction',0) >= MIN_OPAQUE_FOREARM_SHARE)


def clip_candidates(renderer,clip,count,fps):
    return [row for i in range(count) for row in frame_metrics(renderer,clip,i,count,fps) if is_candidate(row)]


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_report(root, candidates, frames):
    root=Path(root)
    assets={'animations.json':_file_hash(root/'animations.json')}
    for clip in frames:
        relative='sheets/'+clip+'.png'
        assets[relative]=_file_hash(root/relative)
    output_hash=_digest(assets)
    entries=[]
    for row in candidates:
        relative='sheets/'+row['clip']+'.png'
        entries.append(dict(row,id=f"{row['clip']}:{row['frame']}:{row['arm']}",
                            asset=relative,asset_sha256=assets[relative],status='review_required'))
    report=dict(version=1,status='review_required' if entries else 'no_candidates',
                output_hash=output_hash,assets=assets,frames=frames,
                candidates=entries,scope='All exported frame timestamps before motion blur/FX; humanoid wrist-relative hand/mid-forearm visibility only. Not general semantic detection or physical failure.',
                thresholds=dict(min_hand_share=MIN_HAND_SHARE,min_visible_hand_pixels=MIN_VISIBLE_HAND_PIXELS,
                    min_source_hand_pixels=MIN_SOURCE_HAND_PIXELS,max_forearm_share=MAX_FOREARM_SHARE,
                    min_opaque_forearm_share=MIN_OPAQUE_FOREARM_SHARE,opaque_transmittance=OPAQUE_TRANSMITTANCE),
                review_command=f'python scripts/review_occlusion.py {root}',
                check_command=f'python scripts/review_occlusion.py {root} --check')
    report['report_id']=_digest(report)
    (root/REPORT).write_text(json.dumps(report,indent=2),encoding='utf-8')
    # Re-generation does not inherit previous acceptance, even when a filename is reused.
    (root/DECISIONS).unlink(missing_ok=True)
    template=dict(reviewer='',report_id=report['report_id'],output_hash=output_hash,
                  decisions=[dict(id=c['id'],verdict='pending',rationale='',asset_sha256=c['asset_sha256']) for c in entries])
    (root/'occlusion_decisions_template.json').write_text(json.dumps(template,indent=2),encoding='utf-8')
    return dict(report=REPORT,status=report['status'],candidates=len(entries),frames_checked=sum(frames.values()),
                report_id=report['report_id'],output_hash=output_hash,check_command=report['check_command'])


def _current_report(root):
    root=Path(root);report=json.loads((root/REPORT).read_text(encoding='utf-8'))
    unsigned={k:v for k,v in report.items() if k!='report_id'}
    if report.get('report_id')!=_digest(unsigned):raise ValueError('report contents changed; regenerate')
    if not report.get('assets') or _digest(report['assets'])!=report.get('output_hash'):
        raise ValueError('invalid output hash')
    trace_path=root/'rig_trace.json'
    if trace_path.exists():
        trace=json.loads(trace_path.read_text(encoding='utf-8'))
        summary=trace.get('occlusion_review')
        if 'occlusion_review' in trace and (not isinstance(summary,dict) or
                summary.get('report_id')!=report['report_id'] or summary.get('output_hash')!=report['output_hash']):
            raise ValueError('report differs from the exported trace summary')
    for relative,digest in report['assets'].items():
        path=root/relative
        if path.resolve().parent!=root.resolve() and root.resolve() not in path.resolve().parents:
            raise ValueError('asset path leaves output directory')
        if _file_hash(path)!=digest:raise ValueError('stale output asset: '+relative)
    return report


def _validate_decisions(report,decisions):
    if decisions.get('report_id')!=report['report_id'] or decisions.get('output_hash')!=report['output_hash']:
        raise ValueError('decisions refer to different output/report')
    if not isinstance(decisions.get('reviewer'),str) or not decisions['reviewer'].strip():
        raise ValueError('reviewer is required')
    expected={c['id']:c for c in report['candidates']};rows=decisions.get('decisions')
    if not isinstance(rows,list) or len(rows)!=len(expected):raise ValueError('every candidate needs one decision')
    seen=set()
    for row in rows:
        ident=row.get('id')
        if ident not in expected or ident in seen:raise ValueError('unknown or duplicate candidate')
        seen.add(ident)
        if row.get('verdict') not in ('accepted','rejected'):raise ValueError('each candidate needs accepted/rejected')
        if not isinstance(row.get('rationale'),str) or not row['rationale'].strip():raise ValueError('visual rationale is required')
        if row.get('asset_sha256')!=expected[ident]['asset_sha256']:raise ValueError('candidate asset hash differs')
    return all(row['verdict']=='accepted' for row in rows)


def record(root,path):
    root=Path(root)
    try:
        report=_current_report(root);decisions=json.loads(Path(path).read_text(encoding='utf-8'))
        accepted=_validate_decisions(report,decisions)
        (root/DECISIONS).write_text(json.dumps(decisions,indent=2),encoding='utf-8')
        print('occlusion review: decisions recorded; '+('accepted' if accepted else 'rejected candidates remain'))
        return 0 if accepted else 1
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
        print('occlusion review: '+str(error));return 1


def check_current(root):
    root=Path(root)
    try:
        if not (root/REPORT).exists():
            trace=root/'rig_trace.json'
            if trace.exists() and 'occlusion_review' in json.loads(trace.read_text()):
                raise ValueError('missing report for opted-in output')
            return 0
        report=_current_report(root)
        if not report['candidates']:
            print('occlusion review: no candidates in measured scope; not semantic approval');return 0
        if not (root/DECISIONS).exists():raise ValueError('review_required; inspect candidate sheets and record decisions')
        accepted=_validate_decisions(report,json.loads((root/DECISIONS).read_text(encoding='utf-8')))
        if not accepted:raise ValueError('rejected candidates remain')
        print('occlusion review: current per-candidate decisions accepted');return 0
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
        print('occlusion review: '+str(error));return 1


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root')
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--check',action='store_true');mode.add_argument('--record')
    args=parser.parse_args()
    if args.check:return check_current(args.root)
    if args.record:return record(args.root,args.record)
    try:report=_current_report(args.root)
    except (OSError,ValueError,TypeError,KeyError) as error:print('occlusion review: '+str(error));return 1
    for c in report['candidates']:
        print(f"{c['id']}: {c['asset']} SHA256={c['asset_sha256']} hand={c['hand_visible_fraction']:.1%} forearm={c['forearm_visible_fraction']:.1%}; inspect this frame visually")
    print('Fill occlusion_decisions_template.json with a named reviewer, accepted/rejected and visual rationale, then use --record FILE.')
    return check_current(args.root)
