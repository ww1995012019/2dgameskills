"""Opt-in dev adapter for an explicitly registered, continuous torso garment.

This is not segmentation, automatic registration, or a replacement for visual
review. It reuses known-joint geometry, replaces the torso/collar artwork, and
removes redundant hips/pelvis_front ownership. The supplied garment is already in
source coordinates; it is never scaled, warped, or claimed to preserve identity.
"""
import argparse
import copy
import ctypes
import hashlib
import io
import json
import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image


HISTORY = 'history/continuous_garment_source'
GARMENT = 'layers/continuous_garment.png'
GARMENT_FRONT = 'layers/continuous_garment_front.png'
GARMENT_BACKING = 'layers/continuous_garment_backing.png'
REQUIRED = {'arm_far', 'leg_far', 'leg_near', 'torso', 'head', 'arm_near'}
OPTIONAL = {'hips', 'pelvis_front', 'torso_front', 'weapon'}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(data, label):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError(f'{label}: duplicate JSON key {key!r}')
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f'{label}: nonfinite JSON number {value}')

    value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError(f'{label}: expected a JSON object')
    return value


def _encode(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value
            or any(part in ('', '.', '..') for part in value.split('/'))
            or PurePosixPath(value).is_absolute() or ':' in value):
        raise ValueError('image paths must be safe relative paths inside the source rig')
    return value


def _offset(value, label):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(v) is not int for v in value)):
        raise ValueError(f'{label}: offset must be an explicit integer pair')
    return tuple(value)


def _rgba(data, label):
    with Image.open(io.BytesIO(data)) as image:
        if image.mode != 'RGBA':
            raise ValueError(f'{label}: image must be RGBA')
        return image.copy()


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _inside(image, offset, canvas, label):
    x, y = offset
    if x < 0 or y < 0 or x + image.width > canvas[0] or y + image.height > canvas[1]:
        raise ValueError(f'{label}: registered image would clip the source reference canvas')


def _snapshot(root):
    """Read everything before writing; reject links rather than copy escaped data."""
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('source rig must not contain symlinks')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path.read_bytes()
        elif not path.is_dir():
            raise ValueError('source rig must contain only regular files and directories')
    return files


def _atomic_publisher():
    """Resolve an atomic *no replacement* rename before making any writes."""
    if os.name == 'nt':
        # Windows rename, unlike POSIX rename, refuses an existing destination.
        return os.rename
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int

        def publish(source, destination):
            if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):  # AT_FDCWD, RENAME_NOREPLACE
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), str(destination))
        return publish
    if sys.platform == 'darwin' and hasattr(libc, 'renamex_np'):
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int

        def publish(source, destination):
            if rename(os.fsencode(source), os.fsencode(destination), 4):  # RENAME_EXCL
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), str(destination))
        return publish
    raise OSError('atomic no-replacement directory publication is unavailable on this platform')


def _layer_order(layers):
    """Only reorder an unambiguous contiguous, recognized ownership block.

    The two supported inputs place the complete torso/head/collar cluster either
    before or after the adjacent legs. Outer unrelated layers retain their exact
    ordering. Unknown interleaving is rejected, never silently discarded/moved.
    """
    if not REQUIRED.issubset(layers):
        raise ValueError('missing required canonical ownership layers')
    names = list(layers)
    recognized = REQUIRED | OPTIONAL
    positions = [i for i, name in enumerate(names) if name in recognized]
    start, end = min(positions), max(positions) + 1
    block = names[start:end]
    if any(name not in recognized for name in block):
        raise ValueError('unknown layer interleaved in canonical ownership block')
    active = [name for name in block if name not in ('hips', 'pelvis_front')]
    legs = [name for name in active if name in ('leg_far', 'leg_near')]
    cluster = ['torso', 'head'] + (['torso_front'] if 'torso_front' in layers else [])
    front = [name for name in active if name in ('weapon', 'arm_near')]
    supported = (['arm_far'] + legs + cluster + front,
                 ['arm_far'] + cluster + legs + front)
    if active not in supported:
        raise ValueError('unsupported layer order: require arm_far, adjacent legs and torso/head cluster, then front arms/weapon')
    return names[:start] + supported[0] + names[end:]


def _retention(original, original_offset, replacement, replacement_offset):
    """Measure byte-identical RGBA preservation at original source coordinates."""
    old = np.asarray(original)
    new = np.asarray(replacement)
    dx = original_offset[0] - replacement_offset[0]
    dy = original_offset[1] - replacement_offset[1]
    x0, y0 = max(0, -dx), max(0, -dy)
    x1, y1 = min(original.width, replacement.width - dx), min(original.height, replacement.height - dy)
    occupied = old[..., 3] > 0
    preserved = 0
    if x1 > x0 and y1 > y0:
        same = np.all(old[y0:y1, x0:x1] == new[y0 + dy:y1 + dy, x0 + dx:x1 + dx], axis=2)
        preserved = int(np.count_nonzero(same & occupied[y0:y1, x0:x1]))
    total = int(np.count_nonzero(occupied))
    return {'source_nontransparent_pixels': total,
            'source_nontransparent_rgba_pixels_preserved': preserved,
            'source_nontransparent_rgba_pixels_changed_or_missing': total - preserved}


