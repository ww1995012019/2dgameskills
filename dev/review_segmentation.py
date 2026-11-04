#!/usr/bin/env python3
"""Export existing local binary masks to a source-coordinate, static web review.

No inference, image generation, upload, anatomy inference, or rig export occurs.
Selection JSON: [{"name": ..., "mask": path relative to selection JSON,
"model_score": 0.9, "notes": "visible region only"}]. Scores are estimates only.
"""
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


def export(source, selection, out):
    source, selection, out = map(Path, (source, selection, out))
    rgb = np.array(Image.open(source).convert('RGB'))
    h, w = rgb.shape[:2]
    entries = json.loads(selection.read_text(encoding='utf-8'))
    if not isinstance(entries, list) or not entries:
        raise ValueError('select at least one local mask')
    masks = []
    for e in entries:
        score = e.get('model_score')
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError('model_score must be null or finite in [0,1]')
        path = (selection.parent / e['mask']).resolve()
        with Image.open(path) as image:
            if image.size != (w, h):
                raise ValueError('mask must preserve source canvas; resizing is forbidden')
            pixels = np.array(image.convert('L'))
        if not np.isin(pixels, [0, 255]).all():
            raise ValueError('mask must be binary 0/255, not an overlay or confidence map')
        mask = pixels == 255
        if not mask.any():
            raise ValueError('empty candidate mask')
        masks.append((e, path, mask))
    out.mkdir(parents=True, exist_ok=False)
    ownership = np.zeros((h, w), np.uint32)
    union = np.zeros((h, w), bool)
    layers = []
    packed = []
    for i, (e, path, mask) in enumerate(masks):
        name = str(e.get('name', f'Candidate {i+1}'))
        rgba = np.zeros((h, w, 4), np.uint8)
        rgba[mask, :3] = rgb[mask]
        rgba[mask, 3] = 255
        file = f'candidate-{i:02d}.png'
        Image.fromarray(rgba).save(out / file)
        maskfile = f'mask-{i:02d}.png'
        Image.fromarray(mask.astype(np.uint8)*255).save(out / maskfile)
        y, x = np.nonzero(mask)
        layer = dict(name=name, file=file, mask=maskfile, offset=[0, 0],
                     bounds=[int(x.min()), int(y.min()), int(x.max()+1), int(y.max()+1)],
                     pixels=int(mask.sum()), model_score=e.get('model_score'),
                     mask_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                     semantic_confidence='unverified', completeness='visible_fragment_only',
                     hidden_area_status='not_reconstructed', hidden_surface_pixels=0,
                     notes=str(e.get('notes', 'Needs semantic and boundary review.')))
        layers.append(layer)
        packed.append(dict(layer, uri=uri(out/file), mask_uri=uri(out/maskfile)))
        ownership += mask
        union |= mask
    composite = np.zeros((h, w, 4), np.uint8)
    composite[union, :3] = rgb[union]
    composite[union, 3] = 255
    Image.fromarray(composite).save(out/'visible-composite.png')
    Image.fromarray(rgb).save(out/'source.png')
    # This compares selected visible pixels, not a complete-character reconstruction.
    proof = dict(selected_pixels=int(union.sum()), selected_canvas_share=float(union.mean()),
                 overlap_pixels=int((ownership > 1).sum()), unselected_canvas_pixels=int((~union).sum()),
                 changed_selected_source_pixels=int(np.any(composite[union, :3] != rgb[union], axis=1).sum()),
                 hidden_surface_pixels=0, animation_frames=0)
    report = dict(schema='segmentation-review-v1', status='needs_semantic_review_not_bindable',
                  canvas=[w,h], source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  model_score_meaning='Model-estimated mask quality, not semantic confidence or completeness.',
                  binding_gate=dict(allowed=False, reasons=['Semantic ownership unverified.',
                      'Complete parts and hidden surfaces unavailable.', 'No joints or motion review.']),
                  layers=layers, proof=proof)
    (out/'review.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    payload = dict(report=report, layers=packed, source=uri(out/'source.png'))
    template = Path(__file__).with_name('segmentation_review.html').read_text(encoding='utf-8')
    # Escape HTML script terminators even when candidate names contain untrusted text.
    (out/'review.html').write_text(template.replace('__OWNERSHIP_LOGIC__', Path(__file__).with_name('segmentation_ownership.js').read_text(encoding='utf-8')).replace('__PAYLOAD__', json.dumps(payload).replace('<', '\\u003c')), encoding='utf-8')
    return report


def uri(path):
    return 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode('ascii')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source'); p.add_argument('selection'); p.add_argument('--out', required=True)
    a = p.parse_args()
    print(json.dumps(export(a.source, a.selection, a.out)['proof'], indent=2))
