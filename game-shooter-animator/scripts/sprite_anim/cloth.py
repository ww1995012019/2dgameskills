"""Verlet chains for hair, capes, scarves. Offline and deterministic.

Loop clips: run the cycle long enough to shed the start-up transient, then close the seam by
cross-fading the last cycle into the one before it. Damped chains would converge on their own,
but a chain near force balance (wall slide: wind about equal to gravity) responds chaotically
and has no periodic solution to converge to, so the closure can't rely on physics.
Non-loop clips: start from the end state of `prev`, and in the tail blend toward the first
state of `next`, so the cloth is continuous through the whole jump chain too.
"""
import math

import numpy as np

from .mathx import rot, smooth
from .rig import full_pose, solve

SIM_HZ = 180
DT = 1.0 / SIM_HZ


class ChainDef:
    def __init__(self, name, attach, n, seg, gravity=520.0, drag=5.0, stiff=0.0, rest=(-0.3, -1.0),
                 flutter=0.0, ground=True, follow=0.0, rest_frame="chest_rot", max_bend=62.0,
                 width=(0.0, 0.0), max_curl=140.0):
        self.name, self.attach, self.n, self.seg = name, attach, n, seg
        self.gravity, self.drag, self.stiff = gravity, drag, stiff
        self.rest = np.array(rest, dtype=float) / (math.hypot(*rest) or 1)
        self.flutter, self.ground, self.follow = flutter, ground, follow
        self.rest_frame = rest_frame
        self.max_bend = max_bend    # degrees between neighbouring segments; stops knots
        self.max_curl = max_curl    # degrees summed root to tip; stops the chain rolling into a loop
        self.width = np.linspace(width[0], width[1], n)     # drawn strip width, root to tip


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


def simulate(defn, clip, body, start=None, settle_seconds=6.0):
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
            p[below, 0] = q[below, 0] * 0.6 + p[below, 0] * 0.4
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
    _limit_bend(p, defn.seg, defn.max_bend, defn.max_curl)


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


def blend_to(bake, target, seg, frac=0.55):
    """Ease the tail of a non-loop bake into `target` (first state of the next clip)."""
    n = len(bake.pos)
    start = int(n * (1 - frac))
    for i in range(start, n):
        w = smooth((i - start) / max(1, n - 1 - start))
        # Blend the shape relative to the anchor, which keeps following the body: blending
        # world positions would pull the chain off a character that is still displaced.
        anchor = bake.pos[i][0].copy()
        rel = (bake.pos[i] - anchor) * (1 - w) + (target - target[0]) * w
        bake.pos[i] = _keep_lengths(anchor + rel, seg)


def bake_all(clips, body, defs):
    """Returns {clip_name: {chain_name: ClothBake}} honouring prev/next wiring."""
    bakes = {c: {} for c in clips}
    loops = [c for c in clips.values() if c.loop]
    for clip in loops:
        for d in defs:
            bakes[clip.name][d.name] = simulate(d, clip, body)
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
                b = simulate(d, clip, body, start=start)
                bakes[clip.name][d.name] = b
            pending.remove(clip)
    for clip in clips.values():
        if clip.loop or clip.next not in clips:
            continue
        for d in defs:
            blend_to(bakes[clip.name][d.name], bakes[clip.next][d.name].first(), d.seg)
    return bakes
