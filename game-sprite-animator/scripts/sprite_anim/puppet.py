"""Layered puppet: whole layers bent along the skeleton, instead of rigid parts hinged at joints.

Each layer is complete art on the reference picture's canvas (see layer_slots.py) and is bound to a
curve through that picture's joints. A pixel keeps its place along the curve and its distance from
it, so when the skeleton moves a sleeve bends with the arm, a knee rounds instead of hinging, and a
cloth follows its simulated chain as one sheet. Nothing is cut, so there is no seam and no patch.
"""
import math
import os

import numpy as np
from PIL import Image

from .mathx import rot

GRID = 14          # source pixels between mesh vertices
CURVE_STEPS = 32   # samples per bone along a curve
BLUR_PASSES = 6    # smoothing of each vertex's place along the curve: keeps wide cloth from shearing
INNER_LIMIT = 0.8  # how close the inner side of a bend may come to the curve's centre of turning
EASE_PASSES = 5    # smoothing of the bent mesh. A rotation passes through it unchanged, a crease doesn't
UNTANGLE_PASSES = 80   # most relaxations of a mesh that still has cells turned inside out
ANKLE_TURN = 62.0      # degrees a foot may turn from the shin's line as drawn. Past that, boot and shin cross
SKIRT_SWING = 40.0     # degrees hanging panels may leave the body's line: past that the thighs lift clear of them


def corner_run(a, b, c, radius, reach):
    """How far along each bone the arc at corner b starts. A sharper corner needs a longer run to
    keep the same radius; a limb half as wide as that radius would otherwise pinch to a point."""
    u, v = b - a, c - b
    turn = abs(math.atan2(u[0] * v[1] - u[1] * v[0], u @ v))
    run = radius * max(1.0, math.tan(min(turn, 2.6) / 2))
    return min(run, reach * np.hypot(*u), reach * np.hypot(*v))


def rounded(points, radius):
    """Polyline -> dense curve, each inner corner replaced by a quadratic arc. Every call on the same
    number of points gives the same number of samples, so two curves match index by index."""
    pts = [np.asarray(p, dtype=np.float64) for p in points]
    reach = 0.68 if len(pts) == 3 else 0.45     # a bone with one corner has room for a longer arc
    runs = [0.0] + [corner_run(pts[i - 1], pts[i], pts[i + 1], radius, reach) for i in range(1, len(pts) - 1)] + [0.0]
    out = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        length = np.hypot(*(b - a)) or 1e-6
        u = (b - a) / length
        start = a + u * runs[i] if i else a
        end = b - u * runs[i + 1] if i < len(pts) - 2 else b
        for t in np.linspace(0, 1, CURVE_STEPS, endpoint=False):
            out.append(start + (end - start) * t)
        if i < len(pts) - 2:
            next_len = np.hypot(*(pts[i + 2] - b)) or 1e-6
            tail = b + (pts[i + 2] - b) / next_len * runs[i + 1]
            for t in np.linspace(0, 1, CURVE_STEPS, endpoint=False):
                out.append((1 - t) ** 2 * end + 2 * t * (1 - t) * b + t * t * tail)
    out.append(pts[-1])
    return np.array(out)


def frames_of(curve):
    """Unit tangents along a curve."""
    tan = np.gradient(curve, axis=0)
    return tan / (np.hypot(tan[:, 0], tan[:, 1])[:, None] + 1e-9)


def extended(curve, reach):
    """Straight run-outs past both ends, so art beyond the first or last joint has a place."""
    tan = frames_of(curve)
    head = curve[0] - tan[0] * np.linspace(reach, 0, CURVE_STEPS, endpoint=False)[:, None]
    tail = curve[-1] + tan[-1] * np.linspace(0, reach, CURVE_STEPS + 1)[1:, None]
    return np.concatenate([head, curve, tail])


def blur(field, passes):
    f = field.copy()
    for _ in range(passes):
        f[1:-1, 1:-1] = (f[1:-1, 1:-1] * 2 + f[:-2, 1:-1] + f[2:, 1:-1] + f[1:-1, :-2] + f[1:-1, 2:]) / 6
    return f


