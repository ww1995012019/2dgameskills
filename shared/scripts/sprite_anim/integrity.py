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

THIGH_DEFORMATION_LIMITS = dict(min_scale=.25,max_scale=3.,min_area=.15,max_area=3.,max_bad_share=.01,
                                root_start=.15,knee_exclusion_radii=2.)

def connection_report_faults(root, doc, trace):
    """Fail closed on missing/tampered full-frame registered connection evidence."""
    if not (trace.get('connection_review_required') or trace.get('binding_profile') == 'basic-side-v1'):
        return []
    import hashlib
    from pathlib import Path
    from PIL import Image
    out = []
    required = {'torso', 'leg_near', 'leg_far'}
    try:
        data = trace['connections']
        reference = Path(root)/'binding_reference.png'
        if hashlib.sha256(reference.read_bytes()).hexdigest() != data['source_reference_sha256']:
            raise ValueError('connection evidence uses a different registered source reference')
        if data['method'] != 'registered_articulations_v2' or set(data['bindings']) != required:
            raise ValueError('missing complete registered connection bindings')
        if data.get('shape_limits') != THIGH_DEFORMATION_LIMITS:
            raise ValueError('missing current thigh shape checks; zero connection drift is insufficient')
        for name, binding in data['bindings'].items():
            points = np.asarray(binding['source_points'], float)
            if points.ndim != 2 or points.shape[1] != 2 or len(points) < 4 or not np.isfinite(points).all():
                raise ValueError(f'{name}: missing attachment edge samples')
            expected = 'registered_pelvis_overlap' if name == 'torso' else 'registered_articulated_socket_v2'
            if binding.get('method') != expected or binding.get('parent') != 'hips':
                raise ValueError(f'{name}: incorrect registered joint/surface binding kind')
            if name != 'torso':
                joint = np.asarray(binding['source_joint'],float)
                if joint.shape != (2,) or not np.isfinite(joint).all():
                    raise ValueError(f'{name}: missing source joint registration')
        if set(data['clips']) != set(doc['clips']):
            raise ValueError('connection scope differs from exported clips')
        for clip, meta in doc['clips'].items():
            count = len(meta['frames']); row = data['clips'][clip]
            if row['frames'] != count or set(row['parts']) != required:
                raise ValueError(f'{clip}: missing connection frame/part coverage')
            for name, errors in row['parts'].items():
                if len(errors) != count or not all(isinstance(x, (int,float)) and not isinstance(x,bool)
                        and math.isfinite(x) and x >= 0 for x in errors):
                    raise ValueError(f'{clip}/{name}: invalid connection measurements')
                for frame, error in enumerate(errors):
                    if error > 1.0:
                        out.append(dict(clip=clip, frame=frame, part=name,
                                        what=f'registered garment connection separates by {error:.3f}px'))
            shapes = row['shape_parts']
            if set(shapes) != {'leg_near','leg_far'}:
                raise ValueError(f'{clip}: missing both thigh shape measurements')
            for name, measurements in shapes.items():
                if len(measurements) != count:
                    raise ValueError(f'{clip}/{name}: incomplete thigh shape frame coverage')
                for frame, measured in enumerate(measurements):
                    if type(measured.get('samples')) is not int or measured['samples'] < 1:
                        raise ValueError(f'{clip}/{name}: missing opaque thigh material samples')
                    for key in ('bad_share','min_scale','max_scale','min_area','max_area'):
                        x = measured[key]
                        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x):
                            raise ValueError(f'{clip}/{name}: invalid thigh deformation measurement')
                    if not 0 <= measured['bad_share'] <= 1:
                        raise ValueError(f'{clip}/{name}: invalid deformed material share')
                    if (measured['min_scale'] < 0 or measured['min_scale'] > measured['max_scale']
                            or measured['min_area'] > measured['max_area']):
                        raise ValueError(f'{clip}/{name}: inconsistent thigh deformation extrema')
                    if measured['bad_share'] > THIGH_DEFORMATION_LIMITS['max_bad_share']:
                        out.append(dict(clip=clip,frame=frame,part=name,
                                        what=f"thigh material collapses or stretches over {measured['bad_share']:.1%} of its shaft"))
            hashes = data['frame_hashes'][clip]
            if len(hashes) != count:
                raise ValueError(f'{clip}: missing measured RGBA frame hashes')
            for frame, expected in enumerate(hashes):
                with Image.open(Path(root)/'frames'/clip/f'{clip}_{frame:03d}.png') as image:
                    image = image.convert('RGBA')
                    current = hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()
                if current != expected:
                    out.append(dict(clip=clip, frame=frame, part='frame', what='connection evidence measures different RGBA pixels'))
    except (KeyError,ValueError,TypeError,IndexError,OSError) as error:
        out.append(dict(clip=next(iter(doc['clips']), ''),frame=0,part='scope',what=str(error)))
    return out

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
