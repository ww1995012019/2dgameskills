"""What numbers can say about a layered puppet: the faults a person sees first on cut-up art.

    smear  a layer holds a blurred patch (a chest repainted as fog)
    hand   the hand lost its drawing on the way to the frame (a bun for a fist)
    fold   the mesh turned inside out somewhere (a limb creased at the joint)
    kink   a cloth chain breaks into straight pieces (a cape in segments)
    crouch the standing leg stays bent in the walk (a stroll on folded knees)
    hole   background shows through the body below the belt (no layer behind a split robe)

Thresholds and how each was set are in references/layered-art.md.
"""
import os

import numpy as np
from PIL import Image

from .puppet import winding
from .rig import full_pose, solve

TILE = 24             # px of a layer's art
SMEAR_RANGE = 30      # 0-255: a tile must change this much to count as having content
SMEAR_STEEP = 0.16    # steepest step between neighbours, as a share of the tile's range. Drawn art has
                      # an inked edge or a shading boundary; a blur only ramps
SMEAR_SHARE = 0.03    # of a layer's filled tiles
HAND_DETAIL = 0.55    # of the reference's edge energy at the same size
HAND_FRAMES = 4       # frames sampled over the clip
FOLD_SHARE = 0.002    # of a layer's drawn mesh area inverted in any frame
KINK_DEG = 42.0       # between neighbouring segments of a cloth chain
CORE_END = 0.85       # of the way from waist to hip
HOLE_SHARE = 0.01     # of the core's pixels that may be see-through
CROUCH_DEG = 30.0     # mean knee bend in the walk while the planted foot carries the body: ahead of or under
                      # the hip. Behind the hip the knee has to bend to push off, 40-50 degrees in any human walk


def smear_tiles(rgba):
    """Tiles of a layer that have colour content but no sharp step anywhere: returns (bad, filled)."""
    a = np.asarray(rgba, dtype=np.float32)
    solid = a[..., 3] > 250
    h, w = solid.shape
    bad = filled = 0
    for y in range(0, h - TILE + 1, TILE):
        for x in range(0, w - TILE + 1, TILE):
            if not solid[y:y + TILE, x:x + TILE].all():
                continue
            filled += 1
            t = a[y:y + TILE, x:x + TILE, :3]     # by channel: red against gold is nearly one grey
            span = float((t.max((0, 1)) - t.min((0, 1))).max())
            if span < SMEAR_RANGE:
                continue
            step = max(float(np.abs(np.diff(t, axis=0)).max()), float(np.abs(np.diff(t, axis=1)).max()))
            if step < SMEAR_STEEP * span:
                bad += 1
    return bad, filled


def check_layers(puppet):
    out = []
    for layer in puppet.layers:
        bad, filled = smear_tiles(layer.image)
        if filled and bad / filled > SMEAR_SHARE:
            out.append(f"smear: {layer.name}: {bad} of {filled} tiles are blurred with no drawn edge; make this layer again")
    return out


def edge_energy(rgb):
    """Mean size of the step between neighbouring pixels, on grey, where the art is."""
    g = np.asarray(rgb, dtype=np.float32)
    grey, on = g[..., :3].mean(2), g[..., 3] > 128
    dx, dy = np.abs(np.diff(grey, axis=1)), np.abs(np.diff(grey, axis=0))
    keep_x, keep_y = on[:, 1:] & on[:, :-1], on[1:, :] & on[:-1, :]
    n = int(keep_x.sum() + keep_y.sum())
    return float((dx[keep_x].sum() + dy[keep_y].sum()) / max(n, 1))


def disc_crop(a, x, y, r):
    h, w = a.shape[:2]
    return a[max(int(y - r), 0):min(int(y + r), h), max(int(x - r), 0):min(int(x + r), w)]


def check_hands(renderer, spec, clip, frames, fps):
    """The hand in the frames against the hand in the reference, shrunk to the same size."""
    from .art import Canvas
    from .render import GROUND_FRAC, frame_time
    puppet = renderer.art.puppet
    source = spec["puppet"].get("source")
    if not source:
        return []
    path = os.path.join(spec.get("_dir", "."), source)
    if not os.path.isfile(path):
        return [f"hand: reference {source} not found next to the character"]
    size = renderer.size
    scale = renderer.unit / puppet.px_per_unit
    ref = Image.open(path).convert("RGBA")
    ref = np.asarray(ref.resize((max(1, round(ref.width * scale)), max(1, round(ref.height * scale))), Image.LANCZOS))
    out = []
    cv = Canvas(size, 1, renderer.unit, GROUND_FRAC, 1, False, (0, 0, 0))
    for side in "nf":
        wrist, elbow = puppet.rest_arm[side]
        radius = 0.5 * float(np.hypot(*np.subtract(wrist, elbow))) * scale
        rx, ry = (wrist[0] + (wrist[0] - elbow[0]) * 0.28) * scale, (wrist[1] + (wrist[1] - elbow[1]) * 0.28) * scale
        want = edge_energy(disc_crop(ref, rx, ry, radius))
        got = []
        for i in np.linspace(0, len(frames) - 1, HAND_FRAMES).astype(int):
            sk = solve(full_pose(clip.sample(frame_time(clip, int(i), len(frames), fps))), renderer.art.body)
            wr, el = np.array(sk["wr_" + side]), np.array(sk["el_" + side])
            x, y = cv.T(tuple(wr + (wr - el) * 0.28))
            got.append(edge_energy(disc_crop(frames[int(i)], x, y, radius)))
        if want > 0 and float(np.mean(got)) < HAND_DETAIL * want:
            out.append(f"hand: {side}: {clip.name}: {np.mean(got) / want:.0%} of the reference's detail; the hand lost its drawing")
    return out


