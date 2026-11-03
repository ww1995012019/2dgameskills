"""The batched mesh rasteriser, curve builder and used-vertex bounds give the original results exactly.

``reference_raster`` and ``reference_rounded`` are the earlier loop implementations, kept here
only as the oracle. Equality is bitwise, including triangles shared by an edge (later wins),
degenerate cells, cells off the canvas and batches split by the memory budget.
"""
import math
import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
from PIL import Image

from sprite_anim import puppet as P
from sprite_anim.art import Canvas


def reference_raster(layer, verts, mip, w, h):
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

def reference_rounded(points, radius):
    pts = [np.asarray(p, dtype=np.float64) for p in points]
    reach = 0.68 if len(pts) == 3 else 0.45
    runs = [0.0] + [P.corner_run(pts[i - 1], pts[i], pts[i + 1], radius, reach) for i in range(1, len(pts) - 1)] + [0.0]
    out = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        length = np.hypot(*(b - a)) or 1e-6
        u = (b - a) / length
        start = a + u * runs[i] if i else a
        end = b - u * runs[i + 1] if i < len(pts) - 2 else b
        for t in np.linspace(0, 1, P.CURVE_STEPS, endpoint=False):
            out.append(start + (end - start) * t)
        if i < len(pts) - 2:
            next_len = np.hypot(*(pts[i + 2] - b)) or 1e-6
            tail = b + (pts[i + 2] - b) / next_len * runs[i + 1]
            for t in np.linspace(0, 1, P.CURVE_STEPS, endpoint=False):
                out.append((1 - t) ** 2 * end + 2 * t * (1 - t) * b + t * t * tail)
    out.append(pts[-1])
    return np.array(out)


def mesh(rng, trial):
    gh, gw = rng.integers(2, 12, 2)
    gx, gy = np.arange(gw) * 14., np.arange(gh) * 14.
    layer = types.SimpleNamespace(gx=gx, gy=gy, name='fixture',
                                  cells=np.argwhere(rng.random((gh - 1, gw - 1)) < .7))
    vx, vy = np.meshgrid(gx, gy)
    s = rng.uniform(.3, 3)
    verts = np.stack([vx * s + rng.uniform(-40, 80), vy * s + rng.uniform(-40, 80)], -1)
    verts += rng.normal(0, rng.choice([0, 2, 15]), verts.shape)     # folded cells overlap
    if trial % 7 == 0:
        verts[..., 0] = verts[..., 0].mean()                          # zero-area cells
    img = rng.random((int(gy[-1] * .7) + 2, int(gx[-1] * .7) + 2, 4)).astype(np.float32)
    return layer, verts, (img, .7), int(rng.integers(20, 200)), int(rng.integers(20, 200))


class BatchedRaster(unittest.TestCase):
    def test_matches_per_triangle_reference(self):
        rng = np.random.default_rng(0)
        for budget in (P.RASTER_BUDGET, 500, 1):
            with self.subTest(budget=budget):
                saved, P.RASTER_BUDGET = P.RASTER_BUDGET, budget
                try:
                    for trial in range(80):
                        args = mesh(rng, trial)
                        np.testing.assert_array_equal(P.raster(*args), reference_raster(*args))
                finally:
                    P.RASTER_BUDGET = saved

    def test_non_finite_mesh_is_refused(self):
        layer, verts, mip, w, h = mesh(np.random.default_rng(1), 1)
        verts[0, 0] = np.nan
        layer.cells = np.array([[0, 0]])
        with self.assertRaises(ValueError):
            P.raster(layer, verts, mip, w, h)

    def test_rounded_matches_reference(self):
        rng = np.random.default_rng(2)
        for k in range(2000):
            pts = rng.normal(0, rng.choice([1, 50, 500]), (int(rng.integers(2, 6)), 2))
            if k % 50 == 0:
                pts[1] = pts[0]
            radius = rng.uniform(0, 80)
            np.testing.assert_array_equal(P.rounded(list(pts), radius), reference_rounded(list(pts), radius))


class UsedVertexBounds(unittest.TestCase):
    """fit_scale measures art bounds from used vertices only; they must equal the full mesh's."""

    def test_used_only_equals_full_mesh_entries_for_every_layer_kind(self):
        rng = np.random.default_rng(3)
        with tempfile.TemporaryDirectory() as tmp:
            a = np.zeros((160, 120, 4), np.uint8)
            a[20:150, 30:90] = (90, 60, 40, 255)
            a[60:100, 0:20] = (90, 60, 40, 255)          # an island: unused grid cells between
            Image.fromarray(a).save(Path(tmp) / 'part.png')
            leg = [[60, 20], [62, 80], [58, 140]]
            foot = dict(side='n', ankle=[58, 140], shin_dir=[0, 1], blend=8., width=12., rest_angle=0.)
            layers = {
                'leg_near': dict(kind='tube', image='part.png', bones=['hip_n', 'kn_n', 'an_n'], rest=leg,
                                 radius=20., root_lock=True, foot=foot),
                'arm_near': dict(kind='tube', image='part.png', bones=['sh_n', 'el_n', 'wr_n'], rest=leg,
                                 radius=15., root_lock=True, tip_lock=True),
                'robe': dict(kind='tube', image='part.png', bones=['hip', 'waist'], rest=[[60, 120], [60, 30]]),
                'cape': dict(kind='cloth', image='part.png', chain='cape', rest=[[60, 20], [60, 90], [60, 150]]),
                'head': dict(kind='rigid', image='part.png', anchor=[60, 30], follow=['head_base', 'head_rot']),
            }
            spec = dict(_dir=tmp, puppet=dict(px_per_unit=4., joints={'head_base': [60, 30]},
                        rest_angles={'head_rot': 0.}, layers=layers))
            puppet = P.Puppet(spec)
            for trial in range(40):
                j = lambda: tuple(rng.normal(0, 12, 2))
                sk = {k: j() for k in ('hip_n', 'kn_n', 'an_n', 'sh_n', 'el_n', 'wr_n', 'hip', 'waist', 'head_base')}
                sk.update(fr_n=float(rng.uniform(-40, 40)), head_rot=float(rng.uniform(-30, 30)))
                cloth = {'cape': [j(), j(), j()]}
                cv = Canvas(2, 1, 1., 0., 1., False, (0, 0, 0))
                ground = bool(trial % 2)
                full = list(puppet.meshes(cv, sk, cloth, ground, relax=False))
                used = list(puppet.meshes(cv, sk, cloth, ground, relax=False, used_only=True))
                for (layer, verts), (_, points) in zip(full, used):
                    self.assertFalse(layer.used.all())
                    np.testing.assert_array_equal(verts[layer.used], points, err_msg=layer.name)
            with self.assertRaises(ValueError):
                next(puppet.meshes(cv, sk, cloth, used_only=True))


if __name__ == '__main__':
    unittest.main()
