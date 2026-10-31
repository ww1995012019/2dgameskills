# Shared by every mode. Edit the copy in the repo's shared/ folder, then run dev/sync_shared.py.
"""Is the whole skeleton in the picture? Measured on pixels, so it holds for any art.

Joint numbers can be perfect while the art is broken: the rig still solves a forearm whose image
lost its middle. Two kinds of check close that gap:

  frame_problems   one rendered frame: a piece of art floating free of the body, or a bone with
                   nothing drawn along it.
  strip_gap, islands   one part image on its own, for rigs that bind images to bones. This is the
                   one that sees a limb lying over the torso, where the frame looks solid.

Thresholds and why they sit where they do are in references/skeleton-qa.md.
"""
import math

import numpy as np

SOLID = 96                # alpha that counts as art; glows, soft edges and contact shadows stay below it
FLOAT_SHARE = 0.005       # a loose piece this share of the body or bigger is visible as a floater
FLOAT_MIN_PX = 4          # below this it is antialiasing noise, however small the character
BONE_GAP_SHARE = 0.2      # longest empty stretch of a bone, as a share of its length ...
BONE_GAP_UNITS = 3.0      # ... and in rig units, so a very short bone can't trip on one pixel
PART_GAP_SHARE = 0.12     # the same along a bone inside its own part image, which fits tighter
ISLAND_SHARE = 0.01       # a part image's loose piece, as a share of that image's art

# Side-view humanoid, shared by the sprite and shooter rigs.
HUMANOID_BONES = [("sh_n", "el_n"), ("el_n", "wr_n"), ("sh_f", "el_f"), ("el_f", "wr_f"),
                  ("hip_n", "kn_n"), ("kn_n", "an_n"), ("hip_f", "kn_f"), ("kn_f", "an_f"),
                  ("hip", "waist"), ("waist", "neck")]


def components(mask):
    """8-connected labels, 0 for background. Row runs joined with union-find."""
    labels = np.zeros(mask.shape, np.int32)
    parent = [0]

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    previous, runs = [], []
    for y, row in enumerate(mask):
        edges = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
        current = []
        for start, end in zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()):
            label = 0
            for p_start, p_end, p_label in previous:
                if p_start <= end and p_end >= start:
                    root = find(p_label)
                    if not label:
                        label = root
                    elif root != label:
                        parent[root] = label
            if not label:
                label = len(parent)
                parent.append(label)
            current.append((start, end, label))
        previous = current
        runs.extend((y, *run) for run in current)
    for y, start, end, label in runs:
        labels[y, start:end] = find(label)
    return labels


def spread(mask, radius):
    """Grow a mask by radius pixels (square brush)."""
    out = mask.copy()
    for _ in range(radius):
        grown = out.copy()
        grown[1:] |= out[:-1]
        grown[:-1] |= out[1:]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def floating_pieces(alpha, unit_px):
    """Pieces of art cut off from the body by more than about one rig unit. A hairline between
    two parts is not a floater, so pieces that close touching are merged first. Returns
    [(share of the body, x, y)], largest first."""
    solid = alpha > SOLID
    if not solid.any():
        return []
    labels = components(spread(solid, max(1, round(unit_px))))
    area = np.bincount(labels[solid], minlength=labels.max() + 1)
    body = int(area.argmax())
    out = []
    for label in np.flatnonzero(area):
        if label == body or area[label] < max(FLOAT_MIN_PX, FLOAT_SHARE * area[body]):
            continue
        ys, xs = np.nonzero(solid & (labels == label))
        out.append((float(area[label] / area[body]), int(xs.mean()), int(ys.mean())))
    return sorted(out, reverse=True)


def empty_bones(alpha, skeleton, bones, unit_px, frame):
    """Bones with a long stretch of nothing drawn along them in one frame. skeleton maps joints to
    per-frame pixel positions. Art a little off the line is fine: the rig's line is not the art's
    centre. Samples outside the frame are left to the bounds check."""
    near = spread(alpha > SOLID, max(1, round(unit_px)))
    h, w = near.shape
    out = []
    for a, b in bones:
        ax, ay = skeleton[a][frame]
        bx, by = skeleton[b][frame]
        length = math.hypot(bx - ax, by - ay)
        if length < 1:
            continue
        run = worst = 0
        for t in np.linspace(0, 1, int(length) + 2):
            x, y = int(ax + (bx - ax) * t), int(ay + (by - ay) * t)
            hit = not (0 <= x < w and 0 <= y < h) or near[y, x]
            run = 0 if hit else run + 1
            worst = max(worst, run)
        if worst > max(BONE_GAP_SHARE * length, BONE_GAP_UNITS * unit_px):
            out.append((f"{a}->{b}", round(worst / length, 2)))
    return out


def frame_problems(frames, unit_px, skeleton=None, bones=(), skip_float=()):
    """Run both frame checks over a clip. frames are RGBA arrays, 0..255 or 0..1. skip_float lists
    frames with a deliberate loose effect (a sword smear can leave the blade behind). Returns
    ({frame: [message]} floating, {frame: [message]} bones)."""
    floating, empty = {}, {}
    for i, frame in enumerate(frames):
        alpha = frame[..., 3]
        alpha = alpha if alpha.dtype == np.uint8 else (alpha * 255).astype(np.uint8)
        if i not in skip_float:
            for share, x, y in floating_pieces(alpha, unit_px):
                floating.setdefault(i, []).append(f"art floating free of the body at {x},{y} ({share:.1%} of its size)")
        if skeleton:
            for bone, share in empty_bones(alpha, skeleton, bones, unit_px, i):
                empty.setdefault(i, []).append(f"{bone}: {share:.0%} of the bone has nothing drawn on it")
    return floating, empty


def strip_gap(solid, pivot, direction, length, half_width):
    """Walk a bone through its own image: the longest stretch, as a share of the bone, with no art
    in a strip half_width either side. direction is a unit vector in image pixels."""
    h, w = solid.shape
    nx, ny = -direction[1], direction[0]
    across = np.arange(-int(half_width), int(half_width) + 1)
    steps = max(int(length), 1)
    run = worst = 0
    for k in range(steps):
        xs = (pivot[0] + direction[0] * k + nx * across).astype(int)
        ys = (pivot[1] + direction[1] * k + ny * across).astype(int)
        inside = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        hit = solid[ys[inside], xs[inside]].any()
        run = 0 if hit else run + 1
        worst = max(worst, run)
    return worst / steps


def islands(solid, bridge=None):
    """Shares of a part image's art that are cut off from its largest piece. Rigid with the part,
    such a piece stays put relative to the bone and floats as soon as the part moves. bridge joins
    pieces meant to be separated in the art, such as a pommel and blade either side of the fist."""
    if not solid.any():
        return []
    labels = components(solid if bridge is None else solid | bridge)
    area = np.bincount(labels[solid], minlength=labels.max() + 1)
    total = area.sum()
    area[0] = 0
    main = area.argmax()
    return sorted((round(float(a / total), 3) for label, a in enumerate(area)
                   if label != main and a >= max(FLOAT_MIN_PX, ISLAND_SHARE * total)), reverse=True)