class Layer:
    """One picture layer: image (premultiplied), its mesh, and each vertex's place on its curve."""

    def __init__(self, name, data, base):
        self.name = name
        self.kind = data["kind"]        # tube | rigid | cloth
        self.bones = data.get("bones", [])
        self.rest = [np.array(p, dtype=np.float64) for p in data.get("rest", [])]
        self.radius = float(data.get("radius", 20.0))
        self.chain = data.get("chain")
        self.foot = data.get("foot")
        self.anchor, self.follow = data.get("anchor"), data.get("follow")
        im = Image.open(os.path.join(base, data["image"])).convert("RGBA")
        self.offset = np.array(data.get("offset", (0, 0)), dtype=np.float64)
        self.image = im
        a = np.asarray(im, dtype=np.float32) / 255
        ys, xs = np.nonzero(a[..., 3] > 0.02)
        self.box = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        w, h = im.size
        gx = np.arange(0, w + GRID, GRID, dtype=np.float64)
        gy = np.arange(0, h + GRID, GRID, dtype=np.float64)
        self.gx, self.gy = gx, gy
        vx, vy = np.meshgrid(gx, gy)
        self.vx, self.vy = vx, vy
        keep = np.zeros((len(gy) - 1, len(gx) - 1), bool)
        solid = a[..., 3] > 0.02
        for j in range(len(gy) - 1):
            y0, y1 = int(gy[j]), min(int(gy[j + 1]) + 1, h)
            for i in range(len(gx) - 1):
                x0, x1 = int(gx[i]), min(int(gx[i + 1]) + 1, w)
                if y0 < h and x0 < w and solid[y0:y1, x0:x1].any():
                    keep[j, i] = True
        self.cells = np.argwhere(keep)
        self.used = np.zeros(vx.shape, bool)
        for dj, di in ((0, 0), (0, 1), (1, 0), (1, 1)):
            self.used[self.cells[:, 0] + dj, self.cells[:, 1] + di] = True
        self.bind_curve()

    def bind_curve(self):
        if self.kind == "rigid":
            return
        rest = rounded(self.rest, self.radius)
        reach = float(max(self.image.size)) * 1.5
        self.rest_curve = extended(rest, reach)
        self.reach = reach
        cur = self.rest_curve
        px = self.vx.ravel() + self.offset[0]
        py = self.vy.ravel() + self.offset[1]
        idx = np.zeros(px.size, dtype=np.float64)
        for start in range(0, px.size, 4000):
            stop = start + 4000
            d = (px[start:stop, None] - cur[:, 0][None]) ** 2 + (py[start:stop, None] - cur[:, 1][None]) ** 2
            idx[start:stop] = d.argmin(1)
        self.place = blur(idx.reshape(self.vx.shape), BLUR_PASSES)
        tan = frames_of(cur)
        at = self.place.round().astype(int).clip(0, len(cur) - 1)
        dx = self.vx + self.offset[0] - cur[at, 0]
        dy = self.vy + self.offset[1] - cur[at, 1]
        self.along = dx * tan[at, 0] + dy * tan[at, 1]
        self.across = -dx * tan[at, 1] + dy * tan[at, 0]
        if self.foot:
            ankle, along = np.array(self.foot["ankle"]), np.array(self.foot["shin_dir"])
            rx, ry = self.vx + self.offset[0] - ankle[0], self.vy + self.offset[1] - ankle[1]
            # The boot's upper reaches above the ankle ahead of the shin: all of it turns with the foot.
            ahead = rx * along[1] - ry * along[0]
            depth = rx * along[0] + ry * along[1] + 0.9 * np.maximum(ahead - self.foot["width"], 0)
            s = np.clip((depth + self.foot["blend"]) / (2 * self.foot["blend"]), 0, 1)
            self.foot_w = s * s * (3 - 2 * s)

    def mapped(self, points, scale):
        """Mesh vertices for a curve through this frame's joints, in output pixels."""
        cur = extended(rounded(points, self.radius * scale), self.reach * scale)
        tan = frames_of(cur)
        i0 = np.floor(self.place).astype(int).clip(0, len(cur) - 2)
        f = (self.place - i0)[..., None]
        c = cur[i0] * (1 - f) + cur[i0 + 1] * f
        t = tan[i0] * (1 - f) + tan[i0 + 1] * f
        t /= np.hypot(t[..., 0], t[..., 1])[..., None] + 1e-9
        n = np.stack([-t[..., 1], t[..., 0]], -1)
        # Inside a bend, art wider than the curve's radius would cross itself. It compresses instead,
        # easing into the radius, as cloth bunches on the inner side of a knee.
        ang = np.unwrap(np.arctan2(tan[:, 1], tan[:, 0]))
        step = np.hypot(*np.gradient(cur, axis=0).T) + 1e-9
        bend = np.gradient(ang) / step
        k = (bend[i0] * (1 - f[..., 0]) + bend[i0 + 1] * f[..., 0])
        across = self.across * scale
        inner = across * k > 0
        limit = INNER_LIMIT / (np.abs(k) + 1e-6)
        x = np.abs(across) / limit
        eased = np.where(inner, np.sign(across) * limit * x / (1 + x ** 4) ** 0.25, across)
        return c + t * self.along[..., None] * scale + n * eased[..., None]


