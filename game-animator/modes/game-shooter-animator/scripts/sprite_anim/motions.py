"""Shooter motion library. Lower-body, upper-body and full-body clips (see build_clips). Clip kinds:

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

from .constraints import low_points
from .mathx import Curve, hermite, lerp, rot
from .weapons import GUN_SCALE, SWAY_FLASH, WEAPONS, shot_frames
from .rig import LAG, REST, Body, full_pose, solve

CH = list(REST)
HIP_H = 40.5
IDX = {c: i for i, c in enumerate(CH)}
TAU = math.tau


class Clip:
    def __init__(self, name, duration, loop, vel=None, events=None, prev=None, next=None,
                 tags=(), speed=0.0, chain_at=None, layer="full", weapon=None, aim=None,
                 fps=None, cloth_ref=None):
        self.name, self.duration, self.loop = name, duration, loop
        self._vel = Curve([k[0] for k in vel], [k[1:] for k in vel]) if vel else None
        self.events = events or []       # [(time, name), ...]
        self.prev, self.next = prev, next
        self.tags = set(tags)
        self.speed = speed               # px speed the engine should move at, in rig units/s
        self.chain_at = chain_at         # combo cancel time
        self.layer, self.weapon, self.aim = layer, weapon, aim
        self.fps = fps                   # per-clip frame rate, None = the run's rate
        self.cloth_ref = cloth_ref       # reuse this clip's cloth bake

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
                 hp=1.0, surge=0.5, over=None, **kw):
        speed = L / (duty * T)
        super().__init__(name, T, True, speed=speed, vel=[(0, speed, 0), (T, speed, 0)], **kw)
        self.T, self.L, self.lift, self.duty, self.front = T, L, lift, duty, front
        self.hip, self.bob, self.bob_at, self.lean, self.pelvis = hip, bob, bob_at, lean, pelvis
        self.head, self.arm_n, self.arm_f, self.wep = head, arm_n, arm_f, wep
        self.peak, self.tan, self.sh, self.hp, self.surge = peak, tan, sh, hp, surge
        self.over = over or {}
        d = duty
        self.pitch = Curve(
            [0, 0.17 * d, 0.5 * d, d, d + 0.3 * (1 - d), d + 0.72 * (1 - d)],
            [[heel], [0], [0], [-toe], [swing_pitch], [heel * 0.7]], loop=True, period=1.0)

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
            m = -L * (1 - d) / d * self.tan
            x = hermite(xb, m, xf, m, s)
            y = self.lift * math.sin(math.pi * s ** self.peak) ** 1.6
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
            wep=self.wep + 4 * math.cos(TAU * (lag("wep") - 0.6)),
            foot_n_x=nx, foot_n_y=ny, foot_n_p=np_, foot_f_x=fx, foot_f_y=fy, foot_f_p=fp,
        )
        p.update(self.over)
        return p


class Reversed(Clip):
    """A gait played backward, for backpedalling while aiming the other way."""

    def __init__(self, name, base, **kw):
        super().__init__(name, base.duration, True, speed=-base.speed, tags=base.tags, layer=base.layer, **kw)
        self.base = base

    def vel(self, t):
        return (-self.base.speed, 0.0)

    def sample(self, t):
        return self.base.sample(self.duration - t % self.duration)

    def contacts(self, t):
        return self.base.contacts(self.duration - t % self.duration)


# What an upper-body clip owns when merged over a lower-body clip.
UPPER_CH = {"aim", "look", "look_w", "spine_up", "gun_ik", "far_ik", "hold_x", "hold_y", "fore_x", "fore_y",
            "recoil", "climb", "nh_x", "nh_y", "fh_x", "fh_y", "pump", "mag", "mag_hand", "mag_t", "gren",
            "flash", "flash_seed", "shot_t", "shot_T", "arm_n_up", "arm_n_lo", "arm_f_up", "arm_f_lo", "wep",
            "eye", "brow", "mouth", "smear", "neck", "head", "sh"}


class Combo(Clip):
    """lower + upper baked into one full-body clip, for engines that want a single sprite.
    Length snaps to a whole number of shots so the flash lands on the same frames every cycle."""

    def __init__(self, name, lower, upper, shot_n, fps):
        n = max(1, int(round(lower.duration * fps)))
        if shot_n:
            n = max(shot_n, shot_n * int(round(n / shot_n)))
        T = n / fps
        self.ratio = lower.duration / T
        super().__init__(name, T, True, speed=lower.speed * self.ratio, tags=tuple(lower.tags) + tuple(upper.tags),
                         layer="full", weapon=upper.weapon, aim=upper.aim)
        self.lower, self.upper = lower, upper

    def vel(self, t):
        return self.lower.vel(t * self.ratio)

    def contacts(self, t):
        return self.lower.contacts(t * self.ratio)

    def sample(self, t):
        p = dict(self.lower.sample(t * self.ratio))
        u = self.upper.sample(t % self.upper.duration if self.upper.loop else min(t, self.upper.duration))
        for c in UPPER_CH:
            p[c] = u[c]
        return p


def aim_tag(a):
    return "0" if a == 0 else ("p" if a > 0 else "m") + str(abs(a))


AIMS_9 = (90, 67, 45, 22, 0, -22, -45, -67, -90)


def build_clips(spec=None, fps=30, aims=AIMS_9, combos=None):
    spec = spec or {}
    style = spec.get("style") or {}
    tm = 1.0 / style.get("speed", 1.0)
    bn = style.get("bounce", 1.0)
    weapons = spec.get("weapons") or ["rifle"]
    primary = weapons[0]
    hold_fps = max(8, fps // 3)     # slow breathing needs few frames; these multiply by every aim angle

    def sq(v):
        return 1 + (v - 1) * bn

    def keys(*ks):
        return [(t * tm, p) for t, p in ks]

    # ---- lower body ---------------------------------------------------------------------
    STANCE = dict(root_y=-3.5, pelvis=3, spine=4, foot_n_x=9, foot_f_x=-10)
    CROUCH = dict(root_y=-15, root_x=-1, pelvis=20, spine=8, foot_n_x=9, foot_f_x=-10, foot_f_p=-16)
    DIP = dict(root_y=-11, root_x=-1, pelvis=14, spine=8, foot_n_x=9, foot_f_x=-10)
    LAUNCH = dict(root_y=2.5, pelvis=0, spine=-2, foot_n_x=3, foot_f_x=-4, foot_n_p=-34, foot_f_p=-40)
    RISE = dict(root_y=3, pelvis=-2, spine=1, foot_n_x=11, foot_n_y=15, foot_n_p=-12, foot_f_x=-8, foot_f_y=5, foot_f_p=-38)
    APEX = dict(root_y=3, pelvis=6, spine=6, foot_n_x=11, foot_n_y=21, foot_n_p=-4, foot_f_x=-2, foot_f_y=14, foot_f_p=-22)
    FALL = dict(root_y=3, pelvis=-3, spine=-2, foot_n_x=8, foot_n_y=6, foot_n_p=-20, foot_f_x=-8, foot_f_y=13, foot_f_p=-40)
    TOUCH = dict(FALL, root_y=-1, foot_n_y=0, foot_f_y=0, foot_n_x=7, foot_f_x=-7, foot_n_p=-6, foot_f_p=-6)
    IMPACT = dict(root_y=-15, root_x=0.5, pelvis=20, spine=12, foot_n_x=9, foot_f_x=-10)
    T_idle = 2.0 * tm

    def idle_fn(t):
        ph = t / T_idle
        p = P(STANCE)
        p["root_y"] += 0.7 * bn * (math.sin(TAU * (ph - 0.25)) - 1) * 0.5
        p["pelvis"] += 0.4 * math.sin(TAU * (ph - 0.2))
        return p

    def crouch_fn(t):
        p = P(CROUCH)
        p["root_y"] += 0.5 * (math.cos(TAU * t / (2.0 * tm)) - 1) * 0.5 * bn
        return p

    def legs_drift(period):
        def fn(t, p):
            ph = t / period
            p["foot_n_y"] += 1.6 * math.sin(TAU * ph)
            p["foot_f_y"] += 1.6 * math.sin(TAU * (ph - 0.3))
            p["foot_f_p"] += 4.0 * math.sin(TAU * (ph - 0.15))
            p["pelvis"] += 0.8 * math.sin(TAU * (ph - 0.1))
        return fn

    idle0 = idle_fn(0.0)
    low = dict(layer="lower")
    lower = [
        Proc("idle", T_idle, idle_fn, tags=("ground", "hold_feet", "subtle"), **low),
        Gait("walk", 0.84 * tm, 30, 7, 0.6, hip=-3, bob=1.0 * bn, lean=4, pelvis=3, tags=("ground",),
             events=[(0.0, "footstep"), (0.42 * tm, "footstep")], **low),
        Gait("run", 0.6 * tm, 44, 16, 0.37, front=0.46, hip=-5, bob=1.7 * bn, bob_at=0.42, lean=7, pelvis=6,
             heel=12, toe=44, swing_pitch=-56, peak=0.64, tan=0.62, surge=0.7, tags=("ground",),
             events=[(0.0, "footstep"), (0.3 * tm, "footstep")], **low),
        Gait("crouch_walk", 0.9 * tm, 24, 5.5, 0.64, hip=-15, bob=0.8 * bn, lean=8, pelvis=20, heel=10, toe=28,
             tags=("ground",), events=[(0.0, "footstep"), (0.45 * tm, "footstep")], **low),
        Proc("crouch_idle", 2.0 * tm, crouch_fn, tags=("ground", "hold_feet", "subtle"), **low),
        Keyed("crouch_enter", keys((0, idle0), (0.1, P(CROUCH, root_y=-16.5)), (0.18, P(CROUCH))),
              tags=("ground", "hold_feet"), **low),
        Keyed("crouch_exit", keys((0, P(CROUCH)), (0.08, P(CROUCH, root_y=-11)), (0.2, idle0)),
              tags=("ground", "hold_feet"), **low),
        Keyed("jump_start", keys((0, idle0), (0.075, P(DIP)), (0.135, P(DIP, root_y=-10)), (0.2, P(LAUNCH)), (0.24, P(RISE))),
              events=[(0.2 * tm, "takeoff")], next="jump_rise", **low),
        Keyed("jump_rise", keys((0, P(RISE)), (0.6, P(RISE))), loop=True, period=0.6 * tm, add=legs_drift(0.6 * tm), tags=("drift",), **low),
        Keyed("jump_apex", keys((0, P(RISE)), (0.14, P(APEX)), (0.24, P(APEX)), (0.34, P(FALL))), next="fall", **low),
        Keyed("fall", keys((0, P(FALL)), (0.66, P(FALL))), loop=True, period=0.66 * tm, add=legs_drift(0.66 * tm), tags=("drift",), **low),
        Keyed("land", keys((0, P(FALL)), (0.034, P(TOUCH)), (0.08, P(IMPACT, root_y=-12)), (0.125, P(IMPACT)),
                           (0.25, P(IMPACT, root_y=-8, pelvis=12, spine=8)), (0.43, idle0)),
              tags=("ground",), events=[(0.0, "land_dust")], next="idle", **low),
    ]
    lower.insert(3, Reversed("backpedal", Gait("_bp", 0.9 * tm, 22, 6, 0.62, hip=-3.5, bob=0.8 * bn, lean=2, pelvis=2, layer="lower",
                                               tags=("ground",)), events=[(0.0, "footstep"), (0.45 * tm, "footstep")]))

    # ---- upper body ---------------------------------------------------------------------
    def U(name, aim=0.0, **kw):
        w = WEAPONS[name]
        rise = max(0.0, math.sin(math.radians(aim))) ** 2
        d = dict(gun_ik=1, far_ik=1, aim=aim, look=aim * 0.72, look_w=1, spine_up=-aim * 0.14, hold_x=w["hold"][0],
                 hold_y=w["hold"][1] - w.get("clear", 10) * rise, fore_x=w["fore"][0] * GUN_SCALE, fore_y=w["fore"][1] * GUN_SCALE, brow=0.5)
        d.update(kw)
        return P(d)

    def hold_fn(name, aim):
        T = 1.0

        def fn(t):
            ph = t / T
            p = U(name, aim)
            p["aim"] += 0.5 * math.sin(TAU * ph)
            p["recoil"] = 0.3 * (1 + math.sin(TAU * (ph - 0.25))) * 0.5
            p["spine_up"] += 0.6 * math.sin(TAU * (ph - 0.1))
            return p
        return T, fn

    def fire_fn(name, aim, n):
        w = WEAPONS[name]
        T = n / fps
        kind = w["kind"]

        def fn(t):
            tt = t % T
            if T - tt < 1e-6:
                tt = 0.0
            s = tt / T
            i = int(round(t * fps))
            f = i % n
            p = U(name, aim)
            burst = (1 - s) ** 2 if kind in ("mag",) else math.exp(-s * 9)
            p["recoil"] = w["kick"] * burst
            p["climb"] = w["climb"] * burst
            p["spine_up"] -= 0.35 * w["kick"] * burst
            p["flash"] = SWAY_FLASH[min(f, 2)] if f < 3 else 0.0
            p["flash_seed"] = float(i // n)
            p["shot_t"], p["shot_T"] = tt, T
            p["brow"] = 1.0
            p["eye"] = 0.75
            if kind == "rocket":
                p["mag"] = 0.0      # the warhead has left the tube; reload puts it back
            if kind == "mag":
                p["pump"] = (1 - s) ** 2
            elif kind == "tube":
                p["pump"] = math.sin(math.pi * min(max((s - 0.3) / 0.55, 0), 1))
                p["fh_x"] = -7 * p["pump"]
            elif kind == "bolt":
                u = min(max((s - 0.25) / 0.6, 0), 1)
                p["pump"] = math.sin(math.pi * u)
                p["nh_x"] = -5 * p["pump"]
                p["nh_y"] = 9 * math.sin(math.pi * u) ** 0.5
            return p
        return T, fn

    def reload_clip(name):
        w = WEAPONS[name]
        k = w["reload"] * tm / 1.7
        fx, fy = w["fore"]
        well = (w["well"][0] - fx, w["well"][1] - fy)
        lift = 8 if w["hold"][0] > 15 else 24
        A = lambda **kw: U(name, lift, recoil=3.5, look=-12, look_w=0.6, **kw)
        if w["kind"] == "tube":
            ks = [(0, U(name, 0)), (0.2, A(fh_x=-8, fh_y=2))]
            t = 0.2
            for _ in range(3):
                ks += [(t + 0.14, A(fh_x=-20, fh_y=-20, mag_hand=0)), (t + 0.2, A(fh_x=-20, fh_y=-20, mag_hand=1)),
                       (t + 0.36, A(fh_x=well[0], fh_y=well[1] - 3, mag_hand=1)), (t + 0.42, A(fh_x=well[0], fh_y=well[1], mag_hand=0))]
                t += 0.42
            ks += [(t + 0.14, U(name, 8, fh_x=0)), (t + 0.26, U(name, 6, fh_x=-7, pump=1)), (t + 0.38, U(name, 6, fh_x=0)), (t + 0.5, U(name, 0))]
            total = t + 0.5
            k = w["reload"] * tm / total
            ev = [(0.2 * k, "reload_start"), ((t + 0.26) * k, "reload_done")]
        elif w["kind"] == "rocket":
            B = lambda **kw: U(name, 16, recoil=2, look=-10, look_w=0.6, **kw)
            ks = [(0, U(name, 0, mag=0)), (0.3, B(mag=0, fh_x=-20, fh_y=-14)), (0.42, B(mag=0, fh_x=-20, fh_y=-14, mag_hand=1)),
                  (1.0, B(mag=0, fh_x=-26, fh_y=2, mag_hand=1)), (1.3, B(mag=0, fh_x=-20, fh_y=4, mag_hand=1)),
                  (1.36, B(mag=1, fh_x=-20, fh_y=4, mag_hand=0)), (1.7, U(name, 0))]
            ev = [(0.1 * k, "reload_start"), (1.36 * k, "reload_done")]
        else:
            charge = w["kind"] != "bolt"
            ks = [(0, U(name, 0)), (0.2, A(fh_x=well[0], fh_y=well[1] - 7)), (0.3, A(fh_x=well[0] + 0.5, fh_y=well[1] - 8)),
                  (0.33, A(fh_x=well[0], fh_y=well[1] - 13, mag=0, mag_hand=1)), (0.37, A(fh_x=well[0] - 3, fh_y=well[1] - 15, mag=0, mag_hand=0, mag_t=0.0)),
                  (0.64, A(fh_x=-20, fh_y=-20, mag=0, mag_t=0.27)), (0.72, A(fh_x=-20, fh_y=-20, mag=0, mag_hand=1, mag_t=0.35)),
                  (0.98, A(fh_x=well[0], fh_y=well[1] - 14, mag=0, mag_hand=1, mag_t=0.61)), (1.06, A(fh_x=well[0], fh_y=well[1] - 9, mag=0, mag_hand=1, mag_t=0.69)),
                  (1.1, A(fh_x=well[0], fh_y=well[1] - 7, mag=1, mag_hand=0, mag_t=0.73, spine_up=-1)), (1.18, A(fh_x=well[0] + 1, fh_y=well[1] - 6, mag_t=0.8))]
            if charge:
                ks += [(1.32, U(name, 14, recoil=2, fh_x=-13, fh_y=7, look=-8, look_w=0.6)), (1.42, U(name, 14, recoil=3, fh_x=-19, fh_y=7, pump=1, look=-8, look_w=0.6)),
                       (1.46, U(name, 12, recoil=2, fh_x=-19, fh_y=7)), (1.7, U(name, 0))]
            else:
                ks += [(1.3, U(name, 10, fh_x=0, recoil=1.5)), (1.42, U(name, 8, nh_x=-5, nh_y=8, pump=1)), (1.54, U(name, 8)), (1.7, U(name, 0))]
            ev = [(0.2 * k, "reload_start"), (0.37 * k, "mag_drop"), (1.1 * k, "reload_done")]
        return Keyed(f"{name}_reload", [(t * k, p) for t, p in ks], layer="upper", weapon=name, aim=0, events=ev, tags=("action",))

    def throw_clip(name):
        B = U(name, 0)
        L = lambda **kw: U(name, -38, recoil=4, far_ik=0, **kw)
        return Keyed(f"{name}_throw", keys(
            (0, B), (0.12, L(arm_f_up=-30, arm_f_lo=70, gren=1)), (0.3, L(arm_f_up=-72, arm_f_lo=84, gren=1, spine_up=-5, brow=1)),
            (0.42, L(arm_f_up=104, arm_f_lo=30, gren=1, spine_up=8, brow=1, mouth=0.6)), (0.46, L(arm_f_up=92, arm_f_lo=20, spine_up=9, brow=1)),
            (0.58, L(arm_f_up=60, arm_f_lo=30, spine_up=4)), (0.82, B)),
            layer="upper", weapon=name, aim=0, events=[(0.44 * tm, "grenade")], tags=("action",))

    def melee_clip(name):
        B = U(name, 0)
        reach = min(12, max(0, 24 - WEAPONS[name]["hold"][0]))     # a pistol arm is already extended
        return Keyed(f"{name}_melee", keys(
            (0, B), (0.12, U(name, 34, recoil=7, spine_up=-7, brow=1)), (0.18, U(name, 36, recoil=8, spine_up=-8, brow=1)),
            (0.25, U(name, -8, recoil=-reach * 0.9, spine_up=9, smear=1, brow=1, mouth=0.7, far_ik=0, arm_f_up=-24, arm_f_lo=30)),
            (0.3, U(name, -18, recoil=-reach, spine_up=11, smear=0.6, brow=1, far_ik=0, arm_f_up=-30, arm_f_lo=30)),
            (0.4, U(name, -14, recoil=-reach * 0.75, spine_up=8, far_ik=0, arm_f_up=-16, arm_f_lo=34)), (0.62, B)),
            layer="upper", weapon=name, aim=0, events=[(0.21 * tm, "hit_on"), (0.3 * tm, "hit_off")], tags=("action", "attack"))

    def draw_clip(name):
        return Keyed(f"{name}_draw", keys((0, U(name, -74, recoil=6, far_ik=0.2, look=-20)), (0.14, U(name, -40, recoil=4, far_ik=0.7, look=-10)), (0.3, U(name, 0))),
                     layer="upper", weapon=name, aim=0, events=[(0.0, "weapon_up")], tags=("action",))

    upper = []
    for name in weapons:
        ref = f"{name}_aim_0"
        for a in aims:
            T, fn = hold_fn(name, a)
            upper.append(Proc(f"{name}_aim_{aim_tag(a)}", T * tm, fn, layer="upper", weapon=name, aim=a, fps=hold_fps,
                              cloth_ref=None if a == 0 else ref, tags=("subtle",)))
        n = shot_frames(name, fps)
        for a in aims:
            T, fn = fire_fn(name, a, n)
            upper.append(Proc(f"{name}_fire_{aim_tag(a)}", T, fn, layer="upper", weapon=name, aim=a, cloth_ref=ref,
                              events=[(0.0, "shot")], tags=("fire",)))
        upper += [reload_clip(name), throw_clip(name), melee_clip(name), draw_clip(name)]

    # ---- full body ----------------------------------------------------------------------
    pw = WEAPONS[primary]
    two_hand = dict(far_ik=1, fore_x=pw["fore"][0] * GUN_SCALE, fore_y=pw["fore"][1] * GUN_SCALE)
    Carry = dict(two_hand, arm_n_up=-14, arm_n_lo=64, wep=12)

    body = Body()

    def stay_above_floor(t, p):
        """A collapsing body can't sink: lift the whole thing when any part would go under."""
        for _ in range(2):
            low = min(low_points(solve(full_pose(p), body), body).values())
            if low >= 0.5:
                break
            p["root_y"] += 0.5 - low

    def spin_about(center, height, floor=False):
        def fn(t, p):
            off = rot(center, p["root_rot"])
            w = p["ik_body"]
            p["root_x"] = lerp(p["root_x"], -off[0], w)
            p["root_y"] = lerp(p["root_y"], height - off[1] - HIP_H, w)
            if floor:
                # Contact constraint: a tucked body changes shape as it turns, so no fixed height
                # works. The lowest part rests on the ground on every frame.
                low = min(low_points(solve(full_pose(p), body), body).values())
                p["root_y"] += (0.5 - low) * min(1.0, w * 3.0)
        return fn

    def ball(deg, **kw):
        return P(dict(root_rot=deg, ik_body=1, pelvis=16, spine=36, head=32, neck=4, arm_n_up=52, arm_n_lo=96, arm_f_up=64, arm_f_lo=96,
                      wep=64, foot_n_x=13, foot_n_y=18, foot_n_p=-20, foot_f_x=6, foot_f_y=14, foot_f_p=-30, eye=0.15), **kw)

    stand = P(STANCE, Carry, head=-6)
    SLIDE = dict(root_y=-22, root_x=-4, pelvis=-30, spine=-10, head=-2, foot_n_x=24, foot_n_y=1, foot_n_p=30, foot_f_x=10, foot_f_y=2, foot_f_p=20,
                 gun_ik=1, far_ik=1, hold_x=WEAPONS[primary]["hold"][0], hold_y=WEAPONS[primary]["hold"][1], fore_x=WEAPONS[primary]["fore"][0] * GUN_SCALE,
                 fore_y=WEAPONS[primary]["fore"][1] * GUN_SCALE, look=0, look_w=1, brow=1)
    DOWN = dict(root_y=-27.5, root_x=-8, root_rot=-90, pelvis=0, spine=0, head=8, ik_body=1, arm_n_up=16, arm_n_lo=12, wep=-28, arm_f_up=32, arm_f_lo=14,
                foot_n_x=10, foot_n_p=8, foot_f_x=3, foot_f_y=4, foot_f_p=10, eye=0, mouth=0.25)
    full = [
        Gait("sprint", 0.54 * tm, 50, 19, 0.34, front=0.46, hip=-6, bob=2.0 * bn, bob_at=0.42, lean=15, pelvis=10, head=-18,
             arm_n=(-16, 10, 66, 6), arm_f=(40, 22, 80, 10), wep=30, over=two_hand, heel=12, toe=46, swing_pitch=-62, peak=0.62, tan=0.62,
             sh=2.2, hp=1.6, surge=0.9, tags=("ground",), events=[(0.0, "footstep"), (0.27 * tm, "footstep")]),
        Keyed("roll", keys(
            (0, P(stand, root_y=-8, pelvis=18, spine=18, head=-20, foot_n_x=14, foot_n_p=8, foot_f_x=-12, foot_f_p=-18)),
            (0.08, ball(40, ik_body=0.75, root_y=-12)), (0.16, ball(120)), (0.24, ball(195)), (0.32, ball(270)),
            (0.4, ball(330, ik_body=0.7, root_y=-12)), (0.5, P(CROUCH, Carry, root_y=-12, root_rot=360, spine=18, head=-22)),
            (0.62, P(stand, root_rot=360))),
            add=spin_about((8, 20), 39, floor=True), vel=[(0, 200, 0), (0.42 * tm, 200, 0), (0.62 * tm, 0, 0)], tags=("ground", "tumble"), speed=200,
            events=[(0.08 * tm, "invincible_on"), (0.42 * tm, "invincible_off")]),
        Keyed("slide", keys((0, P(stand)), (0.08, P(SLIDE, root_y=-16, pelvis=-14, spine=2, squash=sq(0.97))), (0.14, P(SLIDE)),
                            (0.44, P(SLIDE, root_y=-23)), (0.56, P(CROUCH, Carry, head=-14)), (0.74, P(stand))),
              vel=[(0, 200, 0), (0.08 * tm, 300, 0), (0.46 * tm, 120, 0), (0.74 * tm, 0, 0)], tags=("ground",), speed=280,
              events=[(0.08 * tm, "skid_dust")]),
        Keyed("hurt", keys(
            (0, P(stand)), (0.05, P(STANCE, Carry, root_x=-6, root_y=-5, pelvis=-9, spine=-20, head=16, arm_n_up=30, arm_f_up=62, foot_n_x=12, foot_n_y=4, eye=0, mouth=1)),
            (0.11, P(STANCE, Carry, root_x=-7, root_y=-9, pelvis=9, spine=21, head=-14, arm_n_up=6, eye=0.1, mouth=0.6)),
            (0.22, P(STANCE, Carry, root_x=-3, root_y=-6, pelvis=9, spine=13, head=-12, eye=0.7, mouth=0.2)), (0.42, P(stand))),
            tags=("ground", "action"), events=[(0.0, "hit_flash")]),
        Keyed("death", keys(
            (0, P(stand)), (0.08, P(STANCE, Carry, root_x=-7, root_y=-5, pelvis=-9, spine=-22, head=20, arm_n_up=38, arm_f_up=66, foot_n_y=3, eye=0, mouth=1)),
            (0.24, P(STANCE, Carry, root_x=-9, root_y=-7, pelvis=-5, spine=-13, head=14, arm_n_up=20, arm_f_up=40, eye=0.1, mouth=0.7)),
            (0.46, P(STANCE, root_x=-6, root_y=-15, pelvis=14, spine=16, head=26, arm_n_up=-4, arm_n_lo=12, wep=30, arm_f_up=8, arm_f_lo=12, eye=0.1, mouth=0.4, foot_n_x=10, foot_f_x=-8)),
            (0.7, P(DOWN, root_rot=-46, root_y=-24, root_x=-7, ik_body=0.55, arm_n_up=62, arm_f_up=74, head=-8)),
            (0.84, P(DOWN)), (0.92, P(DOWN, root_y=-26, head=2, arm_n_up=26, arm_f_up=40)), (1.04, P(DOWN))),
            add=stay_above_floor, tags=("ground", "tumble"), events=[(0.84 * tm, "body_thud")]),
        Keyed("death_blast", keys(
            (0, P(stand)), (0.06, P(STANCE, Carry, root_x=-14, root_y=8, pelvis=-20, spine=-24, head=22, arm_n_up=70, arm_f_up=110, foot_n_x=18, foot_n_y=14, foot_f_x=6, foot_f_y=20, eye=0, mouth=1)),
            (0.3, P(STANCE, root_x=-12, root_y=26, root_rot=-60, ik_body=0.8, spine=-14, head=16, arm_n_up=96, arm_n_lo=20, wep=40, arm_f_up=130, arm_f_lo=20, foot_n_x=16, foot_n_y=16, foot_f_x=2, foot_f_y=22, eye=0, mouth=1)),
            (0.56, P(DOWN, root_x=-16, root_y=-12, root_rot=-96, arm_n_up=34, arm_f_up=66, wep=-10)), (0.64, P(DOWN, root_x=-18, squash=sq(0.96))),
            (0.74, P(DOWN, root_x=-20, root_y=-24, arm_n_up=30, arm_f_up=44)), (0.84, P(DOWN, root_x=-21)), (1.2, P(DOWN, root_x=-22))),
            tags=("tumble",), events=[(0.64 * tm, "body_thud")]),
        Keyed("victory", keys(
            (0, P(stand)), (0.16, P(STANCE, Carry, root_y=-7, spine=8)), (0.36, P(STANCE, root_y=-1, arm_n_up=88, arm_n_lo=46, wep=26, arm_f_up=18, arm_f_lo=70, spine=-4, head=-4, mouth=0.8, foot_n_p=-8)),
            (0.8, P(STANCE, root_y=-2, arm_n_up=92, arm_n_lo=42, wep=26, arm_f_up=20, arm_f_lo=66, spine=-4, head=-4, mouth=0.5)), (1.0, P(STANCE, root_y=-1.6, arm_n_up=88, arm_n_lo=46, wep=26, arm_f_up=18, arm_f_lo=70, spine=-4, head=-4, mouth=0.8))),
            tags=("ground", "hold_feet")),
    ]

    out = {c.name: c for c in lower + upper + full}
    for pair in (combos if combos is not None else DEFAULT_COMBOS):
        low_name, kind = pair.split(":")
        u = f"{primary}_{kind}"
        if low_name in out and u in out:
            n = shot_frames(primary, fps) if kind.startswith("fire") else 0
            nm = f"{low_name}_{kind}"
            out[nm] = Combo(nm, out[low_name], out[u], n, fps)
            if n:
                out[nm].events = [(i * n / fps, "shot") for i in range(int(round(out[nm].duration * fps)) // n)] + list(out[low_name].events)
    return out


DEFAULT_COMBOS = ("idle:aim_0", "idle:fire_0", "run:aim_0", "run:fire_0", "run:fire_p45", "run:fire_m45", "walk:fire_0",
                  "crouch_idle:fire_0", "jump_rise:fire_m45", "fall:fire_0")

SEAMS = [("idle", "jump_start"), ("jump_start", "jump_rise"), ("jump_rise", "jump_apex"), ("jump_apex", "fall"), ("fall", "land"),
         ("land", "idle"), ("idle", "crouch_enter"), ("crouch_enter", "crouch_idle"), ("crouch_idle", "crouch_exit"), ("crouch_exit", "idle")]
