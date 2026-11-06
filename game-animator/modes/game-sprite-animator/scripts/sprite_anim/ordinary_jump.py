"""A finite ordinary jump fitted to measured legs and the accepted carried pose."""


def build_ordinary_jump(body, base, time_scale=1.):
    from .motions import Keyed, P

    legs = body.thigh+body.shin
    def pose(depth=0.,lift=0.,near=0.,far=0.,lean=0.,head=0.,feet=1.):
        return P(base,root_y=base['root_y']+depth*legs,
                 foot_n_x=base['foot_n_x']*feet,foot_f_x=base['foot_f_x']*feet,
                 foot_n_y=lift*legs,foot_f_y=lift*legs,
                 arm_n_up=base['arm_n_up']+near,arm_f_up=base['arm_f_up']+far,
                 spine=base['spine']+lean,head=base['head']+head,hp=0.,sh=0.)

    crouch = pose(depth=-.07,near=-8.,far=-6.,lean=3.,head=-2.)
    launch = pose(depth=.01,lift=.025,near=5.,far=5.,lean=-1.,feet=.9)
    rise = pose(depth=.02,lift=.06,near=8.,far=8.,lean=-1.,feet=.85)
    apex = pose(depth=.02,lift=.11,near=14.,far=12.,head=-2.,feet=.75)
    falling = pose(depth=-.01,lift=.01,near=6.,far=6.,lean=2.,head=-1.)
    touch = pose(depth=-.01,near=4.,far=4.,lean=2.,head=-2.)
    impact = pose(depth=-.075,near=-8.,far=-6.,lean=4.,head=-3.)

    # The five finite stages form one calibrated flight. Time scaling changes
    # velocity, not jump height. The start/land ramps have opposite equal
    # areas; the airborne parabola returns to its own launch height.
    flight = .84*time_scale
    height = 1.1*legs
    speed = 4*height/flight
    gravity = 8*height/(flight*flight)
    velocity = lambda t: speed-gravity*t*time_scale
    def clip(name,keys,previous,following,vel,events=(),ground=False):
        result = Keyed(name,[(t*time_scale,p) for t,p in keys],
                       prev=previous,next=following,
                       vel=[(t*time_scale,x,y) for t,x,y in vel],
                       events=[(t*time_scale,e) for t,e in events],
                       tags=('ground',) if ground else ())
        result.motion_profile = 'ordinary_jump_v1'
        return result

    start = clip('jump_start',[(0.,base),(.07,crouch),(.12,crouch),(.18,launch),(.20,rise),(.24,rise)],
                 'idle','jump_rise',[(0.,0.,0.),(.20,0.,0.),(.24,0.,speed)],[(.20,'takeoff')])
    rising = clip('jump_rise',[(0.,rise),(.26,apex),(.30,apex)],
                  'jump_start','jump_apex',[(0.,0.,speed),(.30,0.,velocity(.30))])
    top = clip('jump_apex',[(0.,apex),(.08,P(apex,head=base['head']-3.)),(.20,falling),(.24,falling)],
               'jump_rise','fall',[(0.,0.,velocity(.30)),(.12,0.,0.),(.24,0.,velocity(.54))])
    fall = clip('fall',[(0.,falling),(.26,touch),(.30,touch)],
                'jump_apex','land',[(0.,0.,velocity(.54)),(.30,0.,-speed)])
    landing = clip('land',[(0.,touch),(.06,impact),(.11,impact),(.26,base),(.30,base)],
                   'fall','idle',[(0.,0.,-speed),(.04,0.,0.),(.30,0.,0.)],[(0.,'land_dust')],True)
    return {c.name:c for c in (start,rising,top,fall,landing)}
