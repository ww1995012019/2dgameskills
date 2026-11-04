"""Opt-in whole-body assembly from reviewed identity landmarks.

Correspondences are fixture evidence, never character-specific constants in code.
All art receives a whole-part similarity. Limb source poses are preserved while
lengths and root-tip axes come from reference chains; no pixels are painted or axes stretched.
This is an experimental assembly, not automatic anatomy or identity recognition.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
from PIL import Image
from atlas_rig import TOP, BOTTOM, landmarks
from head_registration import fit_similarity, rasterize_registered_head


def chain_transform(source, reference, *, preserve_pose=False):
    """Uniform limb fit with a fixed 5% chain-length consistency guard."""
    source, reference = np.asarray(source, float), np.asarray(reference, float)
    if source.shape != (3, 2) or reference.shape != (3, 2) or not np.isfinite([source, reference]).all():
        raise ValueError('chain: need three finite source/reference points')
    lengths = np.linalg.norm(np.diff(source, axis=0), axis=1)
    target = np.linalg.norm(np.diff(reference, axis=0), axis=1)
    if min(*lengths, *target) <= 0:
        raise ValueError('chain: zero length segment')
    scale = float(target.sum()/lengths.sum())
    error = abs(lengths*scale-target)/target.sum()
    if error.max() > .05:
        raise ValueError('chain: incompatible segment proportions (>5% full chain)')
    a, b = source[-1]-source[0], reference[-1]-reference[0]
    if min(np.linalg.norm(a), np.linalg.norm(b)) < 1e-6:
        raise ValueError('chain: coincident root and tip')
    angle = 0. if preserve_pose else math.atan2(b[1],b[0])-math.atan2(a[1],a[0])
    r = np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    return dict(scale=scale, angle=math.degrees(angle), offset=(reference[0]-scale*(r@source[0])).tolist(),
                segment_relative_errors=error.tolist(), pose_policy='source' if preserve_pose else 'reference_axis')


def point(transform, p):
    a=math.radians(transform['angle']);r=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
    return (transform['scale']*(r@np.asarray(p))+transform['offset']).tolist()


def assemble_reference(parts, reference_image, annotations, out):
    """Create a new binder manifest; reject missing contracts and source changes.

    Three rigid parts need >=3 visible correspondences spanning their artwork.
    Hip/waist joint source coordinates and limb reference joints are explicit
    annotations. Visibility is an attestation requiring independent pixel review.
    Source hashes are mandatory. This does not overwrite or promote any old rig.
    """
    parts, reference_image, out = Path(parts), Path(reference_image), Path(out)
    if out.exists(): raise ValueError('output must be a new directory')
    if annotations.get('head_attachment') not in ('cap_cover','socket'):
        raise ValueError('explicit reviewed head_attachment required')
    if not isinstance(annotations.get('name'),str) or not annotations['name'].strip():
        raise ValueError('nonempty character name required')
    def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(reference_image) != annotations['reference_sha256']:
        raise ValueError('reference hash changed')
    front_garment=annotations.get('front_garment')
    if front_garment is not None and front_garment!={'owner':'torso','hips_behind_legs':True}:
        raise ValueError('front garment requires explicit torso ownership and hips behind legs')
    names=(*TOP,*BOTTOM,*(('garment_front',) if front_garment else ()))
    images={}
    for n in names:
        with Image.open(parts/(n+'.png')) as im:
            if im.mode!='RGBA':raise ValueError(n+': source must be RGBA with genuine transparency')
            alpha=np.asarray(im)[...,3]
            if not np.any(alpha==0) or not np.any(alpha>128):raise ValueError(n+': source must be nonempty with transparent background')
            images[n]=im.copy()
    if set(annotations['source_sha256']) != set(images): raise ValueError('all source hashes required')
    for n in images:
        if digest(parts/(n+'.png')) != annotations['source_sha256'][n]: raise ValueError(n+': source hash changed')
    with Image.open(reference_image) as im:
        canvas=im.size
    transforms={};local={n:landmarks(images[n],n) for n in images}
    for n in ('head','torso','hips',*(('garment_front',) if front_garment else ())):
        pairs=annotations['rigid'][n]
        if len(pairs)<3 or any(p.get('visible') is not True or not p.get('label') for p in pairs):
            raise ValueError(n+': labeled visible correspondences required')
        transforms[n]=fit_similarity([p['source'] for p in pairs],[p['reference'] for p in pairs])
    local['hips']={k:np.asarray(annotations['hips_joints'][k],float) for k in ('hip','waist')}
    for k,p in local['hips'].items():
        if p.shape!=(2,) or not np.isfinite(p).all() or np.any(p<0) or np.any(p>=images['hips'].size):
            raise ValueError('hips: finite in-image hip/waist points required')
    if np.linalg.norm(local['hips']['hip']-local['hips']['waist'])<1:
        raise ValueError('hips: distinct hip and waist required')
    for n in ('arm_near','arm_far','leg_near','leg_far'):
        keys=('shoulder','elbow','wrist') if n.startswith('arm') else ('hip','knee','ankle')
        transforms[n]=chain_transform([local[n][k] for k in keys],annotations['chains'][n],preserve_pose=False)
    hand_registration=annotations.get('hand_registration')
    if hand_registration is not None:
        grip=np.asarray(hand_registration.get('point'),float)
        axis=np.asarray(hand_registration.get('axis'),float)
        if grip.shape!=(2,) or axis.shape!=(2,2) or not np.isfinite(grip).all() or not np.isfinite(axis).all() or np.linalg.norm(axis[1]-axis[0])<=0:
            raise ValueError('hand registration requires a finite grip and nonzero axis')
        if np.any(grip<0) or np.any(grip>=images['arm_near'].size):
            raise ValueError('hand grip must lie within its source image')
        local['arm_near']['grip']=grip
    # The head articulation seat follows the reviewed collar, not a cap-cover fit.
    collar=np.mean([p['reference'] for p in annotations['rigid']['torso'] if p['label'].startswith('collar_')],axis=0)
    if collar.shape!=(2,) or not np.isfinite(collar).all(): raise ValueError('two visible collar landmarks required')
    if sum(p['label'].startswith('collar_') for p in annotations['rigid']['torso']) != 2:
        raise ValueError('two visible collar landmarks required')
    # Weapon pose derives from the already-reviewed prior whole weapon transform,
    # expressed relative to the near arm, not a new identity-length claim.
    prior=annotations['weapon_relative_to_arm']; arm=transforms['arm_near']
    if not np.isfinite([prior['length_ratio'],prior['angle_degrees'],*prior['grip']]).all() or prior['length_ratio']<=0:
        raise ValueError('weapon relative transform invalid')
    arm_length=sum(np.linalg.norm(np.asarray(local['arm_near'][b])-local['arm_near'][a]) for a,b in (('shoulder','elbow'),('elbow','wrist')))*arm['scale']
    extent=np.asarray(prior['source_extent'],float)
    if extent.shape!=(2,2) or not np.isfinite(extent).all() or np.linalg.norm(extent[1]-extent[0])<=0:
        raise ValueError('weapon source extent must be two distinct finite points')
    scale=arm_length*prior['length_ratio']/np.linalg.norm(extent[1]-extent[0]);angle=arm['angle']+prior['angle_degrees']
    if hand_registration is not None:
        target_axis=axis[1]-axis[0];source_axis=extent[1]-extent[0]
        angle=arm['angle']+math.degrees(math.atan2(target_axis[1],target_axis[0])-math.atan2(source_axis[1],source_axis[0]))
    weapon=dict(scale=scale,angle=angle,offset=[0.,0.])
    grip=np.asarray(point(arm,local['arm_near']['grip']))
    weapon['offset']=(grip-point(weapon,prior['grip'])).tolist()
    transforms['weapon']=weapon;local['weapon']={'grip':prior['grip']}
    order=annotations['order']
    runtime_names=set(images)-{'garment_front'}
    if len(order)!=len(runtime_names) or set(order)!=runtime_names:raise ValueError('order must contain every runtime source exactly once')
    if front_garment and not all(order.index('hips')<order.index(n)<order.index('torso') for n in ('leg_near','leg_far')):
        raise ValueError('front garment requires hips behind both thighs and torso in front')
    layers={};composite=Image.new('RGBA',canvas);joints={}
    # All fits and clipping checks precede filesystem writes.
    for n in order:
        cropped,offset=rasterize_registered_head(images[n],transforms[n],canvas)
        full=Image.new('RGBA',canvas);full.paste(cropped,tuple(offset));layers[n]=full
        composite.alpha_composite(full);joints[n]={k:point(transforms[n],p) for k,p in local[n].items()}
    if front_garment:
        cropped,offset=rasterize_registered_head(images['garment_front'],transforms['garment_front'],canvas)
        garment=Image.new('RGBA',canvas);garment.paste(cropped,tuple(offset))
        layers['torso'].alpha_composite(garment)
        composite=Image.new('RGBA',canvas)
        for n in order:composite.alpha_composite(layers[n])
    from atlas_rig import lp
    seat_row,seat_columns,_=lp.neck_core(np.asarray(layers['torso'])[...,3]>128)
    joints['head']={'head_base':[float(seat_columns.mean()),float(seat_row)]}
    manifest=dict(name=annotations['name'],canvas=list(canvas),order=order,layers={n:'layers/'+n+'.png' for n in order},joints=joints,head_attachment=annotations['head_attachment'])
    report=dict(transforms=transforms,annotations=annotations,
        method='reviewed_whole_body_reference',visual_approval='pending',new_pixels_painted=0,
        limits=['Source elbow bend retained; root-to-wrist/ankle axes align to reference without local deformation.',
                'Joint annotations may be occluded; visible garment anchors must be reviewed separately.',
                'No identity, garment continuity, motion or production approval.'])
    serialized_manifest=json.dumps(manifest,indent=2,allow_nan=False)+'\n'
    serialized_report=json.dumps(report,indent=2,allow_nan=False)+'\n'
    from garment_ownership import _atomic_publisher
    import tempfile,shutil
    publish=_atomic_publisher()
    out.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.body-assembly-',dir=out.parent))
    try:
        (staging/'layers').mkdir()
        for n,im in layers.items():im.save(staging/'layers'/(n+'.png'))
        composite.save(staging/'assembled.png')
        (staging/'input.json').write_text(serialized_manifest,encoding='utf-8')
        (staging/'reference_assembly.json').write_text(serialized_report,encoding='utf-8')
        publish(staging,out)
    finally:
        if staging.exists():shutil.rmtree(staging)
    return out/'input.json'


PROFILE_KEYS = ('crown', 'chin', 'collar', 'belt', 'pelvis', 'knee_near', 'knee_far', 'sole_near', 'sole_far')


def compare_visible_profile(reference, candidate):
    """Screen reviewed upright composites, not hidden source-part landmarks.

    Every entry is a visible point annotated on the final composite. The common
    body-height normalization is translation/resolution invariant and must not be
    used for different motion poses. The 4% stature and 15% head-ratio limits are
    fixed development diagnostics, never an identity or anatomy approval.
    """
    profiles=[]
    for label, value in (('reference',reference),('candidate',candidate)):
        if set(value) != set(PROFILE_KEYS): raise ValueError(label+': full visible profile required')
        points={}
        for key in PROFILE_KEYS:
            item=value[key]
            if item.get('visible') is not True: raise ValueError(label+': '+key+' must be visible in composite')
            p=np.asarray(item.get('point'),float)
            if p.shape!=(2,) or not np.isfinite(p).all():raise ValueError(label+': finite profile points required')
            points[key]=p
        crown=points['crown'][1];sole=np.mean([points[k][1] for k in ('sole_near','sole_far')]);height=sole-crown
        if height<=0:raise ValueError(label+': upright positive stature required')
        levels={k:float((p[1]-crown)/height) for k,p in points.items()}
        if not (0<levels['chin']<levels['belt']<levels['pelvis']<min(levels['knee_near'],levels['knee_far']) and all(levels['knee_'+side]<levels['sole_'+side] for side in ('near','far'))):
            raise ValueError(label+': invalid upright landmark ordering')
        if not (0<levels['collar']<levels['belt']) or max(levels['sole_near'],levels['sole_far'])-min(levels['sole_near'],levels['sole_far'])>.05:
            raise ValueError(label+': inconsistent upright collar/sole levels')
        profiles.append(levels)
    ref, cand=profiles;deltas={k:abs(cand[k]-ref[k]) for k in PROFILE_KEYS}
    head_ratio_deviation=abs(cand['chin']/ref['chin']-1)
    blockers=[k+': visible level differs by more than 4% stature' for k,d in deltas.items() if d>.04]
    if head_ratio_deviation>.15:blockers.append('head/body ratio differs by more than 15%')
    return dict(reference=ref,candidate=cand,level_deltas=deltas,head_ratio_deviation=head_ratio_deviation,
                blockers=blockers,geometric_screen_pass=not blockers,visual_approval='pending',
                scope='Reviewed upright visible landmarks only; width, attachment and artwork still require review')


def compare_extent(source, reference, transform):
    """Screen a reviewed pair of homologous endpoints under the whole-part fit.

    In particular, matching leg length does not establish boot width. Endpoints
    must describe the same visible extent; this function does not identify them.
    A >15% difference is a diagnostic blocker, not permission for axis scaling.
    """
    source,reference=np.asarray(source,float),np.asarray(reference,float)
    if source.shape!=(2,2) or reference.shape!=(2,2) or not np.isfinite([source,reference]).all():
        raise ValueError('extent: two finite endpoint pairs required')
    scale=transform.get('scale')
    if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not math.isfinite(scale) or scale<=0:
        raise ValueError('extent: positive finite similarity scale required')
    measured=float(np.linalg.norm(source[1]-source[0])*scale);expected=float(np.linalg.norm(reference[1]-reference[0]))
    if min(measured,expected)<=0:raise ValueError('extent: nonzero spans required')
    deviation=abs(measured/expected-1)
    return dict(measured=measured,reference=expected,relative_deviation=deviation,
                diagnostic_pass=deviation<=.15,limit=.15,visual_approval='pending')


def derive_free_arm_carriage(idle, walk, body, samples=32):
    """Preserve reviewed idle's relative free-wrist position in an opt-in walk.

    This returns the existing public arm_f override, not a per-character angle.
    Average a complete idle cycle to remove breathing. The body-relative forward
    wrist reach, normalized by arm chain length, transfers to the relaxed walking
    elbow while retaining the walk's existing swing and elbow-sway magnitudes.
    It cannot guarantee silhouette visibility; pixel review remains necessary.
    """
    if type(samples) is not int or samples<8:raise ValueError('carriage: at least eight whole-cycle samples required')
    upper,lower=body.arm_bones('f');total=upper+lower
    poses=[idle.sample(idle.duration*i/samples) for i in range(samples)]
    forward=[]
    for p in poses:
        a=math.radians(p['arm_f_up']-p['pelvis']-p['spine']);b=a+math.radians(p['arm_f_lo'])
        forward.append((upper*math.sin(a)+lower*math.sin(b))/total)
    reach=float(np.mean(forward))
    if not math.isfinite(reach) or abs(reach)>.5:
        raise ValueError('carriage: reviewed idle reach outside relaxed walking contract')
    elbow,swing,sway=walk.arm_f[2],walk.arm_f[1],walk.arm_f[3]
    result=walk._carriage('f',elbow,swing,sway,reach)
    return list(result),dict(method='whole_idle_cycle_relative_wrist_reach',samples=samples,
                            forward_reach_fraction=reach,arm_f=list(result),visual_approval='pending')