def winding(verts, cells):
    """Doubled signed area of each cell's two triangles: negative is wound the other way from the
    picture, i.e. drawn mirrored."""
    j, i = cells[:, 0], cells[:, 1]
    a, b, c, d = verts[j, i], verts[j, i + 1], verts[j + 1, i], verts[j + 1, i + 1]
    cross = lambda o, u, v: (u[:, 0] - o[:, 0]) * (v[:, 1] - o[:, 1]) - (u[:, 1] - o[:, 1]) * (v[:, 0] - o[:, 0])
    return cross(a, b, c), cross(d, c, b)


def flipped(verts, cells):
    one, two = winding(verts, cells)
    return (one < 0) | (two < 0)


def untangle(verts, cells):
    """Relax only the mesh around cells that crossed themselves on the tight side of a sharp bend,
    until none do. Everywhere else the mesh stays exactly where the bend put it."""
    if not len(cells):
        return verts
    v = verts.copy()
    h, w = v.shape[:2]
    for _ in range(UNTANGLE_PASSES):
        bad = cells[flipped(v, cells)]
        if not len(bad):
            break
        near = np.zeros((h, w), bool)
        for dj in range(-1, 3):
            for di in range(-1, 3):
                near[np.clip(bad[:, 0] + dj, 1, h - 2), np.clip(bad[:, 1] + di, 1, w - 2)] = True
        mean = (v[:-2, 1:-1] + v[2:, 1:-1] + v[1:-1, :-2] + v[1:-1, 2:]) / 4
        v[1:-1, 1:-1][near[1:-1, 1:-1]] = mean[near[1:-1, 1:-1]]
    return v


def floor_contact(verts, floor, band):
    """A monotone soft floor for loose fabric, in screen coordinates.

    Away from contact this is the identity. Below-floor material gathers into
    a thin layer above the floor; x positions and the body's joints stay put.
    """
    result = verts.copy()
    result[..., 1] = floor - band * np.logaddexp(0, (floor - result[..., 1]) / band)
    return result


def rigid(vx, vy, pivot_src, pivot_out, angle, scale):
    """Vertices turned clockwise on screen by angle about the pivot and carried to pivot_out."""
    c, s = math.cos(angle), math.sin(angle)
    x, y = (vx - pivot_src[0]) * scale, (vy - pivot_src[1]) * scale
    return np.stack([pivot_out[0] + x * c - y * s, pivot_out[1] + x * s + y * c], -1)


