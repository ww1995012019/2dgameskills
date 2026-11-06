# Shared by several modes. Edit only this copy (game-animator/modes/game-sprite-animator/), then run dev/build_standalone.py.
"""Verlet chains for hair, capes, scarves. Offline and deterministic.

Loop clips: run the cycle long enough to shed the start-up transient, then close the seam by
cross-fading the last cycle into the one before it. Damped chains would converge on their own,
but a chain near force balance (wall slide: wind about equal to gravity) responds chaotically
and has no periodic solution to converge to, so the closure can't rely on physics.
Non-loop clips: start from the end state of `prev`, and blend the tail toward the declared
entry state of `next` (normally its first frame), so the cloth is continuous through handovers.
"""
import math
import copy

import numpy as np

from .mathx import rot, smooth

SIM_HZ = 180
FLOOR_TOUCH = 1.5   # rig units above the floor at which a chain counts as lying on it
DT = 1.0 / SIM_HZ


class ChainDef:
    def __init__(self, name, attach, n, seg, gravity=520.0, drag=5.0, stiff=0.0, rest=(-0.3, -1.0),
                 flutter=0.0, ground=True, follow=0.0, rest_frame="chest_rot", max_bend=62.0,
                 width=(0.0, 0.0), max_curl=140.0, swing=None):
        self.name, self.attach, self.n, self.seg = name, attach, n, seg
        self.gravity, self.drag, self.stiff = gravity, drag, stiff
        self.rest = np.array(rest, dtype=float) / (math.hypot(*rest) or 1)
        self.flutter, self.ground, self.follow = flutter, ground, follow
        self.rest_frame = rest_frame
        self.max_bend = max_bend    # degrees between neighbouring segments; stops knots
        self.max_curl = max_curl    # degrees summed root to tip; stops the chain rolling into a loop
        self.width = np.linspace(width[0], width[1], n)     # drawn strip width, root to tip
        self.swing = swing          # (low, high) degrees a segment may turn from rest in its frame, or None


def _anchor_fn(attach):
    """attach = (frame_joint, angle_key, offset): point rigidly bound to a body frame."""
    joint, ang, off = attach

    def fn(sk):
        return np.add(sk[joint], rot(off, sk[ang]))
    return fn


class ClothBake:
    """Holds positions for one chain across a clip: array (steps, n, 2)."""

    def __init__(self, positions, duration, loop):
        self.pos, self.duration, self.loop = positions, duration, loop

    def at(self, t):
        steps = len(self.pos) - (1 if not self.loop else 0)
        x = t / self.duration * steps
        if self.loop:
            x %= steps
        x = max(0.0, min(x, len(self.pos) - 1.0))
        i = int(x)
        j = (i + 1) % len(self.pos) if self.loop else min(i + 1, len(self.pos) - 1)
        return self.pos[i] * (1 - (x - i)) + self.pos[j] * (x - i)

    def first(self):
        return self.pos[0]

    def last(self):
        return self.pos[-1]


def _settle(defn, anchor0, frame_rot):
    d = rot(tuple(defn.rest), frame_rot)
    return np.array([anchor0 + np.array(d) * defn.seg * i for i in range(defn.n)])


