"""Motion library. Three clip kinds:

* Gait  - phase-driven locomotion. Foot paths are computed, so stance feet travel at
          exactly the ground speed (no sliding) and lift-off/touch-down are velocity
          continuous.
* Proc  - closed-form loops (idle, crouch_idle): sums of sines with integer cycle counts.
* Keyed - pose keys joined by a monotone cubic. Keys are given in seconds; bunching keys
          is how snappy timing is authored (e.g. a sword swing over 2-3 frames).

Clips that follow each other share a named pose at the seam (STANCE, CROUCH, RISE, ...),
so transitions are continuous by construction. `prev` / `next` wire the cloth simulation
across those same seams.
"""
import math

from .constraints import LIMITS, face_circle, low_points
from .mathx import Curve, hermite, lerp, rot
from .rig import LAG, REST, Body, full_pose, solve, ankle_with_roll

CH = list(REST)
STANCE_REACH = 0.968   # a standing leg stops short of the soft end of its reach (Body.leg_soft)
WEAPON_HALF = 2.5      # half the thickness of a weapon, plus a little air
IDX = {c: i for i, c in enumerate(CH)}
TAU = math.tau


class Clip:
    def __init__(self, name, duration, loop, vel=None, events=None, prev=None, next=None,
                 tags=(), speed=0.0, chain_at=None, next_at=0.0):
        self.name, self.duration, self.loop = name, duration, loop
        self._vel = Curve([k[0] for k in vel], [k[1:] for k in vel]) if vel else None
        self.events = events or []       # [(time, name), ...]
        self.prev, self.next = prev, next
        self.next_at = next_at  # normalized entry time in next (1 = hold its final pose)
        self.tags = set(tags)
        self.speed = speed               # px speed the engine should move at, in rig units/s
        self.chain_at = chain_at         # combo cancel time

    def vel(self, t):
        return tuple(self._vel(t)) if self._vel else (0.0, 0.0)

    def sample(self, t):
        raise NotImplementedError

    def contacts(self, t):
        return {}


def P(*bases, **over):
    """Build a full pose from bases + overrides."""
    p = dict(REST)
    for b in bases:
        p.update(b)
    p.update(over)
    return p


class Keyed(Clip):
    def __init__(self, name, keys, loop=False, period=None, add=None, **kw):
        times = [k[0] for k in keys]
        dur = period if loop else times[-1]
        super().__init__(name, dur, loop, **kw)
        rows = [[k[1][c] for c in CH] for k in keys]
        self.curve = Curve(times, rows, loop=loop, period=dur)
        self.add = add  # optional fn(t, pose) for layered noise

    def sample(self, t):
        v = self.curve(t)
        p = dict(zip(CH, v.tolist()))
        for c, lag in LAG.items():
            p[c] = float(self.curve(t - lag)[IDX[c]])
        if self.add:
            self.add(t, p)
        return p


class Proc(Clip):
    def __init__(self, name, duration, fn, loop=True, **kw):
        super().__init__(name, duration, loop, **kw)
        self.fn = fn

    def sample(self, t):
        return self.fn(t)


class Gait(Clip):
    """Parametric biped cycle. Phase 0 = near foot touches down."""

    def __init__(self, name, T, L, lift, duty, front=0.56, hip=-1.5, bob=1.0, bob_at=0.05,
                 lean=4.0, pelvis=2.0, head=None, arm_n=(-2, 12, 32, 10), arm_f=(10, 26, 22, 14),
                 wep=60.0, heel=18.0, toe=38.0, swing_pitch=-22.0, peak=0.75, tan=1.0, sh=1.2,
                 hp=1.0, surge=0.5, **kw):
        speed = L / (duty * T)
        super().__init__(name, T, True, speed=speed, vel=[(0, speed, 0), (T, speed, 0)], **kw)
        self.T, self.L, self.lift, self.duty, self.front = T, L, lift, duty, front
        self.hip, self.bob, self.bob_at, self.lean, self.pelvis = hip, bob, bob_at, lean, pelvis
        self.head, self.arm_n, self.arm_f, self.wep = head, arm_n, arm_f, wep
        self.peak, self.tan, self.sh, self.hp, self.surge = peak, tan, sh, hp, surge
        self.wep_sway = 4.0
        d = duty
        self.pitch = Curve(
            [0, 0.17 * d, 0.5 * d, d, d + 0.3 * (1 - d), d + 0.72 * (1 - d)],
            [[heel], [0], [0], [-toe], [swing_pitch], [heel * 0.7]], loop=True, period=1.0)

    def stride(self, L):
        self.L, self.speed = L, L / (self.duty * self.T)
        self._vel = Curve([0, self.T], [(self.speed, 0), (self.speed, 0)])

    def contacts(self, t):
        ph = (t / self.T) % 1
        return {"n": ph < self.duty, "f": (ph + 0.5) % 1 < self.duty}

    def foot(self, ph):
        d, L = self.duty, self.L
        xf, xb = L * self.front, L * (self.front - 1)
        if ph < d:
            s = ph / d
            x, y = xf - L * s, 0.0
        else:
            s = (ph - d) / (1 - d)
            m = -L * (1 - d) / d
            x = hermite(xb, m, xf, m, s)
            # Match stance velocity at both contacts. Shape the swing internally:
            # this term has zero value and slope at either end, while retaining
            # the old tan-controlled velocity at mid-swing.
            x += 4 * m * (self.tan - 1) * s * s * (1 - s) ** 2 * (1 - 2 * s)
            y = self.lift * math.sin(math.pi * s ** self.peak) ** 1.6
            if getattr(self, 'contact_body', None) is not None:
                # Measured support height follows swing lift too. Ease its
                # contact neighbourhood to avoid a visible pelvis jerk.
                edge = min(1., s / .05, (1 - s) / .05)
                y *= edge * edge * (3 - 2 * edge)
        return x, y, float(self.pitch(ph)[0])

    def sample(self, t):
        ph = (t / self.T) % 1
        lag = lambda c: (ph - LAG[c] / self.T) % 1
        nx, ny, np_ = self.foot(ph)
        fx, fy, fp = self.foot((ph + 0.5) % 1)
        c2 = math.cos(TAU * 2 * (ph - self.bob_at))
        c1 = math.cos(TAU * ph)
        an, af = self.arm_n, self.arm_f
        head = -self.lean * 0.9 if self.head is None else self.head
        p = P(
            root_y=self.hip - self.bob * c2, root_x=self.surge * math.cos(TAU * 2 * (ph - 0.22)),
            pelvis=self.pelvis + 0.8 * c2, spine=self.lean + 0.8 * math.cos(TAU * 2 * (ph - 0.1)),
            head=head + 0.9 * math.cos(TAU * 2 * (lag("head") - 0.12)),
            sh=self.sh * -c1, hp=self.hp * c1,
            arm_n_up=an[0] - an[1] * c1,
            arm_n_lo=an[2] + an[3] * math.cos(TAU * (lag("arm_n_lo") - 0.62)),
            arm_f_up=af[0] + af[1] * c1,
            arm_f_lo=af[2] + af[3] * math.cos(TAU * (lag("arm_f_lo") - 0.12)),
            wep=self.wep + self.wep_sway * math.cos(TAU * (lag("wep") - 0.6)),
            foot_n_x=nx, foot_n_y=ny, foot_n_p=np_, foot_f_x=fx, foot_f_y=fy, foot_f_p=fp,
        )
        if getattr(self,'contact_body',None) is not None:
            p['root_y']=measured_walk_height(p,self.contact_body)-self.contact_body.hip_h
        return p


