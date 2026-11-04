"""Known-joint humanoid binding; preserves supplied art, no model calls or pose inference."""
import math
import numpy as np
import layer_parts as lp
from sprite_anim.rig import Body
from sprite_anim.motions import build_clips
from sprite_anim.puppet_check import core_mask, HOLE_SHARE

FOLDED_SHARE = 0.05   # of the arm's length: closer shoulder-wrist spacing cannot define a mirror line

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
        line=wr-root;reach=np.linalg.norm(el-root)+np.linalg.norm(wr-el)
        # A wrist on the shoulder leaves no line to mirror the elbow across.
        if np.linalg.norm(line)<FOLDED_SHARE*reach:
            raise ValueError('arm: shoulder and wrist nearly coincide with a backward elbow; supply a less folded rest arm')
        projection=root+line*((el-root)@line)/(line@line)
        el=2*projection-el;up=lp.angle_down(root,el);lo=lp.angle_down(el,wr)
    return up,(lo-up+180)%360-180,changed


def head_length(mask, neck):
    """Head length from its neck seat along the head's own axis (neck to the art's centroid).

    A tilted head measures as it would upright; for an upright head this is the height of its top.
    """
    ys, xs = np.nonzero(mask)
    axis = np.array([xs.mean(), ys.mean()]) - neck
    axis /= max(float(np.linalg.norm(axis)), 1e-9)
    return float(((np.column_stack([xs, ys]) - neck) @ axis).max())


def free_arm_carriage(upper_length, lower_length, elbow_angle, chest_lean):
    """A free walking arm hangs below its shoulder, with its measured elbow bend.

    Cancelling the two-bone chain's horizontal offset gives a neutral swing
    centre without inventing a new elbow or stretching the source. Otherwise a
    forward-bent source pose may keep the empty fist beside the sword while its
    forearm is hidden behind the chest throughout the forward half of a walk.
    """
    bend = math.radians(elbow_angle)
    offset = math.atan2(lower_length * math.sin(bend),
                        upper_length + lower_length * math.cos(bend))
    return chest_lean - math.degrees(offset)


