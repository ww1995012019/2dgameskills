"""Skateboard support and precomposed clip exports keep their evidence distinct."""
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'game-animator/modes/game-sprite-animator/scripts'
sys.path.insert(0, str(SCRIPTS))

from qa_motion import skateboard_contact
from sprite_anim.motions import build_clips
from sprite_anim.render import Renderer
from sprite_anim.rig import Body, heel_world, solve, toe_world


class SkateboardTests(unittest.TestCase):
    def test_opt_in_and_every_sole_stays_on_deck(self):
        body = Body()
        self.assertNotIn('skateboard', build_clips())
        for width in (52, 64, 84):
            clip = build_clips(body=body, gait={'skateboard': {'profile': 'glide_v1', 'width': width}})['skateboard']
            points = {key: [] for key in ('nheel', 'nball', 'fheel', 'fball')}
            for frame in range(120):
                pose = clip.sample(frame * clip.duration / 120)
                skeleton = solve(pose, body)
                for side in 'nf':
                    for label, fn in (('heel', heel_world), ('ball', toe_world)):
                        x, y = fn(skeleton, side)
                        self.assertAlmostEqual(y, clip.DECK_HEIGHT, delta=1e-5)
                        self.assertLess(abs(x), width / 2)
                        points[side + label].append((x, y))
            for positions in points.values():
                self.assertLess(max(math.dist(positions[0], p) for p in positions), 1e-5)
            for channel in ('root_y', 'pelvis', 'head', 'arm_n_up', 'arm_f_up'):
                self.assertAlmostEqual(clip.sample(0)[channel], clip.sample(clip.duration)[channel])

    def test_invalid_or_unreviewed_art_is_not_silently_accepted(self):
        for config in (None, {}, {'profile': 'unknown'}, {'profile': 'glide_v1', 'width': 200},
                       {'profile': 'glide_v1', 'colors': {'wheels': 'red'}}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                build_clips(gait={'skateboard': config})
        clips = build_clips(gait={'skateboard': {'profile': 'glide_v1'}})
        for spec in ({'weapon': 'sword'}, {'weapon': 'none', 'parts': {'head': {}}},
                     {'weapon': 'none', 'puppet': {'source': 'unknown'}}):
            with self.subTest(spec=spec), self.assertRaisesRegex(ValueError, 'procedural, empty-handed'):
                Renderer({**spec, 'gait': {'skateboard': {'profile': 'glide_v1'}}}, 64, clips=clips)

    def test_contact_audit_fails_missing_or_bad_support(self):
        clip = {'frames': [0, 1], 'skateboard': {'deck_height_px': 10., 'half_width_px': 20.}}
        trace = {'feet': {side: {part: [[0., 10.], [1., 10.]] for part in ('heel', 'ball')}
                          for side in 'nf'}}
        self.assertEqual(skateboard_contact(clip, trace)['status'], 'PASS')
        trace['feet']['f']['heel'][1][1] = 12.
        self.assertEqual(skateboard_contact(clip, trace)['status'], 'FAIL')
        self.assertEqual(skateboard_contact({'frames': [0, 1]}, trace)['status'], 'FAIL')
        trace['feet']['f']['heel'].pop()
        self.assertEqual(skateboard_contact(clip, trace)['status'], 'FAIL')

    def test_export_includes_board_and_contact_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / 'rider.json'
            spec.write_text(json.dumps({'weapon': 'none', 'cloth': [],
                                        'gait': {'skateboard': {'profile': 'glide_v1'}}}))
            out = root / 'build'
            subprocess.run([sys.executable, str(SCRIPTS / 'generate.py'), '--character', str(spec),
                            '--size', '128', '--fps', '10', '--clips', 'skateboard',
                            '--fit-selected-clips', '--no-fx', '--out', str(out)],
                           check=True, capture_output=True, text=True)
            subprocess.run([sys.executable, str(SCRIPTS / 'qa_motion.py'), str(out)],
                           check=True, capture_output=True, text=True)
            doc = json.loads((out / 'animations.json').read_text())
            report = json.loads((out / 'qa_report.json').read_text())
            self.assertEqual(report['clips']['skateboard']['board'], 'PASS')
            self.assertEqual(doc['clips']['skateboard']['skateboard']['support'], 'fixed_to_deck')
            self.assertTrue((out / 'preview.html').is_file())
            with Image.open(next((out / 'frames/skateboard').glob('*.png'))) as image:
                self.assertGreater(image.getchannel('A').getbbox()[3], image.height * .83)
            trace_path = out / 'rig_trace.json'
            trace = json.loads(trace_path.read_text())
            trace['traces']['skateboard']['feet']['f']['heel'][0][1] += 2
            trace_path.write_text(json.dumps(trace))
            result = subprocess.run([sys.executable, str(SCRIPTS / 'qa_motion.py'), str(out)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            broken = json.loads((out / 'qa_report.json').read_text())
            self.assertEqual(broken['clips']['skateboard']['board'], 'FAIL')
            self.assertIn('foot not supported', str(broken['clips']['skateboard']['flags']['0']))

    def test_imported_frame_art_preserves_pixels_and_does_not_claim_a_rig(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sheet = Image.new('RGBA', (32 * 4, 32 * 2), (0, 0, 0, 0))
            draw = ImageDraw.Draw(sheet)
            for index in range(8):
                x, y = (index % 4) * 32, (index // 4) * 32
                draw.rectangle((x + 4, y + 4 + index, x + 24, y + 25), fill=(20 + 20 * index, 50, 80, 255))
            source = root / 'sheet.png'
            sheet.save(source)
            out = root / 'build'
            command = [sys.executable, str(SCRIPTS / 'import_frames.py'), '--sheet', str(source),
                       '--columns', '4', '--rows', '2', '--count', '8', '--fps', '8',
                       '--pivot', '16,28', '--pad', '2', '--out', str(out)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            doc = json.loads((out / 'animations.json').read_text())
            self.assertEqual(doc['frame_size'], 36)
            self.assertEqual(doc['pivot'], [18, 30])
            self.assertEqual(len(doc['clips']['skateboard']['frames']), 8)
            self.assertFalse(doc['source']['skeleton_binding'])
            self.assertFalse((out / 'rig_trace.json').exists())
            subprocess.run([sys.executable, str(SCRIPTS / 'qa_motion.py'), str(out)],
                           capture_output=True, text=True)
            report = json.loads((out / 'qa_report.json').read_text())
            self.assertEqual(report['evidence']['status'], 'WARN')
            self.assertIn('rig_trace.json', report['evidence']['missing'])
            with Image.open(out / 'frames/skateboard/skateboard_003.png') as actual:
                self.assertEqual(actual.crop((2, 2, 34, 34)).tobytes(), sheet.crop((96, 0, 128, 32)).tobytes())
            self.assertTrue((out / 'preview.html').is_file())
            duplicate = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertTrue((out / 'animations.json').is_file())

    def test_import_rejects_cropped_or_invalid_sheets(self):
        from import_frames import grid_frames
        sheet = Image.new('RGBA', (64, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(sheet)
        draw.rectangle((0, 3, 20, 20), fill=(255, 0, 0, 255))
        draw.rectangle((35, 3, 50, 20), fill=(0, 0, 255, 255))
        with self.assertRaisesRegex(ValueError, 'may be cropped'):
            grid_frames(sheet, 2, 1, 2, pad=2)
        with self.assertRaisesRegex(ValueError, 'divisible'):
            grid_frames(sheet, 3, 1, 2)

    def test_import_does_not_bypass_an_owned_basic_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'job.json').write_text(json.dumps({'profile': 'basic-side-v1', 'phase': 'blocked'}))
            sheet = root / 'sheet.png'
            Image.new('RGBA', (64, 32), (0, 0, 0, 0)).save(sheet)
            result = subprocess.run([sys.executable, str(SCRIPTS / 'import_frames.py'),
                                     '--sheet', str(sheet), '--columns', '2', '--rows', '1',
                                     '--count', '2', '--fps', '8', '--out', str(root / 'export')],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('owning reviewed job', result.stderr)
            self.assertFalse((root / 'export').exists())


if __name__ == '__main__':
    unittest.main()
