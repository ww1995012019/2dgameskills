"""Complete the three-part prototype with five separately authored parts.

Development only. Static assembly and binding geometry, not a production walk.
Existing part budgets stay closed in the parent; child cannot regenerate them.
"""
import argparse
import base64
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image,ImageDraw,ImageOps

import template_puppet as tp

EXTRAS=('head','arm_far','leg_far','hips','weapon')
ORDER=('arm_far','hips','leg_far','leg_near','head','torso','weapon','arm_near')


def geometry(slot,profile):
    if slot=='arm_far':
        mask,joints=tp.geometry('arm_near',profile)
        return mask[:,::-1].copy(),{k:(1023-x,y) for k,(x,y) in joints.items()}
    im=Image.new('L',(1024,1024));d=ImageDraw.Draw(im)
    if slot=='head':
        # Generic occupancy placeholder, never an identity-specific skull shape.
        # The old tall cone compressed the back of the head in generated art.
        d.ellipse((200,100,775,650),fill=255)
        d.polygon([(650,230),(770,300),(785,370),(835,420),(780,450),
                   (760,540),(700,650),(580,675),(600,850),(440,850),(440,570)],fill=255)
        joints={'head_base':(500,820),'head_center':(490,400)}
    elif slot=='hips':
        d.polygon([(330,260),(650,260),(690,450),(650,700),(540,730),(500,650),
                   (460,730),(350,700),(310,450)],fill=255)
        joints={'hip':(500,500),'waist':(500,300)}
    elif slot=='leg_far':
        d.polygon([(485,130),(605,130),(585,300),(526,470),(510,530),(476,660),
                   (447,805),(480,846),(585,865),(635,903),(625,929),(340,929),
                   (334,883),(355,820),(352,650),(393,500),(405,355)],fill=255)
        joints={'hip':(550,150),'knee':(455,490),'ankle':(400,820),'toe':(600,900)}
    elif slot=='weapon':
        d.line([(420,900),(500,640)],fill=255,width=34)
        d.ellipse((395,875,445,925),fill=255)
        d.polygon([(483,630),(517,640),(647,163),(650,140),(635,159)],fill=255)
        d.line([(419,615),(581,665)],fill=255,width=24)
        for x,y in ((419,615),(581,665)):d.ellipse((x-15,y-15,x+15,y+15),fill=255)
        joints={'grip':(450,800),'guard':(500,640)}
    else:raise ValueError('unsupported additional part')
    factor=tp.PROFILES[profile]
    if factor!=1:
        # Weapon is a prop and retains its shape between body builds.
        factor=1 if slot=='weapon' else factor
        im=im.transform(im.size,Image.Transform.AFFINE,(1/factor,0,512*(1-1/factor),0,1,0),Image.Resampling.NEAREST)
        joints={k:(512+(x-512)*factor,y) for k,(x,y) in joints.items()}
    return np.asarray(im)>0,joints


DESCRIPTIONS={
 'head':'ONE complete right-facing profile head and bare neck. Preserve the exact young male identity, natural skull width/height, full back-of-head volume, nose, brow, jaw, eye and tousled short dark-brown hair of the character reference. Head proportions come from the character, not from the generic occupancy guide. Include all hair tips, ear, chin and solid skin neck with extra lower skin for mounting behind a separate collar. No collar, clothes, shoulders, earrings, sword, head ornament, alternate view or portrait background. No tall cone hair or squeezed skull. The final head requires a source-derived proportion check and separate visual review; template occupancy alone is insufficient.',
 'arm_far':'ONE complete FAR/LEFT arm. Follow the first guide from shoulder upper-right through elbow center to wrist and COMPLETE empty clenched hand lower-left. Navy-gold short shoulder cap, ivory short cuff, exposed skin upper arm/elbow, dark gold-trim bracer. Keep every segment full length. Fingers and thumb anatomically complete, closed fist without internal transparent openings. No sword, handle, torso or other limb. This is independently painted far-arm art, not a duplicate of the reference character arm pose.',
 'leg_far':'ONE complete far leg, hip at upper-right, knee leaning left, ankle lower-left and entire boot pointing RIGHT, as shown by first guide. Ivory trousers all the way to top attachment; dark gold-trimmed boot, full toe/heel. No navy/gold hip flap, belt, pelvis, shared crotch, second thigh, fork, other leg, sword or torso. Match the broader calf/sole silhouette in the diagram, not the other image pose.',
 'hips':'ONE isolated connected ivory pelvis/upper-trouser piece, solid waist through crotch, following the broad short guide. This hidden supporting garment sits behind a separate navy tunic and behind separate complete legs. No belt, red cord, gold buckle, navy hip flaps, long thighs, knees, boots, torso, skin or weapon. Crisp ivory cloth, subtle cel folds, complete opaque central crotch, no interior hole. It is not a pair of full trousers.',
 'weapon':'Exactly ONE straight single-handed Chinese sword ONLY, matching the identity reference ornament and first guide: slim silver blade pointing upper-right, gold guard, dark wrapped handle, gold pommel. Preserve full sharp tip and full pommel, grip-center position. No hand, arm, person, scabbard, extra blade, sheath, decorative ribbon, text or second view. The sword passes behind a separately painted fist.'}


