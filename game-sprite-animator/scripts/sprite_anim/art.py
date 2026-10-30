"""Character renderer. Parts are drawn from rig joints each frame, not warped from a bitmap,
so line weight and detail stay crisp at any frame rate and size.

Shading is computed in screen space from each part's silhouette (rim shadow on the side away
from the light, thin highlight toward it), so the light direction stays fixed while limbs
rotate - baked-in shading that rotates with the limb is a classic cut-out animation tell.
"""
import colorsys
import math
import os

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
    "name": "hero",
    "body": {},
    "style": {},
    "colors": {
        "skin": "#f2c7a0", "hair": "#5b3a29", "tunic": "#3f7fb5", "tunic2": "#2d5f8e",
        "pants": "#46506b", "boots": "#6b4a32", "belt": "#8a5a33", "metal": "#c9d3dd",
        "accent": "#e8b84a", "cape": "#c23b3b", "glove": "#6b4a32", "eye": "#1d2230",
        "ink": "#1b1a26",
    },
    "head": "hair",        # hair | hood | helmet | wizard
    "weapon": "sword",     # sword | axe | staff | spear | none
    "cloth": ["cape", "hair"],   # cape, scarf, hair (ponytail), plume, tassel
    "armor": False,
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
    if "plume" in cloth:
        out.append(ChainDef("plume", ("head_base", "head_rot", (-2.0 * hs, 31.0 * hs)), 6, 4.0 * hs,
                            gravity=240, drag=7.0, stiff=0.05, rest=(-0.9, -0.2), follow=1.0,
                            flutter=320, rest_frame="head_rot", width=(7.5, 2.2)))
    if "hat_tip" in cloth or spec["head"] == "wizard":
        out.append(ChainDef("hat_tip", ("head_base", "head_rot", (-7.0 * hs, 44.0 * hs)), 4, 4.5 * hs,
                            gravity=340, drag=7.5, stiff=0.09, rest=(-1.0, -0.25), follow=1.0,
                            flutter=160, rest_frame="head_rot", width=(2.0, 1.0)))
    if "tassel" in cloth or spec["head"] == "hood":
        out.append(ChainDef("tassel", ("head_base", "head_rot", (-13.0 * hs, 12.0 * hs)), 5, 4.0 * hs,
                            gravity=340, drag=6.0, stiff=0.04, rest=(-0.9, -0.7), follow=1.0,
                            flutter=300, rest_frame="head_rot", width=(7.0, 2.0)))
    return out


def _limb(a, b):
    """Clockwise rotation that takes a hanging-down image onto the bone a->b."""
    return -math.degrees(math.atan2(b[0] - a[0], -(b[1] - a[1])))


# part -> (joint the pivot sits on, rotation fn). Images are authored with limbs hanging
# straight down, torso/head upright, and the weapon pointing up.
CUTOUT_BONES = {
    "arm_f_up": ("sh_f", lambda s: _limb(s["sh_f"], s["el_f"])),
    "arm_f_lo": ("el_f", lambda s: _limb(s["el_f"], s["wr_f"])),
    "hand_f": ("wr_f", lambda s: _limb(s["el_f"], s["wr_f"])),
    "leg_f_up": ("hip_f", lambda s: _limb(s["hip_f"], s["kn_f"])),
    "leg_f_lo": ("kn_f", lambda s: _limb(s["kn_f"], s["an_f"])),
    "foot_f": ("an_f", lambda s: s["fr_f"]),
    "leg_n_up": ("hip_n", lambda s: _limb(s["hip_n"], s["kn_n"])),
    "leg_n_lo": ("kn_n", lambda s: _limb(s["kn_n"], s["an_n"])),
    "foot_n": ("an_n", lambda s: s["fr_n"]),
    "pelvis": ("hip", lambda s: s["body_rot"]),
    "torso": ("waist", lambda s: s["chest_rot"]),
    "head": ("head_base", lambda s: s["head_rot"]),
    "weapon": ("wr_n", lambda s: 180 - s["wep_a"]),
    "arm_n_up": ("sh_n", lambda s: _limb(s["sh_n"], s["el_n"])),
    "arm_n_lo": ("el_n", lambda s: _limb(s["el_n"], s["wr_n"])),
    "hand_n": ("wr_n", lambda s: _limb(s["el_n"], s["wr_n"])),
}


