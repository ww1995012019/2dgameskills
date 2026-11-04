"""Source-space partition tests do not approve semantic masks or filtered boundaries."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pelvic_overlay as po


class PelvicOverlay(unittest.TestCase):
    def fixture(self, root, scale=1, collar=True):
        source = root / 'source'
        (source / 'layers').mkdir(parents=True)
        rgba = np.zeros((12 * scale, 18 * scale, 4), dtype=np.uint8)
        rgba[..., :3] = (120, 75, 30)
        rgba[scale:-scale, scale:-scale, 3] = 255
        rgba[scale, scale:-scale, 3] = 91
        rgba[2 * scale:5 * scale, scale:-scale, :3] = (230, 180, 35)
        Image.fromarray(rgba).save(source / 'layers/hips.png')
        mask = np.zeros(rgba.shape[:2], dtype=np.uint8)
        mask[scale:5 * scale, scale:-scale] = 255
        Image.fromarray(mask).save(root / 'mask.png')
        names = ['cape', 'arm_far', 'leg_far', 'leg_near', 'torso', 'head']
        if collar:
            names += ['torso_front']
        names += ['hips', 'weapon', 'arm_near', 'sparkle']
        layers = {n: {'image': 'layers/' + n + '.png', 'custom': {'name': n}} for n in names}
        layers['hips'].update(kind='rigid', follow=['hip', 'body_rot'],
                              anchor=[80.25, 100.5], offset=[64, 90])
        for name, row in layers.items():
            row.setdefault('offset', [0, 0])
            if name != 'hips':
                Image.new('RGBA', (2, 2), (20, 30, 40, 255)).save(source / row['image'])
        Image.new('RGBA', (160, 160), (80, 60, 40, 255)).save(source / 'source.png')
        spec = {'puppet': {'layers': layers}, 'custom_spec_field': [1, 2]}
        (source / 'character.json').write_text(json.dumps(spec))
        (source / 'provenance.json').write_text(json.dumps({'final_visual_pass': True}))
        return source, root / 'mask.png', rgba, spec

    @staticmethod
    def snapshot(root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_two_sizes_partition_source_pixels_and_preserve_geometry_and_order(self):
        for scale in (1, 3):
            for collar in (False, True):
                with self.subTest(scale=scale, collar=collar), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    source, mask, rgba, original = self.fixture(root, scale, collar)
                    snapshot = self.snapshot(source)
                    dest = root / 'new-rig'
                    po.install_pelvic_overlay(source, dest, mask, ownership='garment')
                    self.assertEqual(snapshot, self.snapshot(source))
                    self.assertEqual((dest / 'original_reference.png').read_bytes(), snapshot['source.png'])
                    result = json.loads((dest / 'character.json').read_text())
                    layers = result['puppet']['layers']
                    front = np.array(Image.open(dest / layers['pelvis_front']['image']))
                    back = np.array(Image.open(dest / layers['hips']['image']))
                    np.testing.assert_array_equal(front[..., :3], rgba[..., :3])
                    np.testing.assert_array_equal(back[..., :3], rgba[..., :3])
                    np.testing.assert_array_equal(front[..., 3].astype(int) + back[..., 3], rgba[..., 3])
                    self.assertFalse(np.any((front[..., 3] > 0) & (back[..., 3] > 0)))
                    merged = np.array(Image.alpha_composite(Image.fromarray(back), Image.fromarray(front)))
                    np.testing.assert_array_equal(merged[rgba[..., 3] > 0], rgba[rgba[..., 3] > 0])
                    expected_front = copy.deepcopy(original['puppet']['layers']['hips'])
                    expected_front['image'] = 'layers/pelvis_front.png'
                    self.assertEqual(layers['pelvis_front'], expected_front)
                    for name, payload in original['puppet']['layers'].items():
                        self.assertEqual(layers[name], payload)
                    order = list(layers)
                    self.assertEqual([n for n in order if n not in ('hips', 'pelvis_front')],
                                     [n for n in original['puppet']['layers'] if n != 'hips'])
                    self.assertLess(order.index('hips'), min(order.index(n) for n in ('leg_far', 'leg_near', 'torso')))
                    cover = 'torso_front' if collar else 'torso'
                    self.assertEqual(order.index('pelvis_front'), order.index(cover) + 1)
                    for name in ('weapon', 'arm_near'):
                        self.assertLess(order.index('pelvis_front'), order.index(name))
                    recomposed = Image.new('RGBA', (160, 160))
                    for row in layers.values():
                        with Image.open(dest / row['image']) as image:
                            recomposed.alpha_composite(image, tuple(row['offset']))
                    np.testing.assert_array_equal(np.array(Image.open(dest / 'source.png')), np.array(recomposed))
                    report = json.loads((dest / 'provenance.json').read_text())
                    self.assertFalse(report['final_visual_pass'])
                    self.assertEqual(report['derived_pelvic_overlay']['semantic_visual_approval'], 'pending')
                    self.assertFalse(report['derived_pelvic_overlay']['filtered_output_pixel_identity_claimed'])

    def test_opt_in_torso_depth_changes_order_only_and_supports_unarmed_rigs(self):
        for collar in (False, True):
            for armed in (False, True):
                with self.subTest(collar=collar, armed=armed), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    source, mask, _, spec = self.fixture(root, collar=collar)
                    if not armed:
                        del spec['puppet']['layers']['weapon']
                        (source / 'character.json').write_text(json.dumps(spec))
                    before = self.snapshot(source)
                    for policy in (False, True):
                        po.install_pelvic_overlay(source, root / str(policy), mask,
                                                 ownership='garment', torso_under_pelvis=policy)
                    default = json.loads((root / 'False/character.json').read_text())['puppet']['layers']
                    changed = json.loads((root / 'True/character.json').read_text())['puppet']['layers']
                    self.assertEqual(default, changed)
                    cluster = ['torso', 'head'] + (['torso_front'] if collar else [])
                    expected = ['cape', 'arm_far'] + cluster + ['hips', 'leg_far', 'leg_near', 'pelvis_front']
                    expected += (['weapon'] if armed else []) + ['arm_near', 'sparkle']
                    self.assertEqual(list(changed), expected)
                    self.assertEqual(before, self.snapshot(source))
                    for name in default:
                        path = default[name]['image']
                        self.assertEqual((root / 'False' / path).read_bytes(),
                                         (root / 'True' / path).read_bytes())
                    for policy in (False, True):
                        report = json.loads((root / str(policy) / 'pelvic_overlay.json').read_text())
                        self.assertIs(report['torso_under_pelvis'], policy)

    def test_opt_in_exposes_pants_in_unselected_garment_opening(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, mask, _, spec = self.fixture(root, collar=False)
            layers = spec['puppet']['layers']
            for name, color in (('torso', (10, 150, 130, 255)),
                                ('leg_far', (45, 55, 80, 255)),
                                ('leg_near', (0, 0, 0, 0))):
                layers[name]['offset'] = [64, 90]
                Image.new('RGBA', (18, 12), color).save(source / layers[name]['image'])
            (source / 'character.json').write_text(json.dumps(spec))
            for policy in (False, True):
                po.install_pelvic_overlay(source, root / str(policy), mask,
                                         ownership='garment', torso_under_pelvis=policy)
            with Image.open(root / 'False/source.png') as image:
                self.assertEqual(image.getpixel((72, 97)), (10, 150, 130, 255))
            with Image.open(root / 'True/source.png') as image:
                self.assertEqual(image.getpixel((72, 97)), (45, 55, 80, 255))
                # Registered foreground garment still covers both pants and torso.
                self.assertEqual(image.getpixel((72, 93)), (230, 180, 35, 255))

    def test_opt_in_depth_rejects_unknown_interleaving_before_writes(self):
        for placement in ('cluster', 'legs', 'between', 'missing_head', 'bad_collar', 'nonboolean'):
            with self.subTest(placement=placement), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, mask, _, spec = self.fixture(root)
                layers = spec['puppet']['layers']
                order = list(layers)
                if placement in ('cluster', 'legs', 'between'):
                    order.remove('sparkle')
                    target = {'cluster': 'head', 'legs': 'leg_near', 'between': 'torso'}[placement]
                    order.insert(order.index(target), 'sparkle')
                if placement == 'missing_head': order.remove('head')
                if placement == 'bad_collar':
                    a, b = order.index('head'), order.index('torso_front')
                    order[a], order[b] = order[b], order[a]
                spec['puppet']['layers'] = {n: layers[n] for n in order}
                (source / 'character.json').write_text(json.dumps(spec))
                before = self.snapshot(root)
                with self.assertRaises(ValueError):
                    po.install_pelvic_overlay(source, root / 'new-rig', mask, ownership='garment',
                                             torso_under_pelvis='yes' if placement == 'nonboolean' else True)
                self.assertEqual(before, self.snapshot(root))
                self.assertFalse((root / 'new-rig').exists())

    def test_invalid_masks_and_ownership_fail_without_writes(self):
        for fault in ('size', 'empty', 'outside', 'soft', 'rgb', 'ownership', 'order', 'existing', 'nonrigid', 'shared', 'lateleg', 'offset', 'clipping', 'reference'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, mask, rgba, spec = self.fixture(root)
                ownership = 'garment'
                if fault == 'size': Image.new('L', (2, 2), 255).save(mask)
                if fault == 'empty': Image.new('L', (18, 12)).save(mask)
                if fault == 'outside': Image.new('L', (18, 12), 255).save(mask)
                if fault == 'soft': Image.new('L', (18, 12), 128).save(mask)
                if fault == 'rgb': Image.new('RGB', (18, 12)).save(mask)
                if fault == 'ownership': ownership = 'automatic'
                layers = spec['puppet']['layers']
                if fault == 'order': layers['torso_front'] = layers.pop('torso_front')
                if fault == 'offset': layers['hips']['offset'] = [0.5, 1]
                if fault == 'clipping': layers['hips']['offset'] = [159, 159]
                if fault == 'reference': (source / 'original_reference.png').write_bytes(b'existing')
                if fault == 'lateleg': layers['leg_near'] = layers.pop('leg_near')
                if fault == 'existing': layers['pelvis_front'] = copy.deepcopy(layers['hips'])
                if fault == 'nonrigid': layers['hips']['kind'] = 'mesh'
                if fault == 'shared': layers['cape']['image'] = layers['hips']['image']
                (source / 'character.json').write_text(json.dumps(spec))
                before = self.snapshot(root)
                with self.assertRaises(ValueError):
                    po.install_pelvic_overlay(source, root / 'new-rig', mask, ownership=ownership)
                self.assertEqual(before, self.snapshot(root))
                self.assertFalse((root / 'new-rig').exists())

    def test_destination_must_be_new_and_normalized_binary_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, mask, _, _ = self.fixture(root)
            original = self.snapshot(root)
            for dest in (source, source / 'nested'):
                with self.assertRaises(ValueError):
                    po.install_pelvic_overlay(source, dest, mask, ownership='garment')
            self.assertEqual(original, self.snapshot(root))
            values = np.array(Image.open(mask)) // 255
            Image.fromarray(values).save(mask)
            po.install_pelvic_overlay(source, root / 'new-rig', mask, ownership='garment')
            with self.assertRaises(ValueError):
                po.install_pelvic_overlay(source, root / 'new-rig', mask, ownership='garment')


if __name__ == '__main__':
    unittest.main()