def _completed_leg(name, descriptor, original, original_offset, canvas):
    if (not isinstance(descriptor, Mapping) or set(descriptor) != {'image', 'offset'}):
        raise ValueError(f'{name}: completed leg requires exactly image and offset')
    offset = _offset(descriptor['offset'], name)
    data = Path(descriptor['image']).read_bytes()
    replacement = _rgba(data, name + ' completion')
    _inside(replacement, offset, canvas, name)
    dx, dy = original_offset[0] - offset[0], original_offset[1] - offset[1]
    if (dx < 0 or dy < 0 or dx + original.width > replacement.width
            or dy + original.height > replacement.height):
        raise ValueError(f'{name}: completion must contain the entire original image rectangle without clipping')
    measurement = _retention(original, original_offset, replacement, offset)
    if measurement['source_nontransparent_rgba_pixels_changed_or_missing']:
        raise ValueError(f'{name}: completion changes original nontransparent RGBA pixels at source coordinates')
    measurement.update(input_sha256=_sha(data), offset=list(offset), size=list(replacement.size),
                       new_nontransparent_pixels=int(np.count_nonzero(np.asarray(replacement)[..., 3]))
                       - measurement['source_nontransparent_pixels'],
                       original_nontransparent_rgba_preserved=True)
    return replacement, offset, measurement


