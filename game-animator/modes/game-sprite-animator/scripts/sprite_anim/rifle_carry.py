"""Source-preserving, coupled upper-body carry for idle/run only.

The registered illustration already contains the rifle and both gripping hands.
They remain on one material surface; no independent rifle image is synthesized.
The isolated arms supply measured anatomy and hand landmarks, not additional draws.
"""
import math
import numpy as np


PROFILE = 'source_upper_rifle_v1'


def upper_pixels(reference, layers):
    """Select existing upper-body pixels using registered garment/head bounds."""
    torso = layers['torso'][..., 3] > 128
    head = layers['head'][..., 3] > 128
    if not torso.any() or not head.any():
        raise ValueError('source carry needs the registered torso and head')
    bottom = int(np.nonzero(torso)[0].max())
    upper = reference.copy()
    yy = np.arange(len(upper))[:, None]
    # The existing torso-owned neck overlap must survive the head knockout.
    # Reuse only real reference pixels; do not extend or paint an attachment.
    upper[..., 3] = np.where((yy <= bottom) & (~head | torso), upper[..., 3], 0)
    return upper


def configure_binding(reference, layers, spec, state, hand_hints=None):
    """Derive one carried surface from actual registered pixels and arm chains."""
    puppet = spec['puppet']
    material = layers['torso'][..., 3].copy()
    carried = upper_pixels(reference, layers)
    arms = {side:np.asarray(puppet['layers'][name]['rest'],float)
            for side,name in (('n','arm_near'),('f','arm_far'))}
    from .puppet import GRID
    hints = hand_hints if hand_hints is not None else layers
    lowest = max(int(np.nonzero(hints[name][..., 3] > 128)[0].max())
                 for name in ('hand_near_hint','hand_far_hint'))
    bottom = int(np.nonzero(material > 128)[0].max())
    if bottom-lowest < 4*GRID:
        raise ValueError('source carry: both hands need clearance above the garment hem; repair the reference')
    waist, neck = (np.asarray(puppet['joints'][key],float) for key in ('waist','head_base'))
    axis = (neck-waist)/np.linalg.norm(neck-waist)
    forward = np.array([-axis[1],axis[0]])
    chest = math.degrees(math.atan2(neck[0]-waist[0],waist[1]-neck[1]))
    puppet['rest_angles']['chest_rot'] = chest
    spec['body']['chest_len'] = float(np.linalg.norm(neck-waist)/puppet['px_per_unit'])
    carry = dict(profile=PROFILE, protected_y=float(lowest+GRID), blend_end_y=float(bottom),
                 source_points={})
    for side,points in arms.items():
        a,b,c = points
        delta = (a-waist)/puppet['px_per_unit']
        spec['body']['sh_'+side+'_at'] = [float(delta@forward),float(delta@axis)]
        angle = lambda p,q:math.degrees(math.atan2(q[0]-p[0],q[1]-p[1]))
        carry['arm_'+side+'_up'] = angle(a,b)+chest
        carry['arm_'+side+'_lo'] = angle(b,c)-angle(a,b)
        carry['source_points'][side] = points.tolist()
        # Preserve measured screen-space arm geometry in this carried group.
        if side == 'f':
            spec['body']['up_arm_f'] = float(np.linalg.norm(b-a)/puppet['px_per_unit'])
            spec['body']['lo_arm_f'] = float(np.linalg.norm(c-b)/puppet['px_per_unit'])
    layers['torso'] = carried
    spec['weapon'] = 'rifle'
    spec['gait']['carry'] = carry
    for name in ('arm_near','arm_far'):
        puppet['layers'][name]['draw_owner'] = 'torso'
    puppet['layers']['torso']['source_upper_carry'] = dict(
        profile=PROFILE, protected_y=carry['protected_y'], blend_end_y=float(bottom))
    state['carry_material_alpha'] = material
    state['source_upper_carry'] = dict(profile=PROFILE, source='reference.png',
        operation='registered_source_pixel_selection_no_repaint', protected_y=carry['protected_y'],
        blend_end_y=float(bottom), arms_are_landmarks=True,
        supported_clips=['idle','run'], separate_weapon_generation='not_used')


def rigidity_report(puppet, meshes, cv, sk, supersampling):
    """Compare actual final source-group mesh with an independent rigid transform."""
    from .puppet import rigid,mesh_points
    layer,vertices=meshes['torso']
    config=layer.source_upper_carry
    if config is None:
        return None
    if not hasattr(puppet,'carry_source_points'):
        y,x=np.nonzero((np.asarray(layer.image)[...,3]>128)
                       & (np.arange(layer.image.height)[:,None]+layer.offset[1]
                          <= config['protected_y']))
        points=np.column_stack((x,y)).astype(float)+layer.offset
        if len(points)<4:
            raise ValueError('source carry has no protected source surface')
        selected=points[np.linspace(0,len(points)-1,min(128,len(points))).astype(int)]
        extrema=points[[points[:,0].argmin(),points[:,0].argmax(),points[:,1].argmin(),points[:,1].argmax()]]
        puppet.carry_source_points=np.unique(np.vstack((selected,extrema)),axis=0)
    points=puppet.carry_source_points
    expected=rigid(points[:,0],points[:,1],puppet.joints['waist'],cv.T(sk['waist']),
                   math.radians(sk['chest_rot']-puppet.rest_angles['chest_rot']),
                   cv.s/puppet.px_per_unit)
    actual=mesh_points(layer,vertices,points)
    return dict(method=PROFILE,samples=len(points),
                max_error_px=float(np.linalg.norm(actual-expected,axis=-1).max()/supersampling))


def validate_carry(value):
    if value is None:
        return None
    if not isinstance(value,dict) or value.get('profile') != PROFILE:
        raise ValueError('gait.carry requires the registered source-upper rifle profile')
    for side in 'nf':
        for part in ('up','lo'):
            v=value.get('arm_'+side+'_'+part)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
                raise ValueError('source carry arm angles must be finite measured values')
    return value


def apply_carry(pose, carry):
    if carry is None:
        return pose
    pose = pose.copy()
    for side in 'nf':
        for part in ('up','lo'):
            key='arm_'+side+'_'+part
            pose[key]=carry[key]
    # Both shoulders and gripping hands share the same chest-space transform.
    pose['sh']=0.
    pose['wep']=0.
    return pose
