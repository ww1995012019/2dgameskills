"""Reviewed source/reference landmark registration, not semantic landmark detection.

Fit both complete parts to the same identity reference. Keep the torso's existing
similarity transform and derive the head's whole-part similarity from that common
frame. Never fit a head by covering garment pixels or resizing only its neck.
"""
import math
import numpy as np


def fit_similarity(source, reference):
    """Fit at least three noncollinear reviewed pairs; reject >5% span residual.

    The fixed relative guard is shared across resolutions. It measures geometric
    consistency only, not landmark correctness, identity, or animation quality.
    """
    source, reference = np.asarray(source, float), np.asarray(reference, float)
    if (source.ndim != 2 or source.shape[1:] != (2,) or len(source) < 3
            or reference.shape != source.shape or not np.isfinite(source).all()
            or not np.isfinite(reference).all()):
        raise ValueError('registration: need at least three finite paired 2D landmarks')
    x, y = source-source.mean(0), reference-reference.mean(0)
    if min(np.linalg.svd(x, compute_uv=False)) < np.linalg.norm(x)*.05 or min(np.linalg.svd(y, compute_uv=False)) < np.linalg.norm(y)*.05:
        raise ValueError('registration: landmarks must span a noncollinear region')
    u, singular, vt = np.linalg.svd(x.T@y)
    correction = np.eye(2); correction[-1,-1] = np.linalg.det(vt.T@u.T)
    rotation = vt.T@correction@u.T
    scale = float(np.sum(singular*np.diag(correction))/np.sum(x*x))
    if scale <= 0:
        raise ValueError('registration: invalid similarity scale')
    offset = reference.mean(0)-scale*(rotation@source.mean(0))
    residuals = np.linalg.norm(scale*(source@rotation.T)+offset-reference, axis=1)
    span = float(np.max(np.linalg.norm(reference[:,None]-reference[None,:],axis=-1)))
    report = dict(scale=scale, angle=math.degrees(math.atan2(rotation[1,0],rotation[0,0])),
                  offset=offset.tolist(), residuals=residuals.tolist(), reference_span=span,
                  max_relative_residual=float(residuals.max()/span), limit=.05)
    if residuals.max() > span*.05:
        raise ValueError(f"registration: inconsistent landmarks ({residuals.max()/span:.3%} span residual > 5%)")
    return report


def register_head(head_source, head_reference, torso_source, torso_reference, *, torso_transform):
    """Return absolute head similarity in the torso's assembly coordinate frame.

    Input coordinates refer to original uncropped source images and the SAME
    reference image. Callers retain these reviewed landmarks and image hashes.
    Whole-head size comes from identity geometry, never a seam coverage search.
    """
    h=fit_similarity(head_source,head_reference)
    t=fit_similarity(torso_source,torso_reference)
    try:
        ts=float(torso_transform['scale']);ta=float(torso_transform['angle']);to=np.asarray(torso_transform['offset'],float)
    except (KeyError,TypeError,ValueError) as error:
        raise ValueError('registration: invalid torso transform') from error
    if ts<=0 or to.shape!=(2,) or not np.isfinite([ts,ta,*to]).all():
        raise ValueError('registration: invalid torso transform')
    a=math.radians(ta-t['angle']);r=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
    factor=ts/t['scale']
    offset=to+factor*(r@(np.array(h['offset'])-t['offset']))
    return dict(scale=factor*h['scale'],angle=ta+h['angle']-t['angle'],offset=offset.tolist(),
                method='reviewed_common_reference_similarity',head_fit=h,torso_fit=t,
                visual_approval='pending',validation_scope='landmark geometry only')


def _registered_placement(image, transform, canvas):
    """Validate the similarity and locate every nontransparent source pixel."""
    if image.mode!='RGBA' or not image.getbbox():
        raise ValueError('registration: nonempty RGBA source required')
    try:
        s=float(transform['scale']);a=math.radians(float(transform['angle']));o=np.asarray(transform['offset'],float)
    except (KeyError,TypeError,ValueError) as error:
        raise ValueError('registration: invalid head transform') from error
    if len(canvas)!=2 or any(type(n) is not int or n<1 for n in canvas):
        raise ValueError('registration: canvas must contain two positive integer dimensions')
    if s<=0 or o.shape!=(2,) or not np.isfinite([s,a,*o]).all():
        raise ValueError('registration: invalid head transform')
    r=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
    # Exact quarter turns should not darken pixels through floating-point
    # interpolation just below integer sample centers.
    r[np.abs(r)<1e-14]=0.
    ys,xs=np.nonzero(np.asarray(image)[...,3]);placed=s*(np.column_stack((xs,ys))@r.T)+o
    return s, r, o, placed


