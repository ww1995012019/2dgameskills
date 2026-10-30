"""Character renderer. Parts are drawn from rig joints each frame, not warped from a bitmap,
so line weight and detail stay crisp at any frame rate and size.

Shading is computed in screen space from each part's silhouette (rim shadow on the side away
from the light, thin highlight toward it), so the light direction stays fixed while limbs
rotate - baked-in shading that rotates with the limb is a classic cut-out animation tell.
"""
import colorsys
import math

import numpy as np
from PIL import Image, ImageDraw

from .cloth import ChainDef
from .mathx import add, catmull_closed, catmull_open, rot, scale
from .rig import Body, FOOT_BALL


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def shift(rgb, dl=0.0, ds=0.0, dh=0.0):
    h, l, s = colorsys.rgb_to_hls(*[c / 255 for c in rgb])
    r, g, b = colorsys.hls_to_rgb((h + dh) % 1, min(1, max(0, l + dl)), min(1, max(0, s + ds)))
    return (int(r * 255), int(g * 255), int(b * 255))


def ramp(base):
    """(shadow, base, light): hue-shifted toward cool shadows / warm lights."""
    c = hex_rgb(base) if isinstance(base, str) else base
    return (shift(c, -0.15, 0.03, -0.022), c, shift(c, 0.13, 0.02, 0.018))


def darken_far(r):
    """Far-side limbs: darker and cooler so depth reads without a depth buffer."""
    k = 0.70
    return tuple((int(c[0] * k), int(c[1] * k), int(min(255, c[2] * k * 1.03))) for c in r)


# ------------------------------------------------------------------------------- shapes


