"""Humanoid side-view rig: pose channels -> joint positions (FK spine/arms, soft-IK legs).

Space: x = forward (character faces +x), y = up, ground at y=0. Units: standing height = 100.
Rotations are clockwise degrees for the body (lean forward > 0). Limb swing > 0 = toward +x.
"""
import math
from dataclasses import dataclass

from .constraints import ANKLE_SOFT, ankle_angle, ground_clamp, limited
from .mathx import add, rot, scale

# Every channel a pose can set. Poses are sparse dicts layered over these defaults.
REST = dict(
    root_x=0.0, root_y=0.0, root_rot=0.0,      # hip offset, whole-body spin about the hip
    pelvis=2.0, spine=3.0, neck=0.0, head=-3.0,
    sh=0.0, hp=0.0,                            # shoulder / hip fore-aft swing (fake 3D twist)
    arm_n_up=-6.0, arm_n_lo=24.0, hand_n=0.0,  # n = near (camera side, holds weapon)
    arm_f_up=12.0, arm_f_lo=18.0, hand_f=0.0,  # f = far
    foot_n_x=4.0, foot_n_y=0.0, foot_n_p=0.0,  # ankle offset from rest, pitch > 0 = toes up
    foot_f_x=-5.0, foot_f_y=0.0, foot_f_p=0.0,
    ik_body=0.0,                               # 0: foot targets in ground space, 1: in body space
    wep=88.0,                                  # blade angle from forearm axis
    squash=1.0,                                # y-scale about ground, x gets the inverse
    eye=1.0, brow=0.0, mouth=0.0,              # eye 0 = shut; brow > 0 angry; mouth 0..1 open
    smear=0.0, glow=0.0,
    # Gun channels. aim and look are world angles (0 forward, +90 up), so the upper body stays
    # valid on top of any lower-body clip.
    aim=0.0, look=0.0, look_w=0.0, spine_up=0.0,
    gun_ik=0.0, far_ik=0.0,                    # 1: hands solved onto the gun, 0: free FK arms
    hold_x=9.0, hold_y=-7.0,                   # grip position from the near shoulder, in gun frame
    fore_x=17.0, fore_y=1.5,                   # far hand position from the grip, in gun frame
    recoil=0.0, climb=0.0,                     # slide back along the barrel, muzzle rise in degrees
    nh_x=0.0, nh_y=0.0, fh_x=0.0, fh_y=0.0,    # hand offsets from grip / fore points
    pump=0.0,                                  # slide, pump or bolt travel 0..1
    mag=1.0, mag_hand=0.0, mag_t=-1.0,         # mag in gun, mag in far hand, seconds since drop
    gren=0.0, flash=0.0, flash_seed=0.0, shot_t=-1.0, shot_T=0.1,
)

# Follow-through: extremities sample the curves slightly in the past.
LAG = {"arm_n_lo": 0.022, "arm_f_lo": 0.022, "hand_n": 0.035, "hand_f": 0.035,
       "head": 0.018, "wep": 0.012}


@dataclass
class Body:
    thigh: float = 19.0
    shin: float = 18.0
    ankle_h: float = 5.0
    hip_h: float = 40.5
    pelvis_len: float = 10.0
    chest_len: float = 18.0
    neck_len: float = 2.5
    head_size: float = 1.0      # 1.0 = chibi 3.3 heads; 0.8 = heroic
    up_arm: float = 14.5
    lo_arm: float = 13.5
    hip_w: float = 2.2
    sh_w: float = 2.4
    bulk: float = 1.0           # limb thickness multiplier
    weapon_front: float = 0.0   # reach past / behind the hand, for the ground clamp
    weapon_back: float = 0.0
    weapon_margin: float = 2.8  # weapon half-thickness plus clearance

    @classmethod
    def from_spec(cls, spec):
        b = cls()
        for k, v in (spec or {}).items():
            if hasattr(b, k):
                setattr(b, k, v)
        return b


def soft_ik(l1, l2, d):
    """Soft reach limit: approaching full extension the knee would snap straight
    (angular velocity -> infinity). Compress the last few percent exponentially."""
    full = l1 + l2
    start = full * 0.965
    if d <= start:
        return d
    span = full - start
    return start + span * (1 - math.exp(-(d - start) / span))