def measured_walk_height(p,body):
    """Vault over measured rolling soles without locking or crouching the legs.

    Both continuous foot paths bound hip height; a raised swing foot normally
    has more reach available and does not carry the body. A smooth minimum
    avoids a velocity corner when support changes. Existing unmeasured rigs
    retain the authored hip bob.
    """
    rotation=p['root_rot']+p['pelvis'];axis=rot((1.,0.),rotation);heights=[]
    for side in 'nf':
        reach=sum(body.leg_bones(side))*.985
        seat=getattr(body,'hip_'+side+'_at')
        if seat is None:seat=(body.hip_w*.3,0.) if side=='n' else (-body.hip_w,0.)
        offset=rot(tuple(seat),rotation);sign=1 if side=='n' else -1
        offset=(offset[0]+axis[0]*p['hp']*sign,offset[1]+axis[1]*p['hp']*sign)
        ankle=ankle_with_roll((p['foot_'+side+'_x'],body.ankle_h+p['foot_'+side+'_y']),
            p['foot_'+side+'_p'],getattr(body,'foot_'+side+'_heel'),getattr(body,'foot_'+side+'_ball'))
        dx=ankle[0]-p['root_x']-offset[0]
        heights.append(ankle[1]+math.sqrt(max(reach*reach-dx*dx,0.))-offset[1])
    low=min(heights);softness=.25
    return low-softness*math.log(sum(math.exp(-(h-low)/softness) for h in heights))


def stance_reach(pose, body):
    """How far the longer leg is stretched in a pose, as a share of its whole length."""
    sk = solve(full_pose(pose), body)
    return max(math.dist(sk["hip_" + s], sk["an_" + s]) / sum(body.leg_bones(s)) for s in "nf")


def face_gap(pose, body):
    """Clearance in rig units between the whole weapon, butt to tip, and the face."""
    sk = solve(full_pose(pose), body)
    hand = sk['weapon_grip']
    centre, radius = face_circle(sk, body)
    a = (hand[0] - sk["wep_dir"][0] * body.weapon_back, hand[1] - sk["wep_dir"][1] * body.weapon_back)
    b = (hand[0] + sk["wep_dir"][0] * body.weapon_front, hand[1] + sk["wep_dir"][1] * body.weapon_front)
    u = (b[0] - a[0], b[1] - a[1])
    s = max(0.0, min(1.0, ((centre[0] - a[0]) * u[0] + (centre[1] - a[1]) * u[1]) / (u[0] ** 2 + u[1] ** 2 + 1e-9)))
    return math.dist(centre, (a[0] + u[0] * s, a[1] + u[1] * s)) - radius - WEAPON_HALF


def clear_face(clip, body):
    """Attack poses are written for a body whose arm lifts a sword clear of the head. Short arms or a
    long shaft park the weapon over the face instead, so each such key pose takes the smallest turn of
    the arm and weapon that uncovers it. Working on keys keeps the curves between them smooth, and a
    pose shared by two clips changes the same way in both, so the seam between them holds."""
    values = clip.curve.v.copy()
    for row in values:
        pose = dict(zip(CH, row.tolist()))
        if face_gap(pose, body) >= 0:
            continue
        turns = sorted(((a, w) for a in range(0, 121, 6) for w in range(-120, 121, 6)), key=lambda t: t[0] + 0.4 * abs(t[1]))
        for arm, wep in turns:
            if face_gap(dict(pose, arm_n_up=pose["arm_n_up"] - arm, wep=pose["wep"] + wep), body) >= 0:
                row[IDX["arm_n_up"]] -= arm
                row[IDX["wep"]] += wep
                break
    clip.curve = Curve(clip.curve.t, values)


