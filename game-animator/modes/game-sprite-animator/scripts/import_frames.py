#!/usr/bin/env python3
"""Import an already drawn frame sheet into the standard sprite export format.

This does not bind art to a skeleton or certify anatomy, contacts or visual
quality. Use it when the complete character and prop are painted in each frame.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image

from generate import SKILL_ROOT, export_engine_files
from layer_parts import Rejected, find_basic_job
from sprite_anim import export


def name_arg(value):
    if not re.fullmatch(r'[\w-]{1,64}', value, flags=re.UNICODE):
        raise argparse.ArgumentTypeError('use 1–64 letters, numbers, underscores or hyphens')
    return value


def grid_frames(sheet, columns, rows, count, pad=0):
    if columns < 1 or rows < 1 or columns * rows > 4096:
        raise ValueError('grid must contain between 1 and 4096 cells')
    if count < 2 or count > columns * rows:
        raise ValueError('frame count must be at least 2 and no larger than the grid')
    if sheet.width % columns or sheet.height % rows:
        raise ValueError('sheet dimensions must be divisible by its grid')
    width, height = sheet.width // columns, sheet.height // rows
    if width != height or not 1 <= width + 2 * pad <= export.MAX_PAGE:
        raise ValueError('each frame must be square and fit within an atlas page')
    if sheet.mode != 'RGBA' and 'transparency' not in sheet.info:
        raise ValueError('the source sheet needs a transparency channel')
    sheet = sheet.convert('RGBA')
    frames = []
    for index in range(count):
        x, y = (index % columns) * width, (index // columns) * height
        frame = sheet.crop((x, y, x + width, y + height))
        alpha = frame.getchannel('A')
        if not alpha.getbbox() or alpha.getextrema()[0] == 255:
            raise ValueError(f'frame {index} is empty or has no transparent background')
        # Very faint compression/transparency noise can reach a cell edge. Do
        # not erase those pixels: require padding and reject any visibly opaque
        # shape touching the edge, so padding cannot conceal a cropped sprite.
        box = alpha.point(lambda value: 255 if value >= 16 else 0).getbbox()
        if not box or box[0] == 0 or box[1] == 0 or box[2] == width or box[3] == height:
            raise ValueError(f'frame {index} touches a cell edge and may be cropped')
        raw_box = alpha.getbbox()
        if not pad and (raw_box[0] == 0 or raw_box[1] == 0 or raw_box[2] == width or raw_box[3] == height):
            raise ValueError(f'frame {index} has edge transparency noise; add transparent --pad')
        if pad:
            padded = Image.new('RGBA', (width + 2 * pad, height + 2 * pad), (0, 0, 0, 0))
            padded.paste(frame, (pad, pad))
            frame = padded
        frames.append(np.asarray(frame, dtype=np.uint8).copy())
    return frames, width


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sheet', required=True, type=Path)
    ap.add_argument('--columns', required=True, type=int)
    ap.add_argument('--rows', required=True, type=int)
    ap.add_argument('--count', required=True, type=int)
    ap.add_argument('--fps', required=True, type=float)
    ap.add_argument('--clip', type=name_arg, default='skateboard')
    ap.add_argument('--name', type=name_arg, default='character')
    ap.add_argument('--pivot', help='ground anchor x,y in frame pixels; defaults to bottom center')
    ap.add_argument('--pad', type=int, default=0, help='transparent pixels to add around each source cell')
    ap.add_argument('--once', action='store_true', help='play once rather than loop')
    ap.add_argument('--out', required=True, type=Path, help='new output directory')
    a = ap.parse_args(argv)
    if not math.isfinite(a.fps) or not 0 < a.fps <= 240:
        ap.error('fps must be greater than 0 and at most 240')
    if not 0 <= a.pad <= 64:
        ap.error('pad must be between 0 and 64 pixels')
    try:
        if find_basic_job(a.sheet):
            raise ValueError('basic workflow assets must go through their owning reviewed job, not frame import')
        raw = a.sheet.read_bytes()
        with Image.open(a.sheet) as sheet:
            frames, source_size = grid_frames(sheet, a.columns, a.rows, a.count, a.pad)
        if a.pivot is None:
            pivot = (source_size // 2, source_size)
        else:
            pieces = a.pivot.split(',')
            if len(pieces) != 2:
                raise ValueError('pivot must be x,y in frame pixels')
            pivot = tuple(int(v) for v in pieces)
            if not all(0 <= value <= source_size for value in pivot):
                raise ValueError('pivot must lie within the frame')
        pivot = tuple(value + a.pad for value in pivot)
        size = source_size + 2 * a.pad
        a.out.mkdir(parents=True, exist_ok=False)
    except (ValueError, OSError, Rejected) as exc:
        ap.error(str(exc))

    for sub in ('engine/godot', 'engine/cocos', 'engine/web'):
        (a.out / sub).mkdir(parents=True)
    root = str(a.out)
    export.write_frames(root, a.clip, frames)
    sheets = {a.clip: export.write_sheet(root, a.clip, frames, size)}
    rendered = {a.clip: {'frames': frames}}
    duration = len(frames) / a.fps
    meta = {a.clip: dict(fps=a.fps, loop=not a.once, duration=duration,
                         source_duration=duration if not a.once else (len(frames) - 1) / a.fps,
                         speed_px_s=0, events=[], next=None, prev=None, chain_frame=None,
                         tags=['precomposed'])}
    sprites, refs, pages = export.build_atlas(root, rendered, size)
    export.texturepacker_json(root, sprites, refs, pages, size, pivot)
    doc = export.manifest(sprites, refs, pages, meta, size, pivot, a.name)
    doc['source'] = dict(kind='precomposed_frames', sha256=hashlib.sha256(raw).hexdigest(),
                         grid=[a.columns, a.rows], padding=a.pad, skeleton_binding=False)
    (a.out / 'animations.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding='utf-8')
    export_engine_files(root, doc, sheets, meta, SKILL_ROOT)
    export.preview_html(root, str(Path(SKILL_ROOT) / 'assets' / 'preview_template.html'),
                        str(Path(SKILL_ROOT) / 'assets' / 'engine' / 'web' / 'sprite-player.js'),
                        doc, None, a.name)
    print(f'[import] {a.count} frames @ {a.fps:g} fps; precomposed, no skeleton binding')
    print(f'[done] open {a.out / "preview.html"}')


if __name__ == '__main__':
    main()