def capsule(a, ra, b, rb, n=7):
    """Tapered capsule polygon a->b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    base = math.atan2(dy, dx)
    pts = []
    for i in range(n * 2 + 1):
        ang = base + math.pi / 2 + i * math.pi / (n * 2)
        pts.append((a[0] + math.cos(ang) * ra, a[1] + math.sin(ang) * ra))
    for i in range(n * 2 + 1):
        ang = base - math.pi / 2 + i * math.pi / (n * 2)
        pts.append((b[0] + math.cos(ang) * rb, b[1] + math.sin(ang) * rb))
    return pts


def blob(center, ctrl, angle=0.0, s=1.0, sub=7):
    """Smooth closed curve through control points given in a local frame."""
    pts = [add(center, rot(scale(p, s), angle)) for p in ctrl]
    return [tuple(p) for p in catmull_closed(pts, sub)]


def ribbon(points, widths, sub=5):
    """Polygon strip around a polyline with per-point width."""
    c = catmull_open(points, sub)
    w = np.interp(np.linspace(0, len(widths) - 1, len(c)), np.arange(len(widths)), widths)
    d = np.gradient(c, axis=0)
    ln = np.hypot(d[:, 0], d[:, 1])[:, None] + 1e-6
    nrm = np.stack([-d[:, 1], d[:, 0]], axis=1) / ln
    l, r = c + nrm * w[:, None] / 2, c - nrm * w[:, None] / 2
    return [tuple(p) for p in l] + [tuple(p) for p in r[::-1]]


# ------------------------------------------------------------------------------- canvas


class Canvas:
    """Supersampled straight-alpha RGBA canvas; `group` paints one outlined, shaded silhouette."""

    def __init__(self, size, ss, units_per_h, ground_frac, stroke_px, flat, ink):
        self.size, self.ss = size, ss
        self.w = self.h = size * ss
        self.s = units_per_h * ss  # px per rig unit
        self.ox, self.oy = self.w / 2, self.h * ground_frac
        self.buf = np.zeros((self.h, self.w, 4), dtype=np.uint8)
        self.stroke = stroke_px * ss
        self.flat = flat            # flat = no highlight softness, palette-safe (pixel mode)
        self.ink = ink
        self.sx = self.sy = 1.0
        self.squash_x0 = 0.0

    def set_squash(self, sy, x0=0.0):
        self.sy, self.sx, self.squash_x0 = sy, 1.0 / sy ** 0.6, x0

    def T(self, p):
        return (self.ox + (self.squash_x0 + (p[0] - self.squash_x0) * self.sx) * self.s,
                self.oy - p[1] * self.sy * self.s)

    def tpts(self, pts):
        return [self.T(p) for p in pts]

    def group(self, items, stroke=True, shade=1.0, ink=None, stroke_scale=1.0, alpha=1.0):
        """Paint polygons as one silhouette. items: [(pts, ramp), ...] back-to-front."""
        polys = [(self.tpts(p), r) for p, r in items]
        xs = [q[0] for p, _ in polys for q in p]
        ys = [q[1] for p, _ in polys for q in p]
        pad = int(self.stroke * stroke_scale + 3)
        x0, y0 = int(min(xs)) - pad, int(min(ys)) - pad
        x1, y1 = int(max(xs)) + pad + 1, int(max(ys)) + pad + 1
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, self.w), min(y1, self.h)
        if x1 <= x0 or y1 <= y0:
            return
        w, h = x1 - x0, y1 - y0
        idx_im = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(idx_im)
        for i, (p, _) in enumerate(polys):
            d.polygon([(q[0] - x0, q[1] - y0) for q in p], fill=i + 1)
        idx = np.asarray(idx_im)
        m = idx > 0
        out = self.buf[y0:y1, x0:x1]

        if stroke and self.stroke > 0:
            st_im = Image.new("L", (w, h), 0)
            sd = ImageDraw.Draw(st_im)
            sw = int(max(1, round(2 * self.stroke * stroke_scale)))
            for p, _ in polys:
                q = [(a - x0, b - y0) for a, b in p]
                sd.line(q + [q[0]], fill=255, width=sw, joint="curve")
                r = sw / 2
                for a, b in q[:: max(1, len(q) // 24)]:
                    sd.ellipse((a - r, b - r, a + r, b + r), fill=255)
            st = np.asarray(st_im) > 0
            c = ink or self.ink
            out[st] = (*c, 255)

        k = 1.0 * self.s
        lx, ly = -0.62, -0.78                       # light from upper-left
        sh_d, hi_d = 2.1 * k * shade, 0.95 * k * shade

        def shifted(a, dx, dy):
            r = np.zeros_like(a)
            dx, dy = int(round(dx)), int(round(dy))
            if abs(dx) >= a.shape[1] or abs(dy) >= a.shape[0]:
                return r        # sliver clipped at the frame edge: shifted fully out of its box
            ys0, ys1 = max(0, dy), a.shape[0] + min(0, dy)
            xs0, xs1 = max(0, dx), a.shape[1] + min(0, dx)
            r[ys0:ys1, xs0:xs1] = a[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
            return r

        shadow = m & ~shifted(m, lx * sh_d, ly * sh_d)
        light = m & ~shifted(m, -lx * hi_d, -ly * hi_d)
        palette = np.zeros((len(polys) + 1, 3, 3), dtype=np.uint8)
        for i, (_, r) in enumerate(polys):
            palette[i + 1] = r
        rgb = palette[idx, 1]
        rgb[light] = palette[idx, 2][light]
        rgb[shadow] = palette[idx, 0][shadow]
        out[m, :3] = rgb[m]
        out[m, 3] = int(255 * alpha)

    def details(self, polys):
        """Batch of (pts, color, alpha) drawn with a single fast loop on bboxes."""
        for pts, color, alpha in polys:
            if alpha <= 0:
                continue
            q = self.tpts(pts)
            xs = [a[0] for a in q]
            ys = [a[1] for a in q]
            x0, y0 = max(int(min(xs)) - 1, 0), max(int(min(ys)) - 1, 0)
            x1, y1 = min(int(max(xs)) + 2, self.w), min(int(max(ys)) + 2, self.h)
            if x1 <= x0 or y1 <= y0:
                continue
            m = Image.new("L", (x1 - x0, y1 - y0), 0)
            ImageDraw.Draw(m).polygon([(a - x0, b - y0) for a, b in q], fill=255)
            mk = np.asarray(m) > 0
            out = self.buf[y0:y1, x0:x1]
            if alpha >= 255:
                out[mk, :3] = color
                out[mk, 3] = 255
            else:
                # Straight-alpha "over": blending against transparent black would grey the fx.
                a = alpha / 255
                sel = out[mk].astype(np.float32)
                da = sel[:, 3:] / 255
                oa = a + da * (1 - a)
                sel[:, :3] = (np.array(color) * a + sel[:, :3] * da * (1 - a)) / oa
                sel[:, 3:] = oa * 255
                out[mk] = sel.astype(np.uint8)

    def resolve(self):
        """Downsample with premultiplied alpha so edges don't pick up black fringes."""
        f = self.buf.astype(np.float32) / 255
        f[..., :3] *= f[..., 3:]
        n = self.ss
        h, w = self.size, self.size
        f = f[:h * n, :w * n].reshape(h, n, w, n, 4).mean(axis=(1, 3))
        a = f[..., 3:]
        with np.errstate(divide="ignore", invalid="ignore"):
            rgb = np.where(a > 1e-4, f[..., :3] / a, 0.0)
        return np.dstack([rgb, a])


