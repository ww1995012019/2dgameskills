"""Bind approved full-template layers to the existing humanoid runtime.

Development adapter: known source joints, existing writer, mesh and idle/walk.
No inferred replacement joints, new art, generation-budget reset or final pass.
"""
import argparse
import math
from pathlib import Path
import sys
import numpy as np
from PIL import Image
import template_puppet as tp
import template_full_character as full
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'game-sprite-animator/scripts'))
import layer_parts as lp
from sprite_anim.rig import Body
from sprite_anim.motions import build_clips
from sprite_anim.puppet_check import core_mask,HOLE_SHARE


def approved(stage):
    stage=Path(stage);job,c=tp.validate(stage);a=tp.read(stage/'static_user_approval.json')
    if a['contract_sha256']!=tp.sha(stage/'contract.json'):raise ValueError('static approval contract changed')
    for n,h in a['assets'].items():
        if tp.sha(stage/n)!=h:raise ValueError('static approval asset changed: '+n)
    qa=tp.read(stage/'static_checks.json');report=tp.read(stage/'assembly_report.json')
    if qa['status']!='static_numerical_checks_met' or report['blockers']:raise ValueError('static geometry remains blocked')
    for slot in full.ORDER:
        _,entry,_=full.selected(stage,slot)
        if entry['geometry']['blockers']:raise ValueError('part remains blocked: '+slot)
        if tp.sha(stage/'assembled_layers'/(slot+'.png'))!=qa['assets'][slot]:raise ValueError('assembled layer changed: '+slot)
    return report,c


def canonical_arm(points):
    """Keep source endpoints/lengths but choose a legal forward elbow for motion.

    Source rest joints remain untouched. A reflected rear-arm guide may depict
    a backward elbow; mirror that elbow across the shoulder-wrist line for the
    target carried pose rather than relaxing the runtime anatomical limit.
    """
    root,el,wr=np.asarray(points,dtype=float);up=lp.angle_down(root,el);lo=lp.angle_down(el,wr)
    delta=(lo-up+180)%360-180
    changed=delta<0
    if changed:
        line=wr-root;projection=root+line*((el-root)@line)/(line@line)
        el=2*projection-el;up=lp.angle_down(root,el);lo=lp.angle_down(el,wr)
    return up,(lo-up+180)%360-180,changed