def core_mask(size, waist, hip, radius):
    """A square-ended strip from the waist toward the hip, in a frame of (w, h). It stops short of the
    hip joint: below that the legs part, and the gap between them is meant to be open."""
    yy, xx = np.mgrid[0:size[1], 0:size[0]].astype(np.float32)
    a, b = np.array(waist, np.float32), np.array(hip, np.float32)
    u = b - a
    s = ((xx - a[0]) * u[0] + (yy - a[1]) * u[1]) / (u @ u + 1e-6)
    return (s >= 0) & (s <= CORE_END) & ((xx - a[0] - u[0] * s) ** 2 + (yy - a[1] - u[1] * s) ** 2 <= radius * radius)


def check_core(renderer, clip, frames, fps):
    """The body between belt and hips is solid in every frame. The silhouette can't show a hole here,
    because what hangs around it stays in place: the background shows through the middle of the figure."""
    from .art import Canvas
    from .render import GROUND_FRAC, frame_time
    radius = renderer.art.puppet.core_radius * renderer.unit
    if not radius:
        return []
    cv = Canvas(renderer.size, 1, renderer.unit, GROUND_FRAC, 1, False, (0, 0, 0))
    worst, at = 0.0, 0
    for i, frame in enumerate(frames):
        pose = full_pose(clip.sample(frame_time(clip, i, len(frames), fps)))
        sk = solve(pose, renderer.art.body)
        cv.set_squash(pose["squash"], 0.0)
        core = core_mask((frame.shape[1], frame.shape[0]), cv.T(sk["waist"]), cv.T(sk["hip"]), radius)
        share = float((frame[core][:, 3] < 128).mean()) if core.any() else 0.0
        if share > worst:
            worst, at = share, i
    if worst > HOLE_SHARE:
        return [f"hole: {clip.name} frame {at}: {worst:.0%} of the body below the belt is see-through; make the hips layer again"]
    return []


def inverted(verts, cells):
    """Share of the mesh's drawn area wound the other way from the picture, i.e. turned inside out.
    By area, not by cell: a cell crushed to nothing at the centre of a sharp bend shows no art."""
    if not len(cells):
        return 0.0
    areas = np.concatenate(winding(verts, cells))
    return float(-areas[areas < 0].sum() / (np.abs(areas).sum() + 1e-9))


def check_motion(renderer, clip, n, fps):
    """Mesh folds, cloth kinks and the planted knee across one clip."""
    from .art import Canvas
    from .render import GROUND_FRAC, frame_time
    puppet = renderer.art.puppet
    body = renderer.art.body
    cv = Canvas(renderer.size, renderer.ss, renderer.unit, GROUND_FRAC, 1, False, (0, 0, 0))
    out, worst_fold, worst_kink, planted = [], {}, {}, []
    for i in range(n):
        t = frame_time(clip, i, n, fps)
        pose = full_pose(clip.sample(t))
        sk = solve(pose, body)
        cloth = renderer.cloth_at(clip, t)
        cv.set_squash(pose["squash"], 0.0)
        for layer, verts in puppet.meshes(cv, sk, cloth):
            share = inverted(verts, layer.cells)
            if share > worst_fold.get(layer.name, (0,))[0]:
                worst_fold[layer.name] = (share, i)
        for name, pts in cloth.items():
            d = np.diff(np.asarray(pts), axis=0)
            turn = np.degrees(np.abs(np.arctan2(d[:-1, 0] * d[1:, 1] - d[:-1, 1] * d[1:, 0], (d[:-1] * d[1:]).sum(1))))
            if len(turn) and turn.max() > worst_kink.get(name, (0,))[0]:
                worst_kink[name] = (float(turn.max()), i)
        for side, down in clip.contacts(t).items():
            if down and sk["an_" + side][0] >= sk["hip_" + side][0]:
                a = np.subtract(sk["kn_" + side], sk["hip_" + side])
                b = np.subtract(sk["an_" + side], sk["kn_" + side])
                planted.append(np.degrees(np.arccos(np.clip(a @ b / (np.hypot(*a) * np.hypot(*b) + 1e-9), -1, 1))))
    for name, (share, i) in worst_fold.items():
        if share > FOLD_SHARE:
            out.append(f"fold: {name}: {clip.name} frame {i}: {share:.1%} of the mesh turned inside out; the bend is too sharp for this art")
    for name, (deg, i) in worst_kink.items():
        if deg > KINK_DEG:
            out.append(f"kink: {name}: {clip.name} frame {i}: bends {deg:.0f} degrees between segments; the cloth reads as pieces")
    if clip.name == "walk" and planted and float(np.mean(planted)) > CROUCH_DEG:
        out.append(f"crouch: {clip.name}: the knee carrying the body stays bent {np.mean(planted):.0f} degrees, over {CROUCH_DEG:.0f}: a walk on folded legs")
    return out
