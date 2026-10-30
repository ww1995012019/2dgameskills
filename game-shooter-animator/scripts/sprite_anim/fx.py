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
    add("dust_slide", 0.4, lambda cv, u: puffs(cv, dust(skid, 34, [d1, d2, d3], u)))

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

    add("hit_spark", 0.24, hit(_sparks(21, 8, 34), spark))
    add("bullet_impact", 0.2, hit(_sparks(22, 6, 22), [(255, 255, 255), (214, 206, 190), (150, 140, 124)], rings=False))

    fire = [(255, 255, 255), (255, 226, 120), (255, 170, 60), (214, 86, 40)]
    smoke = [(96, 92, 90), (70, 68, 68), (128, 122, 118)]
    blast = _blob_particles(31, 26, (0, math.tau), (0.0, 0.5), life=(0.45, 1.0), size=(9, 20), cols=[0, 1, 2])
    soot = _blob_particles(32, 12, (0, math.tau), (0.3, 0.9), life=(0.7, 1.0), size=(10, 22), cols=[0, 1, 2])

    def explosion(cv, u):
        c = (0, 44)
        ps = dust(soot, 58, smoke, u * 0.9)
        puffs(cv, [((a[0], a[1] + 16), r, k) for a, r, k in ps])
        for p in blast:
            v = min(u / p["life"], 1.0)
            if v >= 1:
                continue
            t = 1 - (1 - v) ** 2.6
            pos = (c[0] + math.cos(p["ang"]) * 62 * p["sp"] * t, c[1] + math.sin(p["ang"]) * 50 * p["sp"] * t + 12 * p["rise"] * t)
            r = p["r"] * (1 - v) ** 0.6 * (0.5 + 0.5 * smooth(v / 0.12))
            col = fire[min(3, int(v * 4 + p["col"] * 0.34))]
            if r > 0.4:
                cv.details([(_circle(pos, r, 12), col, 255)])
        if u < 0.14:
            cv.details([(_circle(c, 46 * smooth(u / 0.1), 20), (255, 255, 255), 255)])
        ring = 26 + 62 * (1 - (1 - u) ** 2)
        w = 7 * (1 - u) ** 2
        if w > 0.4:
            cv.details([(_circle(c, ring + w, 26) + _circle(c, ring, 26)[::-1], (255, 226, 120), 255)])
    add("explosion", 0.7, explosion)

    def bullet(cv, u):
        y = 52
        cv.details([([(-24, y - 0.5), (2, y - 1.2), (6, y), (2, y + 1.2), (-24, y + 0.5)], (255, 226, 120), 255),
                    ([(-6, y - 0.6), (3, y - 0.8), (5, y), (3, y + 0.8), (-6, y + 0.6)], (255, 255, 255), 255)])
    add("bullet", 0.2, bullet, loop=True)

    def grenade(cv, u):
        c = (0, 52)
        a = u * math.tau
        pts = [(c[0] + math.cos(a + i / 10 * math.tau) * (5.5 if i % 5 else 6.4), c[1] + math.sin(a + i / 10 * math.tau) * 4.6) for i in range(10)]
        cv.details([(_circle(c, 6.6, 12), (24, 24, 28), 255), (pts, (86, 102, 70), 255)])
        cv.details([(_circle((c[0] + math.cos(a) * 3, c[1] + math.sin(a) * 2.6), 1.8, 8), (216, 169, 63), 255)])
    add("grenade", 0.4, grenade, loop=True)

    def rocket(cv, u):
        y = 52
        w = math.sin(u * math.tau)
        cv.details([([(-34 - 5 * w, y), (-18, y - 4), (-16, y + 4)], (255, 170, 60), 255), ([(-27 + 3 * w, y), (-18, y - 2.2), (-18, y + 2.2)], (255, 255, 255), 255),
                    ([(-20, y - 3.6), (10, y - 3.6), (21, y), (10, y + 3.6), (-20, y + 3.6)], (24, 24, 28), 255),
                    ([(-18, y - 2.4), (8, y - 2.4), (15, y), (8, y + 2.4), (-18, y + 2.4)], (96, 106, 76), 255)])
    add("rocket", 0.2, rocket, loop=True)
    return out
