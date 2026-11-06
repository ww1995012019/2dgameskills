"""Finite forward roll fitted to measured legs and the accepted carried pose."""
import math

import numpy as np

from .constraints import low_points
from .mathx import rot
from .rig import FOOT_HEEL, FOOT_BALL, LAG, ankle_with_roll, full_pose, solve


def build_ordinary_roll(body, base, time_scale=1.):
    from .motions import Keyed, P

    legs = body.thigh + body.shin
    rest = solve(full_pose(base),body)
    def folded_foot(side,tuck):
        hip = np.subtract(rest['hip_'+side],rest['hip'])
        thigh = np.subtract(rest['kn_'+side],rest['hip_'+side])
        shin = np.subtract(rest['an_'+side],rest['kn_'+side])
        upper = math.degrees(math.atan2(thigh[0],-thigh[1]))
        lower = math.degrees(math.atan2(shin[0],-shin[1]))
        flex = (upper-lower+180.)%360.-180.
        angle = upper+6.*tuck
        bend = flex+(90.-flex)*tuck
        direction = lambda deg: np.array((math.sin(math.radians(deg)),-math.cos(math.radians(deg))))
        a,b = body.leg_bones(side)
        folded_shin = direction(angle-bend)*b
        ankle = hip+direction(angle)*a+folded_shin
        # Preserve the accepted ankle articulation as the shin folds back.
        turn = math.degrees(math.atan2(shin[1]*folded_shin[0]-shin[0]*folded_shin[1],float(shin@folded_shin)))
        pitch = -(rest['fr_'+side]+turn)
        heel = getattr(body,'foot_'+side+'_heel') or FOOT_HEEL
        ball = getattr(body,'foot_'+side+'_ball') or FOOT_BALL
        offset = ankle_with_roll((0.,0.),pitch,heel,ball)
        flat = ankle+np.array((0.,body.hip_h))-np.array(offset)
        return dict(zip(('foot_'+side+'_x','foot_'+side+'_y','foot_'+side+'_p'),
                        (float(flat[0]),float(flat[1]-body.ankle_h),pitch)))

    def pose(spin=0., carried=0., tuck=0.):
        feet = {**folded_foot('n',tuck),**folded_foot('f',tuck)} if tuck else {}
        return P(base, feet, root_rot=spin, ik_body=carried,
                 root_y=base['root_y']-.075*legs*tuck,
                 arm_n_up=base['arm_n_up']+18.*tuck,
                 arm_n_lo=base['arm_n_lo']+8.*tuck,
                 arm_f_up=base['arm_f_up']+50.*tuck,
                 arm_f_lo=base['arm_f_lo']+10.*tuck,
                 spine=base['spine']+26.*tuck, head=base['head']+18.*tuck,
                 hp=base['hp']*(1.-tuck), sh=base['sh']*(1.-tuck))

    centre = (.08*legs, .4*(body.pelvis_len+body.chest_len))
    def contact(t, p):
        w = p['ik_body']
        if w <= 0.:
            return
        probe = getattr(result,'ground_probe',None)
        if probe is not None:
            p['_whole_body_floor'] = True
        measure = probe or (lambda pose:min(low_points(solve(full_pose(pose),body),body).values()))
        clearance = .25 if probe is not None else .75
        offset = rot(centre, p['root_rot'])
        p['root_x'] = -offset[0]*w
        if w >= 1.-1e-9:
            # Solve above the ground before translating the complete ball down.
            # Starting underneath it would trigger each foot's floor clamp and
            # change the leg pose before the whole-body contact is resolved.
            p['root_y'] = body.hip_h+body.pelvis_len+body.chest_len+40.*body.head_size
            low = measure(p)
            p['root_y'] += clearance-low
        else:
            for _ in range(3):
                low = measure(p)
                if low >= clearance:
                    break
                p['root_y'] += (clearance-low)*min(1.,w*3.)

    keys = [(0.,pose()),(.12,pose(carried=.5,tuck=.65)),
            (.22,pose(carried=1.,tuck=1.)),(.35,pose(90.,1.,1.)),
            (.48,pose(180.,1.,1.)),(.61,pose(270.,1.,1.)),
            (.74,pose(360.,1.,1.)),(.78,pose(360.,1.,1.)),
            (.94,pose(360.,.4,.65)),(1.08,pose(360.)),(1.14,pose(360.))]
    speed = 3.*legs/time_scale
    timed = [(t*time_scale,p) for t,p in keys]
    timed[-1] = (max(timed[-1][0],timed[-2][0]+max(LAG.values())+.005),timed[-1][1])
    result = Keyed('roll',timed,add=contact,
                   prev='idle',next='idle',tags=('ground','tumble'),speed=speed,
                   vel=[(0.,0.,0.),(.12*time_scale,0.,0.),(.24*time_scale,speed,0.),
                        (.78*time_scale,speed,0.),(1.08*time_scale,0.,0.),(1.14*time_scale,0.,0.)])
    result.motion_profile = 'ordinary_roll_v1'
    return result