def install_garment_ownership(source_rig, destination_rig, garment_path, *, ownership,
                              garment_offset=None, garment_front_image=None,
                              aperture_backing_image=None, completed_legs=None):
    """Publish a fresh experimental rig, preserving a complete immutable snapshot.

    Without garment_offset, artwork must exactly match the torso image size and
    uses its original offset. An explicit integer garment_offset permits a new
    registered extent (e.g. a wider padded hem), wholly inside source.png. Torso
    and optional torso_front must share geometry and registration. By default
    both use the full garment; garment_front_image can provide the explicit
    front/collar partition at that same size and offset. aperture_backing_image
    optionally adds garment_backing immediately before the legs, using the
    torso's unchanged mesh and replacement registration. Every supplied image
    must be nonempty RGBA. No aperture or collar is inferred automatically.

    completed_legs maps leg_near/leg_far to {'image': path, 'offset': [x, y]}.
    Original nontransparent RGBA bytes must remain at identical source positions,
    including alpha=1 antialiasing. Only originally transparent positions may be
    painted. Expansion must retain the whole old rectangle, even transparent
    margins. Geometry is unchanged; only image paths/registered offsets change.

    All validation, image decoding/compositing, hashing and JSON serialization
    precede filesystem writes. Prior specs, assets, reports, and approvals live
    in history, not as current validation. This does not approve semantics,
    appearance, registration, motion, or the source identity of the new garment.
    """
    source = Path(source_rig).resolve()
    requested_destination = Path(destination_rig)
    destination = requested_destination.resolve()
    if ownership != 'continuous_garment':
        raise ValueError('ownership must explicitly be continuous_garment')
    if (requested_destination.is_symlink() or destination.exists()
            or destination.is_relative_to(source) or source.is_relative_to(destination)):
        raise ValueError('destination must be fresh and neither rig may contain the other')
    if not source.is_dir():
        raise ValueError('source rig must be an existing directory')
    snapshot = _snapshot(source)
    if any(path == HISTORY or path.startswith(HISTORY + '/') or HISTORY.startswith(path + '/') for path in snapshot):
        raise ValueError('reserved continuous garment history already exists')
    reserved = {GARMENT, GARMENT_FRONT, GARMENT_BACKING}
    reserved.update(f'layers/completed_{name}.png' for name in ('leg_near', 'leg_far'))
    if any(path == new or path.startswith(new + '/') or new.startswith(path + '/')
           for path in snapshot for new in reserved):
        raise ValueError('reserved derived artwork already exists')
    spec = _json(snapshot['character.json'], 'character.json')
    _json(snapshot['provenance.json'], 'provenance.json')
    puppet = spec.get('puppet')
    if not isinstance(puppet, dict) or not isinstance(puppet.get('layers'), dict):
        raise ValueError('source rig requires puppet.layers')
    if puppet.get('source') != 'source.png':
        raise ValueError('canonical source rig must reference source.png')
    layers = puppet['layers']
    if 'garment_backing' in layers:
        raise ValueError('garment_backing is reserved for this derived ownership policy')
    order = _layer_order(layers)
    reference = _rgba(snapshot['source.png'], 'source reference')
    originals, offsets, asset_paths = {}, {}, set()
    for name, row in layers.items():
        if not isinstance(row, dict):
            raise ValueError(f'{name}: layer must be an object')
        path = _relative(row.get('image'))
        if path.split('/')[0] == 'history' or path in ('character.json', 'source.png', 'provenance.json', 'garment_ownership.json'):
            raise ValueError(f'{name}: image path conflicts with reserved rig metadata/history')
        if path not in snapshot:
            raise ValueError(f'{name}: image must be a file inside source rig')
        offsets[name] = _offset(row.get('offset'), name)
        originals[name] = _rgba(snapshot[path], name)
        _inside(originals[name], offsets[name], reference.size, name)
        asset_paths.add(path)
    if layers['torso'].get('kind') != 'tube' or not all(k in layers['torso'] for k in ('bones', 'rest')):
        raise ValueError('torso must have explicit known-joint tube geometry')
    if 'torso_front' in layers:
        geometry = lambda row: {k: v for k, v in row.items() if k != 'image'}
        if (geometry(layers['torso_front']) != geometry(layers['torso'])
                or originals['torso_front'].size != originals['torso'].size):
            raise ValueError('torso_front must share exact torso geometry and registration')
    garment_data = Path(garment_path).read_bytes()
    garment = _rgba(garment_data, 'garment')
    if garment_offset is None:
        if garment.size != originals['torso'].size:
            raise ValueError('garment size must match torso unless garment_offset explicitly registers a new extent')
        garment_offset = offsets['torso']
    else:
        garment_offset = _offset(garment_offset, 'garment')
    _inside(garment, garment_offset, reference.size, 'garment')
    if not np.any(np.asarray(garment)[..., 3]):
        raise ValueError('garment must not be empty')
    if completed_legs is None:
        completed_legs = {}
    if not isinstance(completed_legs, Mapping) or set(completed_legs) - {'leg_near', 'leg_far'}:
        raise ValueError('completed_legs may name only leg_near and leg_far')
    replacements = {name: garment for name in ('torso', 'torso_front') if name in layers}
    replacement_offsets = {name: garment_offset for name in replacements}
    replacement_paths = {name: GARMENT for name in replacements}
    extra_art = {}
    for name, supplied, target in (('torso_front', garment_front_image, GARMENT_FRONT),
                                    ('garment_backing', aperture_backing_image, GARMENT_BACKING)):
        if supplied is None:
            continue
        if name == 'torso_front' and name not in layers:
            raise ValueError('garment_front_image requires an existing torso_front layer')
        data = Path(supplied).read_bytes()
        image = _rgba(data, name)
        if image.size != garment.size:
            raise ValueError(f'{name}: dimensions must match registered garment exactly')
        if not np.any(np.asarray(image)[..., 3]):
            raise ValueError(f'{name}: image must not be empty')
        replacements[name], replacement_offsets[name], replacement_paths[name] = image, garment_offset, target
        extra_art[name] = dict(input_sha256=_sha(data), size=list(image.size),
                               offset=list(garment_offset), semantic_visual_approval='pending')
    if aperture_backing_image is not None:
        order.insert(min(order.index(name) for name in ('leg_far', 'leg_near')), 'garment_backing')
    completions = {}
    for name, descriptor in completed_legs.items():
        image, offset, measurement = _completed_leg(name, descriptor, originals[name], offsets[name], reference.size)
        replacements[name], replacement_offsets[name] = image, offset
        replacement_paths[name] = f'layers/completed_{name}.png'
        measurement['source_image_sha256'] = _sha(snapshot[layers[name]['image']])
        measurement['original_offset'] = list(offsets[name])
        completions[name] = measurement
    result = copy.deepcopy(spec)
    if aperture_backing_image is not None:
        result['puppet']['layers']['garment_backing'] = copy.deepcopy(layers['torso'])
    result_layers = result['puppet']['layers'] = {name: result['puppet']['layers'][name] for name in order}
    composed = Image.new('RGBA', reference.size)
    for name, row in result_layers.items():
        if name in replacements:
            row['image'] = replacement_paths[name]
            row['offset'] = list(replacement_offsets[name])
        image = replacements[name] if name in replacements else originals[name]
        composed.alpha_composite(image, tuple(row['offset']))

    # Only known layer assets remain alongside the new runtime spec. Every other
    # source file (including unknown reports/previews) is retained in the snapshot
    # rather than accidentally continuing an obsolete approval or bind report.
    output = {path: snapshot[path] for path in asset_paths}
    output.update({path: _png(replacements[name]) for name, path in replacement_paths.items()})
    output['source.png'] = _png(composed)
    output['character.json'] = _encode(result)
    active_paths = {'character.json', 'source.png'} | {row['image'] for row in result_layers.values()}
    retention = _retention(originals['torso'], offsets['torso'], garment, garment_offset)
    report = {
        'schema_version': 1, 'method': 'explicit_registered_continuous_garment',
        'development_only': True, 'ownership': ownership,
        'source_rig_unchanged': True, 'automatic_segmentation': False,
        'garment_source_identity_claimed': False, 'source_rgb_unchanged_claimed': False,
        'source_character_sha256': _sha(snapshot['character.json']),
        'original_reference_sha256': _sha(snapshot['source.png']),
        'derived_reference_sha256': _sha(output['source.png']),
        'registered_garment': dict(input_sha256=_sha(garment_data),
                                   output_sha256=_sha(output[GARMENT]),
                                   size=list(garment.size), offset=list(garment_offset),
                                   source_torso_sha256=_sha(snapshot[layers['torso']['image']]),
                                   original_size=list(originals['torso'].size),
                                   original_offset=list(offsets['torso']),
                                   **retention),
        'completed_legs': completions,
        'additional_registered_artwork': extra_art,
        'torso_front_policy': ('supplied_registered_partition' if garment_front_image is not None
                               else 'duplicate_supplied_garment' if 'torso_front' in layers else 'absent'),
        'added_active_layers': [name for name in order if name not in layers],
        'removed_active_layers': [name for name in layers if name not in order],
        'source_layer_order': list(layers), 'derived_layer_order': order,
        'history': HISTORY,
        'source_snapshot_sha256': {path: _sha(data) for path, data in snapshot.items()},
        'archived_source_files': sorted(set(snapshot) - asset_paths),
        'inactive_original_assets': sorted(asset_paths - active_paths),
        'bind_approval': 'pending', 'semantic_visual_approval': 'pending',
        'registration_visual_approval': 'pending', 'motion_contact_approval': 'pending',
        'user_motion_approval': 'pending', 'final_visual_pass': False,
    }
    for name, row in completions.items():
        row['output_sha256'] = _sha(output[replacement_paths[name]])
    for name, row in extra_art.items():
        row['output_sha256'] = _sha(output[replacement_paths[name]])
    output['garment_ownership.json'] = _encode(report)
    provenance = {
        'derived_garment_ownership': report,
        'previous_provenance': HISTORY + '/provenance.json',
        'bind_approval': 'pending', 'semantic_verification': 'pending',
        'registration_visual_approval': 'pending', 'motion_contact_approval': 'pending',
        'user_motion_approval': 'pending', 'final_visual_pass': False,
        'source_assets': {name: _sha(output[row['image']]) for name, row in result_layers.items()},
        'runtime_assets': {path: _sha(output[path]) for path in sorted(active_paths)},
    }
    output['provenance.json'] = _encode(provenance)
    output.update({HISTORY + '/' + path: data for path, data in snapshot.items()})
    publish = _atomic_publisher()
    # No source paths, reports, pixels, or JSON remain to validate after this point.
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.garment-ownership-', dir=destination.parent))
    try:
        for relative, data in output.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        # Recheck immediately before publication so an existing destination is not
        # replaced. rename keeps a completed rig invisible until publication.
        if destination.exists() or destination.is_symlink():
            raise FileExistsError('destination appeared during preparation; refusing replacement')
        publish(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination / 'character.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_rig')
    parser.add_argument('destination_rig')
    parser.add_argument('garment_path')
    parser.add_argument('--ownership', required=True, choices=['continuous_garment'])
    parser.add_argument('--garment-offset', nargs=2, type=int, metavar=('X', 'Y'))
    parser.add_argument('--garment-front-image', type=Path)
    parser.add_argument('--aperture-backing-image', type=Path)
    parser.add_argument('--completed-legs', type=Path,
                        help='JSON mapping leg names to image paths (relative to this JSON) and offsets')
    args = parser.parse_args()
    completions = None
    if args.completed_legs:
        completions = _json(args.completed_legs.read_bytes(), 'completed legs')
        for descriptor in completions.values():
            if isinstance(descriptor, dict) and isinstance(descriptor.get('image'), str):
                descriptor['image'] = args.completed_legs.parent / descriptor['image']
    print(install_garment_ownership(args.source_rig, args.destination_rig, args.garment_path,
                                   ownership=args.ownership, garment_offset=args.garment_offset,
                                   garment_front_image=args.garment_front_image,
                                   aperture_backing_image=args.aperture_backing_image,
                                   completed_legs=completions))


if __name__ == '__main__':
    main()
