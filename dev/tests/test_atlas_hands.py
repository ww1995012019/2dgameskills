"""Shape-supported hand inference is colour invariant and rejects ambiguous sleeves."""
import sys
import unittest
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import atlas_rig as ar


class AtlasHands(unittest.TestCase):
    def arm(self, scale=1, colour=(180, 140, 100, 255)):
        im = Image.new('RGBA', (160 * scale, 320 * scale))
        # Tapered forearm, narrow wrist at y=225, then a broad terminal fist.
        points = [(48, 8), (88, 8), (95, 80), (88, 150), (79, 224),
                  (96, 240), (109, 270), (102, 294), (80, 308),
                  (57, 296), (49, 272), (56, 244), (60, 224),
                  (49, 150), (39, 80)]
        ImageDraw.Draw(im).polygon([(x * scale, y * scale) for x, y in points], fill=colour)
        return im

    def test_glove_fur_metal_and_skin_colours_give_identical_landmarks(self):
        reference = None
        for colour in ((180, 140, 100, 255), (20, 30, 45, 255),
                       (90, 160, 195, 255), (170, 170, 170, 255), (90, 60, 40, 255)):
            image = self.arm(colour=colour)
            hand, diagnostic = ar.distal_hand(image)
            self.assertEqual(diagnostic['method'], 'silhouette_neck')
            self.assertGreater(diagnostic['palm_neck_ratio'], 1.25)
            landmarks = ar.landmarks(image, 'arm_near')
            if reference is None:
                reference = hand, landmarks
            else:
                np.testing.assert_array_equal(hand, reference[0])
                for key in landmarks:
                    np.testing.assert_array_equal(landmarks[key], reference[1][key])

    def test_normalized_wrist_is_stable_across_scales(self):
        expected = ar.landmarks(self.arm(4), 'arm_near')['wrist'] / 4
        for scale in (1, 2, 3):
            image = self.arm(scale)
            hand, diagnostic = ar.distal_hand(image)
            row = ar.landmarks(image, 'arm_near')
            np.testing.assert_allclose(row['wrist'] / scale, expected, atol=2.)
            self.assertEqual(diagnostic['method'], 'silhouette_neck')
            self.assertGreater(row['wrist'][1] / scale, 220)
            self.assertLess(row['wrist'][1] / scale, 245)
            self.assertGreater(np.nonzero(hand)[0].min() / scale, 205)

    def test_exposed_forearm_is_not_mistaken_for_whole_hand(self):
        image = self.arm(colour=(230, 175, 125, 255))
        hand, diagnostic = ar.distal_hand(image)
        self.assertEqual(diagnostic['method'], 'silhouette_neck')
        self.assertFalse(hand[150, 70])
        self.assertTrue(hand[275, 75])

    def test_uniform_broad_sleeve_rejected_even_in_skin_colours(self):
        for colour in ((20, 30, 45, 255), (230, 175, 125, 255)):
            image = Image.new('RGBA', (160, 320))
            ImageDraw.Draw(image).rounded_rectangle((35, 8, 115, 308), radius=30, fill=colour)
            with self.assertRaisesRegex(ValueError, 'ambiguous wrist/hand'):
                ar.distal_hand(image)

    def test_two_plausible_necks_are_rejected(self):
        image = self.arm(colour=(20, 30, 45, 255))
        d = ImageDraw.Draw(image)
        # Remove a second proximal band, creating two comparable bottlenecks.
        d.rectangle((0, 165, 60, 180), fill=(0, 0, 0, 0))
        d.rectangle((80, 165, 159, 180), fill=(0, 0, 0, 0))
        with self.assertRaisesRegex(ValueError, 'ambiguous wrist/hand'):
            ar.distal_hand(image)

    def test_empty_and_tiny_inputs_fail_clearly(self):
        for image in (Image.new('RGBA', (40, 40)), Image.new('RGBA', (5, 10), 'white')):
            with self.assertRaises(ValueError):
                ar.distal_hand(image)


if __name__ == '__main__':
    unittest.main()