def simulate(defn, clip, body, start=None, settle_seconds=6.0, state_at=None):
    """Bake a chain. Optional state_at(t) -> (anchor_xy, angle_degrees) supports other rigs.

    The default path retains the original humanoid sampler and numerical operations.
    """
    if state_at is None:
        from .rig import full_pose, solve
    anchor = _anchor_fn(defn.attach)
    dur = clip.duration
    steps_clip = max(2, int(round(dur * SIM_HZ)))
    if clip.loop:
        total = steps_clip * max(3, math.ceil(settle_seconds / dur) + 2)
        keep_from = total - 2 * steps_clip
    else:
        total = steps_clip + 1
        keep_from = 0

    def state(t):
        if state_at is not None:
            return state_at(t)
        sk = solve(full_pose(clip.sample(t)), body)
        return anchor(sk), sk[defn.rest_frame]

    a0, r0 = state(0.0)
    if start is not None:
        p = start.copy()
    else:
        p = _settle(defn, a0, r0 * defn.follow)
    q = p.copy()
    phases = np.linspace(0, 2.2, defn.n)
    base_w = 2 * math.pi * max(1, round(dur * 6)) / dur  # integer cycles per clip period
    out = np.zeros((total - keep_from, defn.n, 2))
    prev_v = np.array(clip.vel(0.0))
    k = 0

    # Non-loop clips with no prior state still need a resting start.
    if start is None and not clip.loop:
        for _ in range(SIM_HZ):
            np_ = p + (p - q) * 0.92 + np.array([0, -defn.gravity]) * DT * DT
            q, p = p, np_
            p[0] = a0
            _constrain(p, defn, r0)

    for i in range(total):
        t = (i * DT) % dur if clip.loop else min(i * DT, dur)
        a, r = state(t)
        wv = np.array(clip.vel(t), dtype=float)
        acc = (wv - prev_v) / DT
        acc = np.clip(acc, -20000, 20000)
        prev_v = wv
        rel_wind = -wv
        speed = float(np.hypot(*rel_wind))
        v = (p - q) / DT
        force = np.zeros_like(p)
        force[:, 1] -= defn.gravity
        force += defn.drag * (rel_wind - v)
        force -= acc * 0.9
        if defn.flutter:
            amp = defn.flutter * (0.25 + min(speed / 200.0, 1.3))
            nrm = np.sin(base_w * t * 1.0 - phases * 2.4) * amp
            tang = rel_wind / (speed + 1e-6) if speed > 1 else np.array([0, -1.0])
            force[:, 0] += nrm * -tang[1]
            force[:, 1] += nrm * tang[0]
        np_ = p + (p - q) * (1 - 0.002) + force * DT * DT
        q, p = p, np_
        p[0] = a
        _constrain(p, defn, r)
        if defn.ground:
            below = _ground(p, defn)
            # Inelastic floor: moving p alone would leave Verlet an upward velocity and bounce
            # the cloth. Then ground friction.
            q[below, 1] = p[below, 1]
            if not defn.swing:
                p[below, 0] = q[below, 0] * 0.6 + p[below, 0] * 0.4
            elif below.any():   # a sheet on the floor slides out flat: gripped, it piles up on its tip
                for _ in range(4):
                    before = p.copy()
                    p[1:-1] = p[1:-1] * 0.5 + (p[:-2] + p[2:]) * 0.25
                    p[:] = _keep_lengths(p, defn.seg)
                    # Repacking is a geometric correction, not motion. Move the
                    # previous positions with it, or Verlet turns each correction
                    # into a fresh lateral impulse on the next step.
                    q += p - before
                    pushed = _ground(p, defn)
                    q[pushed, 1] = p[pushed, 1]
        if i >= keep_from:
            out[k] = p
            k += 1
    if clip.loop:
        out = _close_loop(out[:steps_clip], out[steps_clip:], defn.seg)
        if defn.ground:
            for f in out:
                _ground(f, defn)
    return ClothBake(out, dur, clip.loop)


def _ground(p, defn):
    """Keep the drawn strip, not just its centreline, above the floor. A strip lying flat needs
    half its width of clearance; one hanging straight down needs almost none. The anchor is
    left alone. Returns the mask of points that were pushed up."""
    tan = np.gradient(p, axis=0)
    flat = np.abs(tan[:, 0]) / (np.hypot(tan[:, 0], tan[:, 1]) + 1e-6)
    floor = 0.8 + np.where(defn.width > 0, defn.width * 0.5 * flat + 1.0, 0.0)
    below = p[:, 1] < floor
    below[0] = False
    p[below, 1] = floor[below]
    return below


def _close_loop(before, last, seg):
    """Fade `last` into `before`: it starts as itself and ends on before[-1], which is the frame
    just ahead of last[0] in the simulation, so the wrap is continuous."""
    n = len(last)
    out = last.copy()
    for i in range(n):
        out[i] = _keep_lengths(last[i] * (1 - smooth(i / n)) + before[i] * smooth(i / n), seg)
    return out


def _keep_lengths(p, seg):
    """A straight lerp between two chain shapes shortens the chain; restore segment lengths."""
    p = p.copy()
    for k in range(1, len(p)):
        d = p[k] - p[k - 1]
        p[k] = p[k - 1] + d / (math.hypot(d[0], d[1]) or 1e-6) * seg
    return p


def _constrain(p, defn, frame_rot):
    n = len(p)
    if defn.stiff > 0:
        d = np.array(rot(tuple(defn.rest), frame_rot * defn.follow))
        for i in range(1, n):
            target = p[i - 1] + d * defn.seg
            p[i] += (target - p[i]) * defn.stiff * (1 - 0.6 * i / n)
    for _ in range(6):
        for i in range(n - 1):
            delta = p[i + 1] - p[i]
            dist = math.hypot(delta[0], delta[1]) or 1e-6
            diff = (dist - defn.seg) / dist
            if i == 0:
                p[1] -= delta * diff
            else:
                p[i] += delta * diff * 0.5
                p[i + 1] -= delta * diff * 0.5
    if defn.swing:
        _limit_swing(p, defn, frame_rot)
    _limit_bend(p, defn.seg, defn.max_bend, defn.max_curl)


