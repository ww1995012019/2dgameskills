#!/usr/bin/env python3
"""Localize unchanged source-smear checks, without repairing or approving artwork."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'game-sprite-animator/scripts'))
from sprite_anim.puppet_check import smear_tile_report, TILE, SMEAR_RANGE, SMEAR_STEEP, SMEAR_SHARE


def review(paths, output):
    paths = [Path(p) for p in paths]
    if not paths or len({p.stem for p in paths}) != len(paths):
        raise ValueError('provide images with distinct layer names')
    # Refuse overwrite so review artifacts cannot silently change under a verdict.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(visual_approval='pending', coordinate_space='source layer pixels; half-open bounds',
                  thresholds=dict(tile=TILE, span=SMEAR_RANGE, step_share=SMEAR_STEEP,
                                  failed_tile_share=SMEAR_SHARE), layers=[])
    for path in paths:
        with Image.open(path) as source:
            im = source.convert('RGBA')
        evidence = smear_tile_report(im)
        evidence.update(name=path.stem, source=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        size=list(im.size), status='FAIL' if evidence['filled'] and
                        evidence['bad']/evidence['filled'] > SMEAR_SHARE else 'PASS')
        marked = Image.new('RGBA', im.size, '#353b48')
        marked.alpha_composite(im)
        draw = ImageDraw.Draw(marked)
        for candidate in evidence['candidates']:
            x, y, right, bottom = candidate['bounds']
            draw.rectangle((x, y, right-1, bottom-1), outline='#ff3030', width=1)
        evidence['overlay'] = path.stem + '.png'
        marked.convert('RGB').save(output / evidence['overlay'])
        report['layers'].append(evidence)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = review(args.images, args.out)
    for layer in result['layers']:
        print(f"{layer['name']}: {layer['status']}, {layer['bad']}/{layer['filled']} tiles")
    print('Visual approval pending; this report does not override QA.')