def build_spec(images,joints,order):
    masks={s:np.asarray(a)[:,:,3]>128 for s,a in images.items()}
    j={s:{n:np.asarray(p,float) for n,p in row.items()} for s,row in joints.items()}
    chains={s:np.array([j[s][n] for n in (('shoulder','elbow','wrist') if s.startswith('arm') else ('hip','knee','ankle'))]) for s in ('arm_near','arm_far','leg_near','leg_far')}
    lengths={s:lp.check_limb(s,masks[s],p) for s,p in chains.items()}
    for name in ('arm','leg'):lp.check_pair(name,lengths[name+'_near'],lengths[name+'_far'])
    lp.check_neck_contact(masks)
    ppu=float((sum(lengths['leg_near'])+sum(lengths['leg_far']))/2/lp.LEG_LEN)
    hip=j['hips']['hip'];waist=j['hips']['waist'];neck=j['head']['head_base'];u=(neck-waist)/np.linalg.norm(neck-waist);forward=np.array([-u[1],u[0]])
    def along(p):
        v=(p-waist)/ppu;return [float(v@forward),float(v@u)]
    pelvic=(waist-hip)/np.linalg.norm(waist-hip);pforward=np.array([-pelvic[1],pelvic[0]])
    def seat(p):
        v=(p-hip)/ppu;return [float(np.clip(v@pforward,-lp.HIP_SPREAD,lp.HIP_SPREAD)),float(v@pelvic)]
    near=j['leg_near'];far=j['leg_far'];legs=sum(lengths['leg_near'])/ppu
    seat_up=(seat(near['hip'])[1]+seat(far['hip'])[1])/2
    mid=lp.REACH_MID*legs;low=math.sqrt((lp.REACH_END*legs)**2-(lp.CONTACT_AHEAD*lp.STRIDE*legs)**2)
    soles={s:lp.read_leg(masks[s]) for s in ('leg_near','leg_far')}
    ankle_h=float(np.mean([soles[s]['heel'][1]-j[s]['ankle'][1] for s in soles])/ppu)
    head_top=int(np.nonzero(masks['head'])[0].min())
    body=dict(thigh=float(lengths['leg_near'][0]/ppu),shin=float(lengths['leg_near'][1]/ppu),
      up_arm=float(lengths['arm_near'][0]/ppu),lo_arm=float(lengths['arm_near'][1]/ppu),
      ankle_h=ankle_h,hip_h=ankle_h+lp.GAIT_DROP+(mid+low)/2-seat_up,
      pelvis_len=float(np.linalg.norm(waist-hip)/ppu),chest_len=float(along(neck)[1]),neck_len=0.,
      head_size=float((neck[1]-head_top)/ppu/30),leg_soft=lp.IK_SOFT,foot_wrap=True,
      sh_n_at=along(j['arm_near']['shoulder']),sh_f_at=along(j['arm_far']['shoulder']),
      hip_n_at=[seat(near['hip'])[0],seat_up],hip_f_at=[seat(far['hip'])[0],seat_up])
    for side,word in (('n','near'),('f','far')):
        slot='leg_'+word
        for target,source in (('heel','heel'),('ball','toe')):
            body['foot_'+side+'_'+target]=((soles[slot][source]-j[slot]['ankle'])*[1,-1]/ppu).tolist()
    grip=j['weapon']['grip'];wr=j['arm_near']['wrist'];el=j['arm_near']['elbow'];v=(wr-el)*[1,-1];d=(grip-wr)*[1,-1]
    body.update(weapon_grip_along=float(d@v/(v@v)),weapon_grip_across=float(d@np.array([-v[1],v[0]])/(v@v)))
    yy,xx=np.indices(masks['weapon'].shape);dist=(xx-grip[0])**2+(yy-grip[1])**2;dist[~masks['weapon']]=-1
    ty,tx=np.unravel_index(dist.argmax(),dist.shape);tip=np.array([tx,ty]);axis=(tip-grip)/np.linalg.norm(tip-grip)
    y,x=np.nonzero(masks['weapon']);back=max(float(-((x-grip[0])*axis[0]+(y-grip[1])*axis[1]).min()/ppu),0.)
    reach=float(np.linalg.norm(tip-grip)/ppu);body.update(weapon_front=reach,weapon_back=back)
    width=.5*float(masks['torso'][round(waist[1])].sum());core_px=lp.CORE_SHARE*width
    core=core_mask(images['torso'].size,waist,hip,core_px);solid=masks['torso']|masks['hips']|masks['leg_near']|masks['leg_far']
    if core.any() and (~solid[core]).mean()>HOLE_SHARE:raise ValueError('body core is open')
    data={}
    def tube(slot,bones,rest,**extra):
        length=sum(np.linalg.norm(np.diff(rest,axis=0),axis=1));radius=float(masks[slot].sum()/(2*length))
        data[slot]=dict(kind='tube',bones=bones,rest=np.asarray(rest).tolist(),radius=radius,**extra)
    for side,word in (('n','near'),('f','far')):
        s='arm_'+word;tube(s,['sh_'+side,'el_'+side,'wr_'+side],chains[s])
        s='leg_'+word;rest=chains[s];shin=(rest[2]-rest[1])/np.linalg.norm(rest[2]-rest[1]);radius=masks[s].sum()/(2*sum(lengths[s]))
        tube(s,['hip_'+side,'kn_'+side,'an_'+side],rest,foot=dict(side=side,ankle=rest[2].tolist(),shin_dir=shin.tolist(),blend=float(radius*.6),width=float(radius),rest_angle=0.))
    hem=int(np.nonzero(masks['torso'])[0].max());skirt_len=max(hem-hip[1],.25*sum(lengths['leg_near']))*1.1
    down=(near['knee']+far['knee'])/2-hip;skirt=hip+down/np.linalg.norm(down)*skirt_len
    tube('torso',['skirt','hip','waist','head_base'],[skirt,hip,waist,neck])
    data['head']=dict(kind='rigid',follow=['head_base','head_rot'],anchor=neck.tolist())
    data['hips']=dict(kind='rigid',follow=['hip','body_rot'],anchor=hip.tolist())
    data['weapon']=dict(kind='rigid',follow=['wr_n','wep_a'],anchor=grip.tolist())
    body_rot=lp.angle_up(hip,waist);chest_rot=lp.angle_up(waist,neck);weapon_angle=lp.angle_down(grip,tip)
    canonical={s:canonical_arm(chains[s]) for s in ('arm_near','arm_far')}
    gait={}
    for clip,lean in (('idle',9.),('walk',8.)):
        an,ae,_=canonical['arm_near'];af,fe,_=canonical['arm_far']
        gait[clip]=dict(arm_n=[an+lean,2.5,ae,1.5],arm_f=[af+lean,1.8 if clip=='idle' else 15.,fe,2.6 if clip=='idle' else 5.],wep=weapon_angle-(an+ae),wep_sway=1.5)
    gait['walk'].update(stride=lp.STRIDE*legs,bob=(mid-low)/2)
    puppet=dict(px_per_unit=ppu,joints={n:p.tolist() for n,p in dict(hip=hip,waist=waist,neck=neck,head_base=neck,wr_n=wr,el_n=el).items()},
      rest_angles=dict(head_rot=0.,wep_a=weapon_angle,chest_rot=chest_rot,body_rot=body_rot),
      skirt_len=skirt_len/ppu,core_radius=core_px/ppu,rest_arm={s:[j['arm_'+w]['wrist'].tolist(),j['arm_'+w]['elbow'].tolist()] for s,w in (('n','near'),('f','far'))},
      layers={s:data[s] for s in order},chains={},source='source.png',weapon_length=reach,weapon_back=back)
    spec=dict(puppet=puppet,body=body,gait=gait)
    # Validate legal runtime gait parameters now, before writing any accepted rig.
    build_clips(gait=gait,body=Body.from_spec(body))
    return spec,{'px_per_unit':ppu,'cover':1.,'spill':0.,'fits':{},
       'reference_kind':'user-approved assembled artwork, not original identity coverage',
       'canonical_arm_target':{s:{'upper_angle':v[0],'elbow_angle':v[1],'source_backward_bend_retargeted':v[2]} for s,v in canonical.items()}}


