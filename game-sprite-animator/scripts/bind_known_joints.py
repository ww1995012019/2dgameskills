#!/usr/bin/env python3
"""Bind complete aligned RGBA layers using reusable measured joints, without AI calls.

Manifest: {"name": "hero", "layers": {"head": "layers/head.png", ...},
"joints": {"arm_near": {"shoulder": [x,y], "elbow": [x,y], "wrist": [x,y]}, ...},
"order": [back-to-front layer names]}. All images share one canvas and coordinate system.
This numerical entry does not assert semantic review or user approval.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np
from PIL import Image
import layer_parts as lp
from known_joint_rig import build_spec

REQUIRED = {'head', 'torso', 'hips', 'arm_near', 'arm_far', 'leg_near', 'leg_far'}
JOINTS = {'head': ('head_base',), 'hips': ('hip', 'waist'),
          'arm_near': ('shoulder', 'elbow', 'wrist'),
          'arm_far': ('shoulder', 'elbow', 'wrist'),
          'leg_near': ('hip', 'knee', 'ankle'), 'leg_far': ('hip', 'knee', 'ankle'),
          'weapon': ('grip',)}
GRIP_SHARE = 0.02   # of the near arm's length: grip-to-art tolerance, as check_limb's bone support
GRIP_MIN_PX = 2.0   # never tighter than the former fixed tolerance


def grip_tolerance(arm):
    """Pixels a measured grip may sit from the hand/weapon art: a share of the near arm's length."""
    length = sum(float(np.linalg.norm(np.subtract(arm[b], arm[a])))
                 for a, b in (('shoulder', 'elbow'), ('elbow', 'wrist')))
    return max(GRIP_MIN_PX, GRIP_SHARE * length)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(manifest, destination):
    manifest = Path(manifest).resolve()
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('destination exists; preserve the previous rig and choose a new version')
    job = json.loads(manifest.read_text(encoding='utf-8'))
    names = set(job['layers'])
    if not REQUIRED <= names or names - REQUIRED - {'weapon'}:
        raise ValueError('layers must contain the seven humanoid parts and optionally weapon')
    order = job['order']
    if len(order) != len(names) or set(order) != names:
        raise ValueError('order must contain each layer exactly once')
    paths = {n: (manifest.parent / (p['image'] if isinstance(p, dict) else p)).resolve()
             for n, p in job['layers'].items()}
    images = {}
    for name, path in paths.items():
        with Image.open(path) as im:
            if im.mode == 'RGBA':
                images[name] = im.copy()
            elif im.mode in ('LA', 'PA') or (im.mode == 'P' and 'transparency' in im.info):
                # Alpha-carrying palette/grey PNGs convert to RGBA without changing any pixel.
                images[name] = im.convert('RGBA')
            else:
                raise ValueError(f'{name}: supply a layer with an alpha channel and transparent background')
        alpha = np.asarray(images[name])[..., 3]
        if not (alpha > 128).any():
            raise ValueError(f'{name}: empty layer')
    if 'canvas' in job:
        canvas = job['canvas']
        if (not isinstance(canvas, list) or len(canvas) != 2 or
                any(type(v) is not int or v <= 0 for v in canvas)):
            raise ValueError('canvas must contain two positive integer dimensions')
        for name, image in list(images.items()):
            descriptor = job['layers'][name]
            offset = descriptor.get('offset', [0, 0]) if isinstance(descriptor, dict) else [0, 0]
            if (not isinstance(offset, list) or len(offset) != 2 or
                    any(type(v) is not int or v < 0 for v in offset)):
                raise ValueError(f'{name}: offset must contain two nonnegative integers')
            x, y = offset
            if x + image.width > canvas[0] or y + image.height > canvas[1]:
                raise ValueError(f'{name}: canvas would clip source pixels; increase canvas or fix offset')
            aligned = Image.new('RGBA', tuple(canvas))
            aligned.paste(image, (x, y))
            images[name] = aligned
    elif any(isinstance(p, dict) and p.get('offset', [0, 0]) != [0, 0]
             for p in job['layers'].values()):
        raise ValueError('cropped layers with offsets require canvas dimensions')
    if len({im.size for im in images.values()}) != 1:
        raise ValueError('all layers must share the same canvas; pad/correct metadata, do not redraw')
    for name, image in images.items():
        if not (np.asarray(image)[..., 3] == 0).any():
            raise ValueError(f'{name}: missing transparent background')
    width, height = next(iter(images.values())).size
    for name, keys in JOINTS.items():
        if name not in names:
            continue
        for key in keys:
            point = np.asarray(job['joints'].get(name, {}).get(key, []), dtype=float)
            if point.shape != (2,) or not np.isfinite(point).all():
                raise ValueError(f'{name}.{key}: expected two finite coordinates')
            x, y = point
            if not (0 <= x < width and 0 <= y < height):
                raise ValueError(f'{name}.{key}: joint is outside the canvas')
    for a, b in ((job['joints']['hips']['hip'], job['joints']['hips']['waist']),
                 (job['joints']['hips']['waist'], job['joints']['head']['head_base'])):
        if np.linalg.norm(np.subtract(a, b)) < 1:
            raise ValueError('spine joints must be distinct')
    if 'weapon' in images:
        grip = np.asarray(job['joints']['weapon']['grip'], dtype=float)
        tolerance = grip_tolerance(job['joints']['arm_near'])
        for name in ('arm_near', 'weapon'):
            ys, xs = np.nonzero(np.asarray(images[name])[..., 3] > 128)
            if np.min((xs-grip[0])**2 + (ys-grip[1])**2) > tolerance ** 2:
                raise ValueError(f'{name}: measured grip misses the artwork; correct the joint/contact')
    spec, metrics = build_spec(images, job['joints'], order)
    arrays = {n: np.asarray(images[n]) for n in order}
    reference = Image.new('RGBA', (width, height))
    for name in order:
        reference.alpha_composite(images[name])
    source_hashes = {n: digest(p) for n, p in paths.items()}
    state = dict(layers=arrays, binding_method='known_joints',
                 joint_chains={n: d.get('rest', []) for n, d in spec['puppet']['layers'].items()
                               if d['kind'] == 'tube'},
                 semantic_verification='pending', final_visual_pass=False,
                 source_assets=source_hashes, manifest_sha256=digest(manifest))
    metrics['reference_kind'] = 'assembled supplied layers; semantic review pending'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.rig-', dir=destination.parent) as tmp:
        lp.write_binding(tmp, job.get('name', 'character'), np.asarray(reference), arrays, spec, metrics, state)
        provenance = dict(manifest_sha256=digest(manifest), source_assets=source_hashes,
                          image_generation_calls=0, final_visual_pass=False, user_motion_approval='pending')
        Path(tmp, 'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
        shutil.copy2(manifest, Path(tmp, 'input_manifest.json'))
        Path(tmp).rename(destination)
    print(f'[rig] exported {destination}; image generation calls: 0; visual approval pending')
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        bind(args.manifest, args.out)
    except (ValueError, KeyError, OSError, lp.Rejected) as error:
        message = str(error).split(';')[0]
        parser.exit(2, f'Binding blocked: {message}\nCheck joints, alignment and layer completeness before requesting new art. Known joints do not require hand-hint images.\n')


if __name__ == '__main__':
    main()