def build_clips(style=None, custom=None, key_overrides=None, gait=None, body=None):
    """style: {'speed': time multiplier > 1 = snappier, 'bounce': amplitude multiplier}.
    gait: {clip: {arm_n, arm_f, wep, wep_sway, bob, stride}} replaces a gait's carried pose, hip bob and stride.
    gait.idle accepts arm_n/arm_f = [upper rest, upper sway, elbow rest, elbow sway], wep and wep_sway;
    its rest angles also set shared stance poses and clip handovers.
    body: the character's own proportions, for rules that fit a clip to them. Without it every clip is
    written for the default body."""
    fitted = body is not None
    body = body or Body()
    style = style or {}
    tm = 1.0 / style.get("speed", 1.0)
    bn = style.get("bounce", 1.0)

    def sq(v):
        return 1 + (v - 1) * bn

    def keys(*ks):
        return [(t * tm, p) for t, p in ks]

    # ---- shared seam poses ------------------------------------------------------------
    STANCE = dict(root_y=-3.0, pelvis=4, spine=5, head=-6, arm_n_up=-4, arm_n_lo=30, wep=56,
                  arm_f_up=14, arm_f_lo=26, foot_n_x=8, foot_f_x=-9, foot_f_p=0)
    idle_arms = dict(arm_n=(-4, 1.6, 30, 2.4), arm_f=(14, 1.8, 26, 2.6))
    idle_carry = (gait or {}).get("idle", {})
    for key, values in idle_carry.items():
        if key in ("wep", "wep_sway"):
            if (isinstance(values, bool) or not isinstance(values, (int, float))
                    or not math.isfinite(values) or key == "wep_sway" and values < 0):
                raise ValueError(f"gait.idle.{key}: expected a finite angle or nonnegative sway")
            if key == "wep":
                STANCE["wep"] = values
            continue
        if (key not in idle_arms or not isinstance(values, (list, tuple)) or len(values) != 4
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values)
                or values[1] < 0 or values[3] < 0 or not LIMITS["elbow"][0] <= values[2] <= LIMITS["elbow"][1]):
            raise ValueError(f"gait.idle.{key}: expected finite [upper rest, sway >= 0, legal elbow rest, sway >= 0]")
        upper, upper_sway, elbow, elbow_sway = values
        # Breathing must not drive an almost straight reference elbow backward.
        margin = min(elbow - LIMITS["elbow"][0], LIMITS["elbow"][1] - elbow)
        elbow_sway = min(elbow_sway, 0.9 * margin / max(abs(bn), 1e-9))
        idle_arms[key] = (upper, upper_sway, elbow, elbow_sway)
        STANCE[key + "_up"], STANCE[key + "_lo"] = upper, elbow
    # A stance is written for the default leg. On a longer one the same height leaves the knees locked,
    # where the leg's soft reach shifts a planted foot as the hip moves: sink until they are not.
    sink = 0.0
    while fitted and sink < 6.0 and stance_reach(P(STANCE, root_y=STANCE["root_y"] + 0.8 - sink), body) > STANCE_REACH:
        sink += 0.25
    STANCE["root_y"] -= sink

    CROUCH = dict(root_y=-12, root_x=-1.5, pelvis=16, spine=18, neck=0, head=-26, arm_n_up=-40,
                  arm_n_lo=44, arm_f_up=-26, arm_f_lo=40, foot_n_x=8, foot_f_x=-9, squash=sq(0.93),
                  wep=70, eye=0.9, brow=0.6)
    LAUNCH = dict(root_y=2.5, pelvis=0, spine=-3, head=-8, arm_n_up=62, arm_n_lo=34, arm_f_up=96,
                  arm_f_lo=22, foot_n_x=3, foot_f_x=-4, foot_n_p=-34, foot_f_p=-40,
                  squash=sq(1.09), wep=74, mouth=0.3)
    RISE = dict(root_y=3, pelvis=-2, spine=1, head=-7, arm_n_up=44, arm_n_lo=44, arm_f_up=104,
                arm_f_lo=26, foot_n_x=11, foot_n_y=15, foot_n_p=-12, foot_f_x=-8, foot_f_y=5,
                foot_f_p=-38, squash=sq(1.04), wep=70)
    APEX = dict(root_y=3, pelvis=6, spine=9, head=2, arm_n_up=52, arm_n_lo=52, arm_f_up=128,
                arm_f_lo=34, foot_n_x=11, foot_n_y=21, foot_n_p=-4, foot_f_x=-2, foot_f_y=14,
                foot_f_p=-22, squash=sq(0.985), wep=64)
    FALL = dict(root_y=3, pelvis=-3, spine=-3, head=8, arm_n_up=100, arm_n_lo=12, arm_f_up=148,
                arm_f_lo=22, foot_n_x=8, foot_n_y=6, foot_n_p=-20, foot_f_x=-8, foot_f_y=13,
                foot_f_p=-40, squash=sq(1.03), wep=46, mouth=0.2)
    TOUCH = dict(FALL, root_y=-1, foot_n_y=0, foot_f_y=0, foot_n_x=7, foot_f_x=-7, foot_n_p=-6,
                 foot_f_p=-6, arm_n_up=96, arm_f_up=126, head=4, squash=1.0)
    IMPACT = dict(root_y=-16, root_x=0.5, pelvis=22, spine=22, head=-28, arm_n_up=-24, arm_n_lo=58,
                  arm_f_up=48, arm_f_lo=30, foot_n_x=8, foot_f_x=-9, squash=sq(0.9), wep=64,
                  eye=0.55, brow=0.5)
    CROUCH_HOLD = dict(root_y=-15, root_x=-1, pelvis=26, spine=22, head=-34, arm_n_up=-8,
                       arm_n_lo=62, arm_f_up=30, arm_f_lo=50, foot_n_x=8, foot_f_x=-9, wep=48)

    # ---- attacks (blade world angle = arm_up + arm_lo - chest_rot + wep) ------------------
    A1_WIND = dict(root_y=-5, root_x=-4, pelvis=-2, spine=-9, head=-2, arm_n_up=-70, arm_n_lo=108,
                   wep=176, arm_f_up=56, arm_f_lo=40, foot_n_x=6, foot_n_y=2.5, foot_f_x=-10,
                   brow=1, squash=sq(0.98))
    A1_HIT = dict(root_y=-7, root_x=9, pelvis=12, spine=21, head=-20, arm_n_up=84, arm_n_lo=12,
                  wep=26, arm_f_up=-44, arm_f_lo=28, foot_n_x=19, foot_f_x=-11, foot_f_p=-14,
                  brow=1, mouth=0.7, squash=sq(0.97))
    A1_FOLLOW = dict(A1_HIT, root_y=-9, root_x=11, pelvis=16, spine=26, head=-26, arm_n_up=46,
                     arm_n_lo=8, wep=36, arm_f_up=-58, mouth=0.3)
    A2_WIND = dict(A1_FOLLOW, root_y=-10, root_x=9, spine=30, arm_n_up=16, arm_n_lo=26, wep=24)
    A2_HIT = dict(root_y=-2, root_x=16, pelvis=-2, spine=-8, head=-2, arm_n_up=136, arm_n_lo=14,
                  wep=8, arm_f_up=-30, arm_f_lo=30, foot_n_x=23, foot_n_p=8, foot_f_x=-2,
                  foot_f_p=-30, brow=1, mouth=0.7, squash=sq(1.05))
    A2_FOLLOW = dict(A2_HIT, root_y=-3, root_x=17, spine=-13, head=4, arm_n_up=152, arm_n_lo=24,
                     wep=48, mouth=0.2)
    A3_LEAP = dict(root_y=11, root_x=2, pelvis=-8, spine=-14, head=-2, arm_n_up=150, arm_n_lo=46,
                   wep=44, arm_f_up=120, arm_f_lo=50, foot_n_x=20, foot_n_y=18, foot_n_p=-8,
                   foot_f_x=0, foot_f_y=24, foot_f_p=-32, squash=sq(1.05), brow=1, mouth=0.4)
    A3_HIT = dict(root_y=-12, root_x=2, pelvis=24, spine=26, head=-30, arm_n_up=86, arm_n_lo=10,
                  wep=-6, arm_f_up=-50, arm_f_lo=34, foot_n_x=23, foot_f_x=-5, foot_f_p=-16,
                  brow=1, mouth=1, squash=sq(0.88))
    A3_FOLLOW = dict(A3_HIT, root_y=-14, root_x=2, pelvis=26, spine=30, head=-32, arm_n_up=62,
                     arm_n_lo=8, wep=28, mouth=0.4, squash=sq(0.93))

    # ---- idle --------------------------------------------------------------------------
    T_idle = 2.4 * tm

    def idle_fn(t):
        ph = t / T_idle
        s = lambda off: math.sin(TAU * (ph - off))
        blink_t = (t % T_idle) - 1.5 * tm
        blink = 1 - math.exp(-((blink_t / (0.045 * tm)) ** 2))
        p = P(STANCE)
        p["root_y"] += 0.75 * bn * (s(0.25) - 1) * 0.5
        p["spine"] += 1.1 * s(0.08) * bn
        p["pelvis"] += 0.3 * s(0.2)
        p["head"] += -0.9 * s(0.2)
        p["arm_n_up"] += idle_arms["arm_n"][1] * s(0.16) * bn
        p["arm_n_lo"] += idle_arms["arm_n"][3] * s(0.26) * bn
        p["arm_f_up"] += idle_arms["arm_f"][1] * s(0.2) * bn
        p["arm_f_lo"] += idle_arms["arm_f"][3] * s(0.3) * bn
        p["wep"] += idle_carry.get("wep_sway", 1.4) * s(0.34)
        p["sh"] = 0.25 * s(0.1)
        p["eye"] = blink
        if all(getattr(body, 'foot_'+side+'_'+end) is not None
               for side in 'nf' for end in ('heel', 'ball')):
            p['root_y'] = measured_walk_height(p, body) - body.hip_h - .15 * (1 - s(.25))
        return p

    idle0 = idle_fn(0.0)
    idle = Proc("idle", T_idle, idle_fn, vel=None, tags=("ground", "hold_feet"))

    def breathe(t, p):
        p["spine"] += 0.5 * math.sin(TAU * t / (2.5 * tm))
        margin = max(0.0, min(p["arm_f_lo"] - LIMITS["elbow"][0], LIMITS["elbow"][1] - p["arm_f_lo"]))
        p["arm_f_lo"] += min(0.8, 0.9 * margin) * math.sin(TAU * t / (1.25 * tm))

    idle_look = Keyed("idle_look", keys(
        (0, idle0), (0.35, P(STANCE, head=-16, spine=2, arm_f_up=22, root_y=-2.4 - sink)),
        (0.8, P(STANCE, head=-18, spine=1, root_y=-2.2 - sink, eye=0.95)),
        (1.0, P(STANCE, head=-18, spine=1, root_y=-2.2 - sink, eye=0.1)),
        (1.12, P(STANCE, head=-14, spine=2, root_y=-2.2 - sink)),
        (1.45, P(STANCE, head=14, spine=10, root_y=-4 - sink, arm_n_up=0, eye=0.8)),
        (1.95, P(STANCE, head=12, spine=10, root_y=-4 - sink, arm_n_up=0, eye=0.8)),
        (2.5, idle0)), add=breathe if fitted else None, prev="idle", next="idle", tags=("ground", "hold_feet"))

    # ---- locomotion ---------------------------------------------------------------------
    walk = Gait("walk", 0.84 * tm, 32, 7.5 * min(bn, 1.3), 0.6, hip=-2.2, bob=1.1 * bn, lean=5,
                pelvis=3, arm_n=(-4, 14, 34, 9), arm_f=(10, 28, 22, 13), wep=56, tags=("ground",),
                events=[(0.0, "footstep"), (0.42 * tm, "footstep")])
    if all(getattr(body,'foot_'+s+'_'+end) is not None for s in 'nf' for end in ('heel','ball')):
        walk.contact_body=body
    run = Gait("run", 0.56 * tm, 48, 19, 0.36, front=0.46, hip=-5.0, bob=2.0 * bn, bob_at=0.42,
               lean=13, pelvis=9, head=-15, arm_n=(-26, 14, 40, 8), arm_f=(8, 44, 84, 14),
               wep=-75, heel=12, toe=46, swing_pitch=-62, peak=0.62, tan=0.62, sh=2.2, hp=1.6,
               surge=0.9, tags=("ground",), events=[(0.0, "footstep"), (0.28 * tm, "footstep")])
    crouch_walk = Gait("crouch_walk", 0.9 * tm, 26, 6, 0.64, hip=-15, bob=0.9 * bn, lean=22,
                       pelvis=25, head=-34, arm_n=(-6, 10, 62, 8), arm_f=(30, 16, 50, 10), wep=48,
                       heel=10, toe=30, tags=("ground",),
                       events=[(0.0, "footstep"), (0.45 * tm, "footstep")])

    skid = Keyed("skid", keys(
        (0, P(root_y=-5, pelvis=9, spine=13, head=-15, arm_n_up=-26, arm_n_lo=40, wep=-75,
              arm_f_up=44, arm_f_lo=84, foot_n_x=10, foot_n_y=4, foot_f_x=-16, foot_f_y=8,
              foot_f_p=-30)),
        (0.09, P(root_y=-13, root_x=-5, pelvis=-14, spine=-12, head=6, arm_n_up=44, arm_n_lo=30,
                 wep=70, arm_f_up=70, arm_f_lo=30, foot_n_x=19, foot_n_p=14, foot_f_x=-8,
                 foot_f_p=-12, squash=sq(0.95), eye=0.8)),
        (0.2, P(root_y=-12, root_x=-3, pelvis=-10, spine=-7, head=3, arm_n_up=28, arm_n_lo=34,
                wep=68, arm_f_up=52, arm_f_lo=30, foot_n_x=19, foot_f_x=-8, foot_f_p=-4)),
        (0.3, P(root_y=-6, root_x=1.5, pelvis=9, spine=11, head=-10, arm_n_up=2, arm_n_lo=34,
                wep=58, arm_f_up=16, arm_f_lo=28, foot_n_x=12, foot_f_x=-8)),
        (0.46, idle0)),
        vel=[(0, 220, 0), (0.28 * tm, 25, 0), (0.46 * tm, 0, 0)], prev="run", next="idle",
        tags=("ground",), events=[(0.05 * tm, "skid_dust")])

    # ---- jump chain: jump_start > jump_rise (loop) > jump_apex > fall (loop) > land ------
    def wobble(*chs, a=2.0):
        def fn(t, p):
            ph = t / (0.5 * tm)
            for i, c in enumerate(chs):
                p[c] += a * math.sin(TAU * (ph - i * 0.13))
        return fn

    jump_start = Keyed("jump_start", keys(
        (0, idle0), (0.075, P(CROUCH, eye=0.8)), (0.135, P(CROUCH, root_y=-11, spine=15)),
        (0.2, P(LAUNCH)), (0.24, P(RISE))),
        vel=[(0, 0, 0), (0.135 * tm, 0, 0), (0.21 * tm, 40, 260), (0.24 * tm, 40, 260)],
        prev="idle", next="jump_rise", events=[(0.2 * tm, "takeoff")])
    jump_rise = Keyed("jump_rise", keys((0, P(RISE)), (0.5, P(RISE))), loop=True, period=0.5 * tm,
                      add=wobble("arm_f_lo", "arm_n_lo", "foot_f_p"), vel=[(0, 40, 260), (0.5 * tm, 40, 260)])
    jump_apex = Keyed("jump_apex", keys((0, P(RISE)), (0.14, P(APEX)), (0.24, P(APEX, arm_f_up=136, head=5)),
                                        (0.34, P(FALL))),
                      vel=[(0, 40, 260), (0.17 * tm, 40, 0), (0.34 * tm, 40, -300)],
                      prev="jump_rise", next="fall")
    fall = Keyed("fall", keys((0, P(FALL)), (0.48, P(FALL))), loop=True, period=0.48 * tm,
                 add=wobble("arm_f_up", "arm_n_up", "arm_f_lo", "foot_f_p", a=3.0),
                 vel=[(0, 40, -320), (0.48 * tm, 40, -320)])
    land = Keyed("land", keys(
        (0, P(TOUCH)), (0.055, P(IMPACT, root_y=-13)), (0.1, P(IMPACT)),
        (0.22, P(IMPACT, root_y=-8, pelvis=13, spine=14, head=-18, arm_n_up=-10, arm_f_up=30,
                 squash=sq(0.97), eye=1)),
        (0.44, idle0)),
        vel=[(0, 20, -320), (0.06 * tm, 0, 0), (0.44 * tm, 0, 0)], prev="fall", next="idle",
        tags=("ground",), events=[(0.0, "land_dust")])

    def stay_above_floor(t, p):
        """A collapsing body can't sink: lift the whole thing when any part would go under."""
        for _ in range(2):
            low = min(low_points(solve(full_pose(p), body), body).values())
            if low >= 0.5:
                break
            p["root_y"] += 0.5 - low

    def spin_about(center, height, floor=False):
        """Tucked spins pivot on the ball's centre: pivoting on the hip would swing the head
        through the floor. ik_body doubles as the blend weight."""
        def fn(t, p):
            off = rot(center, p["root_rot"])
            w = p["ik_body"]
            p["root_x"] = lerp(p["root_x"], -off[0], w)
            p["root_y"] = lerp(p["root_y"], height - off[1] - body.hip_h, w)
            if floor:
                # Contact constraint: a tucked body changes shape as it turns, so no fixed height
                # works. The lowest part rests on the ground on every frame.
                low = min(low_points(solve(full_pose(p), body), body).values())
                p["root_y"] += (0.5 - low) * min(1.0, w * 3.0)
        return fn

    def tuck(rot_deg, **kw):
        return P(dict(root_rot=rot_deg, ik_body=1, pelvis=16, spine=34, head=30, arm_n_up=46,
                      arm_n_lo=86, arm_f_up=60, arm_f_lo=90, wep=70, foot_n_x=11, foot_n_y=26,
                      foot_n_p=-16, foot_f_x=3, foot_f_y=21, foot_f_p=-30, eye=0.2), **kw)

    double_jump = Keyed("double_jump", keys(
        (0, P(FALL)), (0.06, tuck(50, ik_body=0.7)), (0.12, tuck(135)), (0.18, tuck(215)),
        (0.24, tuck(290)), (0.31, tuck(340, ik_body=0.8)), (0.4, P(FALL, root_rot=360))),
        add=spin_about((8, 20), 62),
        vel=[(0, 40, 300), (0.2 * tm, 40, 120), (0.4 * tm, 40, -200)],
        prev="fall", next="fall", tags=("tumble",), events=[(0.0, "air_puff")])

    # ---- crouch -------------------------------------------------------------------------
    crouch_enter = Keyed("crouch_enter", keys(
        (0, idle0), (0.1, P(CROUCH_HOLD, root_y=-16.5, squash=sq(0.97))), (0.18, P(CROUCH_HOLD))),
        prev="idle", next="crouch_idle", tags=("ground", "hold_feet"))

    def crouch_fn(t):
        T = 2.0 * tm
        p = P(CROUCH_HOLD)
        s = lambda off: math.sin(TAU * (t / T - off))
        p["root_y"] += 0.55 * (math.cos(TAU * t / T) - 1) * 0.5 * bn
        p["spine"] += 1.0 * s(0.05)
        p["arm_n_lo"] += 2.0 * s(0.2)
        p["arm_f_lo"] += 2.0 * s(0.25)
        return p

    crouch_idle = Proc("crouch_idle", 2.0 * tm, crouch_fn, tags=("ground", "hold_feet"))
    crouch_exit = Keyed("crouch_exit", keys(
        (0, P(CROUCH_HOLD)), (0.08, P(CROUCH_HOLD, root_y=-11, spine=16, head=-22)), (0.2, idle0)),
        prev="crouch_idle", next="idle", tags=("ground", "hold_feet"))

    # ---- evasive ------------------------------------------------------------------------
    def ball(deg, **kw):
        return P(dict(root_rot=deg, ik_body=1, pelvis=16, spine=36, head=32, neck=4, arm_n_up=52,
                      arm_n_lo=96, arm_f_up=64, arm_f_lo=96, wep=64, foot_n_x=13, foot_n_y=18,
                      foot_n_p=-20, foot_f_x=6, foot_f_y=14, foot_f_p=-30, eye=0.15), **kw)

    roll = Keyed("roll", keys(
        (0, P(root_y=-8, pelvis=18, spine=18, head=-20, arm_n_up=-30, arm_n_lo=60, wep=64,
              arm_f_up=-10, arm_f_lo=50, foot_n_x=14, foot_n_p=8, foot_f_x=-12, foot_f_p=-18)),
        (0.08, ball(40, ik_body=0.75, root_y=-12)), (0.16, ball(120)), (0.24, ball(195)),
        (0.32, ball(270)), (0.4, ball(330, ik_body=0.7, root_y=-12)),
        (0.5, P(CROUCH_HOLD, root_y=-12, root_rot=360, spine=18, head=-22)),
        (0.62, P(idle0, root_rot=360))),
        add=spin_about((8, 20), 39, floor=True),
        vel=[(0, 200, 0), (0.42 * tm, 200, 0), (0.62 * tm, 0, 0)], prev="run", next="idle",
        tags=("ground", "tumble"), speed=200, events=[(0.08 * tm, "invincible_on"), (0.42 * tm, "invincible_off")])

    DASH = dict(root_y=-11, root_x=6, pelvis=26, spine=24, head=-40, arm_n_up=-66, arm_n_lo=14,
                wep=8, arm_f_up=-40, arm_f_lo=26, foot_n_x=19, foot_n_y=3, foot_n_p=6, foot_f_x=-26,
                foot_f_y=10, foot_f_p=-54, squash=sq(0.95), brow=1)
    dash = Keyed("dash", keys(
        (0, idle0), (0.03, P(idle0, root_y=-7, root_x=-3, spine=-2, arm_n_up=10, squash=sq(0.96))),
        (0.075, P(DASH)), (0.2, P(DASH, root_y=-12, foot_f_y=12)), (0.27, P(DASH, root_y=-10, squash=1.0)),
        (0.42, idle0)),
        vel=[(0, 0, 0), (0.05 * tm, 520, 0), (0.24 * tm, 520, 0), (0.42 * tm, 0, 0)],
        prev="idle", next="idle", speed=520, events=[(0.05 * tm, "dash_burst")])

    WALL = dict(root_y=6, root_x=-4, pelvis=-16, spine=-12, head=-6, arm_f_up=108, arm_f_lo=12,
                arm_n_up=-30, arm_n_lo=40, wep=-98, foot_n_x=16, foot_n_y=8, foot_n_p=40, foot_f_x=9,
                foot_f_y=20, foot_f_p=46, eye=0.8)
    wall_slide = Keyed("wall_slide", keys((0, P(WALL)), (0.5, P(WALL))), loop=True, period=0.5 * tm,
                       add=wobble("arm_n_up", "arm_n_lo", a=1.8), vel=[(0, 0, -150), (0.5 * tm, 0, -150)])

    # ---- combat -------------------------------------------------------------------------
    attack_1 = Keyed("attack_1", keys(
        (0, idle0), (0.1, P(A1_WIND, root_y=-4)), (0.17, P(A1_WIND, arm_n_up=-78, wep=184)),
        (0.25, P(A1_HIT, smear=1)), (0.29, P(A1_FOLLOW, smear=0.75)), (0.38, P(A1_FOLLOW, root_y=-8)),
        (0.6, idle0)),
        events=[(0.2 * tm, "hit_on"), (0.29 * tm, "hit_off")], next="idle", prev="idle",
        tags=("ground", "attack"), chain_at=0.33 * tm)
    attack_2 = Keyed("attack_2", keys(
        (0, P(A1_FOLLOW)), (0.07, P(A2_WIND)), (0.125, P(A2_WIND, root_y=-10.5)),
        (0.2, P(A2_HIT, smear=1)), (0.24, P(A2_FOLLOW, smear=0.7)), (0.33, P(A2_FOLLOW, root_y=-4)),
        (0.56, idle0)),
        events=[(0.15 * tm, "hit_on"), (0.24 * tm, "hit_off")], prev="attack_1", next="idle",
        tags=("ground", "attack"), chain_at=0.29 * tm)
    attack_3 = Keyed("attack_3", keys(
        (0, P(A2_FOLLOW)), (0.11, P(A3_LEAP, root_y=8)), (0.19, P(A3_LEAP)),
        (0.235, P(A3_LEAP, root_y=9, wep=60, arm_n_up=142, smear=0.6)),
        (0.3, P(A3_HIT, smear=1)), (0.35, P(A3_FOLLOW, smear=0.6)), (0.53, P(A3_FOLLOW, root_y=-13)),
        (0.65, P(A3_FOLLOW, root_y=-9, spine=20, head=-20, wep=40, squash=sq(0.98), mouth=0)), (0.9, P(idle0))),
        events=[(0.25 * tm, "hit_on"), (0.34 * tm, "hit_off"), (0.3 * tm, "screen_shake")],
        vel=[(0, 60, 80), (0.2 * tm, 60, 0), (0.3 * tm, 0, -240), (0.34 * tm, 0, 0), (0.9 * tm, 0, 0)],
        prev="attack_2", next="idle", tags=("ground", "attack"))
    air_attack = Keyed("air_attack", keys(
        (0, P(FALL)), (0.08, P(RISE, arm_n_up=-70, arm_n_lo=108, wep=176, spine=-10, head=-2, brow=1,
                               arm_f_up=66, arm_f_lo=40)),
        (0.14, P(RISE, arm_n_up=-78, arm_n_lo=112, wep=184, spine=-12, head=-2, brow=1, arm_f_up=60)),
        (0.215, P(APEX, arm_n_up=84, arm_n_lo=12, wep=26, spine=20, head=-22, arm_f_up=-40, arm_f_lo=30, smear=1, brow=1, mouth=0.7)),
        (0.255, P(APEX, arm_n_up=46, arm_n_lo=8, wep=34, spine=26, head=-26, arm_f_up=-56, arm_f_lo=28, smear=0.7, brow=1)),
        (0.34, P(APEX, arm_n_up=52, arm_n_lo=14, wep=20, spine=20, head=-14, arm_f_up=-20, arm_f_lo=30)),
        (0.5, P(FALL))),
        vel=[(0, 40, -120), (0.5 * tm, 40, -260)], prev="fall", next="fall",
        events=[(0.17 * tm, "hit_on"), (0.26 * tm, "hit_off")], tags=("attack",))

    CHARGE = dict(root_y=-6, pelvis=-3, spine=-5, head=-10, arm_f_up=118, arm_f_lo=22, arm_n_up=-40,
                  arm_n_lo=58, wep=70, foot_n_x=10, foot_f_x=-11, glow=1, brow=0.6)
    RELEASE = dict(root_y=-8, root_x=7, pelvis=12, spine=18, head=-20, arm_f_up=88, arm_f_lo=6,
                   arm_n_up=-54, arm_n_lo=42, wep=66, foot_n_x=18, foot_f_x=-12, foot_f_p=-12,
                   glow=1.6, brow=1, mouth=0.8, squash=sq(0.97))

    def charge_jitter(t, p):
        if 0.15 * tm < t < 0.62 * tm:
            p["arm_f_lo"] += 1.0 * math.sin(TAU * t * 11)
            p["spine"] += 0.5 * math.sin(TAU * t * 9)

    cast = Keyed("cast", keys(
        (0, idle0), (0.16, P(CHARGE, glow=0.5)), (0.56, P(CHARGE, root_y=-7, arm_f_up=124, glow=1.2)),
        (0.7, P(RELEASE)), (0.84, P(RELEASE, root_y=-7, glow=0.5, arm_f_lo=10)), (1.14, idle0)),
        add=charge_jitter, prev="idle", next="idle", events=[(0.7 * tm, "projectile")],
        tags=("ground", "hold_feet_soft"))

    GUARD = dict(root_y=-7, root_x=-1, pelvis=8, spine=9, head=-14, arm_n_up=58, arm_n_lo=62, wep=62,
                 arm_f_up=44, arm_f_lo=78, foot_n_x=11, foot_f_x=-12, brow=0.8)
    block = Keyed("block", keys((0, idle0), (0.09, P(GUARD, root_y=-8)), (0.14, P(GUARD))),
                  prev="idle", tags=("ground",))
    block_hit = Keyed("block_hit", keys(
        (0, P(GUARD)), (0.05, P(GUARD, root_x=-5, root_y=-9, spine=2, head=-8, arm_n_up=48, arm_n_lo=74, squash=sq(0.97))),
        (0.26, P(GUARD))), prev="block", next="block", next_at=1.0,
        tags=("ground",), events=[(0.0, "block_spark")])

    # ---- reactions ----------------------------------------------------------------------
    hurt = Keyed("hurt", keys(
        (0, idle0), (0.05, P(STANCE, root_x=-6, root_y=-5, pelvis=-9, spine=-20, head=16, arm_n_up=34,
                             arm_n_lo=30, wep=82, arm_f_up=62, arm_f_lo=30, foot_n_x=11, foot_n_y=4,
                             eye=0, mouth=1, squash=sq(1.03))),
        (0.11, P(STANCE, root_x=-7, root_y=-9, pelvis=9, spine=21, head=-14, arm_n_up=14, arm_n_lo=46,
                 wep=66, arm_f_up=24, arm_f_lo=42, foot_n_x=8, foot_n_y=0, eye=0.1, mouth=0.6, squash=sq(0.96))),
        (0.22, P(STANCE, root_x=-3, root_y=-6, pelvis=9, spine=13, head=-12, eye=0.7, mouth=0.2)),
        (0.42, idle0)),
        prev="idle", next="idle", tags=("ground",), events=[(0.0, "hit_flash")])

    DOWN = dict(root_y=-27.5, root_x=-8, root_rot=-90, pelvis=0, spine=0, head=8, ik_body=1, arm_n_up=16,
                arm_n_lo=12, wep=-28, arm_f_up=32, arm_f_lo=14, foot_n_x=10, foot_n_p=8,
                foot_f_x=3, foot_f_y=4, foot_f_p=10, eye=0, mouth=0.25)
    death = Keyed("death", keys(
        (0, idle0),
        (0.08, P(STANCE, root_x=-7, root_y=-5, pelvis=-9, spine=-22, head=20, arm_n_up=38, arm_f_up=66,
                 arm_n_lo=28, wep=82, foot_n_y=3, eye=0, mouth=1)),
        (0.24, P(STANCE, root_x=-9, root_y=-7, pelvis=-5, spine=-13, head=14, arm_n_up=20, arm_f_up=40,
                 eye=0.1, mouth=0.7)),
        (0.46, P(STANCE, root_x=-6, root_y=-15, pelvis=14, spine=16, head=26, arm_n_up=-4, arm_n_lo=12,
                 arm_f_up=8, arm_f_lo=12, wep=78, eye=0.1, mouth=0.4, foot_n_x=10, foot_f_x=-8)),
        (0.7, P(DOWN, root_rot=-46, root_y=-24, root_x=-7, ik_body=0.55, arm_n_up=62, arm_f_up=74, head=-8)),
        (0.84, P(DOWN, squash=sq(0.97))),
        (0.92, P(DOWN, root_y=-26, head=2, arm_n_up=26, arm_f_up=40)),
        (1.02, P(DOWN, squash=sq(0.985))),
        (1.3, P(DOWN))),
        add=stay_above_floor, prev="idle", tags=("ground",), events=[(0.84 * tm, "body_thud")])

    clips = [idle, idle_look, walk, run, skid, jump_start, jump_rise, jump_apex, fall, land,
             double_jump, crouch_enter, crouch_idle, crouch_exit, crouch_walk, roll, dash,
             wall_slide, attack_1, attack_2, attack_3, air_attack, cast, block, block_hit, hurt,
             death]
    out = {c.name: c for c in clips}
    for name, pose in (gait or {}).items():
        if name == "idle":  # already applied before the shared seam poses were built
            continue
        for key, value in pose.items():
            if key == "stride":     # the feet must keep the ground speed, so the speed changes with it
                out[name].stride(value)
            elif key in ("arm_n", "arm_f", "wep", "wep_sway", "bob"):
                setattr(out[name], key, tuple(value) if isinstance(value, list) else value)
            else:
                raise ValueError(f"gait.{name}: unknown field {key!r}")

    for name, spec in (custom or {}).items():
        ks = [(t * tm, P(idle0, **pose)) for t, pose in spec["keys"]]
        loop = bool(spec.get("loop"))
        period = spec["period"] * tm if loop and "period" in spec else ks[-1][0]
        out[name] = Keyed(name, ks, loop=loop, period=period if loop else None,
                          prev=spec.get("prev", "idle"), next=spec.get("next", "idle"),
                          events=[(t * tm, n) for t, n in spec.get("events", [])],
                          tags=tuple(spec.get("tags", ())))

    if fitted and body.weapon_front:
        for clip in out.values():
            if isinstance(clip, Keyed) and not clip.loop and "attack" in clip.tags:
                clear_face(clip, body)

    # Optional character-specific corrections to existing keyed poses. Keeping the
    # clip object retains its events, velocity, combo timing and transition metadata.
    for name, changes in (key_overrides or {}).items():
        if name not in out or not isinstance(out[name], Keyed) or out[name].loop:
            raise ValueError(f"key overrides require a non-looping keyed clip: {name}")
        clip = out[name]
        values = clip.curve.v.copy()
        for index, pose in changes.items():
            if not isinstance(index, str) or not index.isdecimal() or int(index) >= len(values):
                raise ValueError(f"invalid key index for {name}: {index}")
            if not isinstance(pose, dict):
                raise ValueError(f"key override for {name}[{index}] must be an object")
            for channel, value in pose.items():
                if channel not in IDX or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"invalid pose channel or value: {name}[{index}].{channel}")
                values[int(index), IDX[channel]] = value
        clip.curve = Curve(clip.curve.t, values)
    return out


# Which clip follows which in a game: checked by the QA pass for pose continuity.
SEAMS = [("idle", "jump_start"), ("jump_start", "jump_rise"), ("jump_rise", "jump_apex"),
         ("jump_apex", "fall"), ("fall", "land"), ("land", "idle"), ("skid", "idle"),
         ("idle", "crouch_enter"), ("crouch_enter", "crouch_idle"), ("crouch_idle", "crouch_exit"),
         ("crouch_exit", "idle"), ("attack_1", "idle"), ("attack_2", "idle"), ("attack_3", "idle"),
         ("hurt", "idle"), ("cast", "idle"), ("dash", "idle"), ("roll", "idle"),
         ("idle_look", "idle"), ("block", "block_hit"), ("block_hit", "block"),
         ("double_jump", "fall"), ("air_attack", "fall")]