class Cutout:
    """Rigs user-supplied part images onto the skeleton. spec["parts"] maps part names to
    {"image": path, "pivot": [x, y]}; spec["px_per_unit"] is the source art scale."""

    def __init__(self, spec):
        base = spec.get("_dir", ".")
        self.px_per_unit = float(spec.get("px_per_unit", 4.0))
        self.parts = {}
        for name, p in spec["parts"].items():
            if name not in CUTOUT_BONES:
                raise ValueError(f"unknown part {name!r}, expected one of {list(CUTOUT_BONES)}")
            im = Image.open(os.path.join(base, p["image"])).convert("RGBA")
            self.parts[name] = (im, tuple(p["pivot"]))

    def palette(self):
        cols = set()
        for im, _ in self.parts.values():
            q = im.convert("RGB").quantize(colors=24).convert("RGB")
            cols |= {c for _, c in q.getcolors(1 << 16)}
        return sorted(cols)

    def draw(self, cv, sk, cloth, art):
        for name, (joint, ang) in CUTOUT_BONES.items():
            if name not in self.parts:
                continue
            im, pivot = self.parts[name]
            k = cv.s / self.px_per_unit
            a = math.radians(ang(sk))
            # Inverse affine: output pixel -> source pixel. Clockwise on screen (y-down).
            ca, sa = math.cos(a), math.sin(a)
            sx, sy = k * cv.sx, k * cv.sy
            ox, oy = cv.T(sk[joint])
            w, h = im.size
            cs = [(-pivot[0], -pivot[1]), (w - pivot[0], -pivot[1]), (w - pivot[0], h - pivot[1]), (-pivot[0], h - pivot[1])]
            xs = [ox + (x * ca - y * sa) * sx for x, y in cs]
            ys = [oy + (x * sa + y * ca) * sy for x, y in cs]
            x0, y0 = max(int(min(xs)) - 1, 0), max(int(min(ys)) - 1, 0)
            x1, y1 = min(int(max(xs)) + 2, cv.w), min(int(max(ys)) + 2, cv.h)
            if x1 <= x0 or y1 <= y0:
                continue
            coeffs = (ca / sx, sa / sy, pivot[0] + (ca * (x0 - ox) / sx) + (sa * (y0 - oy) / sy),
                      -sa / sx, ca / sy, pivot[1] + (-sa * (x0 - ox) / sx) + (ca * (y0 - oy) / sy))
            patch = im.transform((x1 - x0, y1 - y0), Image.AFFINE, coeffs, resample=Image.BICUBIC)
            base = Image.fromarray(cv.buf[y0:y1, x0:x1], "RGBA")
            base.alpha_composite(patch)
            cv.buf[y0:y1, x0:x1] = np.asarray(base)


