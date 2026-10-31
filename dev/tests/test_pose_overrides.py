"""Character-specific key edits preserve built-in motion metadata."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
from sprite_anim.motions import build_clips, IDX


class PoseOverrides(unittest.TestCase):
    def test_edits_only_requested_key_and_preserves_metadata(self):
        original = build_clips()['attack_3']
        edited = build_clips(key_overrides={'attack_3': {'1': {'arm_n_up': 120}}})['attack_3']
        expected = original.curve.v.copy()
        expected[1, IDX['arm_n_up']] = 120
        self.assertTrue((edited.curve.v == expected).all())
        self.assertEqual(edited.events, original.events)
        self.assertEqual((edited.prev, edited.next, edited.tags, edited.chain_at),
                         (original.prev, original.next, original.tags, original.chain_at))
        self.assertEqual(edited.vel(0.2), original.vel(0.2))
        self.assertEqual(edited.duration, original.duration)

    def test_invalid_corrections_fail(self):
        for changes in ({'walk': {'0': {'arm_n_up': 1}}},
                        {'attack_3': {'99': {'arm_n_up': 1}}},
                        {'attack_3': {'0': {'unknown': 1}}},
                        {'attack_3': {'0': {'arm_n_up': float('nan')}}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_clips(key_overrides=changes)


if __name__ == '__main__':
    unittest.main()