def rasterize_registered_head(image, transform, canvas):
    """Rasterize once, rejecting any art outside the interpolation safety guard."""
    from PIL import Image
    s, r, o, placed = _registered_placement(image, transform, canvas)
    if np.any(placed.min(0)<3) or np.any(placed.max(0)>np.asarray(canvas)-4):
        raise ValueError('registration: source art would clip canvas')
    inverse=r.T/s;shift=-inverse@o
    full=image.transform(tuple(canvas),Image.Transform.AFFINE,
                         (inverse[0,0],inverse[0,1],shift[0]+.5-.5*inverse[0].sum(),inverse[1,0],inverse[1,1],shift[1]+.5-.5*inverse[1].sum()),
                         Image.Resampling.BICUBIC)
    box=full.getbbox()
    return full.crop(box),list(box[:2])


def translate_source_frame(puppet, shift):
    """Translate a supported known-joint puppet, leaving local vectors unchanged.

    Strict field allowlists deliberately reject future coordinate constructs.
    Cropped images remain byte-identical; their offsets move with the frame.
    This is not a general cloth/chain or arbitrary manifest migration.
    """
    import copy
    value = copy.deepcopy(puppet)
    shift = np.asarray(shift, dtype=float)
    if shift.shape != (2,) or not np.isfinite(shift).all() or np.any(shift != np.round(shift)):
        raise ValueError('registration: source-frame shift must be two finite integers')
    def fields(obj, allowed, label):
        unknown = set(obj) - set(allowed.split())
        if unknown:
            raise ValueError(f'registration: unsupported {label} fields: {sorted(unknown)}')
    def point(p):
        p = np.asarray(p, dtype=float)
        if p.shape != (2,) or not np.isfinite(p).all():
            raise ValueError('registration: source coordinate must be a finite 2D point')
        return (p + shift).tolist()
    fields(value, 'px_per_unit joints rest_angles skirt_len robe_len core_radius rest_arm layers chains source weapon_length weapon_back head_attachment attachment_checks', 'puppet')
    if value.get('chains'):
        raise ValueError('registration: source-frame padding does not support chains')
    value['joints'] = {k: point(p) for k, p in value.get('joints', {}).items()}
    if 'rest_arm' in value:
        value['rest_arm'] = {k: [point(p) for p in points] for k, points in value['rest_arm'].items()}
    for name, layer in value['layers'].items():
        fields(layer, 'kind image offset anchor follow rest bones radius source_frame root_lock tip_lock foot', f'layer {name}')
        if layer.get('kind') not in ('rigid', 'tube'):
            raise ValueError('registration: source-frame padding supports only rigid/tube layers')
        layer['offset'] = point(layer.get('offset', [0, 0]))
        if 'anchor' in layer: layer['anchor'] = point(layer['anchor'])
        if 'rest' in layer: layer['rest'] = [point(p) for p in layer['rest']]
        if 'foot' in layer:
            fields(layer['foot'], 'side ankle shin_dir blend width rest_angle', f'foot {name}')
            layer['foot']['ankle'] = point(layer['foot']['ankle'])
    return value