def two_bone(root, target, l1, l2, bend):
    """Returns (mid, end). bend=+1 keeps the mid joint on the +x side of root->target."""
    dx, dy = target[0] - root[0], target[1] - root[1]
    d = math.hypot(dx, dy) or 1e-6
    ds = soft_ik(l1, l2, min(d, l1 + l2 + 30))
    ds = max(ds, abs(l1 - l2) + 0.1)
    ux, uy = dx / d, dy / d
    a = (l1 * l1 - l2 * l2 + ds * ds) / (2 * ds)
    h = math.sqrt(max(l1 * l1 - a * a, 0.0))
    # Normal chosen so that for a leg pointing down, +bend goes forward.
    nx, ny = -uy * bend, ux * bend
    mid = (root[0] + ux * a + nx * h, root[1] + uy * a + ny * h)
    end = (root[0] + ux * ds, root[1] + uy * ds)
    return mid, end


FOOT_HEEL = (-4.5, -5.0)   # heel contact relative to ankle (flat foot)
FOOT_BALL = (6.5, -5.0)    # ball contact


def ankle_with_roll(flat_ankle, pitch):
    """Roll the foot about whichever contact point is on the ground so that the
    contact stays planted while the ankle arcs. Continuous at pitch = 0."""
    pivot = FOOT_HEEL if pitch > 0 else FOOT_BALL
    world = add(flat_ankle, pivot)
    return add(world, rot((-pivot[0], -pivot[1]), -pitch))


def solve(pose, b: Body):
    """Pose dict -> skeleton dict with joints and absolute angles."""
    g = pose.get
    hip = (g("root_x"), b.hip_h + g("root_y"))
    body_rot = g("root_rot") + g("pelvis")
    waist = add(hip, rot((0, b.pelvis_len), body_rot))
    excess = []
    chest_rot = body_rot + limited("spine", g("spine") + g("spine_up"), excess)
    neck = add(waist, rot((0, b.chest_len), chest_rot))
    head_rel = g("neck") + g("head")
    head_rel += (-g("look") - chest_rot - head_rel) * g("look_w")    # look is a world angle
    head_rot = chest_rot + limited("head", head_rel, excess)
    head_base = add(neck, rot((0, b.neck_len), chest_rot + g("neck")))

    sh_axis = rot((1, 0), chest_rot)
    sh_top = add(waist, rot((0, b.chest_len - 3.0), chest_rot))
    sh_n = add(sh_top, scale(sh_axis, g("sh") - b.sh_w * 0.4))
    sh_f = add(sh_top, scale(sh_axis, -g("sh") + b.sh_w))

    def arm(s, up, lo):
        a1 = up - chest_rot
        a2 = a1 + limited("elbow", lo, excess)
        el = add(s, (math.sin(math.radians(a1)) * b.up_arm, -math.cos(math.radians(a1)) * b.up_arm))
        wr = add(el, (math.sin(math.radians(a2)) * b.lo_arm, -math.cos(math.radians(a2)) * b.lo_arm))
        return el, wr, a2

    el_n, wr_n, fa_n = arm(sh_n, g("arm_n_up"), g("arm_n_lo"))
    el_f, wr_f, fa_f = arm(sh_f, g("arm_f_up"), g("arm_f_lo"))

    hip_axis = rot((1, 0), body_rot)
    hip_n = add(hip, scale(hip_axis, g("hp") + b.hip_w * 0.3))
    hip_f = add(hip, scale(hip_axis, -g("hp") - b.hip_w))

    k = g("ik_body")

    def leg(hj, fx, fy, fp):
        flat = (fx, b.ankle_h + fy)

        def reach(pitch, lift=0.0):
            ground = ankle_with_roll(flat, pitch)
            ground = (ground[0], ground[1] + lift)
            if k > 0:
                # Body-space target: same stance, carried by hip motion and root spin.
                local = (ground[0], ground[1] - b.hip_h)
                carried = add(hip, rot(local, g("root_rot")))
                ground = (ground[0] * (1 - k) + carried[0] * k, ground[1] * (1 - k) + carried[1] * k)
            knee, ank = two_bone(hj, ground, b.thigh, b.shin, 1.0)
            return knee, ank, -pitch + g("root_rot") * k

        knee, ank, foot_rot = reach(fp)
        # An ankle only closes so far: past that a real heel lifts and the ball stays planted.
        for _ in range(2):
            tight = ANKLE_SOFT - ankle_angle(knee, ank, foot_rot)
            if tight <= 0:
                break
            fp -= tight * 1.15
            knee, ank, foot_rot = reach(fp)
        if k > 0:
            # A foot turning with the body would swing its heel or ball under the floor.
            sole = min(ank[1] + rot(p, foot_rot)[1] for p in (FOOT_HEEL, FOOT_BALL))
            if sole < 0.3:
                knee, ank, foot_rot = reach(fp, 0.3 - sole)
        return knee, ank, foot_rot

    kn_n, an_n, fr_n = leg(hip_n, g("foot_n_x"), g("foot_n_y"), g("foot_n_p"))
    kn_f, an_f, fr_f = leg(hip_f, g("foot_f_x"), g("foot_f_y"), g("foot_f_p"))

    wep_a = ground_clamp(fa_n + g("wep"), wr_n[1], b.weapon_front, b.weapon_back, b.weapon_margin)
    gaps = (0.0, 0.0)
    ik = g("gun_ik")
    if ik > 0:
        a = g("aim") + g("climb")
        d = (math.cos(math.radians(a)), math.sin(math.radians(a)))
        n = (-d[1], d[0])
        along = g("hold_x") - g("recoil") + g("nh_x")
        grip = add(add(sh_n, scale(d, along)), scale(n, g("hold_y") + g("nh_y")))
        target = (wr_n[0] + (grip[0] - wr_n[0]) * ik, wr_n[1] + (grip[1] - wr_n[1]) * ik)
        el_n, wr_n = two_bone(sh_n, target, b.up_arm, b.lo_arm, -1.0)
        fa_n = _limb_angle(el_n, wr_n)
        wep_a += (90 + a - wep_a) * ik
        gaps = (math.hypot(wr_n[0] - target[0], wr_n[1] - target[1]), 0.0)
    gd = (math.sin(math.radians(wep_a)), -math.cos(math.radians(wep_a)))
    gn = (-gd[1], gd[0])
    fi = g("far_ik")
    if fi > 0:
        along = g("fore_x") + g("fh_x")
        side = add(wr_n, scale(gn, g("fore_y") + g("fh_y")))
        along -= _slide_in(side, gd, along, sh_f, (b.up_arm + b.lo_arm) * 0.965)
        fore = add(side, scale(gd, along))
        target = (wr_f[0] + (fore[0] - wr_f[0]) * fi, wr_f[1] + (fore[1] - wr_f[1]) * fi)
        el_f, wr_f = two_bone(sh_f, target, b.up_arm, b.lo_arm, -1.0)
        fa_f = _limb_angle(el_f, wr_f)
        gaps = (gaps[0], math.hypot(wr_f[0] - target[0], wr_f[1] - target[1]))
    return dict(
        hip=hip, waist=waist, neck=neck, head_base=head_base,
        body_rot=body_rot, chest_rot=chest_rot, head_rot=head_rot,
        sh_n=sh_n, el_n=el_n, wr_n=wr_n, fa_n=fa_n,
        sh_f=sh_f, el_f=el_f, wr_f=wr_f, fa_f=fa_f,
        hip_n=hip_n, kn_n=kn_n, an_n=an_n, fr_n=fr_n,
        hip_f=hip_f, kn_f=kn_f, an_f=an_f, fr_f=fr_f,
        wep_a=wep_a, wep_dir=gd, gun_n=gn, hand_gaps=gaps, excess=excess,
    )


