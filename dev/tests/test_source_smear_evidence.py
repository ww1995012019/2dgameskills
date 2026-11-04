"""Source coordinate evidence cannot remove failures or approve smooth artwork."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_source_smear import review
from sprite_anim import puppet_check as pc


class SourceSmearEvidence(unittest.TestCase):
    def fixture(self):
        a = np.zeros((48, 72, 4), dtype=np.uint8)
        a[..., 3] = 255
        # One fully opaque smooth ramp, away from the origin.
        a[24:48, 24:48, :3] = (np.arange(24)*5)[None, :, None]
        return Image.fromarray(a)

    def test_exact_source_coordinates_and_unchanged_failure(self):
        report = pc.smear_tile_report(self.fixture())
        self.assertEqual((report['bad'], report['filled']), (1, 6))
        self.assertEqual(pc.smear_tiles(self.fixture()), (1, 6))
        candidate = report['candidates'][0]
        self.assertEqual(candidate['bounds'], [24, 24, 48, 48])
        self.assertEqual(candidate['span'], 115)
        self.assertEqual(candidate['max_step'], 5)

    def test_sharp_edge_not_flagged_and_transparency_excluded(self):
        a = np.asarray(self.fixture()).copy()
        a[24:48, 35:37, :3] = 255
        self.assertEqual(pc.smear_tiles(Image.fromarray(a)), (0, 6))
        a = np.asarray(self.fixture()).copy()
        a[24, 24, 3] = 250
        self.assertEqual(pc.smear_tiles(Image.fromarray(a)), (0, 5))

    def test_border_remainders_are_not_new_denominator_tiles(self):
        self.assertEqual(pc.smear_tiles(self.fixture().crop((0, 0, 71, 47))), (0, 2))

    def test_review_preserves_sources_and_never_approves(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'skin.png'; self.fixture().save(source)
            before = source.read_bytes()
            out = Path(tmp)/'evidence'
            result = review([source], out)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(result['visual_approval'], 'pending')
            self.assertEqual(result['layers'][0]['status'], 'FAIL')
            self.assertEqual(result['layers'][0]['sha256'], hashlib.sha256(before).hexdigest())
            self.assertTrue((out/'skin.png').is_file())
            with self.assertRaises(FileExistsError):
                review([source], out)

    @unittest.expectedFailure
    def test_smooth_intentional_shading_can_be_distinguished_from_blur(self):
        # A pristine deliberate gradient has identical statistics to a blur.
        # The gate intentionally remains conservative; do not silently waive it.
        self.assertEqual(pc.smear_tiles(self.fixture())[0], 0)


if __name__ == '__main__':
    unittest.main()