def build_spec(images,joints,order,head_attachment='cap_cover', weapon_hand_binding=False):
    if head_attachment not in ('cap_cover', 'socket'):
        raise ValueError('head_attachment: expected cap_cover or socket')
    masks={s:np.asarray(a)[:,:,3]>128 for s,a in images.items()}
    j={s:{n:np.asarray(p,float) for n,p in row.items()} for s,row in joints.items()}
    chains={s:np.array([j[s][n] for n in (('shoulder','elbow','wrist') if s.startswith('arm') else ('hip','knee','ankle'))]) for s in ('arm_near','arm_far','leg_near','leg_far')}
    lengths={s:lp.check_limb(s,masks[s],p) for s,p in chains.items()}
    for name in ('arm','leg'):lp.check_pair(name,lengths[name+'_near'],lengths[name+'_far'])
    if head_attachment == 'socket':
        from socket_mount import validate_socket
        validate_socket(masks['head'], masks['torso'], j['head']['head_base'])
    else:
        lp.check_neck_contact(masks)
    ppu=float((sum(lengths['leg_near'])+sum(lengths['leg_far']))/2/lp.LEG_LEN)
    hip=j['hips']['hip'];waist=j['hips']['waist'];neck=j['head']['head_base'];u=(neck-waist)/np.linalg.norm(neck-waist);forward=np.array([-u[1],u[0]])
    def along(p):
        v=(p-waist)/ppu;return [float(v@forward),float(v@u)]
    pelvic=(waist-hip)/np.linalg.norm(waist-hip);pforward=np.array([-pelvic[1],pelvic[0]])
    def seat(p):
        v=(p-hip)/ppu;return [float(np.clip(v@pforward,-lp.HIP_SPREAD,lp.HIP_SPREAD)),float(v@pelvic)]
    near=j['leg_near'];far=j['leg_far'];legs=sum(lengths['leg_near'])/ppu;legs_f=sum(lengths['leg_far'])/ppu
    seat_up=(seat(near['hip'])[1]+seat(far['hip'])[1])/2
    # Each leg keeps its measured length. The far hip seat moves by the length difference
    # times the standing reach, so both legs stand equally extended: no limp, both feet down.
    seat_up_f=seat_up+(legs_f-legs)*lp.REACH_MID
    mid=lp.REACH_MID*legs;low=math.sqrt((lp.REACH_END*legs)**2-(lp.CONTACT_AHEAD*lp.STRIDE*legs)**2)
    soles={s:lp.read_leg(masks[s]) for s in ('leg_near','leg_far')}
    ankle_h=float(np.mean([soles[s]['heel'][1]-j[s]['ankle'][1] for s in soles])/ppu)
    head_len=head_length(masks['head'],neck)
    body=dict(thigh=float(lengths['leg_near'][0]/ppu),shin=float(lengths['leg_near'][1]/ppu),
      up_arm=float(lengths['arm_near'][0]/ppu),lo_arm=float(lengths['arm_near'][1]/ppu),
      ankle_h=ankle_h,hip_h=ankle_h+lp.GAIT_DROP+(mid+low)/2-seat_up,
      pelvis_len=float(np.linalg.norm(waist-hip)/ppu),chest_len=float(along(neck)[1]),neck_len=0.,
      head_size=float(head_len/ppu/30),leg_soft=lp.IK_SOFT,foot_wrap=True,
      sh_n_at=along(j['arm_near']['shoulder']),sh_f_at=along(j['arm_far']['shoulder']),
      hip_n_at=[seat(near['hip'])[0],seat_up],hip_f_at=[seat(far['hip'])[0],seat_up_f],
      thigh_f=float(lengths['leg_far'][0]/ppu),shin_f=float(lengths['leg_far'][1]/ppu),
      up_arm_f=float(lengths['arm_far'][0]/ppu),lo_arm_f=float(lengths['arm_far'][1]/ppu))
    for side,word in (('n','near'),('f','far')):
        slot='leg_'+word
        for target,source in (('heel','heel'),('ball','toe')):
            body['foot_'+side+'_'+target]=((soles[slot][source]-j[slot]['ankle'])*[1,-1]/ppu).tolist()
    wr=j['arm_near']['wrist'];el=j['arm_near']['elbow'];v=(wr-el)*[1,-1]
    if 'weapon' in images:
        grip=j['weapon']['grip'];d=(grip-wr)*[1,-1]
        body.update(weapon_grip_along=float(d@v/(v@v)),weapon_grip_across=float(d@np.array([-v[1],v[0]])/(v@v)))
        yy,xx=np.indices(masks['weapon'].shape);dist=(xx-grip[0])**2+(yy-grip[1])**2;dist[~masks['weapon']]=-1
        ty,tx=np.unravel_index(dist.argmax(),dist.shape);tip=np.array([tx,ty]);axis=(tip-grip)/np.linalg.norm(tip-grip)
        y,x=np.nonzero(masks['weapon']);back=max(float(-((x-grip[0])*axis[0]+(y-grip[1])*axis[1]).min()/ppu),0.)
        reach=float(np.linalg.norm(tip-grip)/ppu);body.update(weapon_front=reach,weapon_back=back)
    else:
        grip=wr+(wr-el)*.14;reach=back=0.;tip=grip+np.array([1.,-1.])
    width=.5*float(masks['torso'][round(waist[1])].sum());core_px=lp.CORE_SHARE*width
    core=core_mask(images['torso'].size,waist,hip,core_px);solid=masks['torso']|masks['hips']|masks['leg_near']|masks['leg_far']
    if core.any() and (~solid[core]).mean()>HOLE_SHARE:raise ValueError('body core is open')
    data={}
    def tube(slot,bones,rest,**extra):
        length=sum(np.linalg.norm(np.diff(rest,axis=0),axis=1));radius=float(masks[slot].sum()/(2*length))
        data[slot]=dict(kind='tube',bones=bones,rest=np.asarray(rest).tolist(),radius=radius,source_frame=True,**extra)
    for side,word in (('n','near'),('f','far')):
        s='arm_'+word;tube(s,['sh_'+side,'el_'+side,'wr_'+side],chains[s], tip_lock=True, root_lock=True)
        s='leg_'+word;rest=chains[s];shin=(rest[2]-rest[1])/np.linalg.norm(rest[2]-rest[1]);radius=masks[s].sum()/(2*sum(lengths[s]))
        tube(s,['hip_'+side,'kn_'+side,'an_'+side],rest,root_lock=True,foot=dict(side=side,ankle=rest[2].tolist(),shin_dir=shin.tolist(),blend=float(radius*.6),width=float(radius),rest_angle=0.))
    hem=int(np.nonzero(masks['torso'])[0].max());skirt_len=max(hem-hip[1],.25*sum(lengths['leg_near']))*1.1
    down=(near['knee']+far['knee'])/2-hip;skirt=hip+down/np.linalg.norm(down)*skirt_len
    tube('torso',['skirt','hip','waist','head_base'],[skirt,hip,waist,neck])
    data['head']=dict(kind='rigid',follow=['head_base','head_rot'],anchor=neck.tolist())
    data['hips']=dict(kind='rigid',follow=['hip','body_rot'],anchor=hip.tolist())
    if 'weapon' in images: data['weapon']=dict(kind='rigid',follow=['wr_n','wep_a'],anchor=grip.tolist())
    body_rot=lp.angle_up(hip,waist);chest_rot=lp.angle_up(waist,neck);weapon_angle=lp.angle_down(grip,tip)
    if not isinstance(weapon_hand_binding, bool):
        raise ValueError('weapon_hand_binding must be a boolean')
    if weapon_hand_binding:
        if 'weapon' not in images:
            raise ValueError('weapon_hand_binding requires weapon artwork')
        body['weapon_hand_angle'] = weapon_angle - lp.angle_down(el, wr)
    canonical={s:canonical_arm(chains[s]) for s in ('arm_near','arm_far')}
    gait={}
    for clip,lean in (('idle',9.),('walk',8.)):
        an,ae,_=canonical['arm_near'];af,fe,_=canonical['arm_far']
        gait[clip]=dict(arm_n=[an+lean,2.5,ae,1.5],arm_f=[af+lean,1.8 if clip=='idle' else 15.,fe,2.6 if clip=='idle' else 5.],wep=weapon_angle-(an+ae),wep_sway=1.5)
    # Only the near hand can carry a weapon in this input contract. Keep idle's
    # source pose, but centre the free arm's walk swing beneath its own shoulder.
    gait['walk']['arm_f'][0] = free_arm_carriage(*lengths['arm_far'], canonical['arm_far'][1], 8.)
    gait['walk'].update(stride=lp.STRIDE*legs,bob=(mid-low)/2)
    puppet=dict(px_per_unit=ppu,joints={n:p.tolist() for n,p in dict(hip=hip,waist=waist,neck=neck,head_base=neck,wr_n=wr,el_n=el).items()},
      rest_angles=dict(head_rot=0.,wep_a=weapon_angle,chest_rot=chest_rot,body_rot=body_rot),
      skirt_len=skirt_len/ppu,core_radius=core_px/ppu,rest_arm={s:[j['arm_'+w]['wrist'].tolist(),j['arm_'+w]['elbow'].tolist()] for s,w in (('n','near'),('f','far'))},
      layers={s:data[s] for s in order},chains={},source='source.png',weapon_length=reach,weapon_back=back,
      head_attachment=head_attachment,attachment_checks=True)
    spec=dict(puppet=puppet,body=body,gait=gait)
    # Validate legal runtime gait parameters now, before writing any accepted rig.
    build_clips(gait=gait,body=Body.from_spec(body))
    return spec,{'px_per_unit':ppu,'cover':1.,'spill':0.,'fits':{},
       'reference_kind':'user-approved assembled artwork, not original identity coverage',
       'canonical_arm_target':{s:{'upper_angle':v[0],'elbow_angle':v[1],'source_backward_bend_retargeted':v[2]} for s,v in canonical.items()}}
