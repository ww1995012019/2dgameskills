"""compare_clips.py: fixed-ground preview GIFs used before full verification."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'game-animator/modes/game-sprite-animator/scripts/compare_clips.py'
spec = importlib.util.spec_from_file_location('compare_clips', SCRIPT)
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)

SIZE, PIVOT = 64, (32, 56)


def write_build(folder, heights, fps=10, loose=True):
    """A one-clip build whose figure top sits at the given native heights above the ground."""
    folder.mkdir(parents=True)
    frames, regions = [], []
    for h in heights:
        im = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle((28, PIVOT[1] - h, 36, PIVOT[1] - 1), fill=(200, 40, 40, 255))
        frames.append(im)
    if loose:
        (folder / 'frames/run').mkdir(parents=True)
        for i, im in enumerate(frames):
            im.save(folder / f'frames/run/run_{i:03d}.png')
    atlas = Image.new('RGBA', (SIZE * len(frames), SIZE), (0, 0, 0, 0))
    for i, im in enumerate(frames):
        box = im.getbbox()
        atlas.paste(im.crop(box), (i * SIZE, 0))
        regions.append({'page': 0, 'x': i * SIZE, 'y': 0, 'w': box[2] - box[0], 'h': box[3] - box[1],
                        'ox': box[0], 'oy': box[1]})
    atlas.save(folder / 'atlas.png')
    doc = {'character': 't', 'frame_size': SIZE, 'pivot': list(PIVOT),
           'pages': [{'file': 'atlas.png', 'w': atlas.width, 'h': SIZE}], 'regions': regions,
           'clips': {'run': {'fps': fps, 'loop': True, 'frames': list(range(len(frames)))}}}
    (folder / 'animations.json').write_text(json.dumps(doc))


class CompareClips(unittest.TestCase):
    def test_side_by_side_gif_reports_bob_and_keeps_timing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Rejected version: one step drops by 6px. Repaired version: even 2px bob.
            write_build(tmp / 'old', [30, 30, 24, 30, 30, 30, 30], fps=7)
            write_build(tmp / 'new', [30, 31, 32, 31, 30, 31, 32, 31], fps=10, loose=False)
            compare.main([str(tmp / 'new'), '--before', str(tmp / 'old'), '--clips', 'run',
                          '--out', str(tmp / 'cmp'), '--scale', '2', '--cycles', '2'])
            report = json.loads((tmp / 'cmp/compare.json').read_text())['clips']['run']
            self.assertEqual(report['before']['head_top_range_px'], 6)
            self.assertEqual(report['before']['max_adjacent_head_step_px'], 6)
            self.assertEqual(report['after']['head_top_range_px'], 2)
            self.assertEqual(report['after']['frames'], 8)
            self.assertEqual(report['cycle_ms'], 800)
            with Image.open(tmp / 'cmp/run.gif') as gif:
                self.assertEqual(gif.n_frames, 16)                   # two loops of the new clip
                delays = []
                for i in range(gif.n_frames):
                    gif.seek(i)
                    delays.append(gif.info['duration'])
                gif.seek(0)
                first = gif.convert('RGB')
            self.assertEqual(sum(delays[:8]), sum(delays[8:]))
            # Both panels share one ground line at the same image row.
            half = (first.width - 4) // 2
            ground = [y for y in range(first.height) if first.getpixel((2, y)) == compare.GROUND[:3]]
            ground_new = [y for y in range(first.height)
                          if first.getpixel((half + 6, y)) == compare.GROUND[:3]]
            self.assertTrue(ground)
            self.assertEqual(ground, ground_new)
            self.assertTrue((tmp / 'cmp/run_phases.png').is_file())

    def test_phase_alignment_uses_cycle_fraction_not_frame_number(self):
        self.assertEqual([compare.phase_index(i, 22, 21) for i in (0, 11, 21)], [0, 10, 20])
        self.assertEqual([compare.phase_index(i, 8, 4) for i in range(8)], [0, 0, 1, 1, 2, 2, 3, 3])

    def test_durations_do_not_drift(self):
        delays = compare.durations(22, 30)
        self.assertEqual(sum(delays), 730)
        self.assertEqual(sum(delays[:11]), 370)
        self.assertTrue(all(d % 10 == 0 for d in delays))

    def test_missing_clip_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_build(Path(tmp) / 'b', [10, 11])
            with self.assertRaises(SystemExit) as ctx:
                compare.main([str(Path(tmp) / 'b'), '--clips', 'walk', '--out', str(Path(tmp) / 'o')])
            self.assertIn('no clip', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
