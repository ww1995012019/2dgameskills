"""Rejected real trouser renders must not be cleared by correct hip landmarks."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'shared/scripts/audit_skin_binding.py'
FIXTURES = ROOT / 'dev/fixtures/split_pants'
spec = importlib.util.spec_from_file_location('split_pants_binding_audit', TOOL)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class SplitPantsRegression(unittest.TestCase):
    def test_every_actual_pose_fails_the_shared_fabric_gate(self):
        for character in ('lieying', 'hanfeng'):
            with self.subTest(character=character):
                report, _ = audit.inspect_manifest(FIXTURES / character / 'manifest.json')
                self.assertEqual(report['status'], 'fail')
                self.assertEqual(report['visual_status'], 'pending')
                self.assertEqual(report['scope']['clip_frames'], {'idle': 1, 'crouch': 2})
                self.assertEqual(report['scope']['frames'], 3)
                self.assertEqual(report['scope']['landmarks'], 2)
                self.assertEqual(report['limits']['seam_tolerance_px'], .5)
                expected = {('idle', 0), ('crouch', 0), ('crouch', 1)}
                failures = report['failures']
                self.assertTrue(failures)
                self.assertTrue(all(f['kind'] == 'seam' and f['id'] == 'pants-center' for f in failures))
                self.assertEqual({(f['clip'], f['frame']) for f in failures}, expected)
                # The same fixture passes joint correspondence. That must never
                # override a broken shared garment boundary elsewhere in a frame.
                landmarks = [m for m in report['measurements'] if m['kind'] == 'landmark']
                self.assertEqual(len(landmarks), 6)
                self.assertLess(max(m['error_px'] for m in landmarks), 1e-5)

    def test_the_reported_split_is_visible_in_the_frozen_rgba_crops(self):
        # These exact poses were rejected by the user. Inspect actual alpha
        # between the two mapped sides of formerly opaque source fabric, rather
        # than merely checking that some abstract distance exceeded a threshold.
        for character, clip, frame in (('hanfeng', 'idle', 0), ('lieying', 'crouch', 1)):
            with self.subTest(character=character, clip=clip, frame=frame):
                folder = FIXTURES / character
                report, doc = audit.inspect_manifest(folder / 'manifest.json')
                with Image.open(folder / doc['clips'][clip]['frames'][frame]['image']) as image:
                    self.assertEqual(image.mode, 'RGBA')
                    low, high = image.getchannel('A').getextrema()
                    self.assertEqual(low, 0)
                    self.assertEqual(high, 255)
                    transparent_between_sides = False
                    for failure in report['failures']:
                        if (failure['clip'], failure['frame']) != (clip, frame):
                            continue
                        a, b = failure['a'], failure['b']
                        count = max(1, math.ceil(math.dist(a, b)))
                        for i in range(count + 1):
                            t = i / count
                            x = round(a[0] * (1 - t) + b[0] * t)
                            y = round(a[1] * (1 - t) + b[1] * t)
                            if 0 <= x < image.width and 0 <= y < image.height:
                                transparent_between_sides |= image.getpixel((x, y))[3] < 96
                    self.assertTrue(transparent_between_sides,
                                    'the retained waist/hip crop must contain the reported real gap')

    def test_cli_rejects_both_fixtures_without_repainting_evidence(self):
        for character in ('lieying', 'hanfeng'):
            with self.subTest(character=character), tempfile.TemporaryDirectory() as tmp:
                folder = FIXTURES / character
                before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in folder.iterdir() if p.is_file()}
                output = Path(tmp) / 'report.json'
                process = subprocess.run([sys.executable, str(TOOL),
                                          str(folder / 'manifest.json'), '--out', str(output)],
                                         capture_output=True, text=True)
                self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
                report = json.loads(output.read_text())
                self.assertEqual(report['status'], 'fail')
                self.assertEqual(audit.audit_current(output), 1)
                self.assertTrue(report['review_sheets'])
                for name in report['review_sheets']:
                    self.assertTrue((output.parent / name).is_file())
                self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in folder.iterdir() if p.is_file()})


if __name__ == '__main__':
    unittest.main()
