"""Explicit, static head-stem/socket attachment contract.

This is not material recognition or a rigid-limb renderer. Callers must opt in
following artwork review. The default skin/cap attachment contract is separate.
"""
import numpy as np
from PIL import Image
from sprite_anim.integrity import components
import layer_parts as lp


def validate_socket(head, torso, seat):
    """Revalidate assembled alpha masks; reports never substitute for this check.

    The head must have a narrow connected terminal stem inserted into the torso's
    upper core, with all insertion rows supported. Socket rims may remain visible.
    Dimensions are relative to the artwork, except a two-pixel sampling minimum.
    """
    head, torso = np.asarray(head, bool), np.asarray(torso, bool)
    if head.shape != torso.shape or not head.any() or not torso.any():
        raise ValueError('socket: nonempty masks must share a canvas')
    seat = np.asarray(seat, float)
    if seat.shape != (2,) or not np.isfinite(seat).all():
        raise ValueError('socket: invalid seat')
    try:
        row, columns, _ = lp.neck_core(torso)
    except (ValueError, IndexError) as error:
        raise ValueError("socket: torso upper core has a gap") from error
    core_width = float(len(columns))
    if abs(seat[1] - row) > max(2., core_width * .05) or abs(seat[0] - columns.mean()) > max(2., core_width * .15):
        raise ValueError('socket: seat is not centered on torso upper core')
    yy, xx = np.indices(head.shape)
    hy, hx = np.nonzero(head)
    height, width = float(np.ptp(hy) + 1), float(np.ptp(hx) + 1)
    depth = float(hy.max() - seat[1])
    if not max(2., height * .04) <= depth <= height * .20:
        raise ValueError('socket: insertion depth is outside terminal stem bounds')
    stem = head & (yy >= np.ceil(seat[1]))
    sy, sx = np.nonzero(stem)
    if not len(sx):
        raise ValueError('socket: missing inserted stem')
    # Preserve four-connectivity using the existing eight-connected labeller:
    # doubled pixel centers are joined only by occupied cardinal edges. Crop
    # first so this temporary grid is bounded by the small inserted stem.
    crop = stem[sy.min():sy.max() + 1, sx.min():sx.max() + 1]
    cardinal = np.zeros((crop.shape[0] * 2 - 1, crop.shape[1] * 2 - 1), bool)
    cardinal[::2, ::2] = crop
    cardinal[1::2, ::2] = crop[:-1] & crop[1:]
    cardinal[::2, 1::2] = crop[:, :-1] & crop[:, 1:]
    labels = components(cardinal)
    count = len(np.unique(labels[labels > 0]))
    if count != 1:
        raise ValueError('socket: inserted stem is disconnected')
    stem_width = float(np.ptp(sx) + 1)
    if stem_width > width * .45:
        raise ValueError('socket: terminal stem is not narrow relative to head')
    if abs(float(np.median(sx)) - seat[0]) > max(2., core_width * .15):
        raise ValueError('socket: inserted stem is offset from seat')
    contact = stem & torso
    coverage = float(contact.sum() / stem.sum())
    if coverage < .995:
        raise ValueError('socket: inserted stem lacks full torso support')
    # Total overlap alone cannot excuse a thin full-width gap in the stem.
    rows = np.unique(sy)
    if len(rows) != rows[-1] - rows[0] + 1 or any(not contact[y].any() for y in rows):
        raise ValueError('socket: insertion has a contact gap')
    exposed = float((head & ~torso).sum() / head.sum())
    if exposed < .75:
        raise ValueError('socket: head is excessively buried')
    return dict(mode='socket', stem_coverage=coverage, insertion_depth=depth,
                stem_width=stem_width, core_width=core_width, exposed_head_fraction=exposed,
                validation_scope='static assembled masks; dynamic contact requires separate review')


def place_socket(head, torso, head_scale, torso_scale, torso_offset, canvas):
    """Find a terminal stem seat using fixed scales, changing translation only.

    Return local head anchor, head offset, and independently checked contact data.
    Raises instead of enlarging the head, painting a patch, or changing the mode.
    """
    if not np.isfinite([head_scale, torso_scale]).all() or head_scale <= 0 or torso_scale <= 0:
        raise ValueError('socket: scales must be positive')
    head, torso = np.asarray(head, bool), np.asarray(torso, bool)
    if head.ndim != 2 or torso.ndim != 2 or not head.any() or not torso.any():
        raise ValueError("socket: nonempty two-dimensional masks required")
    def placed(mask, scale, offset):
        source = Image.fromarray(mask.astype('uint8') * 255)
        return np.asarray(source.transform(tuple(canvas), Image.Transform.AFFINE,
            (1 / scale, 0, -offset[0] / scale, 0, 1 / scale, -offset[1] / scale),
            resample=Image.Resampling.NEAREST)) > 128
    torso_offset = np.asarray(torso_offset, float)
    target = placed(torso, torso_scale, torso_offset)
    row, cols, _ = lp.neck_core(target)
    seat = np.array([cols.mean(), float(row)])
    ys, _ = np.nonzero(head)
    height = int(np.ptp(ys) + 1)
    candidates = range(int(ys.min() + height * .80), int(ys.min() + height * .96))
    candidates = sorted(candidates, key=lambda y: abs(y - (ys.min() + height * .90)))
    errors = []
    for y in candidates:
        columns = np.flatnonzero(head[y])
        if not len(columns):
            continue
        anchor = np.array([float(np.median(columns)), float(y)])
        offset = seat - anchor * head_scale
        try:
            report = validate_socket(placed(head, head_scale, offset), target, seat)
        except ValueError as error:
            errors.append(str(error))
            continue
        report['head_scale_unchanged'] = float(head_scale)
        return anchor, offset, report
    raise ValueError('socket: no supported terminal stem placement' + (': ' + errors[0] if errors else ''))
