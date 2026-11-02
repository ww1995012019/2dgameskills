"""Loose painted layers must fit and touch the floor without moving the body."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'game-sprite-animator/scripts'))
from sprite_anim.art import Canvas
from sprite_anim.cloth import ChainDef, bake_all
from sprite_anim.motions import build_clips
from sprite_anim.puppet import Puppet, floor_contact
from sprite_anim import puppet_check as pc
from sprite_anim.render import GROUND_FRAC, Renderer
from sprite_anim.rig import Body


class PuppetContactBounds(unittest.TestCase):
    def test_contact_policy_does_not_ground_airborne_hair_or_mutate_definition(self):
        definition = ChainDef('hair', ('head_base', 'head_rot', (0, 0)), 3, 8, ground=False)
        ground = SimpleNamespace(name='roll', loop=True, tags=('ground',))
        air = SimpleNamespace(name='fall', loop=True, tags=())
        seen = []
        def simulate(d, clip, body):
            seen.append((clip.name, d.ground))
            return object()
        with patch('sprite_anim.cloth.simulate', side_effect=simulate):
            bake_all({'roll': ground, 'fall': air}, None, [definition], grounded_chains={'hair'})
        self.assertEqual(seen, [('roll', True), ('fall', False)])
        self.assertFalse(definition.ground)

    def test_soft_contact_is_monotone_and_leaves_distant_vertices_unchanged(self):
        vertices = np.array([[[3., -30.], [7., -10.]], [[3., 4.], [7., 30.]]])
        result = floor_contact(vertices, 0., 0.5)
        np.testing.assert_array_equal(result[..., 0], vertices[..., 0])
        np.testing.assert_allclose(result[0], vertices[0], atol=1e-8)
        self.assertLessEqual(result[..., 1].max(), 0.)
        self.assertTrue(np.all(result[1, :, 1] >= result[0, :, 1]))

    def test_contact_does_not_project_a_body_layer(self):
        vertices = np.array([[[0., 10.], [10., 10.]], [[0., 20.], [10., 20.]]])
        layer = SimpleNamespace(name='torso', kind='tube', foot=None, bones=['hip', 'waist'],
                                mapped=lambda *args: vertices)
        puppet = Puppet.__new__(Puppet)
        puppet.layers, puppet.px_per_unit = [layer], 1.
        cv = Canvas(2, 1, 1., 0., 1., False, (0, 0, 0))
        actual = list(puppet.meshes(cv, {'hip': (0, 0), 'waist': (0, 10)}, {}, True, False))[0][1]
        np.testing.assert_array_equal(actual, vertices)

    def test_ground_fault_is_reported_with_layer_clip_and_frame(self):
        vertices = np.array([[[20., 120.], [40., 120.]], [[20., 140.], [40., 140.]]])
        layer = SimpleNamespace(name='robe', kind='tube', cells=np.array([[0, 0]]),
                                used=np.ones((2, 2), bool))
        puppet = SimpleNamespace(layers=[layer], meshes=lambda *args: [(layer, vertices)])
        renderer = SimpleNamespace(size=128, ss=1, unit=1., cloth_at=lambda *args: {},
                                   art=SimpleNamespace(body=Body(), puppet=puppet))
        clip = build_clips()['idle']
        faults = pc.check_motion(renderer, clip, 2, 30)
        self.assertTrue(any(s.startswith('garment_ground: robe: idle frame 0:') for s in faults), faults)
        vertices[:] = floor_contact(vertices, 128 * GROUND_FRAC, .5)
        self.assertFalse(any(s.startswith('garment_ground:') for s in pc.check_motion(renderer, clip, 2, 30)))

    def test_actual_painted_extent_fits_on_two_different_builds(self):
        for width, body in [(440, {}), (720, {'head_size': 1.3, 'chest_len': 22})]:
            with self.subTest(width=width), tempfile.TemporaryDirectory() as tmp:
                Image.new('RGBA', (width, 90), (30, 90, 140, 255)).save(Path(tmp) / 'wide.png')
                spec = {'name': 'wide-layer', 'weapon': 'none', 'cloth': [], '_dir': tmp, 'body': body,
                        'puppet': {'px_per_unit': 2., 'joints': {'head_base': [width/2, 90]},
                            'rest_angles': {'head_rot': 0.}, 'chains': {},
                            'layers': {'head': {'kind': 'rigid', 'image': 'wide.png',
                                'anchor': [width/2, 90], 'follow': ['head_base', 'head_rot']}}}}
                clips = {'idle': build_clips(body=Body.from_spec(body))['idle']}
                renderer = Renderer(spec, 128, clips=clips)
                for frame in renderer.render_clip(clips['idle'], 5):
                    ys, xs = np.nonzero(frame[..., 3] > .02)
                    self.assertGreater(len(xs), 0)
                    self.assertGreater(int(xs.min()), 0)
                    self.assertLess(int(xs.max()), 127)
                    self.assertGreater(int(ys.min()), 0)
                    self.assertLess(int(ys.max()), 127)


if __name__ == '__main__':
    unittest.main()
