"""Reference-derived head shape checks, separate from limb occupancy templates.

A numeric proportion check cannot certify anatomy or identity. Actual face/neck
art still requires visual review. Neck overlap never rescales the whole head.
"""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
import template_puppet as tp

MAX_ASPECT_DEVIATION=.15


def descriptor(mask):
    """Exclude the narrow mounting neck using row widths, without face landmarks."""
    ys,xs=np.nonzero(mask)
    if not len(ys):raise ValueError('empty head')
    top,bottom=int(ys.min()),int(ys.max());widths=[]
    for row in mask[top:bottom+1]:
        x=np.flatnonzero(row);widths.append(int(x[-1]-x[0]+1) if len(x) else 0)
    widths=np.array(widths);peak=int(widths.max())
    # Broad cranium + face ends before the narrow neck. No manually marked jaw.
    head_rows=np.flatnonzero(widths>=peak*.55)
    cut=top+int(head_rows[-1]);height=cut-top+1
    return {'width_px':peak,'head_height_px':height,'head_bottom_row':cut,
            'top_row':top,'aspect':peak/height,'total_height_px':bottom-top+1}


def compare(reference,candidate):
    r=descriptor(reference);c=descriptor(candidate)
    deviation=abs(c['aspect']/r['aspect']-1)
    labels,n=ndi.label(candidate);sizes=np.bincount(labels.ravel())[1:]
    substantial=int((sizes>max(4,candidate.sum()*.001)).sum())
    blockers=[]
    if deviation>MAX_ASPECT_DEVIATION:blockers.append('head width/height differs from identity reference by more than 15%')
    if substantial!=1:blockers.append('head has disconnected substantial artwork')
    return {'reference':r,'candidate':c,'aspect_deviation':deviation,
            'max_aspect_deviation':MAX_ASPECT_DEVIATION,'substantial_components':substantial,
            'blockers':blockers,'semantic_identity_verified':False}


def select(out):
    """Validate immutable reference and candidate; never silently reuse stale art."""
    out=Path(out);m=tp.read(out/'head_reference.json')
    job,c=tp.validate(out)
    if c.get('head_shape_contract',{}).get('sha256')!=tp.sha(out/'head_reference.json'):
        raise ValueError('head shape contract changed; recheck')
    if m['processor_sha256']!=tp.sha(__file__):raise ValueError('head proportion processor changed; recheck')
    paths={k:out/m[k]['file'] for k in ('reference','candidate','identity')}
    for k,p in paths.items():
        if tp.sha(p)!=m[k]['sha256']:raise ValueError('head '+k+' changed; recheck')
    if paths['identity'].resolve()!=(out/'identity_reference.png').resolve():raise ValueError('head identity must be stage identity')
    attempts=job['attempts']['head'];raw=out/'head'/('attempt_'+str(m['attempt']))/'raw.png'
    if (m['attempt']!=len(attempts) or attempts[-1]['state']!='generated'
            or tp.sha(raw)!=m['raw_sha256'] or attempts[-1].get('raw_sha256')!=m['raw_sha256']):
        raise ValueError('head generation record changed; recheck')
    a=np.asarray(Image.open(paths['candidate']).convert('RGBA'));ref=np.asarray(Image.open(paths['reference']).convert('RGBA'))
    check=compare(ref[:,:,3]>128,a[:,:,3]>128)
    return paths['candidate'],{'file':m['candidate']['file'],'registered_sha256':tp.sha(paths['candidate']),
        'qualification':'reference head proportions; not old narrow template',
        'geometry':check},m['joints']


