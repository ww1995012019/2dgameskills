"""Explicit registered garment partition for dev rigs; never detects apparel semantics."""
import copy
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _asset(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('hip image must be an asset inside source rig')
    return path


def install_pelvic_overlay(source_rig, destination_rig, mask_path, *, ownership, torso_under_pelvis=False):
    """Copy a rig and partition hips using an explicitly reviewed garment mask.

    The caller owns semantic review. This function checks registration and pixel
    conservation, not whether the selected pixels depict a garment. Mask values
    must be binary (0/1 or 0/255), including normalized grayscale arrays. Assigning
    each whole source pixel to exactly one layer preserves its original alpha,
    including antialiasing. Runtime deformation/contact still require review.
    """
    source = Path(source_rig).resolve()
    destination = Path(destination_rig).resolve()
    mask_path = Path(mask_path)
    if not isinstance(torso_under_pelvis, bool):
        raise ValueError('torso_under_pelvis must be an explicit boolean')
    if ownership != 'garment':
        raise ValueError('ownership must explicitly identify garment pixels')
    if destination.exists() or destination.is_relative_to(source):
        raise ValueError('destination must be a fresh rig copy outside the source')
    spec = json.loads((source / 'character.json').read_text())
    provenance = json.loads((source / 'provenance.json').read_text())
    layers = spec['puppet']['layers']
    if 'pelvis_front' in layers:
        raise ValueError('pelvic overlay already installed')
    required = {'hips', 'torso', 'leg_far', 'leg_near', 'arm_near'}
    if not required.issubset(layers):
        raise ValueError('missing required ownership layers')
    hips = layers['hips']
    if hips.get('kind') != 'rigid' or not all(k in hips for k in ('follow', 'anchor', 'offset')):
        raise ValueError('hips must have explicit rigid follow, anchor, and offset')
    order = [name for name in layers if name != 'hips']
    cover = 'torso_front' if 'torso_front' in layers else 'torso'
    if any(order.index(name) <= order.index(cover) for name in ('weapon', 'arm_near') if name in order):
        raise ValueError('invalid front order: garment cover must precede weapon and arm_near')
    if any(order.index(name) >= order.index(cover) for name in ('leg_far', 'leg_near')):
        raise ValueError('invalid front order: both legs must precede garment cover')
    if cover == 'torso_front' and order.index('torso_front') <= order.index('torso'):
        raise ValueError('invalid ownership: torso_front must follow torso')
    source_image = _asset(source, hips['image'])
    if any(row.get('image') == hips['image'] for name, row in layers.items() if name != 'hips'):
        raise ValueError('hip image is shared by another layer; ownership is ambiguous')
    with Image.open(source_image) as image:
        if image.mode != 'RGBA':
            raise ValueError('source hips image must be RGBA')
        rgba = np.array(image)
    with Image.open(mask_path) as image:
        if image.mode not in ('1', 'L', 'I', 'F', 'I;16'):
            raise ValueError('mask must be binary or normalized grayscale')
        mask = np.array(image)
    if mask.shape != rgba.shape[:2]:
        raise ValueError('mask dimensions must match the cropped hips image')
    values = np.unique(mask)
    if not (np.isin(values, (0, 1)).all() or np.isin(values, (0, 255)).all()):
        raise ValueError('mask must have binary values; soft masks duplicate source coverage')
    selected = mask > 0
    if not selected.any():
        raise ValueError('mask must not be empty')
    if np.any(selected & (rgba[..., 3] == 0)):
        raise ValueError('mask selects pixels outside source alpha')
    background, foreground = rgba.copy(), rgba.copy()
    background[selected, 3] = 0
    foreground[~selected, 3] = 0
    front = copy.deepcopy(hips)
    front['image'] = 'layers/pelvis_front.png'
    if (source / front['image']).exists() or (source / 'pelvic_mask.png').exists():
        raise ValueError('reserved pelvic overlay asset already exists')
    if torso_under_pelvis:
        # This opt-in policy moves only a recognized contiguous ownership block.
        # Unknown interleaving must be reviewed, never silently reordered.
        cluster_names = {'torso', 'head'} | ({'torso_front'} if 'torso_front' in layers else set())
        if not cluster_names.issubset(order):
            raise ValueError('torso_under_pelvis requires the complete head/torso cluster')
        indices = sorted(order.index(n) for n in cluster_names)
        cluster = order[indices[0]:indices[-1] + 1]
        if len(cluster) != len(cluster_names) or set(cluster) != cluster_names:
            raise ValueError('torso_under_pelvis rejects interleaved head/torso cluster')
        if 'torso_front' in cluster and cluster != ['torso', 'head', 'torso_front']:
            raise ValueError('torso_under_pelvis requires torso, head, torso_front ownership order')
        start = min(order.index(n) for n in ('leg_far', 'leg_near'))
        span = order[start:indices[-1] + 1]
        leg_order = order[start:start + 2]
        if set(leg_order) != {'leg_far', 'leg_near'} or span != leg_order + cluster:
            raise ValueError('torso_under_pelvis rejects unknown leg/torso interleaving')
        order = order[:start] + cluster + ['hips'] + leg_order + ['pelvis_front'] + order[indices[-1] + 1:]
    else:
        # Default preserves every non-hips layer's relative order.
        at = min(order.index(n) for n in ('leg_far', 'leg_near', 'torso'))
        order.insert(at, 'hips')
        order.insert(order.index(cover) + 1, 'pelvis_front')
    layers = dict(layers, pelvis_front=front)
    spec['puppet']['layers'] = {name: layers[name] for name in order}
    reference_path = source / 'source.png'
    if (source / 'original_reference.png').exists():
        raise ValueError('original_reference.png already exists; source history is ambiguous')
    with Image.open(reference_path) as reference:
        static_reference = Image.new('RGBA', reference.size)
    for name in order:
        row = layers[name]
        offset = row.get('offset')
        if not isinstance(offset, (list, tuple)) or len(offset) != 2 or any(
                not isinstance(v, (int, float)) or not np.isfinite(v) or int(v) != v for v in offset):
            raise ValueError(name + ': source offset must be an explicit integer pair')
        if name == 'hips':
            image = Image.fromarray(background)
        elif name == 'pelvis_front':
            image = Image.fromarray(foreground)
        else:
            with Image.open(_asset(source, row['image'])) as asset:
                image = asset.convert('RGBA')
        x, y = map(int, offset)
        if x < 0 or y < 0 or x + image.width > static_reference.width or y + image.height > static_reference.height:
            raise ValueError(name + ': static source reference would clip registered image')
        static_reference.alpha_composite(image, (x, y))
    report = {'method': 'explicit_registered_binary_garment_partition',
              'ownership': ownership, 'torso_under_pelvis': torso_under_pelvis, 'source_image_sha256': _hash(source_image),
              'original_reference_sha256': _hash(reference_path),
              'source_character_sha256': _hash(source / 'character.json'),
              'mask_sha256': _hash(mask_path), 'selected_pixels': int(selected.sum()),
              'source_rgb_unchanged': True, 'source_alpha_partitioned_without_duplication': True,
              'semantic_visual_approval': 'pending', 'motion_contact_approval': 'pending', 'filtered_boundary_visual_approval': 'pending',
              'source_space_partition_only': True, 'filtered_output_pixel_identity_claimed': False,
              'source_rig_unchanged': True}
    # All input/ownership checks precede any filesystem writes. Publish atomically.
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.pelvic-overlay-', dir=destination.parent))
    try:
        shutil.copytree(source, staging, dirs_exist_ok=True)
        shutil.copyfile(reference_path, staging / 'original_reference.png')
        static_reference.save(staging / 'source.png')
        report['derived_reference_sha256'] = _hash(staging / 'source.png')
        Image.fromarray(background).save(staging / hips['image'])
        (staging / 'layers').mkdir(exist_ok=True)
        Image.fromarray(foreground).save(staging / front['image'])
        shutil.copyfile(mask_path, staging / 'pelvic_mask.png')
        report['background_sha256'] = _hash(staging / hips['image'])
        report['foreground_sha256'] = _hash(staging / front['image'])
        (staging / 'character.json').write_text(json.dumps(spec, indent=2) + '\n')
        (staging / 'pelvic_overlay.json').write_text(json.dumps(report, indent=2) + '\n')
        provenance['derived_pelvic_overlay'] = report
        provenance['final_visual_pass'] = False
        provenance['user_motion_approval'] = 'pending'
        provenance['runtime_assets'] = {str(p.relative_to(staging)): _hash(p)
                                        for p in staging.rglob('*')
                                        if p.is_file() and p.name != 'provenance.json'}
        (staging / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination / 'character.json'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_rig')
    parser.add_argument('destination_rig')
    parser.add_argument('mask_path')
    parser.add_argument('--torso-under-pelvis', action='store_true')
    parser.add_argument('--ownership', required=True, choices=['garment'])
    args = parser.parse_args()
    print(install_pelvic_overlay(args.source_rig, args.destination_rig,
                                 args.mask_path, ownership=args.ownership,
                                 torso_under_pelvis=args.torso_under_pelvis))
