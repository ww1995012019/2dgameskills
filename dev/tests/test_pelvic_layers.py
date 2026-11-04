"""Explicit apparel depth preserves source pixels; static checks are not art approval."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import atlas_rig as ar


class PelvicLayers(unittest.TestCase):
    def make_parts(self, root, scale):
        root.mkdir()
        dimensions = {'torso': (100, 200), 'hips': (100, 100),
                      'head': (120, 120), 'weapon': (20, 160)}
        dimensions.update({n: (40, 200) for n in
                           ('arm_far', 'arm_near', 'leg_far', 'leg_near')})
        for name, (w, h) in dimensions.items():
            image = Image.new('RGBA', (w, h), (40, 70, 110, 255))
            draw = ImageDraw.Draw(image)
            if name == 'torso':
                image = Image.new('RGBA', (w, h))
                draw = ImageDraw.Draw(image)
                draw.rectangle((5, 30, 95, 199), fill=(30, 60, 90, 255))
                draw.rectangle((40, 0, 60, 40), fill=(220, 170, 130, 255))
            if name == 'hips':
                draw.rectangle((0, 0, 99, 19), fill=(240, 180, 35, 255))
                draw.rectangle((40, 40, 59, 99), fill=(0, 0, 0, 0))
            image.resize((w * scale, h * scale), Image.Resampling.NEAREST).save(root / (name + '.png'))

    @staticmethod
    def measured_joints(image, name):
        # Fixed synthetic measurements isolate compositing from landmark detection.
        scale = image.height / 200
        if name.startswith('arm'):
            return {key: np.array(value) * scale for key, value in
                    {'shoulder': (20, 10), 'elbow': (20, 100),
                     'wrist': (20, 185), 'grip': (20, 190)}.items()}
        if name.startswith('leg'):
            return {key: np.array(value) * scale for key, value in
                    {'hip': (20, 10), 'knee': (20, 100), 'ankle': (20, 190)}.items()}
        return {}

    def test_collar_order_accepts_either_adjacency_and_rejects_interleaving(self):
        for pair in (['head', 'torso'], ['torso', 'head']):
            original = ['cape'] + pair + ['hips', 'weapon', 'arm_near', 'sparkle']
            snapshot = original.copy()
            self.assertEqual(ar.collar_layer_order(original),
                             ['cape', 'torso', 'head', 'torso_front',
                              'hips', 'weapon', 'arm_near', 'sparkle'])
            self.assertEqual(original, snapshot)
        with self.assertRaisesRegex(ValueError, 'adjacent'):
            ar.collar_layer_order(['head', 'hips', 'torso'])

    def test_ambiguous_depth_is_rejected_before_reading_art(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'pelvis_cover'):
                ar.assemble(Path(tmp) / 'missing-parts', Path(tmp) / 'output',
                            pelvis_cover='automatic')

    def test_front_belt_is_visible_without_changing_any_source_or_placed_pixels(self):
        for scale in (1, 2):
            with self.subTest(scale=scale), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                parts = root / 'parts'
                self.make_parts(parts, scale)
                before = {p.name: p.read_bytes() for p in parts.iterdir()}
                with mock.patch.object(ar, 'landmarks', side_effect=self.measured_joints):
                    for depth in ('behind', 'front'):
                        ar.assemble(parts, root / depth, canvas=(1280, 1536), pelvis_cover=depth)
                    ar.assemble(parts, root / 'default', canvas=(1280, 1536))
                self.assertEqual(before, {p.name: p.read_bytes() for p in parts.iterdir()})
                specs = {n: json.loads((root / n / 'input.json').read_text())
                         for n in ('behind', 'front', 'default')}
                self.assertEqual(specs['behind']['order'], specs['default']['order'])
                order = specs['front']['order']
                self.assertGreater(order.index('hips'), order.index('torso'))
                self.assertLess(order.index('hips'), order.index('weapon'))
                self.assertLess(order.index('hips'), order.index('arm_near'))
                self.assertEqual([n for n in order if n != 'hips'],
                                 [n for n in specs['behind']['order'] if n != 'hips'])
                for name in order:
                    self.assertEqual((root / 'front/layers' / (name + '.png')).read_bytes(),
                                     (root / 'behind/layers' / (name + '.png')).read_bytes())
                layers = {n: np.array(Image.open(root / 'front/layers' / (n + '.png')))
                          for n in order}
                belt = np.all(layers['hips'] == (240, 180, 35, 255), axis=2)
                visible = belt & (layers['torso'][..., 3] == 255)
                for name in order[order.index('hips') + 1:]:
                    visible &= layers[name][..., 3] == 0
                self.assertGreater(int(visible.sum()), 100)
                front = np.array(Image.open(root / 'front/assembled.png'))
                behind = np.array(Image.open(root / 'behind/assembled.png'))
                np.testing.assert_array_equal(front[visible], layers['hips'][visible])
                self.assertTrue(np.any(front[visible] != behind[visible]))

    def test_collar_preserves_extra_layers_payloads_and_selected_pelvic_depth(self):
        for depth in ('front', 'behind'):
            for scale in (1, 2):
                with self.subTest(depth=depth, scale=scale), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_parts(root / 'layers', scale)
                    order = ['cape', 'arm_far', 'leg_far', 'leg_near', 'head', 'torso',
                             'hips', 'weapon', 'arm_near', 'sparkle']
                    if depth == 'behind':
                        order.remove('hips')
                        order.insert(2, 'hips')
                    layers = {n: {'image': 'layers/' + n + '.png',
                                  'sentinel': {'original_index': i}}
                              for i, n in enumerate(order)}
                    original = copy.deepcopy(layers)
                    source = (root / 'layers/torso.png').read_bytes()
                    (root / 'character.json').write_text(json.dumps({'puppet': {'layers': layers}}))
                    (root / 'provenance.json').write_text('{}')
                    mask=np.zeros((200*scale,100*scale),np.uint8);mask[:41*scale,40*scale:61*scale]=255
                    self.assertGreater(ar.install_collar_overlay(root, ownership='head_skin', neck_mask=mask), 0)
                    result = json.loads((root / 'character.json').read_text())['puppet']['layers']
                    result_order = list(result)
                    self.assertEqual([n for n in result_order if n not in ('torso', 'torso_front')],
                                     [n for n in order if n != 'torso'])
                    self.assertEqual(set(result), set(original) | {'torso_front'})
                    for name in original:
                        self.assertEqual(result[name], original[name])
                    self.assertLess(result_order.index('torso'), result_order.index('head'))
                    self.assertLess(result_order.index('head'), result_order.index('torso_front'))
                    if depth == 'front':
                        self.assertGreater(result_order.index('hips'), result_order.index('torso_front'))
                    else:
                        self.assertLess(result_order.index('hips'), result_order.index('torso'))
                    self.assertEqual(source, (root / 'layers/torso.png').read_bytes())
                    provenance = json.loads((root / 'provenance.json').read_text())
                    self.assertEqual(provenance['runtime_assets']['layers/torso.png'],
                                     hashlib.sha256(source).hexdigest())
                    with self.assertRaisesRegex(ValueError, 'already installed'):
                        ar.install_collar_overlay(root, ownership='head_skin', neck_mask=mask)


if __name__ == '__main__':
    unittest.main()
