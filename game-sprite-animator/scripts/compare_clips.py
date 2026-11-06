#!/usr/bin/env python3
"""Fast motion preview for the user: fixed-ground looping GIFs, optionally old vs new side by side.

    python scripts/compare_clips.py out/new --clips idle,run --out out/compare
    python scripts/compare_clips.py out/new --before out/old --clips run --out out/compare

Use this right after a repair, BEFORE the full test suite, regression and publishing. Render only
the affected clips of the affected characters, send `<clip>.gif` to the user and wait for their
verdict. Both builds are drawn at the same world scale on one fixed ground line, with a dashed line
at the highest head position so vertical bob and limping are visible. Frame counts may differ, so
the old clip is sampled at the same cycle phase as each new frame, never by frame number.

Outputs per clip: `<clip>.gif` (plays at the clip's fps, `--cycles` loops per GIF period),
`<clip>_phases.png` (eight evenly spaced phases, old row above new row) and `compare.json`
(frame counts, fps and native head-top range). The head-top range is a measurement, not a
naturalness verdict; the user's look at the moving GIF is the gate.
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

BACKGROUND = (236, 240, 244, 255)
GROUND = (90, 98, 110, 255)
HEAD_LINE = (214, 72, 72, 255)
TEXT = (40, 44, 52, 255)
LABEL_H = 18
MARGIN = 8


def load(path):
    with Image.open(path) as image:
        return image.convert('RGBA')


class Build:
    """Frames of one exported build, read from frames/<clip>/ or rebuilt from the atlas."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.doc = json.loads((self.folder / 'animations.json').read_text(encoding='utf-8'))
        self.size = int(self.doc['frame_size'])
        self.pivot = tuple(int(v) for v in self.doc['pivot'])
        self._pages = None

    def fps(self, clip):
        return float(self.clip(clip)['fps'])

    def clip(self, clip):
        clips = self.doc['clips']
        if clip not in clips:
            raise SystemExit(f'{self.folder}: no clip {clip!r} (has {", ".join(sorted(clips))})')
        return clips[clip]

    def frames(self, clip):
        loose = sorted((self.folder / 'frames' / clip).glob('*.png'))
        if loose:
            return [load(p) for p in loose]
        if self._pages is None:
            self._pages = [load(self.folder / p['file']) for p in self.doc['pages']]
        out = []
        for index in self.clip(clip)['frames']:
            r = self.doc['regions'][index]
            frame = Image.new('RGBA', (self.size, self.size), (0, 0, 0, 0))
            if r['w'] and r['h']:
                piece = self._pages[r['page']].crop((r['x'], r['y'], r['x'] + r['w'], r['y'] + r['h']))
                frame.paste(piece, (r['ox'], r['oy']))
            out.append(frame)
        return out


def head_top(frame):
    """Topmost opaque row in native pixels, or None for an empty frame."""
    box = frame.getchannel('A').point(lambda a: 255 if a > 24 else 0).getbbox()
    return None if box is None else box[1]


def window(builds):
    """Union of opaque bounds in pivot-relative coordinates, so both builds share one scale."""
    left = top = 10 ** 9
    right = bottom = -10 ** 9
    for build, frames in builds:
        px, py = build.pivot
        for frame in frames:
            box = frame.getchannel('A').getbbox()
            if box:
                left, top = min(left, box[0] - px), min(top, box[1] - py)
                right, bottom = max(right, box[2] - px), max(bottom, box[3] - py)
    if right < left:
        raise SystemExit('every frame is empty')
    bottom = max(bottom, 1)
    return left - MARGIN, top - MARGIN, right + MARGIN, bottom + MARGIN