def bind(stage,out):
    stage=Path(stage).resolve();out=Path(out).resolve();report,c=approved(stage)
    if out.exists():raise ValueError('binding destination exists; preserve prior rig')
    images={s:Image.open(stage/'assembled_layers'/(s+'.png')).convert('RGBA') for s in full.ORDER}
    spec,metrics=build_spec(images,report['joints'],c['order']);out.mkdir(parents=True)
    arrays={s:np.asarray(images[s]) for s in c['order']};ref=np.asarray(Image.open(stage/'character_draft.png').convert('RGBA'))
    state=dict(layers=arrays,joint_chains={s:spec['puppet']['layers'][s].get('rest',[]) for s in c['order'] if spec['puppet']['layers'][s]['kind']=='tube'},
      scope='known-joint numerical binding only; motion and visual approval separate',static_user_approval_sha256=tp.sha(stage/'static_user_approval.json'))
    lp.write_binding(str(out),'Template character',ref,arrays,spec,metrics,state)
    provenance={'stage':str(stage),'assets':{str(p.relative_to(out)):tp.sha(p) for p in out.rglob('*') if p.is_file()},
      'source_approval_sha256':tp.sha(stage/'static_user_approval.json'),'source_contract_sha256':tp.sha(stage/'contract.json'),
      'source_assembled_layers':{s:tp.sha(stage/'assembled_layers'/(s+'.png')) for s in full.ORDER},
      'processor_sha256':tp.sha(__file__),'full_character_bound':True,'motion_approved':False,'final_visual_pass':False}
    tp.write(out/'provenance.json',provenance);return metrics


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage');p.add_argument('out');a=p.parse_args();print(bind(a.stage,a.out))
