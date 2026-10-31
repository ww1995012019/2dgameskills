#!/usr/bin/env python3
"""Generate a side or top-down view from a shared character manifest.

The existing view generators remain authoritative; this resolves the manifest
to their current character format and runs the selected generator unchanged.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODES = {'side': 'game-sprite-animator', 'topdown': 'game-topdown-animator'}
SHARED_COLORS = {'skin', 'hair', 'pants', 'boots', 'ink', 'coat', 'trim'}
COLOR_MAP = {'side': {'coat': 'tunic', 'trim': 'accent'}, 'topdown': {}}


def merge(base, overlay):
    """Merge nested configuration objects without mutating either input."""
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_character(manifest_path, view):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or not isinstance(manifest.get('name'), str) or not manifest['name'].strip():
        raise ValueError('manifest needs a nonempty name')
    views = manifest.get('views')
    if not isinstance(views, dict) or view not in MODES or not isinstance(views.get(view), dict):
        raise ValueError(f'manifest has no {view!r} view')
    if 'body' in manifest and not isinstance(manifest['body'], dict):
        raise ValueError('body must be an object')
    palette = manifest.get('palette', {})
    if not isinstance(palette, dict) or set(palette) - SHARED_COLORS:
        raise ValueError(f'palette keys must be from {sorted(SHARED_COLORS)}')
    for key, color in palette.items():
        if (not isinstance(color, str) or len(color) != 7 or color[0] != '#' or
                any(c not in '0123456789abcdefABCDEF' for c in color[1:])):
            raise ValueError(f'invalid color for {key}: {color!r}')
    selected = views[view]
    base = selected.get('base')
    source_dir = manifest_path.parent
    spec = {}
    if base is not None:
        if not isinstance(base, str) or not base:
            raise ValueError('view base must be a path string')
        source = (source_dir / base).resolve()
        spec = json.loads(source.read_text(encoding='utf-8'))
        source_dir = source.parent
        if not isinstance(spec, dict):
            raise ValueError('view base must contain a JSON object')
    override = selected.get('overrides', {})
    if not isinstance(override, dict):
        raise ValueError('view overrides must be an object')
    colors = {COLOR_MAP[view].get(k, k): v for k, v in palette.items()}
    common = {'name': manifest['name'], 'colors': colors}
    if view == 'side' and 'body' in manifest:
        common['body'] = manifest['body']
    spec = merge(merge(spec, common), override)
    # A temporary resolved spec lives in the output directory. Preserve the
    # original base's image root for cut-out parts, including overridden parts.
    parts = spec.get('parts', {})
    if not isinstance(parts, dict):
        raise ValueError('parts must be an object')
    for part in parts.values():
        if isinstance(part, dict) and isinstance(part.get('image'), str):
            part['image'] = str((source_dir / part['image']).resolve())
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--view', required=True, choices=MODES)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--preset', default='hd', choices=('hd', 'hd60', 'hd512', 'pixel48', 'pixel', 'pixel96'))
    parser.add_argument('--size', type=int)
    parser.add_argument('--fps', type=int)
    parser.add_argument('--clips', default='all')
    args = parser.parse_args()
    try:
        spec = resolve_character(args.manifest, args.view)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    # Existing generators clear output subdirectories. Require a new directory
    # to prevent the convenience wrapper from overwriting an existing result.
    try:
        args.out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(f'output already exists: {args.out}')
    resolved = args.out.resolve() / 'character-resolved.json'
    resolved.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
    script = ROOT / 'modes' / MODES[args.view] / 'scripts/generate.py'
    command = [sys.executable, str(script), '--character', str(resolved), '--out', str(args.out.resolve()),
               '--preset', args.preset, '--clips', args.clips]
    for name in ('size', 'fps'):
        value = getattr(args, name)
        if value is not None:
            command.extend(['--' + name, str(value)])
    return subprocess.run(command).returncode


if __name__ == '__main__':
    sys.exit(main())