def prepare(parent,out,identity):
    parent=Path(parent).resolve();out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('existing full stage must keep its history')
    job,c=tp.validate(parent);out.mkdir(parents=True,exist_ok=True)
    shutil.copy2(parent/'identity_reference.png',out/'identity_reference.png')
    imported={};(out/'imports').mkdir()
    for slot in tp.SLOTS:
        src,entry=tp.selected_part(parent,slot)
        if entry['geometry']['blockers']:raise ValueError('parent static part is blocked')
        dst=out/'imports'/(slot+'.png');shutil.copy2(src,dst)
        imported[slot]={'file':str(dst.relative_to(out)),'sha256':tp.sha(dst),
           'joints':c['slots'][slot]['joints'],'parent_file':str(src),
           'source_attempt_count':len(job['attempts'][slot]),'parent_geometry':entry['geometry']}
    contract={'version':'template-full-static-v1.1','profile':c['profile'],'size':1024,
              'rules':tp.RULES,'imported':imported,'slots':{},'order':list(ORDER)}
    for slot in EXTRAS:
        folder=out/slot;folder.mkdir();mask,joints=geometry(slot,c['profile'])
        if slot=='arm_far':guide=ImageOps.mirror(tp.plate('arm_near',c['profile'])[0])
        else:
            a=np.full((1024,1024,4),255,np.uint8);a[:,:,:3]=(230,233,236)
            a[mask]=(225,218,209,255)
            yy,xx=np.indices(mask.shape)
            if slot=='head':
                a[mask]=(230,191,161,255);a[mask&((yy<350)|((xx<420)&(yy<650)))]=(48,42,44,255)
            if slot=='leg_far':a[mask&(yy>555)]=(48,44,46,255)
            if slot=='weapon':
                a[mask]=(205,211,222,255);a[mask&(yy>610)]=(174,142,84,255)
                a[mask&(yy>680)&(yy<865)]=(54,42,46,255)
            guide=Image.fromarray(a)
        guide.save(folder/'guide.png');Image.fromarray(mask.astype('uint8')*255).save(folder/'structure_mask.png')
        overlay=guide.copy();draw=ImageDraw.Draw(overlay)
        for name,(x,y) in joints.items():
            draw.ellipse((x-8,y-8,x+8,y+8),fill='cyan',outline='black');draw.text((x+12,y),name,fill='black')
        overlay.save(folder/'joints.png')
        (folder/'prompt.txt').write_text(tp.PROMPT.format(description=DESCRIPTIONS[slot],identity=identity),encoding='utf-8')
        contract['slots'][slot]={'joints':joints,'guide_sha256':tp.sha(folder/'guide.png'),
                                 'mask_sha256':tp.sha(folder/'structure_mask.png')}
    tp.write(out/'contract.json',contract)
    tp.write(out/'job.json',{'phase':'full_static_parts','source_kind':job['source_kind'],
          'source_note':job['source_note'],'source_sha256':tp.sha(out/'identity_reference.png'),
          'contract_sha256':tp.sha(out/'contract.json'),'identity':identity,'parent_identity_text':job['identity'],
          'attempts':{slot:[] for slot in EXTRAS},'parent':str(parent),
          'parent_contract_sha256':job['contract_sha256'],'parent_generation_counts':{s:len(v) for s,v in job['attempts'].items()},
          'binding_performed':False,'animations_generated':False})


