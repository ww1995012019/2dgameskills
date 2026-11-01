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
    weapon_front: float = 0.0   # reach past / behind the weapon origin, for the ground clamp
    weapon_back: float = 0.0
    weapon_margin: float = 2.8  # weapon half-thickness plus clearance
    foot_wrap: bool = False     # blend a foot toward a spinning body the short way round
    # Measured joint seats for art that sets its own proportions, as (forward, up) in the chest frame
    # from the waist, and in the pelvis frame from the hip. None keeps the fitted sh_w and hip_w.
    leg_soft: float = 0.965     # share of the leg's reach where its IK starts to ease off
    sh_n_at: tuple = None
    sh_f_at: tuple = None
    hip_n_at: tuple = None
    hip_f_at: tuple = None

    @classmethod
    def from_spec(cls, spec):
        b = cls()
        for k, v in (spec or {}).items():
            if hasattr(b, k):
                setattr(b, k, v)
        return b


def soft_ik(l1, l2, d, soft=0.965):
    """Soft reach limit: approaching full extension the knee would snap straight
    (angular velocity -> infinity). Compress the last few percent exponentially."""
    full = l1 + l2
    start = full * soft
    if d <= start:
        return d
    span = full - start
    return start + span * (1 - math.exp(-(d - start) / span))


def two_bone(root, target, l1, l2, bend, soft=0.965):
    """Returns (mid, end). bend=+1 keeps the mid joint on the +x side of root->target."""
    dx, dy = target[0] - root[0], target[1] - root[1]
    d = math.hypot(dx, dy)
    # A coincident target has no direction. Use the rest limb's downward axis
    # for it and subprecision noise, rather than normalizing a zero vector or
    # letting tiny sign changes flip the folded limb.
    if d <= (l1 + l2) * 1e-8:
        ux, uy = 0.0, -1.0
    else:
        ux, uy = dx / d, dy / d
    ds = soft_ik(l1, l2, min(d, l1 + l2 + 30), soft)
    ds = max(ds, abs(l1 - l2) + min(0.1, l1, l2))
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
    chest_rot = body_rot + limited("spine", g("spine"), excess)
    neck = add(waist, rot((0, b.chest_len), chest_rot))
    head_rot = chest_rot + limited("head", g("neck") + g("head"), excess)
    head_base = add(neck, rot((0, b.neck_len), chest_rot + g("neck")))

    sh_axis = rot((1, 0), chest_rot)
    sh_top = add(waist, rot((0, b.chest_len - 3.0), chest_rot))
    sh_n = add(sh_top, scale(sh_axis, g("sh") - b.sh_w * 0.4))
    sh_f = add(sh_top, scale(sh_axis, -g("sh") + b.sh_w))
    if b.sh_n_at:
        sh_n = add(add(waist, rot(tuple(b.sh_n_at), chest_rot)), scale(sh_axis, g("sh")))
    if b.sh_f_at:
        sh_f = add(add(waist, rot(tuple(b.sh_f_at), chest_rot)), scale(sh_axis, -g("sh")))

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
    if b.hip_n_at:
        hip_n = add(add(hip, rot(tuple(b.hip_n_at), body_rot)), scale(hip_axis, g("hp")))
    if b.hip_f_at:
        hip_f = add(add(hip, rot(tuple(b.hip_f_at), body_rot)), scale(hip_axis, -g("hp")))

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
            knee, ank = two_bone(hj, ground, b.thigh, b.shin, 1.0, b.leg_soft)
            spin = (g("root_rot") + 180.0) % 360.0 - 180.0 if b.foot_wrap else g("root_rot")
            return knee, ank, -pitch + spin * k

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

    # The weapon's line passes through its drawing origin just past the wrist (art.weapon_origin),
    # and that point's height depends only on the forearm, so clamp about it.
    pivot_y = wr_n[1] + (wr_n[1] - el_n[1]) * 0.14
    weapon_input = fa_n + g("wep")
    contact_angle = pose.get("_weapon_angle")
    wep_a = ground_clamp(weapon_input if contact_angle is None else contact_angle,
                         pivot_y, b.weapon_front, b.weapon_back, b.weapon_margin,
                         reference=contact_angle)
    return dict(
        hip=hip, waist=waist, neck=neck, head_base=head_base,
        body_rot=body_rot, chest_rot=chest_rot, head_rot=head_rot,
        sh_n=sh_n, el_n=el_n, wr_n=wr_n, fa_n=fa_n,
        sh_f=sh_f, el_f=el_f, wr_f=wr_f, fa_f=fa_f,
        hip_n=hip_n, kn_n=kn_n, an_n=an_n, fr_n=fr_n,
        hip_f=hip_f, kn_f=kn_f, an_f=an_f, fr_f=fr_f,
        wep_a=wep_a, excess=excess, weapon_input=weapon_input, weapon_pivot_y=pivot_y,
        wep_dir=(math.sin(math.radians(wep_a)), -math.cos(math.radians(wep_a))),
    )


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

