"""A leg must register to a planted shoe rather than a similar-colour robe."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
import layer_parts as lp


class LayerFootAnchors(unittest.TestCase):
    def test_both_legs_align_to_their_shoes_on_different_figures(self):
        for ground, width in ((360, 36), (330, 48)):
            ref = Image.new('RGBA', (256, 384))
            draw = ImageDraw.Draw(ref)
            # Large white robe is an attractive false match for a white leg.
            draw.rectangle((40, 60, 215, 265), fill=(240, 230, 215, 255))
            for heel in (60, 160):
                draw.rectangle((heel, ground - 12, heel + width, ground),
                               fill=(240, 230, 215, 255))
            reference = np.asarray(ref)
            layer = Image.new('RGBA', ref.size)
            draw = ImageDraw.Draw(layer)
            draw.rectangle((105, 90, 130, 260), fill=(240, 230, 215, 255))
            draw.rectangle((100, 250, 155, 270), fill=(240, 230, 215, 255))
            layer = np.asarray(layer)
            for side, heel in (('far', 60), ('near', 160)):
                with self.subTest(ground=ground, width=width, side=side):
                    fit = lp.place_leg(layer, reference, side)
                    placed = lp.placed(layer, fit, ref.size)
                    ys, xs = np.nonzero(placed[..., 3] > 128)
                    self.assertAlmostEqual(int(ys.max()), ground, delta=1)
                    bottom = xs[ys >= ground - 2]
                    self.assertAlmostEqual(int(bottom.min()), heel, delta=1)
                    self.assertAlmostEqual(int(bottom.max()), heel + width, delta=1)

    def test_ambiguous_single_foot_uses_existing_registration(self):
        ref = np.zeros((100, 100, 4), dtype=np.uint8)
        ref[20:91, 30:61] = (240, 230, 215, 255)
        sentinel = {'registration': 'unchanged'}
        with patch.object(lp, 'place', return_value=sentinel) as fallback:
            self.assertIs(lp.place_leg(ref, ref, 'far'), sentinel)
            fallback.assert_called_once_with(ref, ref)

    def test_small_boot_arch_gap_is_one_footprint(self):
        ref = np.zeros((400, 300, 4), dtype=np.uint8)
        ref[30:301, 40:100] = (80, 90, 100, 255)
        ref[30:301, 190:250] = (80, 90, 100, 255)
        ref[292:301, 60:62, 3] = 0  # two-pixel gap across the sole band
        layer = np.zeros_like(ref)
        layer[30:301, 80:140] = (80, 90, 100, 255)
        with patch.object(lp, 'place', side_effect=AssertionError('ambiguous footprints')):
            for side, heel in (('far', 40), ('near', 190)):
                fit = lp.place_leg(layer, ref, side)
                self.assertAlmostEqual(fit['s'], 1)
                self.assertAlmostEqual(fit['dx'], heel - 80)

    def test_three_separate_footprints_remain_ambiguous(self):
        ref = np.zeros((400, 300, 4), dtype=np.uint8)
        for x in (20, 120, 220):
            ref[50:301, x:x + 50] = (80, 90, 100, 255)
        sentinel = {'registration': 'unchanged'}
        with patch.object(lp, 'place', return_value=sentinel):
            self.assertIs(lp.place_leg(ref, ref, 'near'), sentinel)

    def test_hand_landmark_wins_over_a_long_sleeve_tail(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                arm = Image.new('L', (240, 240))
                draw = ImageDraw.Draw(arm)
                draw.rectangle((110, 10, 130, 190), fill=255)
                draw.polygon(((110, 10), (130, 10), (210, 190), (30, 190)), fill=255)
                hand_x = 120 + direction * 70
                draw.rectangle((min(120, hand_x), 80, max(120, hand_x), 100), fill=255)
                hand = Image.new('L', arm.size)
                ImageDraw.Draw(hand).rectangle((hand_x - 8, 80, hand_x + 8, 100), fill=255)
                hand_mask = np.asarray(hand) > 0
                result = lp.read_arm(np.asarray(arm) > 0, hand_mask)
                x, y = result['wrist']
                self.assertTrue(hand_mask[round(y), round(x)])
                self.assertLess(y, 105)
                self.assertGreater(abs(x - 120), 50)

    def test_inferred_elbow_obeys_limits_inside_the_sleeve(self):
        mask = np.ones((200, 200), dtype=bool)
        shoulder, wrist = np.array([100., 10.]), np.array([50., 160.])
        elbow = lp.legal_elbow(mask, shoulder, np.array([120., 100.]), wrist)
        bend = (lp.angle_down(elbow, wrist) - lp.angle_down(shoulder, elbow) + 180) % 360 - 180
        self.assertGreaterEqual(bend, lp.LIMITS['elbow'][0] + lp.BAND)
        self.assertLessEqual(bend, lp.LIMITS['elbow'][1] - lp.BAND)
        self.assertTrue(mask[round(elbow[1]), round(elbow[0])])

    def test_valid_elbow_is_unchanged(self):
        elbow = np.array([50., 100.])
        self.assertIs(lp.legal_elbow(np.ones((200, 200), dtype=bool),
                                    np.array([100., 10.]), elbow, np.array([110., 160.])), elbow)

    def test_coincident_arm_landmarks_are_rejected(self):
        point = np.array([100., 100.])
        with self.assertRaisesRegex(lp.Rejected, 'shoulder and hand overlap'):
            lp.legal_elbow(np.ones((200, 200), dtype=bool), point, point, point)

    def test_hidden_hips_can_follow_measured_body_without_filling_holes(self):
        layer = np.zeros((384, 256, 4), dtype=np.uint8)
        layer[50:201, 70:131] = (230, 220, 210, 255)
        waist, hip = np.array([100., 190.]), np.array([104., 270.])
        core = lp.core_mask((256, 384), waist, hip, 15)
        for hole in (False, True):
            with self.subTest(hole=hole):
                source = layer.copy()
                if hole:
                    source[110:131, 90:111, 3] = 0
                aligned, fit = lp.align_hips(source, waist, hip)
                self.assertIsNotNone(fit)
                alpha = lp.trimmed(aligned, waist, hip, 25)[..., 3]
                open_share = float((alpha[core] <= 128).mean())
                if hole:
                    self.assertGreater(open_share, lp.HOLE_SHARE)
                else:
                    self.assertEqual(open_share, 0)

    def test_hidden_hips_do_not_enlarge_a_thin_scrap(self):
        layer = np.zeros((384, 256, 4), dtype=np.uint8)
        layer[90:93, 70:131] = (230, 220, 210, 255)
        actual, fit = lp.align_hips(layer, np.array([100., 190.]), np.array([104., 270.]))
        self.assertIs(actual, layer)
        self.assertIsNone(fit)


if __name__ == '__main__':
    unittest.main()
