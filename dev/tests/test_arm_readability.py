"""The previously accepted idle fused two otherwise readable reference arms."""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
from sprite_anim import puppet_check as pc
from sprite_anim.motions import build_clips
from sprite_anim.rig import Body


class ArmReadability(unittest.TestCase):
    def puppet(self):
        image = Image.new('RGBA', (24, 24), (60, 90, 110, 255))
        near = SimpleNamespace(name='arm_near', rest=np.array([[0, 0], [6, 8], [13, 9]]),
                               radius=1., image=image, bones=['sh_n', 'el_n', 'wr_n'])
        far = SimpleNamespace(name='arm_far', rest=np.array([[-3, 0], [-8, 8], [-10, 16]]),
                              radius=1., image=image, bones=['sh_f', 'el_f', 'wr_f'])
        torso = SimpleNamespace(name='torso', image=image)
        return SimpleNamespace(layers=[far, torso, near], px_per_unit=1., meshes=lambda *args: [])

    def check(self, profile, common=False, action='idle'):
        body = Body(up_arm=10, lo_arm=7.071, sh_n_at=(0, 18),
                    sh_f_at=(0, 18) if common else (-3, 18))
        renderer = SimpleNamespace(art=SimpleNamespace(body=body, puppet=self.puppet()),
                                   size=128, ss=1, unit=1., cloth_at=lambda *args: {})
        clip = build_clips(gait={'idle': profile}, body=body)[action]
        return pc.check_motion(renderer, clip, 72, 30)

    def test_previous_one_arm_adaptation_is_detected(self):
        for common in (False, True):
            with self.subTest(common=common):
                found = self.check({'arm_f': [-19.41, 1.8, 1.86, 2.6]}, common=common)
                self.assertTrue(any(p.startswith('arm_spacing:') for p in found), found)

    def test_both_reference_arms_remain_readable(self):
        found = self.check({'arm_n': [45.87, 1.6, 45, 1.5],
                            'arm_f': [-23.0, 1.8, 17.97, 2.6], 'wep': 64})
        self.assertEqual(found, [])

    def test_reference_comparison_does_not_restrict_active_actions(self):
        self.assertEqual(self.check({'arm_f': [-19.41, 1.8, 1.86, 2.6]}, action='block'), [])

    def test_spacing_is_invariant_to_rotation_translation_and_scale(self):
        p = self.puppet()
        near, far = p.layers[-1].rest, p.layers[0].rest
        baseline = pc.arm_spacing(near, far)
        for angle in (0, 0.4, -1.2):
            matrix = np.array([[math.cos(angle), -math.sin(angle)],
                               [math.sin(angle), math.cos(angle)]])
            for scale in (0.5, 3):
                np.testing.assert_allclose(pc.arm_spacing(near @ matrix * scale + 57,
                                                         far @ matrix * scale + 57), baseline * scale)

    def test_cross_binding_an_arm_to_the_other_chain_is_rejected(self):
        p = self.puppet()
        p.layers[-1].bones = ['sh_n', 'el_f', 'wr_f']
        self.assertTrue(any(s.startswith('arm_chain:') for s in pc.check_layers(p)))


if __name__ == '__main__':
    unittest.main()
