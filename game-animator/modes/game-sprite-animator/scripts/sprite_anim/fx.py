"""Stand-alone effect sprites that pair with clip events (footstep, land_dust, hit_on, ...).
Particles are seeded, so the output is deterministic."""
import math
import random

from .art import Canvas, hex_rgb
from .mathx import clamp, smooth
from .render import GROUND_FRAC, UNIT_PX, to_u8


def _circle(c, r, n=14):
    return [(c[0] + math.cos(i / n * math.tau) * r, c[1] + math.sin(i / n * math.tau) * r) for i in range(n)]


def _blob_particles(seed, count, spread, rise, life=(0.55, 1.0), size=(5, 11), cols=None):
    rng = random.Random(seed)
    out = []
    for _ in range(count):
        ang = rng.uniform(*spread)
        speed = rng.uniform(0.55, 1.0)
        out.append(dict(ang=ang, sp=speed, life=rng.uniform(*life), r=rng.uniform(*size),
                        rise=rng.uniform(*rise), col=rng.randrange(len(cols or [0]))))
    return out


def dust(parts, dist, cols, t):
    """Outward puffs with ease-out travel; radius blooms then collapses (no alpha fade, so
    the same art works in pixel mode)."""
    polys = []
    for p in parts:
        u = clamp(t / p["life"])
        if u >= 1:
            continue
        travel = (1 - (1 - u) ** 2.4) * dist * p["sp"]
        x = math.cos(p["ang"]) * travel
        y = max(0, math.sin(p["ang"]) * travel) + p["rise"] * u * 30 + 3
        r = p["r"] * (smooth(u / 0.28) * (1 - smooth((u - 0.3) / 0.7)) * 1.05)
        if r > 0.3:
            polys.append(((x, y), r, cols[p["col"]]))
    return polys


def _sparks(seed, count, length):
    rng = random.Random(seed)
    return [(rng.uniform(0, math.tau), rng.uniform(0.55, 1.0) * length, rng.uniform(1.6, 3.2)) for _ in range(count)]


def _render_polys(size, pixel, ss, draw_fn):
    cv = Canvas(size, ss, size * UNIT_PX, GROUND_FRAC, 0, pixel, (0, 0, 0))
    draw_fn(cv)
    f = cv.resolve()
    if pixel:
        f[..., 3] = (f[..., 3] > 0.5).astype(f.dtype)
    return to_u8(f)


def build_fx(size, fps, pixel, spec):
    ss = 4 if size >= 128 else 5
    col = spec.get("colors", {})
    d1, d2, d3 = hex_rgb(col.get("dust", "#d8cfbc")), hex_rgb(col.get("dust2", "#b5a890")), (240, 234, 220)
    spark = [(255, 255, 255), (255, 236, 150), (255, 190, 80)]
    magic = [(255, 255, 255), (190, 235, 255), (110, 195, 255)]
    out = {}

    def add(name, dur, fn, loop=False):
        n = max(3, int(round(dur * fps)))
        frames = []
        for i in range(n):
            u = i / n if loop else (i + 0.5) / n
            frames.append(_render_polys(size, pixel, ss, lambda cv: fn(cv, u)))
        out[name] = dict(frames=frames, fps=fps, loop=loop, duration=dur)

    def puffs(cv, ps):
        cv.details([(_circle(c, r), col_, 255) for c, r, col_ in ps])

    step = _blob_particles(3, 5, (2.3, 3.1), (0.0, 0.25), size=(2.5, 5), cols=[0, 1, 2])
    add("dust_step", 0.3, lambda cv, u: puffs(cv, dust(step, 20, [d1, d2, d3], u)))

    land_l = _blob_particles(5, 7, (2.7, 3.14), (0.0, 0.2), size=(4, 8), cols=[0, 1, 2])
    land_r = _blob_particles(6, 7, (0.0, 0.44), (0.0, 0.2), size=(4, 8), cols=[0, 1, 2])
    add("dust_land", 0.42, lambda cv, u: puffs(cv, dust(land_l + land_r, 46, [d1, d2, d3], u)))

    skid = _blob_particles(9, 9, (0.1, 0.9), (0.05, 0.4), size=(3, 7), cols=[0, 1, 2])
    add("dust_skid", 0.4, lambda cv, u: puffs(cv, dust(skid, 34, [d1, d2, d3], u)))

    burst = _blob_particles(11, 10, (2.8, 3.5), (0.0, 0.15), size=(3, 7), cols=[0, 1, 2])
    add("dust_dash", 0.34, lambda cv, u: puffs(cv, dust(burst, 60, [d1, d2, d3], u)))

    puff_air = _blob_particles(13, 12, (0, math.tau), (0.0, 0.0), size=(3, 6), cols=[0, 1, 2])

    def air(cv, u):
        ps = dust(puff_air, 30, [(255, 255, 255), (214, 232, 255), (190, 214, 245)], u)
        puffs(cv, [((c[0], c[1] + 30), r, k) for c, r, k in ps])
    add("puff_air", 0.34, air)

    def hit(sparks_, cols, cy=52, rings=True):
        def fn(cv, u):
            c = (0, cy)
            if rings:
                r = 8 + 26 * (1 - (1 - u) ** 2)
                w = 5 * (1 - u)
                if w > 0.35:
                    ring = _circle(c, r + w, 24) + _circle(c, r, 24)[::-1]
                    cv.details([(ring, cols[1], 255)])
                core = 12 * (1 - smooth(u / 0.45))
                if core > 0.4:
                    star = []
                    for i in range(16):
                        k = core * (1.9 if i % 2 == 0 else 0.62)
                        a = i / 16 * math.tau + 0.2
                        star.append((c[0] + math.cos(a) * k, c[1] + math.sin(a) * k))
                    cv.details([(star, cols[0], 255)])
            for a, ln, w in sparks_:
                p = 1 - (1 - u) ** 2.2
                head = ln * p
                tail = ln * max(0.0, p - 0.28 * (1 - u) - 0.05)
                wid = w * (1 - u)
                if wid < 0.2 or head - tail < 0.5:
                    continue
                nx, ny = -math.sin(a) * wid, math.cos(a) * wid
                tx, ty = math.cos(a), math.sin(a)
                cv.details([([(c[0] + tx * tail, c[1] + ty * tail), (c[0] + tx * (head * 0.8) + nx, c[1] + ty * (head * 0.8) + ny),
                              (c[0] + tx * head, c[1] + ty * head), (c[0] + tx * (head * 0.8) - nx, c[1] + ty * (head * 0.8) - ny)],
                             cols[2 if a % 1 > 0.5 else 1], 255)])
        return fn

    add("hit_spark", 0.3, hit(_sparks(21, 9, 44), spark))
    add("block_spark", 0.24, hit(_sparks(22, 7, 34), magic))

    def orb(cv, u):
        c = (0, 52)
        w = math.sin(u * math.tau)
        for k, (col_, r) in enumerate(((magic[2], 14 + 1.6 * w), (magic[1], 10 - 1.2 * w), (magic[0], 5.5 + 0.8 * w))):
            cv.details([(_circle(c, r, 18), col_, 255)])
        for i in range(4):
            a = u * math.tau + i * math.tau / 4
            p = (c[0] + math.cos(a) * 19, c[1] + math.sin(a * 2 + i) * 6 + math.sin(a) * 15)
            cv.details([(_circle(p, 2.3, 8), magic[1], 255)])
    add("projectile_orb", 0.5, orb, loop=True)
    return out
