"""Three-part template/art proof. Development-only; does not approve a rig.

Geometry is shared by all characters using a profile. No source pose detection,
character-specific masks, forced silhouette clipping, or automatic visual pass.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import base64
import html

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from template_registration import fit as fit_art

SIZE = 1024
SLOTS = ('torso', 'arm_near', 'leg_near')
GENERATABLE_SLOTS = (*SLOTS,'head','arm_far','leg_far','hips','weapon')
PROFILES = {'slim': 1.0, 'compact': 1.22}
LIMIT = 3
# Exploratory fixed geometry requirements, not evidence of art quality.
RULES = dict(core_coverage=.98, inside_envelope=.99, max_scale_delta=.12,
             max_translation_fraction=.08, envelope_px=28)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def geometry(slot, profile='slim'):
    if profile not in PROFILES or slot not in SLOTS:
        raise ValueError('unsupported template profile or slot')
    im = Image.new('L', (SIZE, SIZE)); d = ImageDraw.Draw(im)
    if slot == 'torso':
        points = [(450,150),(540,150),(560,205),(625,240),(655,400),(640,610),
                  (665,850),(580,880),(520,825),(420,860),(345,840),(380,650),
                  (365,430),(360,285),(420,225)]
        d.polygon(points, fill=255)
        joints = dict(neck=(500,175), shoulder=(500,285), waist=(500,635), hip=(500,780))
    elif slot == 'arm_near':
        points = [(400,170),(500,470),(690,710)]
        d.line(points, fill=255, width=106, joint='curve')
        for x,y,r in [(400,170,77),(500,470,52),(690,710,47)]:
            d.ellipse((x-r,y-r,x+r,y+r),fill=255)
        # Complete fist-shaped hand envelope, not final finger artwork.
        d.polygon([(658,711),(704,682),(765,745),(778,790),(745,824),(701,802)],fill=255)
        joints = dict(shoulder=(400,170), elbow=(500,470), wrist=(690,710), grip=(737,773))
    else:
        d.polygon([(405,130),(525,130),(563,265),(552,430),(538,500),
                   (550,660),(527,805),(563,846),(672,865),(710,903),(700,929),
                   (415,929),(409,883),(417,820),(407,650),(416,500),(397,355)],fill=255)
        joints = dict(hip=(470,150), knee=(478,490), ankle=(480,820), toe=(675,900))
    factor = PROFILES[profile]
    # Scale width about the local center for BOTH masks and their known joints.
    if factor != 1:
        im = im.transform(im.size, Image.Transform.AFFINE,
                          (1/factor,0,512*(1-1/factor),0,1,0),Image.Resampling.NEAREST)
        joints = {k:(512+(x-512)*factor,y) for k,(x,y) in joints.items()}
    return np.asarray(im)>0, joints


def plate(slot, profile):
    mask, joints = geometry(slot, profile)
    a = np.full((SIZE,SIZE,4),255,np.uint8); a[:,:,:3]=(230,233,236)
    a[mask]=(64,74,102,255)
    yy,xx=np.indices(mask.shape)
    if slot=='torso':
        a[mask&(yy>610)&(yy<700)]=(55,49,48,255)
        a[mask&(yy>673)&(yy<694)]=(158,54,48,255)
        a[mask&(xx>575)&(yy<610)]=(225,218,209,255)
    elif slot=='arm_near':
        a[mask&(yy>280)&(yy<350)]=(225,218,209,255)
        a[mask&(yy>=350)&(yy<505)]=(230,191,161,255)
        a[mask&(yy>=505)&(yy<710)]=(48,44,46,255)
        a[mask&(yy>=710)]=(230,191,161,255)
    else:
        a[mask]=(225,218,209,255)
        a[mask&(yy>555)]=(48,44,46,255)
    return Image.fromarray(a),mask,joints


PROMPT = '''Create ONE finished isolated 2D game puppet part, not a character illustration.
Image 1 is the exact geometry/material registration guide. Image 2 supplies character identity,
palette, linework, gold motifs and cel shading only. The second image's pose/other limbs must
NOT be copied into this part. Rebuild the requested complete part, including hidden roots.
Keep the first image's contour, pose, component scale and placement on the square canvas.
Replace its flat diagram with detailed crisp finished art; no diagram colors, guide marks or text.
Transparent background. No shadows on a floor, no second view, no inset, no extra objects.
PART: {description}
STYLE AND DESIGN: {identity}
We will preserve the returned contour rather than cut a bad drawing to fit. Extra branches,
missing sections, cropped hands/boots, grey background inside the part and displaced features
are rejected. Return a single square registration image containing just this complete part.
'''
DESCRIPTIONS = {
 'torso': 'A complete RIGHT-FACING SIDE-VIEW short SLEEVELESS torso garment, including upright collar, continuous chest/back fabric, waist belt and short hip hem. The navy fabric beneath both shoulder/arm positions is fully painted and opaque. No armholes cut through the interior. No arms, skin shoulders, sleeves, sleeve cuffs, rounded shoulder shields, pauldrons, head, neck skin, hands, pants, legs, sword or scabbard. The gold shoulder cloud SHIELD belongs to the separate arm and must not appear here. Use gold edging at collar/lapel and the short hem, ivory front lapel, dark belt with fitted red cord. Do not produce a front-view tunic or a shoulder cape.',
 'arm_near': 'Exactly ONE complete near/right arm from its rounded SHOULDER ROOT at upper-left through the elbow at center to wrist and COMPLETE empty loosely clenched HAND at lower-right, matching the diagonal guide. Navy/gold short shoulder cap, short ivory sleeve cuff, exposed upper arm/elbow skin, dark gold-edged forearm bracer, anatomically drawn knuckles and thumb. Both upper arm and forearm are full length. The palm is empty: no sword, handle or scabbard. No torso, other arm or detached fingers. Cover the shoulder root completely for later overlap.',
 'leg_near': 'Exactly ONE complete right-facing leg from its OWN upper thigh/hip root at the top through knee to ankle and the COMPLETE forward-pointing BOOT including toe and heel. Ivory trousers and dark black/brown knee-high boot with restrained gold trim matching the reference. One unbranched trouser leg only. No pelvis, belt, shared crotch, second thigh, extra boot, arms, torso, sword or trailing cloth. The top is a complete attachment root, not an amputated second leg.'}


def prepare(source,out,identity,profile='slim'):
    out=Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('new template proof needs an empty directory; preserve previous attempts')
    out.mkdir(parents=True,exist_ok=True);shutil.copy2(source,out/'identity_reference.png')
    contract={'version':'template-three-part-v1.2','profile':profile,'size':SIZE,'rules':RULES,'slots':{}}
    for slot in SLOTS:
        part=out/slot;part.mkdir()
        guide,mask,joints=plate(slot,profile)
        guide.save(part/'guide.png');Image.fromarray(mask.astype('uint8')*255).save(part/'structure_mask.png')
        overlay=guide.copy();d=ImageDraw.Draw(overlay)
        for name,(x,y) in joints.items():
            d.ellipse((x-8,y-8,x+8,y+8),fill='white',outline='black',width=2)
            d.text((x+12,y),name,fill='black')
        overlay.save(part/'joints.png')
        (part/'prompt.txt').write_text(PROMPT.format(description=DESCRIPTIONS[slot],identity=identity),encoding='utf-8')
        contract['slots'][slot]={'joints':joints,'guide_sha256':sha(part/'guide.png'),
                                 'mask_sha256':sha(part/'structure_mask.png')}
    write(out/'contract.json',contract)
    write(out/'job.json',{'phase':'three_part_proof','source_kind':'generated_standard_side_reference',
          'source_sha256':sha(out/'identity_reference.png'),'contract_sha256':sha(out/'contract.json'),
          'source_note':'Prior approved short-hair/short-clothes adaptation, not the original uploaded image.',
          'identity':identity,'attempts':{slot:[] for slot in SLOTS},'binding_performed':False,'animations_generated':False})


def validate(out):
    out=Path(out);job=read(out/'job.json');contract=read(out/'contract.json')
    if sha(out/'contract.json')!=job['contract_sha256'] or sha(out/'identity_reference.png')!=job['source_sha256']:
        raise ValueError('proof source/contract changed')
    for slot,row in contract['slots'].items():
        for field,name in [('guide_sha256','guide.png'),('mask_sha256','structure_mask.png')]:
            if sha(out/slot/name)!=row[field]:raise ValueError('guide/mask changed')
    return job,contract


def begin(out,slot,correction=''):
    out=Path(out);job,contract=validate(out)
    if slot not in GENERATABLE_SLOTS or slot not in contract['slots']:
        raise ValueError('unsupported or imported slot; cannot reopen its generation budget')
    attempts=job['attempts'][slot]
    if job['phase']=='blocked' or len(attempts)>=LIMIT:
        raise ValueError('attempt limit or terminal blocker; do not reset this proof')
    if attempts and attempts[-1]['state']=='requested':raise ValueError('previous request not recorded')
    n=len(attempts)+1;attempt=out/slot/f'attempt_{n}';attempt.mkdir()
    prompt=(out/slot/'prompt.txt').read_text(encoding='utf-8')
    mask=np.asarray(Image.open(out/slot/'structure_mask.png'))>0
    yy,xx=np.nonzero(mask)
    prompt+='\nREGISTRATION: measured on a square canvas, coordinate origin is top-left. '
    prompt+='Keep this contour bounding box: left {:.1f}%, top {:.1f}%, right {:.1f}%, bottom {:.1f}%. '.format(
        xx.min()/SIZE*100,yy.min()/SIZE*100,(xx.max()+1)/SIZE*100,(yy.max()+1)/SIZE*100)
    prompt+='Leave all remaining margins EMPTY, even if the part looks small. Do not enlarge to fill the canvas. '
    prompt+='Joint centers (percent of width, percent of height): '+json.dumps(
        {k:[round(x/SIZE*100,1),round(y/SIZE*100,1)] for k,(x,y) in contract['slots'][slot]['joints'].items()})
    prompt+='\nThese coordinates describe the diagram, not labels to draw. Copy its bent bone path exactly.\n'
    if correction:prompt+='\nOBSERVED DEFECT TO CORRECT: '+correction+'\n'
    (attempt/'prompt.txt').write_text(prompt,encoding='utf-8')
    attempts.append({'attempt':n,'state':'requested','prompt_sha256':sha(attempt/'prompt.txt'),
                     'contract_sha256_at_request':job['contract_sha256']})
    write(out/'job.json',job)
    return str(attempt)


def silhouette_metrics(mask,structure,joints):
    core=ndi.binary_erosion(structure,iterations=8)
    allowed=ndi.binary_dilation(structure,iterations=RULES['envelope_px'])
    yy,xx=np.indices(mask.shape)
    anchors={name:float(mask[(xx-x)**2+(yy-y)**2<=12**2].mean()) for name,(x,y) in joints.items()}
    holes=ndi.binary_fill_holes(mask)&~mask
    return {'core_coverage':float(mask[core].mean()),
            'inside_envelope':float((mask&allowed).sum()/max(mask.sum(),1)),
            'anchor_coverage':anchors,'enclosed_transparent_pixels':int(holes.sum())}


def metric_blockers(metrics):
    blockers=[]
    if metrics['core_coverage']<RULES['core_coverage']:blockers.append('required_structure_uncovered')
    if metrics['inside_envelope']<RULES['inside_envelope']:blockers.append('art_outside_part_envelope')
    if any(v<.98 for v in metrics['anchor_coverage'].values()):blockers.append('attachment_or_joint_uncovered')
    if metrics['enclosed_transparent_pixels']:blockers.append('internal_transparent_holes_require_review')
    return blockers


def ingest(out,slot,raw):
    out=Path(out);job,contract=validate(out)
    if slot not in contract['slots']:raise ValueError('unsupported or imported slot')
    rows=job['attempts'][slot]
    if not rows or rows[-1]['state']!='requested':raise ValueError('begin an attempt first')
    attempt=out/slot/f'attempt_{len(rows)}';shutil.copy2(raw,attempt/'raw.png')
    image=Image.open(raw).convert('RGBA')
    if image.width!=image.height:raise ValueError('generated registration image must be square')
    image=image.resize((SIZE,SIZE),Image.Resampling.LANCZOS);a=np.array(image)
    # Native alpha is preferred. Flat-key fallback never invents missing artwork.
    mode='native_alpha'
    missing_alpha=(a[:,:,3]<128).sum()<100
    if (a[:,:,3]<128).sum()<100:
        key=(a[:,:,0]>180)&(a[:,:,2]>180)&(a[:,:,1]<100)
        if key.sum()>100:
            a[key]=0;mode='magenta_key'
    mask=a[:,:,3]>128
    structure=np.asarray(Image.open(out/slot/'structure_mask.png'))>0
    image,registration=fit_art(Image.fromarray(a),structure,contract['slots'][slot]['joints'],RULES)
    a=np.asarray(image);mask=a[:,:,3]>128
    metrics=silhouette_metrics(mask,structure,contract['slots'][slot]['joints'])
    blockers=metric_blockers(metrics)
    if registration['clipped_source_pixels']:blockers.append('art_clipped_by_registration_canvas')
    if mode=='native_alpha' and missing_alpha:blockers.append('no_transparent_or_key_background')
    image.save(attempt/'registered.png')
    guide=np.array(Image.open(out/slot/'guide.png').convert('RGBA'));guide[:,:,3]=np.where(structure,60,0)
    bg=Image.new('RGBA',(SIZE,SIZE),(215,220,225,255));bg.alpha_composite(image)
    overlay=Image.fromarray(guide);bg.alpha_composite(overlay)
    d=ImageDraw.Draw(bg)
    for name,(x,y) in contract['slots'][slot]['joints'].items():
        d.ellipse((x-7,y-7,x+7,y+7),fill='cyan',outline='black');d.text((x+10,y),name,fill='black')
    bg.convert('RGB').save(attempt/'registration_review.jpg')
    report={'status':'blocked' if blockers else 'needs_visual_review','binding_approved':False,
            'raw_sha256':sha(attempt/'raw.png'),'alpha_mode':mode,'registration':registration,
            'registered_sha256':sha(attempt/'registered.png'),
            'metrics':metrics,'blockers':blockers,'silhouette_forced_to_template':False,
            'note':'Exploratory geometry only. Wrong anatomy, background-colored interiors and duplicate clothing require visual review.'}
    write(attempt/'geometry_report.json',report)
    rows[-1].update(state='generated',raw_sha256=report['raw_sha256'],geometry_status=report['status'])
    if len(rows)==LIMIT and blockers:job['phase']='blocked'
    write(out/'job.json',job)
    return report


def repair(out,slot):
    """Reprocess existing art; generation budgets and original failures are immutable."""
    from template_mesh_fit import deform
    out=Path(out);job,contract=validate(out)
    if slot not in contract['slots'] or slot not in ('arm_near','arm_far','leg_near','leg_far'):
        raise ValueError('cage repair requires an existing limb')
    rows=job['attempts'][slot]
    if not rows or rows[-1]['state']!='generated':raise ValueError('existing generated art required')
    source=out/slot/f'attempt_{rows[-1]["attempt"]}'/'registered.png'
    folder=out/'repairs'/slot/'cage_v1'
    if folder.exists():raise ValueError('repair already recorded; preserve its history')
    folder.mkdir(parents=True)
    structure=np.asarray(Image.open(out/slot/'structure_mask.png'))>0
    image,deformation=deform(Image.open(source),structure)
    metrics=silhouette_metrics(np.asarray(image)[:,:,3]>128,structure,contract['slots'][slot]['joints'])
    blockers=metric_blockers(metrics)
    if deformation['clipped_source_pixels']:blockers.append('art_clipped_by_deformation')
    image.save(folder/'part.png')
    report={'status':'blocked' if blockers else 'needs_visual_review','binding_approved':False,
            'source':str(source.relative_to(out)),'source_sha256':sha(source),
            'contract_sha256':job['contract_sha256'],'processor_sha256':sha(Path(__file__).with_name('template_mesh_fit.py')),
            'output_sha256':sha(folder/'part.png'),'metrics':metrics,'blockers':blockers,
            'deformation':deformation,'original_generation_phase':job['phase'],
            'generation_counts':{k:len(v) for k,v in job['attempts'].items()}}
    write(folder/'report.json',report)
    manifest=read(out/'repairs.json') if (out/'repairs.json').exists() else {}
    manifest[slot]={'file':str((folder/'part.png').relative_to(out)),
                    'report':str((folder/'report.json').relative_to(out)),
                    'report_sha256':sha(folder/'report.json')}
    write(out/'repairs.json',manifest)
    return report


def selected_part(out,slot):
    out=Path(out);job,contract=validate(out)
    rows=[row for row in job['attempts'][slot] if row['state']=='generated']
    if not rows:raise ValueError('all three parts need a recorded generated image')
    row=rows[-1];folder=out/slot/f'attempt_{row["attempt"]}'
    path=folder/'registered.png';geometry_report=read(folder/'geometry_report.json')
    if 'registered_sha256' in geometry_report and sha(path)!=geometry_report['registered_sha256']:
        raise ValueError('registered part changed after its geometry report')
    entry={'attempt':row['attempt'],'file':str(path.relative_to(out)),'geometry':geometry_report}
    if (out/'repairs.json').exists() and slot in read(out/'repairs.json'):
        item=read(out/'repairs.json')[slot];report=read(out/item['report'])
        if (sha(out/item['report'])!=item['report_sha256'] or sha(path)!=report['source_sha256'] or
            sha(out/item['file'])!=report['output_sha256'] or report['contract_sha256']!=job['contract_sha256'] or
            sha(Path(__file__).with_name('template_mesh_fit.py'))!=report['processor_sha256']):
            raise ValueError('derived repair is stale or changed')
        path=out/item['file'];entry.update(file=item['file'],geometry=report,repair=item['report'])
        current=silhouette_metrics(np.asarray(Image.open(path))[:,:,3]>128,
            np.asarray(Image.open(out/slot/'structure_mask.png'))>0,contract['slots'][slot]['joints'])
        if metric_blockers(current)!=report['blockers']:
            raise ValueError('repair metrics no longer match current acceptance rules')
    entry['registered_sha256']=sha(path)
    return path,entry


def preview(out):
    """A clearly marked draft, including rejected art; never emits production files."""
    out=Path(out);job,contract=validate(out)
    selected={};images={}
    for slot in SLOTS:
        path,selected[slot]=selected_part(out,slot)
        images[slot]=Image.open(path).convert('RGBA')
    # Fixed generic layout, derived from known template anchors, never source measurements.
    hip=np.array([500.,800.]);torso_scale=.70
    tj=contract['slots']['torso']['joints'];torso_offset=hip-np.array(tj['hip'])*torso_scale
    shoulder=torso_offset+np.array(tj['shoulder'])*torso_scale
    transforms={
        'torso':(torso_scale,torso_offset),
        'arm_near':(.68,shoulder-np.array(contract['slots']['arm_near']['joints']['shoulder'])*.68),
        'leg_near':(.83,hip-np.array(contract['slots']['leg_near']['joints']['hip'])*.83),
    }
    canvas_size=(1024,1536)
    def assemble(displacement=0):
        bg=Image.new('RGBA',canvas_size,(232,235,239,255))
        for slot in ('leg_near','torso','arm_near'):
            scale,offset=transforms[slot];x,y=map(float,offset)
            if slot=='arm_near':x+=displacement
            mapped=images[slot].transform(canvas_size,Image.Transform.AFFINE,
                       (1/scale,0,-x/scale,0,1/scale,-y/scale),Image.Resampling.BICUBIC)
            bg.alpha_composite(mapped)
        return bg
    for name,move in [('assembly_draft',0),('exposed_torso_draft',210)]:
        assemble(move).save(out/(name+'.png'))
    # Inspection-only resizing. Exported registered parts keep full square canvas.
    sheet=Image.new('RGB',(1600,920),(246,247,249));draw=ImageDraw.Draw(sheet)
    draw.text((24,14),'TEMPLATE ART STUDY / THREE PARTS ONLY / NOT BOUND',fill=(25,35,55))
    labels={'torso':'Complete torso / attempt 1','arm_near':'Complete arm / latest attempt','leg_near':'Single leg / latest attempt'}
    for i,slot in enumerate(SLOTS):
        im=images[slot].copy();im.thumbnail((500,650))
        bg=Image.new('RGBA',im.size,(222,227,233,255));bg.alpha_composite(im)
        sheet.paste(bg.convert('RGB'),(i*530+(530-im.width)//2,75))
        draw.text((i*530+20,50),labels[slot],fill=(25,35,55))
        status=selected[slot]['geometry']['status']
        draw.text((i*530+20,615),'Geometry: '+status,fill=(150,45,40) if status=='blocked' else (60,70,85))
        guide=Image.open(out/slot/'joints.png').convert('RGB').resize((230,230))
        sheet.paste(guide,(i*530+150,650))
    sheet.save(out/'parts_preview.jpg',quality=94)
    comparison=Image.new('RGB',(1050,900),(246,247,249));draw=ImageDraw.Draw(comparison)
    for i,(label,move) in enumerate([('Draft assembly: three parts only',0),('Arm moved away: garment exposure',210)]):
        image=assemble(move);image.thumbnail((500,820));comparison.paste(image.convert('RGB'),(i*525+12,60))
        draw.text((i*525+15,20),label,fill=(25,35,55))
    comparison.save(out/'assembly_comparison.jpg',quality=94)
    report={'report_type':'template_three_part_draft','status':'draft_requires_revision',
            'binding_approved':False,'binding_performed':False,'animations_generated':False,
            'contract_sha256':job['contract_sha256'],'selected':selected,
            'layout':{k:{'scale':s,'offset':o.tolist()} for k,(s,o) in transforms.items()},
            'note':'Latest generated parts displayed for review even when blocked. No forced silhouette clipping. No head, second arm or second leg has been made for this proof.'}
    report['all_three_part_geometry_checks_met']=all(not p['geometry']['blockers'] for p in selected.values())
    write(out/'draft_report.json',report)
    def data(path):return 'data:image/png;base64,'+base64.b64encode(Path(path).read_bytes()).decode()
    payload={slot:{'art':data(out/selected[slot]['file']), 'guide':data(out/slot/'guide.png'),
                   'joints':contract['slots'][slot]['joints'],'scale':transforms[slot][0],
                   'offset':transforms[slot][1].tolist()} for slot in SLOTS}
    # All assets embedded; offline review has no service/account dependency.
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>剑客三部件试做</title><style>
*{box-sizing:border-box}body{margin:0;background:#111724;color:#e6eaf1;font:16px/1.65 system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:28px}h1{margin:0;font-size:28px}p{color:#b4bed0}button{background:#29354a;color:#e6eaf1;border:1px solid #52617c;border-radius:8px;padding:8px 16px;margin-right:8px;cursor:pointer}.badge{color:#f1b879}.parts{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:#1b2434;border-radius:12px;padding:16px}.card img{width:100%;display:block;background:#dce2e9;border-radius:8px}h2{font-size:19px;margin:4px 0 12px}canvas{display:block;width:min(100%,640px);height:auto;background:#e8ebef;border-radius:12px;margin:20px auto}input{width:260px;vertical-align:middle}label{display:inline-block;margin:10px 18px 5px 0}@media(max-width:650px){.parts{grid-template-columns:1fr}main{padding:18px}}</style>
<main><span class="badge">第一版 · 三部件外观预览 · 尚未通过绑定验收</span><h1>武侠剑客：先看部件，再看组装</h1>
<p>保留蓝白金、红腰绳及护腕长靴。此处仅制作躯干、一条手臂和一条腿，头部与其他肢体尚未制作。__GEOMETRY_NOTE__</p>
<div><button id="art">查看美术</button><button id="guides">查看结构引导</button></div><div class="parts">__CARDS__</div>
<h2 style="margin-top:30px">局部组装与躯干暴露检查</h2><p>移动手臂可查看原先被遮挡的衣服。滑块只做静态位移，尚无完整角色的待机或走路。</p>
<label>移开手臂 <input id="separate" type="range" min="0" max="250" value="0"></label><label><input style="width:auto" id="joints" type="checkbox"> 显示模板关节点</label><canvas id="stage" width="1024" height="1536"></canvas>
__MOTION__<p>几何报告保留所有失败项。预览不代表完整角色或动画已经通过验收。</p></main><script>
const parts=__PAYLOAD__,order=['leg_near','torso','arm_near'];
const stage=document.getElementById('stage'),ctx=stage.getContext('2d');
Promise.all(Object.values(parts).map(p=>new Promise(resolve=>{p.image=new Image();p.image.onload=resolve;p.image.src=p.art}))).then(draw);
function draw(){ctx.fillStyle='#e8ebef';ctx.fillRect(0,0,1024,1536);for(const k of order){const p=parts[k],x=p.offset[0]+(k==='arm_near'?+document.getElementById('separate').value:0),y=p.offset[1];ctx.drawImage(p.image,x,y,1024*p.scale,1024*p.scale);if(document.getElementById('joints').checked)for(const [name,point]of Object.entries(p.joints)){const a=x+point[0]*p.scale,b=y+point[1]*p.scale;ctx.fillStyle='#00b6d2';ctx.beginPath();ctx.arc(a,b,7,0,Math.PI*2);ctx.fill();ctx.fillStyle='#122334';ctx.font='16px sans-serif';ctx.fillText(name,a+10,b)}}}
for(const name of ['separate','joints'])document.getElementById(name).addEventListener('input',draw);
document.getElementById('art').onclick=()=>document.querySelectorAll('[data-part]').forEach(im=>im.src=parts[im.dataset.part].art);
document.getElementById('guides').onclick=()=>document.querySelectorAll('[data-part]').forEach(im=>im.src=parts[im.dataset.part].guide);
</script></html>'''
    cards=''.join('<section class="card"><h2>'+html.escape(label)+'</h2><img data-part="'+slot+'" src="'+payload[slot]['art']+'"></section>'
                  for slot,label in [('torso','完整躯干'),('arm_near','完整手臂'),('leg_near','独立单腿')])
    motion=''
    motion_report=out/'motion_probe/report.json'
    if motion_report.exists():
        checked=read(motion_report)
        for part in checked['parts'].values():
            if sha(out/part['source_file'])!=part['source_sha256']:
                raise ValueError('motion test is stale after an art change')
        uri='data:image/gif;base64,'+base64.b64encode((out/'motion_probe/joint_range.gif').read_bytes()).decode()
        motion='<h2>独立部件活动测试</h2><p>抬臂与屈膝测试，使用现有骨骼网格渲染；尚未测试完整角色走路、落脚或持剑。</p><img style="width:100%;border-radius:12px" src="'+uri+'">'
    note=('三块部件的几何检查已通过，正在核对活动效果；完整角色尚未补齐。'
          if report['all_three_part_geometry_checks_met'] else '当前部件尚未全部通过几何验收，仍需修订。')
    document=document.replace('__CARDS__',cards).replace('__PAYLOAD__',json.dumps(payload)).replace('__GEOMETRY_NOTE__',note).replace('__MOTION__',motion)
    (out/'preview.html').write_text(document,encoding='utf-8')
    return {'status':report['status'],'preview':str(out/'preview.html')}


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('prepare');a.add_argument('source');a.add_argument('out');a.add_argument('--identity',required=True)
    a.add_argument('--profile',choices=PROFILES,default='slim')
    a=s.add_parser('begin');a.add_argument('out');a.add_argument('slot',choices=GENERATABLE_SLOTS);a.add_argument('--correction',default='')
    a=s.add_parser('ingest');a.add_argument('out');a.add_argument('slot',choices=GENERATABLE_SLOTS);a.add_argument('raw')
    a=s.add_parser('preview');a.add_argument('out')
    a=s.add_parser('repair');a.add_argument('out');a.add_argument('slot',choices=GENERATABLE_SLOTS)
    args=vars(p.parse_args());command=args.pop('command');result=globals()[command](**args)
    if result is not None:print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
