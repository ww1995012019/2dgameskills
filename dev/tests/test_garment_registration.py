"""Explicit row registration preserves source upper pixels, not garment semantics."""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import garment_registration as gr


class GarmentRegistration(unittest.TestCase):
    def fixture(self, scale=1):
        width, height = 96 * scale, 100 * scale
        source = np.zeros((height, width, 4), dtype=np.uint8)
        # Arbitrary hidden RGB and partial alpha must survive in the source upper.
        yy, xx = np.indices((height, width))
        source[..., 0] = xx % 251
        source[..., 1] = yy % 251
        source[..., 2] = 113
        source[:40 * scale, 26 * scale:66 * scale, 3] = 191
        source[40 * scale, 28 * scale:66 * scale, 3] = 255
        generated = np.zeros_like(source)
        cut, hem = 30 * scale, 75 * scale
        generated[:cut, :, :] = (220, 50, 70, 255)  # Must never enter the upper source.
        for y in range(cut, hem + 1):
            fraction = (y - cut) / (hem - cut)
            left = round(28 * scale - 5 * scale * min(fraction * 3, 1))
            right = round(64 * scale + 5 * scale * min(fraction * 3, 1))
            generated[y, left:right + 1] = (70, 110 + (y % 40), 145, 255)
            if y > cut + 10 * scale:
                generated[y, 43 * scale:52 * scale] = 0  # A real transparent slit.
            if y > hem - 6 * scale:
                generated[y, 52 * scale:] = 0  # Only one narrow panel survives at the tip.
        return Image.fromarray(source), Image.fromarray(generated), dict(
            source_seam_row=40 * scale, generated_seam_row=cut,
            target_hem_width=42 * scale, target_hem_center=47 * scale)

    def test_two_sizes_source_upper_is_byte_identical_and_inputs_are_unmodified(self):
        for scale in (1, 3):
            with self.subTest(scale=scale):
                source, generated, options = self.fixture(scale)
                source_bytes, generated_bytes = source.tobytes(), generated.tobytes()
                result, report = gr.register_lower_garment(source, generated, **options)
                self.assertEqual(source.size, result.size)
                cut = options['source_seam_row']
                np.testing.assert_array_equal(np.array(result)[:cut], np.array(source)[:cut])
                self.assertEqual(source_bytes, source.tobytes())
                self.assertEqual(generated_bytes, generated.tobytes())
                self.assertEqual(report['source_upper_unchanged_through_row'], cut - 1)
                self.assertTrue(report['source_upper_rgba_unchanged'])
                self.assertFalse(report['source_identity_claimed'])
                self.assertFalse(report['automatic_clothing_detection'])
                self.assertEqual(report['clipped_pixels'], 0)
                for key in ('semantic_visual_approval', 'registration_visual_approval', 'motion_contact_approval'):
                    self.assertEqual(report[key], 'pending')
                self.assertFalse(np.array(result)[report['target_last_row'] + 1:].any())

    def test_profile_interpolates_fixed_anchors_and_does_not_inflate_panel_tips(self):
        for scale in (1, 3):
            with self.subTest(scale=scale):
                source, generated, options = self.fixture(scale)
                result, report = gr.register_lower_garment(source, generated, **options)
                profile = report['row_profile']
                for key in ('reference_width', 'reference_center', 'target_width', 'target_center'):
                    np.testing.assert_allclose([row[key] for row in profile],
                                               np.linspace(profile[0][key], profile[-1][key], len(profile)), atol=1e-12)
                self.assertEqual(profile[-1]['target_width'], options['target_hem_width'])
                self.assertEqual(profile[-1]['target_center'], options['target_hem_center'])
                self.assertLess(report['generated_widest_reference_row'], report['generated_hem_row'] - 6 * scale)
                # The widest-row reference stays broad even when the last row is
                # only a single panel. Refitting that tip would inflate it 2x+.
                last = np.array(generated)[report['generated_hem_row']]
                original_tip = np.flatnonzero(last[:, 3] > 128)
                self.assertGreater(profile[-1]['reference_width'], 2 * (original_tip[-1] - original_tip[0]))
                transformed_tip = np.flatnonzero(np.array(result)[report['target_last_row'], :, 3] > 128)
                expected_span = (original_tip[-1] - original_tip[0]) * profile[-1]['scale']
                self.assertLessEqual(abs((transformed_tip[-1] - transformed_tip[0]) - expected_span), 2)
                self.assertLess(transformed_tip[-1] - transformed_tip[0], options['target_hem_width'] * .6)
                # Consecutive tip rows use one smooth affine profile, not each
                # row's visible width; left boundaries cannot suddenly flare.
                edges = []
                for y in range(report['target_last_row'] - 5 * scale, report['target_last_row'] + 1):
                    xs = np.flatnonzero(np.array(result)[y, :, 3] > 128)
                    edges.append(int(xs[0]))
                self.assertLessEqual(max(abs(b - a) for a, b in zip(edges, edges[1:])), 1)

    def test_transparent_slits_and_empty_or_one_pixel_lower_rows_are_retained(self):
        source, generated, options = self.fixture()
        pixels = np.array(generated)
        pixels[58] = 0
        pixels[59] = 0
        pixels[59, 30] = (70, 110, 145, 255)
        generated = Image.fromarray(pixels)
        result, report = gr.register_lower_garment(source, generated, **options)
        output = np.array(result)
        for row in report['row_profile']:
            if 45 <= row['source_row'] <= 55:
                gap_center = int(round(47 * row['scale'] + row['shift']))
                self.assertEqual(output[row['target_row'], gap_center, 3], 0)
        self.assertFalse(output[68].any())
        self.assertTrue(output[69, :, 3].any())

    def test_pixel_center_registration_does_not_add_half_pixel_drift(self):
        band = Image.new('RGBA', (40, 1))
        band.putpixel((10, 0), (255, 0, 0, 255))
        out = np.array(gr._transform_row(band, 80, 2., 0., 'probe'))[0, :, 3]
        center = (np.arange(80) * out).sum() / out.sum()
        self.assertAlmostEqual(center, 20., places=12)

    def test_bounds_reject_vertical_horizontal_and_filtered_edge_clipping(self):
        source, generated, options = self.fixture()
        for changes in ({'source_seam_row': 70}, {'target_hem_width': 100}, {'target_hem_center': 5}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                gr.register_lower_garment(source, generated, **dict(options, **changes))
        # Move a tiny alpha=1 fragment outside the row's ordinary solid span.
        pixels = np.array(generated)
        pixels[65, 0] = (40, 60, 80, 1)
        with self.assertRaisesRegex(ValueError, 'clip'):
            gr.register_lower_garment(source, Image.fromarray(pixels), **dict(options, target_hem_center=30))
        # Mapped occupied centers fit, but bicubic alpha would escape the canvas.
        band = Image.new('RGBA', (10, 1))
        band.putpixel((0, 0), (30, 60, 90, 255))
        with self.assertRaisesRegex(ValueError, 'filtered'):
            gr._transform_row(band, 20, 2., 0., 'edge probe')

    def test_low_alpha_bottom_pixels_are_not_silently_dropped(self):
        source, generated, options = self.fixture()
        pixels = np.array(generated)
        pixels[95, 40] = (20, 40, 60, 1)
        with self.assertRaisesRegex(ValueError, 'vertically'):
            gr.register_lower_garment(source, Image.fromarray(pixels), **options)

    def test_invalid_images_rows_spans_and_numeric_parameters_are_rejected(self):
        source, generated, options = self.fixture()
        for bad in (None, -1, 100, 1.0, .5, float('nan'), float('inf'), True, '30'):
            for key in ('source_seam_row', 'generated_seam_row'):
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    gr.register_lower_garment(source, generated, **dict(options, **{key: bad}))
        for key in ('target_hem_width', 'target_hem_center'):
            for bad in (None, True, float('nan'), float('inf'), '42'):
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    gr.register_lower_garment(source, generated, **dict(options, **{key: bad}))
        for width in (0, -1, .5):
            with self.subTest(width=width), self.assertRaises(ValueError):
                gr.register_lower_garment(source, generated, **dict(options, target_hem_width=width))
        for bad in (source.convert('RGB'), Image.new('RGBA', source.size), None):
            with self.subTest(image=type(bad).__name__), self.assertRaises(ValueError):
                gr.register_lower_garment(bad, generated, **options)
            with self.assertRaises(ValueError):
                gr.register_lower_garment(source, bad, **options)
        for target in ('source', 'generated', 'flat_lower'):
            a, b = np.array(source), np.array(generated)
            if target == 'source':
                a[options['source_seam_row']] = 0
                a[options['source_seam_row'], 30] = (10, 20, 30, 255)
            if target == 'generated': b[options['generated_seam_row']] = 0
            if target == 'flat_lower': b[options['generated_seam_row'] + 1:] = 0
            with self.subTest(target=target), self.assertRaises(ValueError):
                gr.register_lower_garment(Image.fromarray(a), Image.fromarray(b), **options)

    def test_two_sizes_backing_uses_only_interior_spans_and_preserves_registration(self):
        for scale in (1, 3):
            for mode in ('RGB', 'RGBA'):
                with self.subTest(scale=scale, mode=mode):
                    source, generated, options = self.fixture(scale)
                    garment, _ = gr.register_lower_garment(source, generated, **options)
                    swatch = Image.new(mode, (4, 5), (35, 50, 70) if mode == 'RGB' else (35, 50, 70, 255))
                    before = (garment.tobytes(), swatch.tobytes())
                    backing, report = gr.lower_aperture_backing(garment, swatch, seam_row=options['source_seam_row'])
                    self.assertEqual(backing.size, garment.size)
                    self.assertEqual(before, (garment.tobytes(), swatch.tobytes()))
                    expected = np.zeros((garment.height, garment.width), bool)
                    for y in range(options['source_seam_row'], garment.height):
                        xs = np.flatnonzero(np.array(garment)[y, :, 3] > 128)
                        if len(xs) >= 2:
                            expected[y, xs[0] + 1:xs[-1]] = True
                    data = np.array(backing)
                    np.testing.assert_array_equal(data[..., 3] > 0, expected)
                    self.assertFalse(data[~expected].any())
                    np.testing.assert_array_equal(data[expected], np.tile([35, 50, 70, 255], (int(expected.sum()), 1)))
                    self.assertEqual(report['backing_pixels'], int(expected.sum()))
                    self.assertTrue(report['external_edge_pixels_excluded'])
                    self.assertEqual(report['semantic_visual_approval'], 'pending')

    def test_backing_samples_swatch_over_bbox_without_exterior_rgb(self):
        garment = Image.new('RGBA', (30, 20))
        array = np.array(garment)
        array[5:15, 7] = (20, 30, 40, 255)
        array[5:15, 22] = (20, 30, 40, 255)
        array[10, 3:7, 3] = 128  # Not endpoints; these must not widen the backing.
        garment = Image.fromarray(array)
        swatch = Image.fromarray(np.array([[[0, 0, 0], [255, 120, 80]]], dtype=np.uint8))
        image, report = gr.lower_aperture_backing(garment, swatch, seam_row=5)
        self.assertEqual(report['interior_bbox'], [8, 5, 22, 15])
        data = np.array(image)
        self.assertGreater(data[10, 21, 0], data[10, 8, 0])
        self.assertFalse(data[:, :8].any())
        self.assertFalse(data[:, 22:].any())

    def test_backing_invalid_swatch_rows_and_degenerate_interiors_are_rejected(self):
        source, _, _ = self.fixture()
        good = Image.new('RGB', (2, 2), (30, 50, 80))
        for swatch in (None, good.convert('L'), Image.new('RGBA', (2, 2), (30, 50, 80, 254))):
            with self.subTest(swatch=type(swatch).__name__), self.assertRaises(ValueError):
                gr.lower_aperture_backing(source, swatch, seam_row=20)
        for bad in (-1, 100, 1., None, float('nan'), True):
            with self.subTest(row=bad), self.assertRaises(ValueError):
                gr.lower_aperture_backing(source, good, seam_row=bad)
        narrow = Image.new('RGBA', (10, 10))
        narrow.putpixel((4, 4), (10, 20, 30, 255))
        narrow.putpixel((5, 4), (10, 20, 30, 255))
        with self.assertRaisesRegex(ValueError, 'nondegenerate'):
            gr.lower_aperture_backing(narrow, good, seam_row=0)


if __name__ == '__main__':
    unittest.main()