class CharacterArt:
    def __init__(self, spec):
        self.spec = merged_spec(spec)
        self.body = Body.from_spec(self.spec.get("body"))
        col = self.spec["colors"]
        self.c = {k: ramp(v) for k, v in col.items()}
        self.ink = hex_rgb(col["ink"])
        self.bulk = self.body.bulk
        self.body.weapon_front = {"sword": 47, "axe": 40, "staff": 54, "spear": 62}.get(self.spec["weapon"], 0)
        self.body.weapon_back = {"sword": 7, "axe": 10, "staff": 22, "spear": 20}.get(self.spec["weapon"], 0)
        self.cutout = Cutout(self.spec) if self.spec.get("parts") else None

    def palette(self):
        """All flat colours used: pixel mode quantizes to exactly this list."""
        if self.cutout:
            return self.cutout.palette()
        cols = {self.ink}
        for r in self.c.values():
            for c in r:
                cols.add(c)
            for c in darken_far(r):
                cols.add(c)
        cols |= {(255, 255, 255), (250, 240, 200), (150, 220, 255), (205, 235, 255)}
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
        items = [(up, tunic), (lo, c["skin"] if not far else darken_far(c["skin"])), (hand, skin)]
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

    def torso(self, cv, sk):
        c = self.c
        b = self.body
        q = self.bulk
        hip, waist = sk["hip"], sk["waist"]
        br, cr = sk["body_rot"], sk["chest_rot"]

        q *= 1.16

        def C(x, y):  # chest frame, origin at waist
            return add(waist, rot((x * q, y), cr))

        def H(x, y):  # pelvis frame, origin at hip
            return add(hip, rot((x * q, y), br))

        L = b.chest_len
        # Hem follows the thighs so the tunic drapes over a raised knee.
        thigh_f = sk["kn_n"]
        thigh_b = sk["kn_f"]
        fwd = max(thigh_f[0], thigh_b[0]) - hip[0]
        bak = min(thigh_f[0], thigh_b[0]) - hip[0]
        hem_f = add(hip, (max(8.6, min(fwd * 0.62, 14)), -4.6))
        hem_b = add(hip, (min(-8.6, max(bak * 0.62, -14)), -4.6))
        hem_m = add(hip, ((hem_f[0] + hem_b[0] - 2 * hip[0]) / 2, -3.2))
        ctrl = [C(-5.5, L + 1), C(5.0, L + 1), C(9.2, L - 6.5), C(8.6, L * 0.3), C(7.2, 0.8), H(8.0, 3),
                hem_f, hem_m, hem_b, H(-8.0, 3), C(-7.2, 1), C(-8.2, L * 0.45), C(-9.2, L - 6)]
        shape = [tuple(p) for p in catmull_closed(ctrl, 5)]
        cv.group([(shape, c["tunic"])])
        # Darker lower skirt band, belt, collar, chest strap.
        band_h = 2.6
        belt = [H(-9.0, 3.2 + band_h), H(9.2, 3.2 + band_h), H(9.0, 3.0 - band_h + 2), H(-8.8, 3.0 - band_h + 2)]
        strip = [add(hem_b, (0.4, 2.6)), add(hem_m, (0, 2.6)), add(hem_f, (-0.4, 2.6)), hem_f, hem_m, hem_b]
        collar = blob(C(1.0, L + 0.3), [(-7, 1.6), (0, 3), (7, 1.6), (6, -2.6), (0, -4), (-6, -2.6)], cr, 1.0, 4)
        strap = [C(-5.5, L - 1), C(-3.0, L - 1), C(7.0, 3.6), C(4.0, 3.6)]
        trim = [C(6.0, L + 0.5), C(8.8, L - 7), C(8.3, L * 0.32), C(6.2, 1), C(3.4, 1), C(5.6, L * 0.32), C(6.0, L - 7), C(3.6, L + 0.5)]
        det = [(strip, c["tunic2"][1], 255), (trim, c["tunic2"][1], 255)]
        if not self.spec.get("armor"):
            det.append((strap, c["belt"][0], 255))
        else:
            plate = blob(C(1.4, L * 0.62), [(-7, 6), (6.6, 6), (8, -1), (2, -7), (-7, -5)], cr, q, 5)
            cv.group([(plate, c["metal"])], stroke_scale=0.6, shade=0.8)
        cv.details(det)
        cv.group([(belt, c["belt"])], stroke_scale=0.55, shade=0.5)
        buckle = blob(H(6.6, 3.6), [(-2, 2), (2, 2), (2.4, 0), (2, -2), (-2, -2), (-2.4, 0)], br, 1.0, 3)
        cv.group([(buckle, c["accent"])], stroke_scale=0.4, shade=0.4)
        pouch = blob(H(-6.6, 0.2), [(-3, 3), (3, 3), (3.5, -2), (0, -4.2), (-3.5, -2)], br, 1.0, 4)
        cv.group([(pouch, c["belt"])], stroke_scale=0.5, shade=0.5)
        cv.group([(collar, c["tunic2"])], stroke_scale=0.6, shade=0.5)

    # -- head -------------------------------------------------------------------------

    def head(self, cv, sk, pose, bakes):
        c = self.c
        hs = self.body.head_size
        o, r = sk["head_base"], sk["head_rot"]

        def H(x, y):
            return add(o, rot((x * hs, y * hs), r))

        def B(ctrl, sub=6):
            return [tuple(p) for p in catmull_closed([H(*p) for p in ctrl], sub)]

        kind = self.spec["head"]
        skull = B([(-13.5, 15), (-12, 25), (-3, 30.5), (8, 29), (14, 22), (15.5, 13), (14.6, 6.5),
                   (10, 1.2), (3, -0.3), (-5, 2.5), (-11.5, 7)])
        # Hair/back-of-head mass goes behind the face.
        if kind == "hair":
            back = B([(-15, 10), (-15.8, 20), (-11, 29), (-3, 33.2), (7, 32.5), (14, 27.5), (9, 25),
                      (-1, 24), (-6, 17), (-6.5, 8), (-11, 4)])
            cv.group([(back, c["hair"])])
        ear = None
        if kind in ("hair",):
            ear = blob(H(-6.2, 12.0), [(-1.9, 2.4), (1.7, 2.6), (2.1, -0.9), (0, -3.0), (-2.2, -0.9)], r, hs, 4)
        items = [(skull, c["skin"])]
        if kind == "helmet":
            pass
        else:
            cv.group(items)

        if kind == "hair":
            # Bangs + spiky fringe, on top of the face.
            bangs = B([(-13, 27), (-5, 33), (6, 33), (13.2, 28.5), (16.4, 20.5), (14.2, 22.6), (12.4, 18.8),
                       (9.8, 23.6), (6.2, 19), (3, 24.5), (-1.5, 21), (-4.5, 24), (-8, 17.5), (-11.8, 21)], 3)
            cv.group([(bangs, c["hair"])], shade=0.8)
            if ear:
                cv.group([(ear, c["skin"])], stroke_scale=0.6, shade=0.5)
        elif kind == "hood":
            hood = B([(-16.5, 8), (-17.5, 20), (-12, 31), (-2, 35), (9, 33), (16, 26), (17.5, 19.5), (15, 24.5),
                      (6, 26.5), (-1.5, 21), (-4, 11), (-2, 3), (2, -1), (-8, -1.2)], 5)
            cv.group([(hood, c["tunic"])])
            cv.details([(B([(-1, 24), (6, 28), (14.5, 25.5), (15, 24), (6, 26.4), (-1.3, 21.5), (-3.8, 11), (-2, 3.4), (-3.4, 3.4), (-5.4, 11)], 3),
                         c["tunic2"][0], 255)])
        elif kind == "helmet":
            dome = B([(-14.6, 8), (-15.5, 19), (-11, 29), (-2, 33.4), (8, 32), (14.6, 25), (16, 16), (15.8, 8),
                      (11, 1), (3, -1), (-9, 1)], 6)
            cv.group([(dome, c["metal"])])
            visor = B([(1.5, 21.5), (9, 23), (16.6, 21.5), (17.4, 13), (16.2, 7.5), (8, 8), (1.5, 11)], 3)
            slit = [H(4.6, 17.8), H(17.0, 18.1), H(17.2, 15.2), H(4.6, 14.9)]
            nose = [H(11.8, 15.4), H(14.2, 15.4), H(14.6, 9.2), H(11.6, 9.2)]
            rib = [H(-1.6, 33.2), H(1.6, 33.5), H(1.4, 21.4), H(-1.4, 21.2)]
            cheek = [H(-6, 12), H(0.8, 10.6), H(0.8, 1.4), H(-4, 0.6), H(-7.6, 4)]
            cv.group([(visor, c["metal"])], stroke_scale=0.55, shade=0.5)
            cv.details([(slit, (20, 22, 32), 255), (nose, c["metal"][0], 255), (rib, c["metal"][2], 255),
                        (cheek, c["metal"][0], 255)])
        elif kind == "wizard":
            hb = B([(-14, 20), (-12, 27), (-3, 31), (9, 30), (14.8, 24.5), (9, 23), (-3, 22), (-7, 14), (-12, 13)], 4)
            cv.group([(hb, c["hair"])])

        # Face (skipped behind a helmet).
        if kind != "helmet":
            e = max(0.0, min(1.0, pose["eye"]))
            ey = 13.5
            eh = 5.0 * e + 0.55
            eye_col = c["eye"][1]
            det = []
            def oval(cx, cy, rx, ry, n=12):
                return [H(cx + math.cos(i / n * math.tau) * rx, cy + math.sin(i / n * math.tau) * ry) for i in range(n)]

            det.append((oval(6.9, ey, 2.7, eh), eye_col, 255))
            det.append((oval(13.3, ey, 1.55, eh * 0.9), eye_col, 255))
            if e > 0.45:
                det.append((oval(7.3, ey - eh * 0.42, 1.7, eh * 0.42), c["eye"][2], 255))
                det.append((oval(6.0, ey + eh * 0.42, 1.15, 1.45), (255, 255, 255), 255))
                det.append((oval(12.9, ey + eh * 0.42, 0.65, 1.0), (255, 255, 255), 255))
            bw = pose["brow"]
            brow_col = c["hair"][0] if kind != "hood" else c["eye"][1]
            by = ey + 6.8
            det.append(([H(3.8, by + 1.1 + bw * 0.9), H(9.8, by + 0.2 - bw * 1.8), H(9.8, by - 1.2 - bw * 1.8), H(3.8, by - 0.3 + bw * 0.9)], brow_col, 255))
            det.append(([H(12.0, by - 0.2 - bw * 1.6), H(15, by + 0.6 + bw * 0.5), H(15, by - 0.7 + bw * 0.5), H(12.0, by - 1.5 - bw * 1.6)], brow_col, 255))
            m = pose["mouth"]
            mw, my = 2.2, 5.4
            if m > 0.12:
                det.append(([H(8.6, my + 1.2 * m), H(12.6, my + 1.2 * m), H(12.0, my - 2.6 * m), H(9.2, my - 2.6 * m)], (120, 50, 50), 255))
            else:
                det.append(([H(10.5 - mw, my + 0.35), H(10.5 + mw, my + 0.6), H(10.5 + mw, my - 0.35), H(10.5 - mw, my - 0.5)], c["skin"][0], 255))
            det.append(([H(14.5, 10.4), H(16.2, 9.4), H(14.5, 8.7)], c["skin"][0], 255))
            det.append((oval(3.4, 8.2, 2.3, 1.3), (240, 150, 130), 120))
            cv.details(det)
        if kind == "wizard":
            brim = B([(-20, 23.5), (-6, 26.5), (8, 26.6), (21.5, 24.4), (9, 22), (-6, 21.8)], 4)
            tip = bakes.get("hat_tip")
            cone = [H(-12, 24.5), H(-9, 36), H(-7, 44)]
            cone_r = [H(10, 24.5), H(5, 34), H(-5, 44.5)]
            if tip is not None:
                tp = [tuple(p) for p in tip]
                cone_pts = cone + tp[1:] + tp[:0:-1] + cone_r[::-1]
            else:
                cone_pts = cone + cone_r[::-1]
            cv.group([(cone_pts, c["tunic"])])
            cv.group([(brim, c["tunic2"])])
            band = [H(-12, 24.6), H(10.2, 24.8), H(9, 28.8), H(-11.4, 28.6)]
            cv.details([(band, c["accent"][1], 255)])

    # -- weapon -----------------------------------------------------------------------

    def blade_points(self, sk):
        """(hilt, tip) for smears."""
        kind = self.spec["weapon"]
        length = {"sword": 47, "axe": 40, "staff": 54, "spear": 62}.get(kind, 0)
        return sk["wr_n"], add(sk["wr_n"], scale(sk["wep_dir"], length))

    primary = None

    def extent_points(self, sk, pose):
        """Every point that must stay inside the frame on this pose."""
        pts = [sk[j] for j in ("wr_n", "wr_f", "an_n", "an_f", "kn_n", "kn_f", "hip", "neck", "head_base")]
        pts.append(add(sk["head_base"], rot((0, 36 * self.body.head_size), sk["head_rot"])))
        span = self.weapon_span(sk)
        if span:
            pts += [span[0], span[1]]
        return pts

    def weapon_span(self, sk):
        """Blade as (start, end, radius) for clipping checks."""
        if self.spec["weapon"] == "none":
            return None
        h, t = self.blade_points(sk)
        return h, t, 2.5

    def weapon(self, cv, sk, pose):
        kind = self.spec["weapon"]
        if kind == "none":
            return
        c = self.c
        o = add(sk["wr_n"], scale((sk["wr_n"][0] - sk["el_n"][0], sk["wr_n"][1] - sk["el_n"][1]), 0.14))
        a = sk["wep_a"]
        # Local frame: +y along the blade; rot(angle=180-a) maps +y to the blade direction.
        ang = 180 - a

        def W(x, y):
            return add(o, rot((x, y), ang))

        if kind == "sword":
            blade = [W(-2.5, 5.5), W(2.5, 5.5), W(2.5, 41), W(0, 47), W(-2.5, 41)]
            guard = [tuple(p) for p in catmull_closed([W(-6.8, 4.4), W(0, 5.6), W(6.8, 4.4), W(7.3, 2.4), W(0, 3.1), W(-7.3, 2.4)], 4)]
            grip = capsule(W(0, 3), 1.7, W(0, -6), 1.7, 3)
            pom = blob(W(0, -7.4), [(-2.2, 2), (2.2, 2), (2.6, 0), (2.2, -2), (-2.2, -2), (-2.6, 0)], ang, 1, 3)
            cv.group([(grip, c["belt"]), (pom, c["accent"])], stroke_scale=0.7, shade=0.5)
            cv.group([(blade, c["metal"])], stroke_scale=0.8, shade=0.55)
            cv.details([([W(-0.45, 6), W(0.45, 6), W(0.45, 40), W(0, 44), W(-0.45, 40)], c["metal"][0], 255),
                        ([W(0.45, 6), W(2.5, 6), W(2.5, 41), W(0.1, 46.4)], c["metal"][2], 200)])
            cv.group([(guard, c["accent"])], stroke_scale=0.7, shade=0.5)
        elif kind == "axe":
            shaft = capsule(W(0, -10), 1.8, W(0, 39), 1.8, 3)
            head = blob(W(0, 32), [(-1, 8), (7, 10.5), (15, 13), (17, 3), (15, -9), (7, -6), (-1, -6)], ang, 1, 4)
            spike = [W(-1.5, 38), W(-8, 35), W(-11, 31), W(-8, 28), W(-1.5, 26)]
            cv.group([(shaft, c["belt"])], stroke_scale=0.8, shade=0.5)
            cv.group([(spike, c["metal"]), (head, c["metal"])], stroke_scale=0.8, shade=0.6)
            edge = [W(14, 45), W(17.4, 35), W(15, 23), W(13.2, 24.4), W(15, 35), W(12.6, 43.6)]
            cv.details([(edge, c["metal"][2], 255)])
        elif kind == "staff":
            shaft = capsule(W(0, -22), 1.7, W(0, 46), 1.9, 3)
            crook = ribbon([W(0, 45), W(3, 51), W(9.5, 53), W(13, 49), W(11, 45)], [3.8, 3.8, 3.4, 3.0, 2.2])
            gem = blob(W(5.5, 46.6), [(-3.6, 3.6), (0, 5), (3.6, 3.6), (4.4, 0), (0, -4.8), (-4.4, 0)], ang, 1, 3)
            cv.group([(shaft, c["belt"]), (crook, c["belt"])], stroke_scale=0.8, shade=0.5)
            cv.group([(gem, c["accent"])], stroke_scale=0.6, shade=0.6)
        elif kind == "spear":
            shaft = capsule(W(0, -20), 1.5, W(0, 52), 1.5, 3)
            tip = [W(-3.2, 51), W(0, 66), W(3.2, 51), W(1, 48), W(-1, 48)]
            wrap = capsule(W(0, 47), 2.2, W(0, 50), 2.2, 3)
            cv.group([(shaft, c["belt"])], stroke_scale=0.8, shade=0.5)
            cv.group([(tip, c["metal"])], stroke_scale=0.8, shade=0.5)
            cv.group([(wrap, c["accent"])], stroke_scale=0.5, shade=0.5)

    # -- cloth ------------------------------------------------------------------------

    def cape(self, cv, pts):
        c = self.c
        n = len(pts)
        w = np.linspace(11, 19, n)
        strip = ribbon([tuple(p) for p in pts], list(w))
        cv.group([(strip, c["cape"])], shade=1.0)
        # Fold lines track the chain so they ripple with the flutter.
        p = catmull_open(pts, 4)
        d = np.gradient(p, axis=0)
        nrm = np.stack([-d[:, 1], d[:, 0]], axis=1)
        nrm /= (np.hypot(nrm[:, 0], nrm[:, 1])[:, None] + 1e-6)
        det = []
        ww = np.interp(np.linspace(0, n - 1, len(p)), np.arange(n), w)
        for off, tone in ((-0.2, 0), (0.24, 0)):
            line = p + nrm * (ww * off)[:, None]
            start = len(line) // 5
            poly = [tuple(q) for q in line[start:]] + [tuple(q + nn * 1.0) for q, nn in zip(line[start:][::-1], nrm[start:][::-1])]
            det.append((poly, c["cape"][tone], 255))
        edge = p - nrm * (ww * 0.5)[:, None]
        hem = [tuple(q) for q in edge] + [tuple(q + nn * 1.5) for q, nn in zip(edge[::-1], nrm[::-1])]
        det.append((hem, c["accent"][1], 255))
        cv.details(det)

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

    def glow(self, cv, center, level):
        if level <= 0.02:
            return
        r = 5 + 7 * level
        for k, (col, al) in enumerate((((120, 200, 255), 70), ((180, 230, 255), 130), ((255, 255, 255), 240))):
            rr = r * (1 - k * 0.3)
            poly = [(center[0] + math.cos(i / 16 * math.tau) * rr, center[1] + math.sin(i / 16 * math.tau) * rr) for i in range(16)]
            cv.details([(poly, col, al)])

    # -- frame ------------------------------------------------------------------------

    def draw(self, cv, sk, pose, cloth, smear_hist=None):
        c = self.c
        cv.set_squash(pose["squash"], 0.0)
        if self.cutout:
            if smear_hist:
                self.smear(cv, smear_hist[0], smear_hist[1], pose["smear"])
            self.cutout.draw(cv, sk, cloth, self)
            return
        if smear_hist:
            self.smear(cv, smear_hist[0], smear_hist[1], pose["smear"])
        if "cape" in cloth:
            self.cape(cv, cloth["cape"])
        if "tassel" in cloth:
            self.tail(cv, cloth["tassel"], c["tunic"], 7.0, 2.0)
        if "scarf" in cloth:
            self.scarf(cv, cloth["scarf"])
        self.arm(cv, sk, "f", True)
        self.leg(cv, sk, "f", True)
        self.leg(cv, sk, "n", False)
        self.torso(cv, sk)
        if "scarf" in cloth:
            self.neck_wrap(cv, sk)
        if "hair" in cloth:
            self.tail(cv, cloth["hair"], c["hair"], 7.0, 1.4)
        if "plume" in cloth:
            self.tail(cv, cloth["plume"], c["cape"], 7.5, 2.2)
        self.head(cv, sk, pose, cloth)
        self.weapon(cv, sk, pose)
        self.arm(cv, sk, "n", False)
        if pose["glow"] > 0:
            self.glow(cv, sk["wr_f"], pose["glow"])