# ------------------------------------------------------------------------------- character


DEFAULT_SPEC = {
    "name": "soldier",
    "body": {},
    "style": {},
    "colors": {
        "skin": "#e9bd96", "hair": "#3a2c24", "tunic": "#5d7048", "tunic2": "#46553a",
        "pants": "#4d5a3f", "boots": "#3b3530", "belt": "#2e2a26", "metal": "#b9c1c9",
        "accent": "#d8a93f", "cape": "#a6392f", "glove": "#2f2c29", "eye": "#1d2230",
        "ink": "#17161c", "vest": "#6b6a4a", "helmet": "#55654a", "gun": "#3c4048",
        "gun2": "#2a2c31", "wood": "#7a4e2c",
    },
    "head": "helmet",        # helmet | beret | cap | headband | balaclava | hair
    "goggles": False,
    "weapons": ["rifle"],    # first one is carried in full-body clips and combos
    "weapon": "rifle",
    "cloth": [],             # scarf, hair, headband
    "armor": False,
    "backpack": False,
    "long_sleeves": False,
}


def merged_spec(spec):
    s = {**DEFAULT_SPEC, **(spec or {})}
    s["colors"] = {**DEFAULT_SPEC["colors"], **(spec or {}).get("colors", {})}
    return s


def chain_defs(spec):
    b = Body.from_spec(spec.get("body"))
    hs = b.head_size
    out = []
    cloth = spec["cloth"]
    if "cape" in cloth:
        out.append(ChainDef("cape", ("neck", "chest_rot", (-6.0, -1.0)), 8, 6.6, gravity=620, drag=5.0,
                            flutter=900, stiff=0.0025, rest=(-0.22, -1.0), follow=1.0, width=(11, 19)))
    if "scarf" in cloth:
        out.append(ChainDef("scarf", ("neck", "chest_rot", (-7.0, 0.5)), 9, 5.0, gravity=420, drag=4.5,
                            flutter=1400, stiff=0.006, rest=(-0.8, -0.6), follow=0.3, width=(6.5, 5.0)))
    if "hair" in cloth:
        out.append(ChainDef("hair", ("head_base", "head_rot", (-11.0 * hs, 20.0 * hs)), 6, 4.2 * hs,
                            gravity=300, drag=6.5, stiff=0.03, rest=(-0.75, -0.8), follow=1.0,
                            flutter=260, rest_frame="head_rot", width=(7.0, 1.4)))
    if "headband" in cloth or spec["head"] == "headband":
        out.append(ChainDef("headband", ("head_base", "head_rot", (-13.0 * hs, 21.0 * hs)), 6, 3.6 * hs,
                            gravity=300, drag=6.0, stiff=0.02, rest=(-0.9, -0.6), follow=1.0,
                            flutter=420, rest_frame="head_rot", width=(4.2, 1.6)))
    return out