def raster(layer, verts, mip, w, h):
    """Draw the layer's mesh into a premultiplied RGBA float image of (h, w)."""
    img, k = mip
    out = np.zeros((h, w, 4), np.float32)
    ih, iw = img.shape[:2]
    dst_y, dst_x, src_u, src_v = [], [], [], []
    u_grid, v_grid = layer.gx * k, layer.gy * k

    def tri(p0, p1, p2, t0, t1, t2):
        x0 = max(int(math.floor(min(p0[0], p1[0], p2[0]))), 0)
        x1 = min(int(math.ceil(max(p0[0], p1[0], p2[0]))) + 1, w)
        y0 = max(int(math.floor(min(p0[1], p1[1], p2[1]))), 0)
        y1 = min(int(math.ceil(max(p0[1], p1[1], p2[1]))) + 1, h)
        if x1 <= x0 or y1 <= y0:
            return
        det = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
        if abs(det) < 1e-9:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        a = ((xx - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (yy - p0[1])) / det
        b = ((p1[0] - p0[0]) * (yy - p0[1]) - (xx - p0[0]) * (p1[1] - p0[1])) / det
        inside = (a >= -1e-3) & (b >= -1e-3) & (a + b <= 1.001)
        if not inside.any():
            return
        a, b = a[inside], b[inside]
        dst_y.append(yy[inside].astype(np.int32))
        dst_x.append(xx[inside].astype(np.int32))
        src_u.append(t0[0] + a * (t1[0] - t0[0]) + b * (t2[0] - t0[0]))
        src_v.append(t0[1] + a * (t1[1] - t0[1]) + b * (t2[1] - t0[1]))

    for j, i in layer.cells:
        p00, p10, p01, p11 = verts[j, i], verts[j, i + 1], verts[j + 1, i], verts[j + 1, i + 1]
        t00 = (u_grid[i], v_grid[j])
        t10 = (u_grid[i + 1], v_grid[j])
        t01 = (u_grid[i], v_grid[j + 1])
        t11 = (u_grid[i + 1], v_grid[j + 1])
        tri(p00, p10, p01, t00, t10, t01)
        tri(p11, p01, p10, t11, t01, t10)
    if not dst_y:
        return out
    yy, xx = np.concatenate(dst_y), np.concatenate(dst_x)
    u, v = np.concatenate(src_u).clip(0, iw - 1.001), np.concatenate(src_v).clip(0, ih - 1.001)
    u0, v0 = u.astype(np.int32), v.astype(np.int32)
    fu, fv = (u - u0)[:, None], (v - v0)[:, None]
    sample = (img[v0, u0] * (1 - fu) * (1 - fv) + img[v0, u0 + 1] * fu * (1 - fv)
              + img[v0 + 1, u0] * (1 - fu) * fv + img[v0 + 1, u0 + 1] * fu * fv)
    out[yy, xx] = sample
    return out


class Puppet:
    def __init__(self, spec):
        data = spec["puppet"]
        base = spec.get("_dir", ".")
        self.px_per_unit = float(data["px_per_unit"])
        self.joints = {k: np.array(v, dtype=np.float64) for k, v in data["joints"].items()}
        self.rest_angles = data["rest_angles"]
        self.skirt_len = float(data.get("skirt_len", 0.0))
        self.robe_len = float(data.get("robe_len", 0.0))
        self.core_radius = float(data.get("core_radius", 0.0))
        self.rest_arm = {k: tuple(tuple(p) for p in v) for k, v in data.get("rest_arm", {}).items()}
        self.layers = [Layer(n, d, base) for n, d in data["layers"].items()]
        self.mips = {}

    def palette(self):
        cols = set()
        for layer in self.layers:
            q = layer.image.convert("RGB").quantize(colors=24).convert("RGB")
            cols |= {c for _, c in q.getcolors(1 << 16)}
        return sorted(cols)

    def mip(self, layer, scale):
        """The layer shrunk once, ahead of warping. Shrinking far inside a bilinear warp would
        alias fine lines; this keeps them, and the warp then moves it by less than a pixel's worth."""
        key = (layer.name, round(scale, 3))
        if key not in self.mips:
            k = min(1.0, scale * 1.15)
            a = np.asarray(layer.image, dtype=np.float32) / 255
            a[..., :3] *= a[..., 3:]
            size = max(2, round(a.shape[1] * k)), max(2, round(a.shape[0] * k))
            bands = [Image.fromarray(a[..., c]).resize(size, Image.LANCZOS) for c in range(4)]
            self.mips[key] = (np.clip(np.stack([np.asarray(b) for b in bands], -1), 0, 1), size[0] / a.shape[1])
        return self.mips[key]

    def tube_points(self, layer, sk, cv):
        return [np.array(cv.T(self.joint_at(b, sk))) for b in layer.bones]

    def joint_at(self, name, sk):
        if name not in ("skirt", "robe_hem"):
            return sk[name]
        # Hanging panels sit between the two thighs, so they swing by half of what either leg does.
        hip = np.array(sk["hip"])
        mean = (np.array(sk["kn_n"]) + np.array(sk["kn_f"])) / 2 - hip
        line = hip - np.array(sk["waist"])
        off = math.atan2(line[0] * mean[1] - line[1] * mean[0], line @ mean)
        limit = math.radians(SKIRT_SWING)
        turn = max(-limit, min(limit, off)) + math.atan2(line[1], line[0])
        length = self.robe_len if name == "robe_hem" else self.skirt_len
        return tuple(hip + np.array((math.cos(turn), math.sin(turn))) * length)

    def meshes(self, cv, sk, cloth, ground_contact=False, relax=True):
        """Each layer, back to front, with its mesh for this frame in canvas pixels."""
        scale = cv.s / self.px_per_unit
        for layer in self.layers:
            if layer.kind == "rigid":
                verts = self.rigid_verts(layer, sk, cv, scale)
            elif layer.kind == "cloth":
                verts = layer.mapped([np.array(cv.T(p)) for p in cloth[layer.chain]], scale)
            else:
                verts = layer.mapped(self.tube_points(layer, sk, cv), scale)
                if layer.foot:
                    side = layer.foot["side"]
                    angle = self.foot_turn(layer, sk, cv)
                    held = rigid(layer.vx + layer.offset[0], layer.vy + layer.offset[1], layer.foot["ankle"],
                                 cv.T(sk["an_" + side]), angle, scale)
                    verts = verts * (1 - layer.foot_w[..., None]) + held * layer.foot_w[..., None]
            if layer.kind != "rigid" and relax:
                verts = untangle(blur(verts, EASE_PASSES), layer.cells)
            if ground_contact and (layer.kind == "cloth" or layer.name == "robe"):
                # The chain supports its centreline. The painted sheet has
                # width too: compress the contacting fabric continuously onto
                # the floor without lifting the body or cutting source pixels.
                verts = floor_contact(verts, cv.oy, max(cv.s * 0.5, 1e-6))
                if relax:
                    verts = untangle(verts, layer.cells)
            yield layer, verts

    def foot_turn(self, layer, sk, cv):
        """Radians the boot turns from the picture, clockwise on screen, kept within the ankle's reach."""
        side, foot = layer.foot["side"], layer.foot
        knee, ankle = cv.T(sk["kn_" + side]), cv.T(sk["an_" + side])
        shin = math.atan2(ankle[1] - knee[1], ankle[0] - knee[0]) - math.atan2(foot["shin_dir"][1], foot["shin_dir"][0])
        rel = (math.radians(sk["fr_" + side] - foot["rest_angle"]) - shin + math.pi) % math.tau - math.pi
        return shin + max(-math.radians(ANKLE_TURN), min(math.radians(ANKLE_TURN), rel))

    def draw(self, cv, sk, cloth, ground_contact=False):
        scale = cv.s / self.px_per_unit
        for layer, verts in self.meshes(cv, sk, cloth, ground_contact):
            drawn = raster(layer, verts, self.mip(layer, scale), cv.w, cv.h)
            ys, xs = np.nonzero(drawn[..., 3] > 1e-3)
            if not len(ys):
                continue
            box = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            over = drawn[box[0]:box[1], box[2]:box[3]]
            under = cv.buf[box[0]:box[1], box[2]:box[3]].astype(np.float32) / 255
            ua = under[..., 3:]
            a = over[..., 3:]
            out_a = a + ua * (1 - a)
            rgb = over[..., :3] + under[..., :3] * ua * (1 - a)
            rgb = np.where(out_a > 1e-4, rgb / np.maximum(out_a, 1e-4), 0)
            cv.buf[box[0]:box[1], box[2]:box[3]] = np.clip(np.concatenate([rgb, out_a], -1) * 255 + 0.5, 0, 255).astype(np.uint8)

    def rigid_verts(self, layer, sk, cv, scale):
        vx, vy = layer.vx + layer.offset[0], layer.vy + layer.offset[1]
        joint, angle_key = layer.follow
        pivot_src = np.array(layer.anchor)
        if layer.name == "weapon":     # the fist closes on it just past the wrist, as drawn weapons
            wr, el = np.array(sk["wr_n"]), np.array(sk["el_n"])
            pivot_out = np.array(cv.T(sk.get('weapon_grip',tuple(wr + (wr - el) * 0.14))))
        else:
            pivot_out = self.carried(layer, sk, cv, scale)
        # Clockwise on screen, in the rig's convention, except a weapon angle, measured the other way.
        turn = sk[angle_key] - self.rest_angles[angle_key]
        if angle_key == "wep_a":
            turn = -turn
        return rigid(vx, vy, pivot_src, pivot_out, math.radians(turn), scale)

    def carried(self, layer, sk, cv, scale):
        """Where a rigid layer's anchor lands: on its joint, with the bind offset turned with it."""
        joint, angle_key = layer.follow
        rest = self.joints[joint]
        delta = (np.array(layer.anchor) - rest) * (1, -1) / self.px_per_unit
        now = rot(rot(tuple(delta), -self.rest_angles[angle_key]), sk[angle_key])
        return np.array(cv.T((sk[joint][0] + now[0], sk[joint][1] + now[1])))