def selected(out,slot):
    out=Path(out);job,c=tp.validate(out)
    if slot=='head' and (out/'head_reference.json').exists():
        import template_head_proportions as hp
        return hp.select(out)
    if slot in c['imported']:
        row=c['imported'][slot];path=out/row['file']
        if tp.sha(path)!=row['sha256']:raise ValueError('imported part changed')
        return path,{'file':row['file'],'geometry':row['parent_geometry'],'registered_sha256':row['sha256']},row['joints']
    path,entry=tp.selected_part(out,slot)
    return path,entry,c['slots'][slot]['joints']


def layout(contract):
    hip=np.array([500.,800.]);torso_scale=.70;tj=contract['imported']['torso']['joints']
    torso_offset=hip-np.array(tj['hip'])*torso_scale
    shoulder=torso_offset+np.array(tj['shoulder'])*torso_scale
    joints={k:v['joints'] for k,v in {**contract['slots'],**contract['imported']}.items()}
    transforms={'torso':(torso_scale,torso_offset),
      'arm_near':(.68,shoulder-np.array(joints['arm_near']['shoulder'])*.68),
      'arm_far':(.68,shoulder+[-35,0]-np.array(joints['arm_far']['shoulder'])*.68),
      'leg_near':(.83,hip+[20,0]-np.array(joints['leg_near']['hip'])*.83),
      'leg_far':(.83,hip+[-20,0]-np.array(joints['leg_far']['hip'])*.83),
      'hips':(.50,hip-np.array(joints['hips']['hip'])*.50),
      'head':(.29,torso_offset+np.array(tj['neck'])*torso_scale-np.array(joints['head']['head_base'])*.29)}
    s,o=transforms['arm_near'];grip=o+np.array(joints['arm_near']['grip'])*s
    transforms['weapon']=(.72,grip-np.array(joints['weapon']['grip'])*.72)
    return transforms


def head_mount(images,transforms,contract,out=None):
    """Fit a complete neck to the collar using common bounded seating rules."""
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'game-sprite-animator/scripts'))
    import layer_parts as lp
    def mapped(slot):
        s,o=transforms[slot];x,y=o
        return np.asarray(images[slot].transform((1024,1536),Image.Transform.AFFINE,
            (1/s,0,-x/s,0,1/s,-y/s),Image.Resampling.BICUBIC))[:,:,3]>128
    torso=mapped('torso');row,columns,_=lp.neck_core(torso)
    hs,ho=transforms['head'];anchor=np.array(contract['slots']['head']['joints']['head_base'],dtype=float)
    neck_world=ho+anchor*hs;mask=np.asarray(images['head'])[:,:,3]>128
    if out is not None and (Path(out)/'head_reference.json').exists():
        import template_head_proportions as hp
        path,entry,joints=hp.select(out);manifest=tp.read(Path(out)/'head_reference.json')
        ref=Image.open(Path(out)/manifest['reference']['file']).convert('RGBA')
        rd=hp.descriptor(np.asarray(ref)[:,:,3]>128);cd=hp.descriptor(mask)
        identity=lp.reference(Path(out)/'identity_reference.png')
        source_ground=int(np.nonzero(identity[:,:,3]>128)[0].max())
        target_ground=max(int(np.nonzero(mapped(s))[0].max()) for s in ('leg_near','leg_far'))
        source_depth=source_ground-rd['head_bottom_row']
        if source_depth<=0:raise ValueError('reference head must use the full identity image coordinates')
        scale=(target_ground-row)/source_depth*rd['head_height_px']/cd['head_height_px']
        anchor=np.array(joints['head_base']);transforms['head']=(scale,neck_world-anchor*scale)
        fit={'strategy':'reference_proportions_uniform_scale_translation_only','base_scale':scale,
             'scale':scale,'nominal_neck_world':neck_world.tolist(),'reference_head':rd,
             'candidate_head':cd,'source_body_depth_px':source_depth,
             'target_body_depth_px':target_ground-row,'max_scale_growth':1.0,
             'collar_does_not_control_head_scale':True}
        try:
            dx,dy=lp.seat_head(mapped('head'),torso)
            s,o=transforms['head'];transforms['head']=(s,o+[dx,dy])
            fit.update(translation_px=[dx,dy],coverage=lp.neck_coverage(mapped('head'),torso),
                       source_bind_anchor=((neck_world-transforms['head'][1])/s).tolist())
        except lp.Rejected as exc:fit['error']=str(exc)
        return fit
    x,y=map(int,np.rint(anchor));lo=hi=x
    while lo>0 and mask[y,lo-1]:lo-=1
    while hi<1023 and mask[y,hi+1]:hi+=1
    width=hi-lo+1 if mask[y,x] else 0
    fit={'base_scale':hs,'neck_source_width_px':width,'collar_core_width_px':len(columns),
         'max_scale_growth':1.25,'nominal_neck_world':neck_world.tolist()}
    # Grow uniformly, never just stretch the face, to support the collar cross-section.
    if width:
        scale=max(hs,min(hs*1.25,(len(columns)*.95+2)/width))
        transforms['head']=(scale,neck_world-anchor*scale)
    try:
        dx,dy=lp.seat_head(mapped('head'),torso)
        s,o=transforms['head'];transforms['head']=(s,o+[dx,dy])
        fit.update(scale=s,translation_px=[dx,dy],coverage=lp.neck_coverage(mapped('head'),torso),
                   source_bind_anchor=((neck_world-transforms['head'][1])/s).tolist())
    except lp.Rejected as exc:fit['error']=str(exc)
    return fit