def _limit_swing(p, defn, frame_rot):
    """Each segment stays inside a fan around the rest direction, which turns with the body. Cloth
    behind a figure stays behind it through a flip, and hair never falls across the face. A chain on
    the floor lies where it fell: the body turning above it can't drag it through the ground."""
    if defn.ground and p[1:, 1].min() < FLOOR_TOUCH:
        return
    low, high = math.radians(defn.swing[0]), math.radians(defn.swing[1])
    d = rot(tuple(defn.rest), frame_rot * defn.follow)
    base = math.atan2(d[1], d[0])
    for i in range(len(p) - 1):
        s = p[i + 1] - p[i]
        turn = (math.atan2(s[1], s[0]) - base + math.pi) % math.tau - math.pi
        fixed = max(low, min(high, turn))
        if fixed != turn:
            p[i + 1] = p[i] + np.array((math.cos(base + fixed), math.sin(base + fixed))) * defn.seg


def _limit_bend(p, seg, max_bend, max_curl=360.0):
    """Each joint bends at most max_bend, and the turns summed along the chain stay within
    max_curl, so a strip can arc but not roll up. The rest of the chain follows a corrected joint."""
    limit, curl = math.radians(max_bend), math.radians(max_curl)
    total = 0.0
    for i in range(1, len(p) - 1):
        a = p[i] - p[i - 1]
        b = p[i + 1] - p[i]
        turn = math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1])
        fixed = max(-limit, min(limit, turn))
        fixed = max(-curl - total, min(curl - total, fixed))
        total += fixed
        if fixed != turn:
            base = math.atan2(a[1], a[0]) + fixed
            p[i + 1] = p[i] + np.array((math.cos(base), math.sin(base))) * seg


def turn_to(pos, target, w, seg):
    """A chain shape part way to another, each segment turned the short way round. Averaging points
    instead would crumple a chain whose body is still mid-flip, far from the shape it's heading for."""
    a, b = np.diff(pos, axis=0), np.diff(target, axis=0)
    from_ang, to_ang = np.arctan2(a[:, 1], a[:, 0]), np.arctan2(b[:, 1], b[:, 0])
    ang = from_ang + ((to_ang - from_ang + math.pi) % math.tau - math.pi) * w
    steps = np.stack([np.cos(ang), np.sin(ang)], 1) * seg
    return pos[0] + np.concatenate([np.zeros((1, 2)), np.cumsum(steps, axis=0)])


def blend_to(bake, target, seg, frac=0.55, turning=None):
    """Ease the tail of a non-loop bake into the next clip's declared entry state."""
    n = len(bake.pos)
    start = int(n * (1 - frac))
    for i in range(start, n):
        w = smooth((i - start) / max(1, n - 1 - start))
        if turning:         # the chain's definition, when it should turn instead of fade
            bake.pos[i] = turn_to(bake.pos[i], target, w, seg)
            _limit_bend(bake.pos[i], seg, turning.max_bend, turning.max_curl)
            continue
        # Blend the shape relative to the anchor, which keeps following the body: blending
        # world positions would pull the chain off a character that is still displaced.
        anchor = bake.pos[i][0].copy()
        rel = (bake.pos[i] - anchor) * (1 - w) + (target - target[0]) * w
        bake.pos[i] = _keep_lengths(anchor + rel, seg)


def bake_all(clips, body, defs, grounded_chains=()):
    """Returns {clip_name: {chain_name: ClothBake}} honouring prev/next wiring."""
    def contact_def(d, clip):
        if d.name in grounded_chains and 'ground' in getattr(clip, 'tags', ()) and not d.ground:
            d = copy.copy(d)
            d.ground = True
        return d

    bakes = {c: {} for c in clips}
    loops = [c for c in clips.values() if c.loop]
    for clip in loops:
        for d in defs:
            bakes[clip.name][d.name] = simulate(contact_def(d, clip), clip, body)
    # Resolve non-loop clips in dependency order so prev is ready first.
    pending = [c for c in clips.values() if not c.loop]
    guard = 0
    while pending and guard < 64:
        guard += 1
        for clip in list(pending):
            prev = clip.prev if clip.prev in clips else None
            if prev and not bakes[prev]:
                if guard < 32:
                    continue
                prev = None
            for d in defs:
                start = bakes[prev][d.name].last() if prev else None
                b = simulate(contact_def(d, clip), clip, body, start=start)
                bakes[clip.name][d.name] = b
            pending.remove(clip)
    for clip in clips.values():
        if clip.loop or clip.next not in clips:
            continue
        for d in defs:
            target = bakes[clip.next][d.name]
            entry = getattr(clip, "next_at", 0.0)
            effective = contact_def(d, clip)
            blend_to(bakes[clip.name][d.name], target.at(clips[clip.next].duration * entry), d.seg, turning=effective if d.swing else None)
    return bakes
