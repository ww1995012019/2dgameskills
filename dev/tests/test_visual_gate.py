"""Inject bad visual verdicts; they must never become a passing report."""
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('shared_review_gate', ROOT/'shared/scripts/visual_review.py')
vr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vr)
sys.path.insert(0, str(ROOT/'game-sprite-animator/scripts'))
import layer_parts as lp


class VisualGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'review').mkdir()
        (self.root/'frames/walk').mkdir(parents=True)
        Image.new('RGBA', (16, 16), 'red').save(self.root/'frames/walk/walk_000.png')
        Image.new('RGB', (16, 16), 'red').save(self.root/'review/arms_00.png')
        self.refresh()
        self.verdict = {'reviewer': 'fault injection', 'review_id': self.ident,
                        'sheets': {'arms_00.png': {'verdict': 'pass', 'checks': {
                            k: {'status': 'pass', 'evidence': 'walk frame 0 fixture inspected'} for k in vr.CHECKS}, 'issues': []}}}

    def refresh(self):
        self.ident = vr.review_id(vr.review_assets(str(self.root)))
        (self.root/'review/index.json').write_text(json.dumps({'review_id': self.ident, 'sheets': [{'sheet': 'arms_00.png'}]}))

    def record(self, v=None):
        path = self.root/'verdict.json'
        path.write_text(json.dumps(v or self.verdict))
        return vr.record(str(self.root), str(path))

    def issue(self, severity='blocker', resolved=False):
        return dict(id='short-arm', category='missing_limb', severity=severity, resolved=resolved,
                    clip='walk', frame=0, what='持剑手臂仍为短桩臂，无完整摆臂')

    def test_clean_current_review_passes(self):
        self.assertEqual(self.record(), 0)
        self.assertEqual(vr.check_current(str(self.root)), 0)
        self.assertEqual(json.loads((self.root/'visual_report.json').read_text())['status'], 'pass')

    def test_structural_issue_cannot_be_polish(self):
        self.verdict['sheets']['arms_00.png']['issues'] = [self.issue('polish', True)]
        with self.assertRaisesRegex(SystemExit, 'must be blocker'):
            self.record()

    def test_string_false_and_unsupported_resolution_are_rejected(self):
        for value, reason in [('false', 'boolean'), (True, 'previous_review_id')]:
            self.verdict['sheets']['arms_00.png']['issues'] = [self.issue(resolved=value)]
            with self.assertRaisesRegex(SystemExit, reason):
                self.record()

    def test_fail_sheet_never_returns_success_even_for_cosmetic(self):
        row = self.verdict['sheets']['arms_00.png']
        row['verdict'] = 'fail'
        row['issues'] = [dict(self.issue('polish'), category='cosmetic')]
        self.assertEqual(self.record(), 1)

    def test_unresolved_problem_and_failed_check_cannot_pass(self):
        row = self.verdict['sheets']['arms_00.png']
        row['issues'] = [self.issue()]
        with self.assertRaisesRegex(SystemExit, 'unresolved'):
            self.record()
        row['issues'] = []
        row['checks']['complete_limbs']['status'] = 'fail'
        with self.assertRaisesRegex(SystemExit, 'cannot have a pass'):
            self.record()

    def test_missing_semantic_checks_are_refused(self):
        del self.verdict['sheets']['arms_00.png']['checks']['complete_limbs']
        with self.assertRaisesRegex(SystemExit, 'complete_limbs'):
            self.record()

    def test_changed_frames_invalidate_old_pass(self):
        self.record()
        Image.new('RGBA', (16, 16), 'blue').save(self.root/'frames/walk/walk_000.png')
        self.assertEqual(vr.check_current(str(self.root)), 1)
        with self.assertRaisesRegex(SystemExit, 'stale'):
            self.record()
        self.assertFalse((self.root/'visual_report.json').exists())

    def test_issue_cannot_disappear_or_resolve_without_changed_pixels(self):
        row = self.verdict['sheets']['arms_00.png']
        row['verdict'] = 'fail'; row['issues'] = [self.issue()]
        self.assertEqual(self.record(), 1)
        previous = self.ident
        row['verdict'] = 'pass'; row['issues'] = []
        with self.assertRaisesRegex(SystemExit, 'omitted'):
            self.record()
        resolved = self.issue(resolved=True)
        resolved['resolution'] = dict(previous_review_id=previous, change='rebuilt complete arm', frames=[{'clip': 'walk', 'frame': 0}])
        row['issues'] = [resolved]
        with self.assertRaisesRegex(SystemExit, 'no changed frame'):
            self.record()
        Image.new('RGBA', (16, 16), 'blue').save(self.root/'frames/walk/walk_000.png')
        Image.new('RGB', (16, 16), 'blue').save(self.root/'review/arms_00.png')
        self.refresh(); self.verdict['review_id'] = self.ident
        self.assertEqual(self.record(), 0)

    def test_recompression_does_not_count_as_repaired_pixels(self):
        frame = self.root/'frames/walk/walk_000.png'
        before = vr.file_hash(frame)
        with Image.open(frame) as image:
            image.save(frame, compress_level=0)
        self.assertEqual(vr.file_hash(frame), before)

    def test_mandatory_checks_cannot_be_marked_not_applicable(self):
        self.verdict['sheets']['arms_00.png']['checks']['complete_limbs']['status'] = 'not_applicable'
        with self.assertRaisesRegex(SystemExit, 'cannot be skipped'):
            self.record()

    def test_plan_template_is_pending_and_cli_bind_requires_review(self):
        image = self.root/'ref.png'
        Image.new('RGBA', (600, 1200)).save(image)
        from PIL import ImageDraw
        with Image.open(image) as im:
            ImageDraw.Draw(im).rectangle((250, 100, 350, 1100), fill='red')
            im.save(image)
        planned = self.root/'plan'
        with patch.object(sys, 'argv', ['layer_parts.py', 'plan', '--image', str(image), '--out', str(planned)]):
            lp.main()
        pending = json.loads((planned/'reference_review.json').read_text())
        self.assertTrue(all(c['status'] == 'pending' for c in pending['checks'].values()))
        output = self.root/'rig'
        args = ['layer_parts.py', 'bind', '--image', str(image), '--layers', str(planned/'layers'), '--out', str(output)]
        with patch.object(sys, 'argv', args):
            with self.assertRaisesRegex(SystemExit, 'semantic review required'):
                lp.main()
        self.assertFalse((output/'character.json').exists())
        self.assertEqual(json.loads((output/'bind_report.json').read_text())['status'], 'rejected')

    def test_reference_requires_explicit_current_semantic_review(self):
        image = self.root/'ref.png'
        Image.new('RGBA', (32, 32), 'red').save(image)
        path = self.root/'reference_review.json'
        with self.assertRaisesRegex(lp.Rejected, 'semantic review required'):
            lp.check_reference_review(image, None)
        review = lp.reference_review_template(image)
        path.write_text(json.dumps(review))
        with self.assertRaises(lp.Rejected):
            lp.check_reference_review(image, path)
        review['reviewer'] = 'fixture reviewer'
        for check in review['checks'].values():
            check.update(status='pass', evidence='visual inspection of this fixture')
        path.write_text(json.dumps(review)); lp.check_reference_review(image, path)
        Image.new('RGBA', (32, 32), 'blue').save(image)
        with self.assertRaisesRegex(lp.Rejected, 'stale'):
            lp.check_reference_review(image, path)

if __name__ == '__main__':
    unittest.main()