def assemble(out):
    out=Path(out);job,c=tp.validate(out);transforms=layout(c)
    canvas=Image.new('RGBA',(1024,1536));joints_canvas={};reports={}
    (out/'assembled_layers').mkdir(exist_ok=True)
    sources={slot:selected(out,slot) for slot in c['order']}
    images={slot:Image.open(item[0]).convert('RGBA') for slot,item in sources.items()}
    mount=head_mount(images,transforms,c,out)
    for slot in c['order']:
        path,entry,joints=sources[slot];s,o=transforms[slot];x,y=map(float,o)
        im=images[slot].transform(canvas.size,Image.Transform.AFFINE,
                (1/s,0,-x/s,0,1/s,-y/s),Image.Resampling.BICUBIC)
        im.save(out/'assembled_layers'/(slot+'.png'));canvas.alpha_composite(im)
        joints_canvas[slot]={k:(o+np.array(v)*s).tolist() for k,v in joints.items()}
        reports[slot]=entry
    # Head rig pivot remains the known torso neck joint after artwork seating.
    joints_canvas['head']['head_base']=mount['nominal_neck_world']
    canvas.save(out/'character_draft.png')
    bg=Image.new('RGBA',canvas.size,(225,230,237,255));bg.alpha_composite(canvas);bg.convert('RGB').save(out/'character_draft.jpg')
    overlay=bg.copy();draw=ImageDraw.Draw(overlay)
    for slot,points in joints_canvas.items():
        for name,(x,y) in points.items():
            draw.ellipse((x-7,y-7,x+7,y+7),fill='cyan',outline='black');draw.text((x+10,y),slot+':'+name,fill='black')
    overlay.convert('RGB').save(out/'assembly_joints.jpg')
    blockers={slot:entry['geometry']['blockers'] for slot,entry in reports.items() if entry['geometry']['blockers']}
    if 'error' in mount:blockers['head_mount']=[mount['error']]
    depth_pairs=[('hips','leg_far'),('hips','leg_near'),('arm_far','torso'),('head','torso'),('weapon','arm_near')]
    bad_depth=[a+' must precede '+b for a,b in depth_pairs if c['order'].index(a)>c['order'].index(b)]
    if bad_depth:blockers['layer_order']=bad_depth
    report={'status':'blocked' if blockers else 'static_geometry_met_needs_visual_review','binding_approved':False,
      'full_character_bound':False,'idle_walk_generated':False,'contract_sha256':job['contract_sha256'],
      'parts':reports,'joints':joints_canvas,'blockers':blockers,
      'head_mount':mount,'processor_sha256':tp.sha(__file__),
      'layout':{k:{'scale':s,'offset':o.tolist()} for k,(s,o) in transforms.items()},
      'note':'Geometry and a static assembly only. Layer ownership, facial identity, grips, seams and all exposed hidden regions require visual review.'}
    tp.write(out/'assembly_report.json',report)
    return {'status':report['status'],'blockers':blockers,'preview':str(out/'character_draft.jpg')}


