"""Semantic review is visible in QA without masquerading as physical damage."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
import qa_motion


class OcclusionHooks(unittest.TestCase):
    def test_legacy_is_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(qa_motion.occlusion_status(root, {}, {}))

    def test_pending_marks_exact_frame_and_warns_not_fails(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'occlusion_review.json').write_text(json.dumps({'candidates': [
                {'clip': 'raise', 'frame': 3, 'arm': 'arm_far'}]}))
            clips = {'raise': {'frames': 5}}
            with patch('sprite_anim.occlusion_review.check_current', return_value=1):
                result = qa_motion.occlusion_status(root, {}, clips)
            self.assertEqual(result['status'], qa_motion.WARN)
            self.assertTrue(result['review_required'])
            self.assertIn('arm_far', clips['raise']['flags']['3'][0])
            self.assertEqual(set(clips['raise']['flags']), {'3'})

    def test_missing_and_malformed_opted_report_remain_pending(self):
        with tempfile.TemporaryDirectory() as root:
            with patch('sprite_anim.occlusion_review.check_current', return_value=1):
                for contents in (None, '{"candidates": 3}'):
                    if contents:
                        Path(root, 'occlusion_review.json').write_text(contents)
                    result = qa_motion.occlusion_status(root, {'occlusion_review': {}}, {})
                    self.assertTrue(result['review_required'])
                    self.assertEqual(result['status'], qa_motion.WARN)

    def test_current_decisions_do_not_mark_frames_as_pending(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'occlusion_review.json').write_text('{"candidates": []}')
            with patch('sprite_anim.occlusion_review.check_current', return_value=0):
                result = qa_motion.occlusion_status(root, {}, {})
            self.assertFalse(result['review_required'])
            self.assertEqual(result['status'], qa_motion.PASS)


if __name__ == '__main__':
    unittest.main()