def _slide_in(base, d, along, root, reach):
    """How far the support hand slides back along the gun so it stays within reach of the
    shoulder. Aiming steeply up carries the forend past arm's length; a shooter slides the
    hand toward the receiver rather than letting go."""
    rel = (base[0] - root[0], base[1] - root[1])
    p = (rel[0] + d[0] * along, rel[1] + d[1] * along)
    if math.hypot(*p) <= reach:
        return 0.0
    # Smallest s with |p - s*d| = reach, never sliding past the grip.
    b = p[0] * d[0] + p[1] * d[1]
    disc = b * b - (p[0] ** 2 + p[1] ** 2 - reach * reach)
    if disc < 0:
        return max(0.0, min(along, b))
    return max(0.0, min(along, b - math.sqrt(disc)))


def _limb_angle(a, b):
    """Swing angle of the limb a->b: 0 hangs down, 90 points forward."""
    return math.degrees(math.atan2(b[0] - a[0], -(b[1] - a[1])))


def toe_world(sk, side):
    a, r = sk["an_" + side], sk["fr_" + side]
    return add(a, rot(FOOT_BALL, r))


def heel_world(sk, side):
    a, r = sk["an_" + side], sk["fr_" + side]
    return add(a, rot(FOOT_HEEL, r))


def full_pose(sparse):
    p = dict(REST)
    p.update(sparse)
    return p

