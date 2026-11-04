"""Explicit source-space garment registration experiments, never clothing detection.

The caller reviews both seam rows and the target hem profile. Only supplied lower
art is resampled; source upper rows stay byte-identical. A separate optional
backing uses reviewed lower row interiors and a supplied opaque texture swatch.
These helpers neither infer apparel ownership nor certify identity or motion.
They are development-only, pure image operations with no filesystem writes.
"""
import hashlib
import math
from numbers import Real

import numpy as np
from PIL import Image


def _rgba(image, name):
    if not isinstance(image, Image.Image) or image.mode != 'RGBA':
        raise ValueError(f'{name}: expected a nonempty RGBA image')
    if image.width < 1 or image.height < 1 or not np.any(np.asarray(image)[..., 3]):
        raise ValueError(f'{name}: expected a nonempty RGBA image')
    return np.asarray(image)


def _row(value, height, name):
    if type(value) is not int or not 0 <= value < height:
        raise ValueError(f'{name}: expected an integer seam row inside the image')
    return value


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f'{name}: expected a finite number')
    return float(value)


def _span(alpha, name):
    xs = np.flatnonzero(alpha > 128)
    if len(xs) < 2:
        raise ValueError(f'{name}: need two distinct solid-alpha endpoints')
    return float(xs[-1] - xs[0]), float((int(xs[0]) + int(xs[-1])) / 2)


def _digest(image):
    return hashlib.sha256(image.tobytes()).hexdigest()


def _transform_row(band, output_width, scale, shift, label):
    """Reject lost alpha, including filtered edge support, before cropping padding."""
    xs = np.flatnonzero(np.asarray(band)[0, :, 3] > 0)
    if not len(xs):
        return Image.new('RGBA', (output_width, 1))
    left, right = float(xs[0]) * scale + shift, float(xs[-1]) * scale + shift
    if left < 0 or right > output_width - 1:
        raise ValueError(f'{label}: registered lower garment would clip horizontally')
    # Bicubic support extends beyond mapped occupied pixel centers. Render a
    # guard band rather than silently discard fractional-alpha edge samples.
    padding = max(4, math.ceil(2 * scale) + 2)
    # Profile anchors use integer pixel centers; Pillow's affine coordinates use
    # pixel corners. Compensate so scaling does not introduce a half-pixel drift.
    inverse_shift = 0.5 - (shift + padding + 0.5) / scale
    transformed = band.transform((output_width + 2 * padding, 1), Image.Transform.AFFINE,
                                 (1 / scale, 0, inverse_shift, 0, 1, 0),
                                 Image.Resampling.BICUBIC)
    alpha = np.asarray(transformed)[0, :, 3]
    if np.any(alpha[:padding]) or np.any(alpha[padding + output_width:]):
        raise ValueError(f'{label}: filtered lower garment edge would clip horizontally')
    return transformed.crop((padding, 0, padding + output_width, 1))