def inspect(out):
    """Static numerical attachments plus an offline visual-review surface."""
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'game-sprite-animator/scripts'))
    import layer_parts as lp
    out=Path(out);assemble(out);job,c=tp.validate(out);report=tp.read(out/'assembly_report.json')
    masks={s:np.asarray(Image.open(out/'assembled_layers'/(s+'.png')))[:,:,3]>128 for s in ORDER}
    errors=[];lengths={};attachments={}
    clipped={}
    for slot in ORDER:
        path,_,_=selected(out,slot);src=np.asarray(Image.open(path))[:,:,3]>128
        y,x=np.nonzero(src);s=report['layout'][slot]['scale'];ox,oy=report['layout'][slot]['offset']
        clipped[slot]=int(((x*s+ox<0)|(x*s+ox>=1024)|(y*s+oy<0)|(y*s+oy>=1536)).sum())
        if clipped[slot]:errors.append({'part':slot,'what':'art clipped by assembled canvas','pixels':clipped[slot]})
    for slot in ('arm_near','arm_far','leg_near','leg_far'):
        names=('shoulder','elbow','wrist') if slot.startswith('arm') else ('hip','knee','ankle')
        try:
            lengths[slot]=lp.check_limb(slot,masks[slot],np.array([report['joints'][slot][n] for n in names])).tolist()
        except lp.Rejected as exc:errors.append({'part':slot,'what':str(exc)})
    for kind in ('arm','leg'):
        if kind+'_near' in lengths and kind+'_far' in lengths:
            try:lp.check_pair(kind,np.array(lengths[kind+'_near']),np.array(lengths[kind+'_far']))
            except lp.Rejected as exc:errors.append({'part':kind,'what':str(exc)})
    try:lp.check_neck_contact(masks)
    except lp.Rejected as exc:errors.append({'part':'neck','what':str(exc)})
    yy,xx=np.indices((1536,1024))
    def overlap(name,a,b,point,radius):
        x,y=point;disk=(xx-x)**2+(yy-y)**2<=radius**2
        share=float((masks[a]&masks[b])[disk].mean());attachments[name]=share
        if share<.95:errors.append({'part':name,'what':'static attachment overlap below 95%','coverage':share})
    for side in ('near','far'):
        overlap('shoulder_'+side,'arm_'+side,'torso',report['joints']['arm_'+side]['shoulder'],8)
        overlap('hip_'+side,'leg_'+side,'hips',report['joints']['leg_'+side]['hip'],8)
    overlap('hand_weapon','arm_near','weapon',report['joints']['weapon']['grip'],8)
    overlap('waist','hips','torso',report['joints']['hips']['waist'],8)
    feet={s:int(np.nonzero(masks[s])[0].max()) for s in ('leg_near','leg_far')}
    # A diagnostic, not an assertion that planted feet stay still in animation.
    feet['static_bottom_difference_px']=abs(feet['leg_near']-feet['leg_far'])
    qa={'status':'blocked' if errors or report['blockers'] else 'static_numerical_checks_met',
        'scope':'full assembled static pose only','errors':errors,'part_blockers':report['blockers'],
        'attachments':attachments,'bone_lengths_px':lengths,'feet':feet,
        'clipped_source_pixels':clipped,
        'full_character_bound':False,'idle_walk_generated':False,
        'assets':{s:tp.sha(out/'assembled_layers'/(s+'.png')) for s in ORDER}}
    tp.write(out/'static_checks.json',qa)
    # Detail crops use known joints and fixed normalized sizes, never hand-marked image coordinates.
    centers=[('neck',report['joints']['head']['head_base']),('near shoulder',report['joints']['arm_near']['shoulder']),
             ('hip roots',report['joints']['hips']['hip']),('sword grip',report['joints']['weapon']['grip'])]
    whole=Image.open(out/'character_draft.jpg');sheet=Image.new('RGB',(1440,420),(240,243,246));draw=ImageDraw.Draw(sheet)
    for i,(label,(x,y)) in enumerate(centers):
        sheet.paste(whole.crop((round(x-110),round(y-110),round(x+110),round(y+110))).resize((340,340)),(i*360+10,45))
        draw.text((i*360+15,15),label,fill='black')
    sheet.save(out/'attachment_details.jpg')
    parts={}
    names={'head':'头部','torso':'躯干','arm_near':'近侧手臂','arm_far':'远侧手臂',
           'leg_near':'近侧腿','leg_far':'远侧腿','hips':'髋部衬层','weapon':'剑'}
    for slot in ORDER:
        path,entry,joints=selected(out,slot);s=report['layout'][slot]['scale'];o=np.array(report['layout'][slot]['offset'])
        if slot=='head':joints={**joints,'head_base':report['head_mount'].get('source_bind_anchor',joints['head_base'])}
        with Image.open(path) as part_image:size=list(part_image.size)
        parts[slot]={'image':'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode(),
                     'scale':s,'offset':o.tolist(),'joints':joints,'label':names[slot],
                     'size':size}
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>剑客完整分层预览</title><style>
*{box-sizing:border-box}body{margin:0;background:#111925;color:#e7edf5;font:16px/1.65 system-ui,sans-serif}main{max-width:1240px;margin:auto;padding:26px}h1{font-size:28px;margin:4px 0}p{color:#acbace}label{margin-right:18px;display:inline-block}input{vertical-align:middle}canvas{width:min(100%,800px);display:block;margin:20px auto;background:#e1e6ed;border-radius:14px}.parts{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}.parts label{padding:6px 10px;background:#243247;border-radius:8px}.status{color:#efbd7b}button{background:#365476;border:0;color:white;padding:8px 14px;border-radius:8px;cursor:pointer}.gallery{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.gallery figure{margin:0;background:#243247;padding:10px;border-radius:10px}.gallery img{width:100%;background:#dce2e9;border-radius:8px}.gallery figcaption{margin-bottom:8px}@media(max-width:700px){.gallery{grid-template-columns:repeat(2,1fr)}main{padding:16px}}</style>
<main><span class="status">完整静态组装 · 待动态验收</span><h1>武侠剑客：八个独立图层</h1><p>沿用已认可的短发短衣适配，补齐头、远侧手臂、远侧腿、髋部与剑。可隐藏图层或移开双臂，查看挂接与遮挡。尚未生成完整人物待机、走路。</p>
<label>移开双臂 <input id="apart" type="range" min="0" max="220" value="0"></label><label><input id="joints" type="checkbox"> 显示关节</label><button id="reset">恢复显示</button>
<div class="parts" id="toggles"></div><canvas id="stage" width="1408" height="1536"></canvas><h2>独立部件</h2><div class="gallery" id="gallery"></div>
<p>这是分层素材与静态挂接预览。静态数值通过不能代替完整骨骼动作、脚步接地和持剑活动验收。</p></main><script>
const parts=__PARTS__,order=__ORDER__,images={},visible=new Set(order),canvas=document.getElementById('stage'),ctx=canvas.getContext('2d');
for(const key of order){const p=parts[key];const label=document.createElement('label');const check=document.createElement('input');check.type='checkbox';check.checked=true;check.dataset.part=key;check.onchange=()=>{check.checked?visible.add(key):visible.delete(key);draw()};label.append(check,document.createTextNode(' '+p.label));document.getElementById('toggles').append(label);const f=document.createElement('figure'),caption=document.createElement('figcaption'),img=new Image();caption.textContent=p.label;img.src=p.image;f.append(caption,img);document.getElementById('gallery').append(f)}
Promise.all(order.map(k=>new Promise(resolve=>{const im=new Image();im.onload=resolve;im.src=parts[k].image;images[k]=im}))).then(draw);
function draw(){ctx.fillStyle='#e1e6ed';ctx.fillRect(0,0,1408,1536);const gap=+document.getElementById('apart').value;for(const k of order){if(!visible.has(k))continue;const p=parts[k],x=192+p.offset[0]+(k==='arm_far'?-gap:(k==='arm_near'||k==='weapon'?gap:0)),y=p.offset[1];ctx.drawImage(images[k],x,y,p.size[0]*p.scale,p.size[1]*p.scale);if(document.getElementById('joints').checked){for(const [name,point]of Object.entries(p.joints)){const a=x+point[0]*p.scale,b=y+point[1]*p.scale;ctx.beginPath();ctx.arc(a,b,6,0,Math.PI*2);ctx.fillStyle='#00bcd4';ctx.fill();ctx.fillStyle='#18283b';ctx.font='15px sans-serif';ctx.fillText(name,a+8,b)}}}}
document.getElementById('apart').oninput=draw;document.getElementById('joints').onchange=draw;document.getElementById('reset').onclick=()=>{order.forEach(k=>visible.add(k));document.querySelectorAll('[data-part]').forEach(c=>c.checked=true);document.getElementById('apart').value=0;document.getElementById('joints').checked=false;draw()};
</script></html>'''
    (out/'preview.html').write_text(document.replace('__PARTS__',json.dumps(parts)).replace('__ORDER__',json.dumps(c['order'])),encoding='utf-8')
    return qa


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('parent');a.add_argument('out');a.add_argument('--identity',required=True)
    a=sub.add_parser('assemble');a.add_argument('out')
    a=sub.add_parser('inspect');a.add_argument('out')
    args=vars(p.parse_args());command=args.pop('command');print(globals()[command](**args))
