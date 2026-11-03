#!/usr/bin/env python3
"""Run the sprite generator or motion QA with the prototype "skin" layer kind (dev only).

    python dev/skin_runtime.py generate --character skin-rig/character.json --clips idle,walk --preset hd512 --no-fx --out build/
    python dev/skin_runtime.py qa build/

Adds one layer kind to the layered puppet at run time, without editing the skill: a skin layer is
one picture on one mesh; each vertex is a weighted blend of its bones' rigid motions (linear blend
skinning). Cells were sorted back to front when the rig was built, and later cells draw over
earlier ones, so a near limb stays in front of the trunk and the far limbs.
"""
import math
import os
import runpy
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "game-sprite-animator/scripts"
sys.path.insert(0, str(SCRIPTS))
from sprite_anim import puppet as P  # noqa: E402


class SkinLayer:
    kind = "skin"
    foot = None
    root_lock = tip_lock = False
    chain = None

    def __init__(self, name, data, base):
        self.name = name
        self.image = Image.open(os.path.join(base, data["image"])).convert("RGBA")
        self.offset = np.array(data.get("offset", (0, 0)), dtype=np.float64)
        z = np.load(os.path.join(base, data["skin"]))
        self.gx, self.gy = z["gx"], z["gy"]
        self.vx, self.vy = np.meshgrid(self.gx, self.gy)
        self.all_cells = self.cells = z["cells"]
        self.weights = z["weights"]
        self.bones = list(data["bones"])
        self.rest = {k: [np.array(p, dtype=np.float64) for p in v] for k, v in data["rest"].items()}
        self.defs = {k: (v[0], v[1]) for k, v in data["bone_defs"].items()}
        self.used = np.zeros(self.vx.shape, bool)
        for dj, di in ((0, 0), (0, 1), (1, 0), (1, 1)):
            self.used[self.cells[:, 0] + dj, self.cells[:, 1] + di] = True
        a = np.asarray(self.image)[..., 3]
        ys, xs = np.nonzero(a > 5)
        self.box = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        self.radius = 0.0
        self.rest_curve = None

    def transform(self, name, sk, cv, scale, rest_angles):
        """Rotation (radians, clockwise on screen), source pivot and output pivot of one bone."""
        kind, data = self.defs[name]
        if kind == "seg":
            a0, b0 = self.rest[name]
            a1, b1 = np.array(cv.T(sk[data[0]])), np.array(cv.T(sk[data[1]]))
            turn = math.atan2(*(b1 - a1)[::-1]) - math.atan2(*(b0 - a0)[::-1])
            return turn, a0, a1
        pivot, key, sign = data
        turn = math.radians(sign * (sk[key] - rest_angles.get(key, 0.0)))
        return turn, self.rest[name][0], np.array(cv.T(sk[pivot]))

    def deform(self, sk, cv, scale, rest_angles, sel=None):
        vx = self.vx + self.offset[0]
        vy = self.vy + self.offset[1]
        w = self.weights
        if sel is not None:
            vx, vy, w = vx[sel], vy[sel], w[sel]
        out = np.zeros(vx.shape + (2,))
        for k, name in enumerate(self.bones):
            wk = w[..., k]
            if not wk.any():
                continue
            turn, src, dst = self.transform(name, sk, cv, scale, rest_angles)
            out += wk[..., None] * P.rigid(vx, vy, src, dst, turn, scale)
        return out


_original_init = P.Puppet.__init__
_original_meshes = P.Puppet.meshes


def _init(self, spec):
    data = spec["puppet"]
    skins = {n: d for n, d in data["layers"].items() if d.get("kind") == "skin"}
    if not skins:
        return _original_init(self, spec)
    rest = {n: d for n, d in data["layers"].items() if d.get("kind") != "skin"}
    trimmed = dict(spec, puppet=dict(data, layers=rest))
    _original_init(self, trimmed)
    base = spec.get("_dir", ".")
    self.layers = [SkinLayer(n, d, base) for n, d in skins.items()] + self.layers


def _meshes(self, cv, sk, cloth, ground_contact=False, relax=True, used_only=False):
    scale = cv.s / self.px_per_unit
    others = [layer for layer in self.layers if layer.kind != "skin"]
    for layer in self.layers:
        if layer.kind == "skin":
            if used_only:
                yield layer, layer.deform(sk, cv, scale, self.rest_angles, layer.used)
                continue
            verts = layer.deform(sk, cv, scale, self.rest_angles)
            # Where two parts squeeze the sheet between them it folds over: those cells, now turned
            # face down, would draw the fold's outline as a comb of dark marks. The cloth on either
            # side covers the fold, so face-down cells are not drawn.
            layer.cells = layer.all_cells[~P.flipped(verts, layer.all_cells)]
            yield layer, verts
    if others:
        saved = self.layers
        self.layers = others
        try:
            yield from _original_meshes(self, cv, sk, cloth, ground_contact, relax, used_only)
        finally:
            self.layers = saved


P.Puppet.__init__ = _init
P.Puppet.meshes = _meshes


def main():
    mode, args = sys.argv[1], sys.argv[2:]
    script = {"generate": "generate.py", "qa": "qa_motion.py"}[mode]
    sys.argv = [str(SCRIPTS / script)] + args
    runpy.run_path(str(SCRIPTS / script), run_name="__main__")


if __name__ == "__main__":
    main()