def register_lower_garment(source_torso, generated_garment, *, source_seam_row,
                           generated_seam_row, target_hem_width, target_hem_center):
    """Join supplied lower garment art to an unchanged source upper torso.

    Both seam rows are explicit, reviewed pixel indices. source_seam_row is the
    FIRST REPLACED row: source rows [0, source_seam_row) remain byte-identical,
    including hidden RGB and partial alpha. generated_seam_row is the first row
    imported from generated_garment. Vertical registration is translation only;
    every lower row through the last nonzero-alpha row is retained or rejected
    if it cannot fit the source canvas. Neither image is mutated.

    Widths are distances between pixel centers (right - left), not pixel counts.
    The source seam's alpha>128 endpoints supply the target seam width/center.
    The generated seam and widest solid-alpha lower row supply two fixed source
    profile anchors. The reference width/center interpolate between those two
    anchors over the full lower height; they NEVER refit a surviving panel tip
    or slit row. The target profile likewise interpolates from source seam to
    explicit target_hem_width/center. Their ratio gives a horizontal affine for
    each row. Bicubic RGBA sampling retains transparent slits and edge alpha;
    no solid silhouette, inpainting, or generated upper pixels are introduced.

    Returns (registered_rgba, report). Numerical registration and upper-pixel
    identity are not semantic, source-identity, garment-seam, or motion approval.
    """
    source = _rgba(source_torso, 'source torso')
    generated = _rgba(generated_garment, 'generated garment')
    source_seam_row = _row(source_seam_row, source_torso.height, 'source_seam_row')
    generated_seam_row = _row(generated_seam_row, generated_garment.height, 'generated_seam_row')
    target_hem_width = _finite(target_hem_width, 'target_hem_width')
    target_hem_center = _finite(target_hem_center, 'target_hem_center')
    if target_hem_width < 1:
        raise ValueError('target_hem_width must span at least two distinct pixel centers')
    if target_hem_center - target_hem_width / 2 < 0 or target_hem_center + target_hem_width / 2 > source_torso.width - 1:
        raise ValueError('target hem profile would clip the source canvas')
    seam_width, seam_center = _span(source[source_seam_row, :, 3], 'source seam')
    generated_width, generated_center = _span(generated[generated_seam_row, :, 3], 'generated seam')
    occupied_rows = np.flatnonzero(np.any(generated[..., 3] > 0, axis=1))
    hem_row = int(occupied_rows[-1])
    if hem_row <= generated_seam_row:
        raise ValueError('generated lower garment must extend below its seam')
    target_last_row = source_seam_row + hem_row - generated_seam_row
    if target_last_row >= source_torso.height:
        raise ValueError('registered lower garment would clip vertically')
    widest_row, widest_width, widest_center = generated_seam_row, generated_width, generated_center
    for row in range(generated_seam_row + 1, hem_row + 1):
        xs = np.flatnonzero(generated[row, :, 3] > 128)
        if len(xs) >= 2 and xs[-1] - xs[0] > widest_width:
            widest_row = row
            widest_width, widest_center = _span(generated[row, :, 3], 'lower reference')
    result = Image.new('RGBA', source_torso.size)
    result.paste(source_torso.crop((0, 0, source_torso.width, source_seam_row)), (0, 0))
    profile = []
    for row in range(generated_seam_row, hem_row + 1):
        fraction = (row - generated_seam_row) / (hem_row - generated_seam_row)
        reference_width = generated_width * (1 - fraction) + widest_width * fraction
        reference_center = generated_center * (1 - fraction) + widest_center * fraction
        width = seam_width * (1 - fraction) + target_hem_width * fraction
        center = seam_center * (1 - fraction) + target_hem_center * fraction
        scale = width / reference_width
        shift = center - reference_center * scale
        target_row = source_seam_row + row - generated_seam_row
        band = generated_garment.crop((0, row, generated_garment.width, row + 1))
        result.paste(_transform_row(band, source_torso.width, scale, shift, f'generated row {row}'), (0, target_row))
        profile.append(dict(source_row=row, target_row=target_row,
                            reference_width=reference_width, reference_center=reference_center,
                            target_width=width, target_center=center, scale=scale, shift=shift))
    report = dict(method='explicit_two_anchor_rowwise_garment_registration', development_only=True,
                  automatic_clothing_detection=False, source_identity_claimed=False,
                  source_rgba_sha256=_digest(source_torso), generated_rgba_sha256=_digest(generated_garment),
                  output_rgba_sha256=_digest(result), source_size=list(source_torso.size),
                  generated_size=list(generated_garment.size), source_seam_row=source_seam_row,
                  source_upper_unchanged_through_row=source_seam_row - 1,
                  source_upper_rgba_unchanged=True, generated_seam_row=generated_seam_row,
                  generated_hem_row=hem_row, target_last_row=target_last_row,
                  generated_widest_reference_row=widest_row,
                  target_hem_width=target_hem_width, target_hem_center=target_hem_center,
                  row_profile=profile, lower_garment_resampled=True, clipped_pixels=0,
                  semantic_visual_approval='pending', registration_visual_approval='pending',
                  motion_contact_approval='pending')
    return result, report


def lower_aperture_backing(garment, swatch, *, seam_row):
    """Return (backing_rgba, report) at exactly garment's size/registration.

    This explicit ownership trial fills each lower row strictly BETWEEN its
    alpha>128 endpoint pixels, excluding both outer endpoints and all exterior
    pixels. It may also sit behind opaque garment interiors. It is not a hole
    detector and does not infer which regions depict trousers or clothing.

    swatch is an explicit RGB image or fully opaque RGBA image. Its RGB texture
    is resized to the interior mask's bounding box; every selected pixel receives
    alpha=255 and every unselected pixel remains RGBA=(0,0,0,0). The caller places
    this separate layer under the legs on the same garment mesh and reviews its
    semantic ownership, seams, and motion. No input image is mutated.
    """
    rgba = _rgba(garment, 'garment')
    seam_row = _row(seam_row, garment.height, 'seam_row')
    if not isinstance(swatch, Image.Image) or swatch.mode not in ('RGB', 'RGBA') or swatch.width < 1 or swatch.height < 1:
        raise ValueError('swatch must be a nonempty opaque RGB or RGBA image')
    if swatch.mode == 'RGBA' and not np.all(np.asarray(swatch)[..., 3] == 255):
        raise ValueError('swatch must be fully opaque')
    mask = np.zeros(rgba.shape[:2], dtype=bool)
    for row in range(seam_row, garment.height):
        xs = np.flatnonzero(rgba[row, :, 3] > 128)
        if len(xs) >= 2 and xs[-1] - xs[0] >= 2:
            mask[row, xs[0] + 1:xs[-1]] = True
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError('lower garment has no nondegenerate row-span interior for backing')
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    left, top, right, bottom = box
    texture = np.asarray(swatch.convert('RGB').resize((right - left, bottom - top), Image.Resampling.LANCZOS))
    output = np.zeros_like(rgba)
    local_mask = mask[top:bottom, left:right]
    output[top:bottom, left:right, :3][local_mask] = texture[local_mask]
    output[..., 3] = mask.astype(np.uint8) * 255
    image = Image.fromarray(output)
    report = dict(method='explicit_lower_row_span_interior_backing', development_only=True,
                  automatic_clothing_detection=False, seam_row=seam_row, size=list(garment.size),
                  garment_rgba_sha256=_digest(garment), swatch_pixel_sha256=_digest(swatch),
                  swatch_mode=swatch.mode, output_rgba_sha256=_digest(image),
                  interior_bbox=list(box), backing_pixels=int(mask.sum()),
                  external_edge_pixels_excluded=True, semantic_visual_approval='pending',
                  registration_visual_approval='pending', motion_contact_approval='pending')
    return image, report