def install(out,candidate,reference,source_note):
    """Archive a new accounted-for head attempt under an explicit new contract."""
    import shutil
    out=Path(out);candidate=Path(candidate);reference=Path(reference)
    job,c=tp.validate(out);attempts=job['attempts']['head']
    if not attempts:raise ValueError('head generation must be recorded before installing')
    if attempts[-1]['state']!='generated' or tp.sha(candidate)!=attempts[-1].get('raw_sha256'):
        raise ValueError('candidate must be the recorded generated head')
    # Candidate must be the actual last reserved attempt, not an uncounted redraw.
    attempt=out/'head'/('attempt_'+str(len(attempts)));attempt.mkdir(exist_ok=True)
    dst=attempt/'reference_qualified.png'
    Image.open(candidate).convert('RGBA').save(dst)
    ref=out/'head_proportion_fix/shape_reference.png';ref.parent.mkdir(exist_ok=True)
    if reference.resolve()!=ref.resolve():shutil.copy2(reference,ref)
    reference_pixels=np.asarray(Image.open(ref).convert('RGBA'))
    identity_pixels=np.asarray(Image.open(out/'identity_reference.png').convert('RGBA'))
    if reference_pixels.shape!=identity_pixels.shape:
        raise ValueError('segmented head must retain full identity canvas coordinates')
    occupied=reference_pixels[:,:,3]>128
    if not np.array_equal(reference_pixels[occupied,:3],identity_pixels[occupied,:3]):
        raise ValueError('segmented head pixels differ from identity reference')
    a=np.asarray(Image.open(dst));mask=a[:,:,3]>128;d=descriptor(mask)
    # Preserve the reference's neck/head ratio. Extra generated mounting skin
    # belongs behind the torso; attaching at its bottom would create a long neck.
    rd=descriptor(np.asarray(Image.open(ref).convert('RGBA'))[:,:,3]>128)
    neck_ratio=(rd['total_height_px']-rd['head_height_px'])/rd['head_height_px']
    bottom=int(np.nonzero(mask)[0].max())
    y=min(bottom-3,round(d['head_bottom_row']+neck_ratio*d['head_height_px']))
    xs=np.flatnonzero(mask[y]);
    if not len(xs):raise ValueError('head neck base missing')
    anchor=[float((xs[0]+xs[-1])/2),float(y)]
    manifest={'version':'reference-head-v1','identity':{'file':'identity_reference.png','sha256':tp.sha(out/'identity_reference.png')},
      'reference':{'file':str(ref.relative_to(out)),'sha256':tp.sha(ref)},
      'candidate':{'file':str(dst.relative_to(out)),'sha256':tp.sha(dst)},
      'joints':{'head_base':anchor,'head_center':[float((np.nonzero(mask)[1].min()+np.nonzero(mask)[1].max())/2),float((d['top_row']+d['head_bottom_row'])/2)]},
      'source_note':source_note,'processor_sha256':tp.sha(__file__),
      'body_scale_rule':'preserve reference head height / full reference height; uniform scale only',
      'neck_ratio':neck_ratio,
      'mounting_rule':'bounded translation only; never grow head to satisfy collar',
      'old_template_disposition':'user rejected; archived, not a valid head identity shape contract',
      'attempt':len(attempts),'needs_visual_review':True}
    manifest['raw_sha256']=attempts[-1]['raw_sha256']
    tp.write(out/'head_reference.json',manifest)
    previous=tp.sha(out/'contract.json')
    c['head_shape_contract']={'file':'head_reference.json','sha256':tp.sha(out/'head_reference.json'),
        'reason':'User rejected generic narrow head template; use identity-derived head and neck proportions. Limb/attachment gates unchanged.'}
    if c!=tp.read(out/'contract.json'):
        history=out/'contract_history';history.mkdir(exist_ok=True)
        shutil.copy2(out/'contract.json',history/('before_head_'+previous[:12]+'.json'))
        tp.write(out/'contract.json',c);job['contract_sha256']=tp.sha(out/'contract.json')
        job.setdefault('contract_revisions',[]).append({'previous_sha256':previous,
            'current_sha256':job['contract_sha256'],'reason':c['head_shape_contract']['reason']})
        tp.write(out/'job.json',job)
    _,entry,_=select(out);tp.write(attempt/'head_proportions.json',entry['geometry'])
    return entry
