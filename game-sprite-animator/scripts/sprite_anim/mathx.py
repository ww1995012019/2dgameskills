"""Interpolation primitives. Everything here is C1-continuous on purpose:
velocity jumps between keys are what the eye reads as stutter."""
import math

import numpy as np


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def hermite(p0, m0, p1, m1, s):
    s2, s3 = s * s, s * s * s
    return ((2 * s3 - 3 * s2 + 1) * p0 + (s3 - 2 * s2 + s) * m0
            + (-2 * s3 + 3 * s2) * p1 + (s3 - s2) * m1)


def rot(v, deg):
    """Rotate vector clockwise (y-up space) by deg."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c + v[1] * s, -v[0] * s + v[1] * c)


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def scale(a, k):
    return (a[0] * k, a[1] * k)


def _pchip_tangents(t, v, loop):
    """Fritsch-Carlson monotone tangents: no overshoot between keys, C1 at keys.
    t: (n,), v: (n, c). When loop=True the last key must duplicate the first."""
    h = np.diff(t)[:, None]
    d = np.diff(v, axis=0) / h
    n = len(t)
    m = np.zeros_like(v)
    if loop:
        dp = np.vstack([d[-1:], d[:-1]])  # incoming slope at keys 0..n-2
        hp = np.vstack([h[-1:], h[:-1]])
        rng = range(n - 1)
    else:
        dp = np.vstack([d[:1], d[:-1]])
        hp = np.vstack([h[:1], h[:-1]])
        rng = range(1, n - 1)
    for k in rng:
        same = dp[k] * d[k] > 0
        w1 = 2 * h[k] + hp[k]
        w2 = h[k] + 2 * hp[k]
        with np.errstate(divide="ignore", invalid="ignore"):
            hm = (w1 + w2) / (w1 / dp[k] + w2 / d[k])
        m[k] = np.where(same, hm, 0.0)
    if loop:
        m[-1] = m[0]
    return m


class Curve:
    """Vector-valued monotone cubic spline over (time, value-row) keys."""

    def __init__(self, times, values, loop=False, period=None):
        self.t = np.asarray(times, dtype=float)
        self.v = np.asarray(values, dtype=float)
        self.loop = loop
        if loop:
            self.period = float(period)
            if self.t[0] > 0 or self.t[-1] < self.period:
                # Wrap: append first key one period later so the seam is smooth.
                self.t = np.append(self.t, self.t[0] + self.period)
                self.v = np.vstack([self.v, self.v[0]])
        self.m = _pchip_tangents(self.t, self.v, loop) if len(self.t) > 1 else None

    def __call__(self, t):
        if len(self.t) == 1:
            return self.v[0].copy()
        if self.loop:
            t = self.t[0] + (t - self.t[0]) % self.period
        else:
            t = clamp(t, self.t[0], self.t[-1])
        i = int(np.searchsorted(self.t, t, side="right") - 1)
        i = min(max(i, 0), len(self.t) - 2)
        h = self.t[i + 1] - self.t[i]
        s = (t - self.t[i]) / h
        return hermite(self.v[i], self.m[i] * h, self.v[i + 1], self.m[i + 1] * h, s)


def periodic1(keys, x):
    """Scalar periodic curve on [0,1). keys: [(phase, value), ...]."""
    ts, vs = zip(*keys)
    return float(Curve(ts, [[v] for v in vs], loop=True, period=1.0)(x)[0])


def catmull_closed(pts, sub=8):
    """Resample a closed control polygon into a smooth loop."""
    p = np.asarray(pts, dtype=float)
    n = len(p)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = p[(i - 1) % n], p[i], p[(i + 1) % n], p[(i + 2) % n]
        for k in range(sub):
            t = k / sub
            out.append(0.5 * ((2 * p1) + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (3 * p1 - p0 - 3 * p2 + p3) * t * t * t))
    return np.array(out)


def catmull_open(pts, sub=6):
    p = np.asarray(pts, dtype=float)
    n = len(p)
    if n < 3:
        return p
    out = []
    for i in range(n - 1):
        p0, p1, p2, p3 = p[max(i - 1, 0)], p[i], p[i + 1], p[min(i + 2, n - 1)]
        for k in range(sub):
            t = k / sub
            out.append(0.5 * ((2 * p1) + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (3 * p1 - p0 - 3 * p2 + p3) * t * t * t))
    out.append(p[-1])
    return np.array(out)