def create_reference_candidate(source_rig, output, source_head, *, landmarks, torso_transform, canvas, pad_canvas=False):
    """Create a new head version; optionally rebase the entire source canvas.

    Existing rigs are never overwritten. Anatomy, motions, garment and other
    layer pixels are preserved. Padding translates source-space coordinates only;
    body dimensions, directions and motion are unchanged. Fit landmarks remain in
    their original reviewed frame. A numeric fit is not a visual approval.
    """
    import hashlib,json,shutil
    from pathlib import Path
    from PIL import Image
    source_rig,output,source_head=Path(source_rig),Path(output),Path(source_head)
    if output.exists():
        raise ValueError('registration: output must be a new version directory')
    if source_rig.resolve() in output.resolve().parents:
        raise ValueError('registration: output must not be inside source rig')
    spec=json.loads((source_rig/'character.json').read_text())
    layer=spec['puppet']['layers']['head']
    if layer.get('kind')!='rigid':
        raise ValueError('registration: reference candidate requires a rigid head layer')
    result=register_head(**landmarks,torso_transform=torso_transform)
    with Image.open(source_head) as original:
        original = original.convert('RGBA')
        if pad_canvas:
            _, _, _, placed = _registered_placement(original, result, canvas)
            before = list(canvas)
            low = np.maximum(0, np.ceil(3 - placed.min(0))).astype(int)
            high = np.maximum(0, np.ceil(placed.max(0) + 4 - np.asarray(canvas))).astype(int)
            # Keep complete old image rectangles, including transparent margins.
            # Do not silently crop unrelated art already outside the old canvas.
            for old_layer in spec['puppet']['layers'].values():
                at = np.asarray(old_layer.get('offset', [0, 0]), dtype=float)
                if at.shape != (2,) or not np.isfinite(at).all() or np.any(at != np.round(at)):
                    raise ValueError('registration: padding requires integer layer offsets')
                with Image.open(source_rig / old_layer['image']) as old_image:
                    low = np.maximum(low, np.maximum(0, -at).astype(int))
                    high = np.maximum(high, np.maximum(0, at + old_image.size - np.asarray(canvas)).astype(int))
            spec['puppet'] = translate_source_frame(spec['puppet'], low)
            layer = spec['puppet']['layers']['head']
            canvas = tuple(int(v) for v in np.asarray(canvas) + low + high)
            result['unpadded_offset'] = list(result['offset'])
            result['offset'] = (np.asarray(result['offset']) + low).tolist()
            result['canvas_padding'] = dict(before=before, after=list(canvas),
                                          translation=low.tolist(), trailing=high.tolist())
        raster,offset=rasterize_registered_head(original,result,canvas)
    result.update(landmarks=landmarks,source_head_sha256=hashlib.sha256(source_head.read_bytes()).hexdigest())
    shutil.copytree(source_rig,output)
    (output/'layers').mkdir(exist_ok=True)
    raster.save(output/'layers/head_reference.png')
    layer.update(image='layers/head_reference.png',offset=offset)
    (output/'character.json').write_text(json.dumps(spec,indent=2))
    (output/'head_registration.json').write_text(json.dumps(result,indent=2))
    refresh_candidate_metadata(output,canvas)
    return output/'character.json'


def refresh_candidate_metadata(output,canvas):
    """Rebuild the active rest composite and invalidate copied approval metadata."""
    import hashlib,json,shutil
    from pathlib import Path
    from PIL import Image
    output=Path(output);spec=json.loads((output/'character.json').read_text())
    source=output/spec['puppet'].get('source','source.png')
    history=output/'history';history.mkdir(exist_ok=True)
    for name in ('bind_report.json','bind_joints.png','layers_check.png','input_manifest.json'):
        stale=output/name
        if stale.exists():
            target=history/('before_head_registration_'+name)
            if target.exists():raise ValueError('registration: ambiguous stale binding history')
            shutil.move(str(stale),str(target))
    previous=history/'before_head_registration_source.png'
    if source.exists() and not previous.exists():shutil.copy2(source,previous)
    composite=Image.new('RGBA',tuple(canvas))
    for layer in spec['puppet']['layers'].values():
        with Image.open(output/layer['image']) as im:
            offset=layer.get('offset',[0,0])
            if len(offset)!=2 or any(float(v)!=int(v) for v in offset):
                raise ValueError('registration: rest composite requires integer layer offsets')
            composite.alpha_composite(im.convert('RGBA'),tuple(int(v) for v in offset))
    source.parent.mkdir(parents=True,exist_ok=True);composite.save(source)
    provenance_path=output/'provenance.json'
    provenance=json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
    result=json.loads((output/'head_registration.json').read_text())
    provenance['derived_head_registration']=result
    for key in ('bind_approval','semantic_verification','registration_visual_approval','motion_contact_approval','user_motion_approval','final_visual_pass'):
        provenance[key]=False if key=='final_visual_pass' else 'pending_after_head_registration'
    provenance['rest_composite_rebuilt_from_active_layers']=True
    provenance['registered_source_frame']={'size':list(canvas),'source':spec['puppet'].get('source','source.png'),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    provenance['runtime_assets']={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in output.rglob('*') if p.is_file() and p.name!='provenance.json'}
    provenance_path.write_text(json.dumps(provenance,indent=2))
