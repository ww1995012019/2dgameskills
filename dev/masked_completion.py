"""Experimental extraction/completion boundary; never grants art or binding approval.

Masks come from a reviewed segmentation proposal, not this tool. No model or
character coordinates are embedded here. Only generated pixels in the recorded
completion mask can enter an export. See docs/segmentation-experiment.md.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_mask(path, size):
    image = Image.open(path)
    if image.size != size or image.mode not in ('1', 'L'):
        raise ValueError('mask must be a binary grayscale image at source size')
    pixels = np.asarray(image.convert('L'))
    if not np.isin(pixels, [0, 255]).all():
        raise ValueError('mask must contain only 0 and 255')
    return pixels > 0


def extract(source, mask):
    """Keep source coordinates and RGBA bytes; zero every unowned pixel."""
    result = np.zeros_like(source)
    result[mask] = source[mask]
    return result


def hole_pixels(mask):
    """Pixels in enclosed transparent regions (topology only, not semantics)."""
    image = ImageOps.expand(Image.fromarray(mask.astype('uint8') * 255), 1)
    ImageDraw.floodfill(image, (0, 0), 128)
    return int(np.count_nonzero(np.asarray(image)[1:-1, 1:-1] == 0))


def geometry_blockers(visible, completion, target=.20):
    blockers = []
    if completion.sum() / (visible | completion).sum() > target:
        blockers.append('initial_small_area_target_exceeded')
    if hole_pixels(visible | completion):
        blockers.append('enclosed_transparent_regions_require_review')
    return blockers


def prepare(source, visible_mask, completion_mask, out):
    source, visible_mask, completion_mask = map(Path, (source, visible_mask, completion_mask))
    out = Path(out)
    if (out / 'request.json').exists():
        raise ValueError('request already exists; use a new experiment directory')
    rgba = np.asarray(Image.open(source).convert('RGBA'))
    size = (rgba.shape[1], rgba.shape[0])
    visible, completion = [read_mask(p, size) for p in (visible_mask, completion_mask)]
    if not visible.any() or not completion.any():
        raise ValueError('visible and completion masks must both be nonempty')
    if (visible & completion).any():
        raise ValueError('visible and completion masks overlap')
    if (rgba[:, :, 3][visible] != 255).any():
        raise ValueError('experimental visible extraction requires opaque source pixels')
    y, x = np.nonzero(visible | completion)
    width, height = int(x.max() - x.min() + 1), int(y.max() - y.min() + 1)
    side = max(width, height) + 2 * round(max(width, height) * .12)
    left = round((int(x.min()) + int(x.max()) + 1 - side) / 2)
    top = round((int(y.min()) + int(y.max()) + 1 - side) / 2)
    crop = [left, top, left + side, top + side]
    plate = np.full_like(rgba, 255)
    plate[:, :, :3] = (230, 233, 236)
    plate[visible] = rgba[visible]
    plate[completion] = (0, 255, 0, 255)
    out.mkdir(parents=True, exist_ok=True)
    # Padding matches the background, including requests at a canvas edge.
    padded = Image.new('RGBA', (side, side), (230, 233, 236, 255))
    padded.paste(Image.fromarray(plate), (-left, -top))
    padded.resize((1024, 1024), Image.Resampling.LANCZOS).save(out / 'plate.png')
    Image.fromarray(extract(rgba, visible)).save(out / 'visible.png')
    blockers = geometry_blockers(visible, completion)
    request = {
        'version': 1, 'status': 'blocked_preflight' if blockers else 'experiment_requires_visual_review',
        'preflight_blockers': blockers,
        'envelope_enclosed_pixels': hole_pixels(visible | completion),
        'source': str(source.resolve()), 'visible_mask': str(visible_mask.resolve()),
        'completion_mask': str(completion_mask.resolve()), 'crop': crop,
        'size': list(size), 'visible_pixels': int(visible.sum()),
        'completion_pixels': int(completion.sum()),
        'completion_share': float(completion.sum() / (visible | completion).sum()),
        'initial_small_area_target': .20,
        'hashes': {name: digest(path) for name, path in (
            ('source', source), ('visible_mask', visible_mask),
            ('completion_mask', completion_mask), ('plate', out / 'plate.png'))},
    }
    (out / 'request.json').write_text(json.dumps(request, indent=2) + '\n', encoding='utf-8')
    return request


def compose(directory, generated):
    directory, generated = Path(directory), Path(generated)
    request = json.loads((directory / 'request.json').read_text(encoding='utf-8'))
    for name in ('source', 'visible_mask', 'completion_mask', 'plate'):
        path = directory / 'plate.png' if name == 'plate' else Path(request[name])
        if digest(path) != request['hashes'][name]:
            raise ValueError(f'{name} changed since preparation')
    rgba = np.asarray(Image.open(request['source']).convert('RGBA'))
    visible = read_mask(request['visible_mask'], tuple(request['size']))
    completion = read_mask(request['completion_mask'], tuple(request['size']))
    patch = Image.open(generated).convert('RGBA')
    if patch.width != patch.height:
        raise ValueError('generated registration plate must be square')
    left, top, right, bottom = request['crop']
    # Resample the returned patch only. Never resize/reposition original artwork.
    patch = patch.resize((right - left, bottom - top), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', tuple(request['size']))
    canvas.paste(patch, (left, top))
    proposed = np.asarray(canvas)
    result = extract(rgba, visible)
    result[completion] = proposed[completion]
    if not np.array_equal(result[visible], rgba[visible]):
        raise AssertionError('source pixels changed')
    if result[~(visible | completion)].any():
        raise AssertionError('pixels escaped the approved envelope')
    blockers = geometry_blockers(visible, completion, request['initial_small_area_target'])
    green = (result[:, :, 0] < 40) & (result[:, :, 1] > 210) & (result[:, :, 2] < 40)
    remaining_green = int((green & completion).sum())
    if remaining_green:
        blockers.append('unfilled_green_marker')
    holes = hole_pixels(result[:, :, 3] > 0)
    if holes and 'enclosed_transparent_regions_require_review' not in blockers:
        blockers.append('enclosed_transparent_regions_require_review')
    report = {
        'status': 'blocked' if blockers else 'needs_visual_review', 'binding_approved': False,
        'generated_sha256': digest(generated), 'request_sha256': digest(directory / 'request.json'),
        'original_visible_changed_pixels': 0, 'outside_envelope_pixels': 0,
        'remaining_green_pixels': remaining_green, 'enclosed_transparent_pixels': holes,
        'completion_share': request['completion_share'], 'blockers': blockers,
        'limitations': ['Mask ownership and reconstructed anatomy are not checked numerically.',
                        'Pixel locality does not prove registration, seam quality or complete artwork.'],
    }
    Image.fromarray(result).save(directory / 'completed.png')
    (directory / 'integrity_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    for name in ('source', 'visible_mask', 'completion_mask', 'out'):
        prep.add_argument('--' + name.replace('_', '-'), required=True, type=Path)
    comp = sub.add_parser('compose')
    comp.add_argument('directory', type=Path)
    comp.add_argument('generated', type=Path)
    args = vars(parser.parse_args())
    command = args.pop('command')
    report = prepare(**args) if command == 'prepare' else compose(**args)
    print(json.dumps(report, indent=2))
    if report['status'] in ('blocked', 'blocked_preflight'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