class CharacterArt:
    def __init__(self, spec):
        self.spec = merged_spec(spec)
        self.body = Body.from_spec(self.spec.get("body"))
        col = self.spec["colors"]
        self.c = {k: ramp(v) for k, v in col.items()}
        self.ink = hex_rgb(col["ink"])
        self.bulk = self.body.bulk

    def palette(self):
        """All flat colours used: pixel mode quantizes to exactly this list."""
        cols = {self.ink}
        for r in self.c.values():
            for c in r:
                cols.add(c)
            for c in darken_far(r):
                cols.add(c)
        cols |= {(255, 255, 255), (250, 240, 200), (255, 226, 120), (255, 170, 60), (225, 175, 60)}
        return sorted(cols)

    # -- limbs ------------------------------------------------------------------------

    def leg(self, cv, sk, side, far):
        c = self.c
        pants, boots = c["pants"], c["boots"]
        metal = c["metal"]
        if far:
            pants, boots, metal = darken_far(pants), darken_far(boots), darken_far(metal)
        hipj, kn, an, fr = sk["hip_" + side], sk["kn_" + side], sk["an_" + side], sk["fr_" + side]
        q = self.bulk
        thigh = capsule(hipj, 6.4 * q, kn, 4.6 * q)
        sh_dir = (an[0] - kn[0], an[1] - kn[1])
        sl = math.hypot(*sh_dir) or 1
        su = (sh_dir[0] / sl, sh_dir[1] / sl)
        top = add(kn, scale(su, sl * 0.4))
        shin_up = capsule(kn, 4.7 * q, top, 4.3 * q)
        shin_lo = capsule(top, 4.5 * q, add(an, (0, 0.5)), 3.7 * q)
        # Foot with a toe hinge: when the heel lifts the toe stays flat on the ground.
        pitch = -fr
        ball = FOOT_BALL

        def f(p):
            if p[0] > ball[0] and pitch < 0:
                d = rot((p[0] - ball[0], p[1] - ball[1]), -pitch * 0.85)
                p = (ball[0] + d[0], ball[1] + d[1])
            return add(an, rot(p, fr))

        ctrl = [(-3.8, 3.2), (-5.4, -0.8), (-5.0, -5.0), (0.5, -5.2), (6.5, -5.2), (11.6, -5.0),
                (12.2, -2.6), (8.0, -0.3), (4.2, 1.8), (3.6, 4.5)]
        foot = [tuple(p) for p in catmull_closed([f(p) for p in ctrl], 5)]
        cv.group([(thigh, pants), (shin_up, pants), (shin_lo, boots), (foot, boots)], shade=1.0)
        nx, ny = -su[1], su[0]
        cuff = capsule(add(top, (nx * 4.7 * q, ny * 4.7 * q)), 1.3, add(top, (-nx * 4.7 * q, -ny * 4.7 * q)), 1.3, 3)
        sole = [f((-5.0, -3.9)), f((6.5, -3.9)), f((12.0, -3.8)), f((12.1, -5.2)), f((6.5, -5.3)), f((-5.1, -5.3))]
        det = [(sole, boots[0], 255), (cuff, boots[2], 255)]
        if self.spec.get("armor"):
            pad = blob(kn, [(-3, 2.6), (2, 3.4), (4, 0), (2, -3.4), (-3, -2.6)], s=q)
            cv.group([(pad, boots)], stroke_scale=0.6, shade=0.6)
        cv.details(det)

    def arm(self, cv, sk, side, far):
        c = self.c
        tunic, skin = c["tunic2"] if far else c["tunic"], c["glove"] if self.spec.get("gloves", True) else c["skin"]
        metal = c["metal"]
        if far:
            tunic, skin, metal = darken_far(tunic), darken_far(skin), darken_far(metal)
        q = self.bulk
        s, e, w = sk["sh_" + side], sk["el_" + side], sk["wr_" + side]
        up = capsule(s, 4.5 * q, e, 3.4 * q)
        lo = capsule(e, 3.5 * q, w, 2.9 * q)
        hand = blob(add(w, scale((w[0] - e[0], w[1] - e[1]), 0.13)),
                    [(-2.7, 2.8), (2.6, 3.0), (3.6, 0), (2.4, -3.1), (-2.6, -2.9)], -sk["fa_" + side], q)
        fore = tunic if self.spec.get("long_sleeves") else (c["skin"] if not far else darken_far(c["skin"]))
        items = [(up, tunic), (lo, fore), (hand, skin)]
        cv.group(items)
        dx, dy = w[0] - e[0], w[1] - e[1]
        ln = math.hypot(dx, dy) or 1
        ux, uy = dx / ln, dy / ln
        mid = add(w, (-ux * 2.2, -uy * 2.2))
        band = capsule(add(mid, (-uy * 3.1 * q, ux * 3.1 * q)), 1.5, add(mid, (uy * 3.1 * q, -ux * 3.1 * q)), 1.5, 3)
        cv.details([(band, skin[0], 255)])
        if self.spec.get("armor"):
            pad = blob(s, [(-5.5, 3), (0, 6.5), (6, 3.5), (6, -3), (0, -6), (-5.5, -3)], s=q)
            cv.group([(pad, metal)], shade=0.7)

    # -- torso ------------------------------------------------------------------------


    # -- head -------------------------------------------------------------------------


    # -- weapon -----------------------------------------------------------------------


    # -- cloth ------------------------------------------------------------------------


    def scarf(self, cv, pts):
        c = self.c
        n = len(pts)
        strip = ribbon([tuple(p) for p in pts], list(np.linspace(6.5, 5.0, n)))
        cv.group([(strip, c["cape"])], shade=0.7)
        t = pts[-1]
        d = pts[-1] - pts[-2]
        ln = math.hypot(*d) or 1
        u = d / ln
        nrm = np.array([-u[1], u[0]])
        fringe = [tuple(t + nrm * 2.7), tuple(t + u * 3.5 + nrm * 1.6), tuple(t + u * 1.4), tuple(t + u * 3.5 - nrm * 1.6), tuple(t - nrm * 2.7)]
        cv.group([(fringe, c["accent"])], stroke_scale=0.5, shade=0.4)

    def tail(self, cv, pts, color, w0=6.4, w1=1.2):
        n = len(pts)
        strip = ribbon([tuple(p) for p in pts], list(np.linspace(w0, w1, n)))
        cv.group([(strip, color)], shade=0.7)

    def neck_wrap(self, cv, sk):
        o = sk["neck"]
        wrap = blob(add(o, rot((0.5, 1.2), sk["chest_rot"])), [(-8, 3.6), (0, 5), (8, 3.4), (8.6, -1.6), (0, -3.4), (-8.4, -1.6)], sk["chest_rot"], 1.0, 4)
        cv.group([(wrap, self.c["cape"])], shade=0.7)

    # -- smear / fx baked into the sprite ----------------------------------------------

    def smear(self, cv, tips, hilts, strength):
        """Crescent through recent blade positions; bridges fast swings between frames."""
        if len(tips) < 2:
            return
        tips = catmull_open(tips, 5)
        hilts = catmull_open(hilts, 5)
        # Pixel output hard-thresholds alpha, so it needs a thin solid arc, not a soft fan.
        inner = hilts + (tips - hilts) * (0.74 if cv.flat else 0.45)
        core = (235, 246, 255)
        tint = (150, 220, 255)
        m = len(tips)
        for i in range(m - 1):
            a = (i + 1) / m
            if cv.flat:
                if a * strength < 0.3:
                    continue
                al = 255
            else:
                al = int(240 * a ** 1.4 * strength)
            quad = [tuple(tips[i]), tuple(tips[i + 1]), tuple(inner[i + 1]), tuple(inner[i])]
            cv.details([(quad, tint if a < 0.6 else core, al)])


    # -- frame ------------------------------------------------------------------------