def panel(frame, build, view, scale, label, head_y):
    left, top, right, bottom = view
    px, py = build.pivot
    crop = frame.crop((px + left, py + top, px + right, py + bottom))
    width, height = (right - left) * scale, (bottom - top) * scale
    canvas = Image.new('RGBA', (width, height + LABEL_H), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    ground = (0 - top) * scale + LABEL_H
    draw.line([(0, ground), (width, ground)], fill=GROUND, width=max(1, scale))
    if head_y is not None:
        y = (head_y - py - top) * scale + LABEL_H
        for x in range(0, width, 8):
            draw.line([(x, y), (min(x + 4, width), y)], fill=HEAD_LINE, width=1)
    canvas.alpha_composite(crop.resize((width, height), Image.NEAREST), (0, LABEL_H))
    draw.text((4, 3), label, fill=TEXT)
    return canvas


def durations(count, fps):
    """GIF delays in whole centiseconds without drift, so both half-cycles keep equal length."""
    return [(round((i + 1) * 100 / fps) - round(i * 100 / fps)) * 10 for i in range(count)]


def phase_index(i, count, other):
    return int(i * other / count) % other


def compare_clip(clip, after, before, out, scale, cycles):
    new = after.frames(clip)
    old = before.frames(clip) if before else None
    if not new:
        raise SystemExit(f'{after.folder}: clip {clip!r} has no frames')
    view = window([(after, new)] + ([(before, old)] if old else []))
    tops_new = [t for t in map(head_top, new) if t is not None]
    tops_old = [t for t in map(head_top, old) if t is not None] if old else []
    gif = []
    for i, frame in enumerate(new):
        panels = []
        if old:
            j = phase_index(i, len(new), len(old))
            panels.append(panel(old[j], before, view, scale, f'before {j + 1}/{len(old)}',
                                min(tops_old) if tops_old else None))
        panels.append(panel(frame, after, view, scale, f'{"after " if old else ""}{i + 1}/{len(new)}',
                            min(tops_new) if tops_new else None))
        sheet = Image.new('RGBA', (sum(p.width for p in panels) + 4 * (len(panels) - 1), panels[0].height),
                          (255, 255, 255, 255))
        x = 0
        for p in panels:
            sheet.paste(p, (x, 0))
            x += p.width + 4
        gif.append(sheet.convert('RGB'))
    delays = durations(len(new), after.fps(clip))
    looped = gif * cycles
    looped[0].save(out / f'{clip}.gif', save_all=True, append_images=looped[1:],
                   duration=delays * cycles, loop=0, disposal=1)
    phases = [int(k * len(new) / 8) for k in range(8)] if len(new) >= 8 else list(range(len(new)))
    rows = []
    for name, frames, build, tops in ([('before ', old, before, tops_old)] if old else []) + \
            [('after ' if old else '', new, after, tops_new)]:
        row = []
        for i in phases:
            k = phase_index(i, len(new), len(frames))
            row.append(panel(frames[k], build, view, scale, f'{name}{k + 1}/{len(frames)}',
                             min(tops) if tops else None))
        rows.append(row)
    pw, ph = rows[0][0].size
    strip = Image.new('RGB', (pw * len(phases) + 4 * (len(phases) - 1), ph * len(rows) + 4 * (len(rows) - 1)),
                      (255, 255, 255))
    for r, row in enumerate(rows):
        for c, p in enumerate(row):
            strip.paste(p.convert('RGB'), (c * (pw + 4), r * (ph + 4)))
    strip.save(out / f'{clip}_phases.png')

    def summary(build, frames, tops):
        return {'frames': len(frames), 'fps': build.fps(clip),
                'head_top_range_px': (max(tops) - min(tops)) if tops else None,
                'max_adjacent_head_step_px': max((abs(a - b) for a, b in zip(tops, tops[1:] + tops[:1])),
                                                 default=None) if tops else None}
    row = {'after': summary(after, new, tops_new), 'cycle_ms': sum(delays)}
    if old:
        row['before'] = summary(before, old, tops_old)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('after', type=Path, help='build folder to show (the repaired output)')
    parser.add_argument('--before', type=Path, help='earlier build to show on the left, e.g. the rejected version')
    parser.add_argument('--clips', required=True, help='comma list, e.g. idle,run')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scale', type=int, default=2, help='integer zoom (nearest neighbour)')
    parser.add_argument('--cycles', type=int, default=2, help='loops stored per GIF period')
    args = parser.parse_args(argv)
    if args.scale < 1 or args.cycles < 1:
        parser.error('--scale and --cycles must be at least 1')
    after = Build(args.after)
    before = Build(args.before) if args.before else None
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'after': str(args.after), 'before': str(args.before) if before else None, 'clips': {}}
    for clip in [c.strip() for c in args.clips.split(',') if c.strip()]:
        report['clips'][clip] = compare_clip(clip, after, before, args.out, args.scale, args.cycles)
        print(f'[compare] {clip}: {args.out / (clip + ".gif")}')
    (args.out / 'compare.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Send the GIFs to the user and wait for their verdict before full verification or publishing.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
