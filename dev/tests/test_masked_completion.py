"""Fault injection for a locality boundary; no AI visual acceptance claims."""
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import masked_completion as mc


class MaskedCompletion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self, width=80, height=120):
        y, x = np.indices((height, width))
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        rgba[:, :, 0] = x
        rgba[:, :, 1] = y
        rgba[:, :, 2:] = 255
        owned = (x >= width // 4) & (x < width * 3 // 4) & (y > 10) & (y < height - 10)
        completion = owned & (x == width // 2)
        visible = owned & ~completion
        Image.fromarray(rgba).save(self.root / 'source.png')
        for name, mask in [('visible', visible), ('completion', completion)]:
            Image.fromarray(mask.astype('uint8') * 255).save(self.root / (name + '.png'))
        mc.prepare(self.root / 'source.png', self.root / 'visible.png',
                   self.root / 'completion.png', self.root / 'job')
        return rgba, visible, completion

    def test_two_builds_lock_original_pixels_despite_full_plate_redraw(self):
        for width, height in [(80, 120), (140, 90)]:
            with self.subTest(size=(width, height)):
                if (self.root / 'job').exists():
                    import shutil
                    shutil.rmtree(self.root / 'job')
                source, visible, completion = self.fixture(width, height)
                Image.new('RGBA', (1254, 1254), 'red').save(self.root / 'red.png')
                report = mc.compose(self.root / 'job', self.root / 'red.png')
                result = np.asarray(Image.open(self.root / 'job/completed.png'))
                np.testing.assert_array_equal(result[visible], source[visible])
                self.assertTrue((result[completion] == (255, 0, 0, 255)).all())
                self.assertFalse(result[~(visible | completion)].any())
                self.assertFalse(report['binding_approved'])
                self.assertEqual(report['status'], 'needs_visual_review')

    def test_stale_source_mask_or_plate_cannot_be_composited(self):
        self.fixture()
        for path in [self.root / 'source.png', self.root / 'visible.png',
                     self.root / 'completion.png', self.root / 'job/plate.png']:
            original = path.read_bytes()
            path.write_bytes(original + b'changed')
            with self.assertRaisesRegex(ValueError, 'changed since preparation'):
                mc.compose(self.root / 'job', self.root / 'source.png')
            path.write_bytes(original)

    def test_unfilled_marker_is_blocker(self):
        self.fixture()
        Image.new('RGB', (256, 256), (0, 255, 0)).save(self.root / 'green.png')
        report = mc.compose(self.root / 'job', self.root / 'green.png')
        self.assertIn('unfilled_green_marker', report['blockers'])
        self.assertEqual(report['status'], 'blocked')

    def test_incomplete_envelope_blocks_before_generation(self):
        self.fixture()
        visible = np.asarray(Image.open(self.root / 'visible.png')).copy()
        visible[30:40, 25:30] = 0
        Image.fromarray(visible).save(self.root / 'broken.png')
        result = subprocess.run([
            sys.executable, str(Path(mc.__file__)), 'prepare',
            '--source', str(self.root / 'source.png'), '--visible-mask', str(self.root / 'broken.png'),
            '--completion-mask', str(self.root / 'completion.png'), '--out', str(self.root / 'broken-job'),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('enclosed_transparent_regions_require_review', result.stdout)

    def test_large_completion_budget_is_not_silently_accepted(self):
        visible = np.zeros((20, 20), dtype=bool)
        completion = visible.copy()
        visible[2:10, 2:18] = True
        completion[10:18, 2:18] = True
        self.assertIn('initial_small_area_target_exceeded', mc.geometry_blockers(visible, completion))

    def test_internal_hole_is_reported(self):
        mask = np.zeros((20, 20), dtype=bool)
        mask[2:18, 2:18] = True
        mask[8:11, 8:11] = False
        self.assertEqual(mc.hole_pixels(mask), 9)
        mask[0:9, 9] = False  # now open to the outside
        self.assertEqual(mc.hole_pixels(mask), 0)

    def test_overlap_and_soft_masks_are_rejected(self):
        self.fixture()
        with self.assertRaisesRegex(ValueError, 'overlap'):
            mc.prepare(self.root / 'source.png', self.root / 'visible.png',
                       self.root / 'visible.png', self.root / 'overlap')
        Image.new('L', (80, 120), 128).save(self.root / 'soft.png')
        with self.assertRaisesRegex(ValueError, 'only 0 and 255'):
            mc.prepare(self.root / 'source.png', self.root / 'visible.png',
                       self.root / 'soft.png', self.root / 'soft')


if __name__ == '__main__':
    unittest.main()
