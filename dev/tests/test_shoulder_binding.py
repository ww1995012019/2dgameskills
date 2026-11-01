"""Side-view attachment, depth, and the mandatory shoulder review sheet."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'game-sprite-animator/scripts'
sys.path.insert(0, str(SCRIPTS))
import layer_parts as lp
import visual_review as review
from sprite_anim import puppet_check as pc
from sprite_anim.motions import build_clips
from sprite_anim.rig import Body, full_pose, solve
from dev.tests.test_puppet import figure, keyed, reference_of


class ShoulderBinding(unittest.TestCase):
    def test_independent_measured_shoulders_are_preserved(self):
        for kw in ({}, {'hip': (480, 960), 'leg': 300, 'chest': (170, 240), 'head': 210, 'stride': 70, 'width': 84}):
            with self.subTest(kw=kw):
                layers = figure(**kw)
                rgba = {k: keyed(v) for k, v in layers.items()}
                ref = reference_of(layers)
                # Plant the old heuristic's trigger: reference pixels favour
                # the rear sleeve over the torso where their roots overlap.
                far = rgba['arm_far'][..., 3] > 128
                ref[far] = rgba['arm_far'][far]
                identity = dict(s=1., deg=0., dx=0., dy=0., cx=0., cy=0., error=0.)
                with patch.object(lp, 'place', return_value=identity), patch.object(lp, 'place_leg', return_value=identity):
                    out, spec, _ = lp.bind(ref, rgba)
                self.assertNotEqual(spec['body']['sh_n_at'], spec['body']['sh_f_at'])
                order = list(spec['puppet']['layers'])
                self.assertLess(order.index('arm_far'), order.index('torso'))
                self.assertLess(order.index('torso'), order.index('arm_near'))
                self.assertNotEqual(spec['puppet']['layers']['arm_far']['rest'][0],
                                    spec['puppet']['layers']['arm_near']['rest'][0])
                np.testing.assert_array_equal(out['arm_far'], rgba['arm_far'])
                body = Body.from_spec(spec['body'])
                separation = []
                for turn in (-90, 0, 90, 180):
                    sk = solve(full_pose({'root_rot': turn}), body)
                    separation.append(math.dist(sk['sh_n'], sk['sh_f']))
                self.assertGreater(min(separation), 0)
                np.testing.assert_allclose(separation, separation[0], atol=1e-8)

    def test_layer_check_rejects_far_arm_promoted_over_torso(self):
        image = Image.new('RGBA', (24, 24), (70, 90, 100, 255))
        def layer(name):
            side = 'n' if name == 'arm_near' else 'f'
            return SimpleNamespace(name=name, image=image, bones=['sh_'+side, 'el_'+side, 'wr_'+side])
        puppet = SimpleNamespace(layers=[layer(n) for n in ('torso', 'arm_far', 'arm_near')])
        self.assertTrue(any('shoulder:' in s for s in pc.check_layers(puppet)))
        puppet.layers[0], puppet.layers[1] = puppet.layers[1], puppet.layers[0]
        self.assertEqual(pc.check_layers(puppet), [])

    def test_motion_check_does_not_force_shoulders_to_one_point(self):
        body = Body(sh_n_at=(-1, 18), sh_f_at=(-4, 20))
        puppet = SimpleNamespace(meshes=lambda *args: [])
        renderer = SimpleNamespace(art=SimpleNamespace(puppet=puppet, body=body),
                                   size=128, ss=1, unit=1., cloth_at=lambda *args: {})
        clip = build_clips()['idle']
        self.assertEqual(pc.check_motion(renderer, clip, 2, 30), [])
        body.sh_f_at = body.sh_n_at
        self.assertEqual(pc.check_motion(renderer, clip, 2, 30), [])


class ShoulderReview(unittest.TestCase):
    def skeleton(self):
        return {'neck': [[32, 10]] * 6, 'waist': [[32, 36]] * 6,
                'sh_n': [[32, 20]] * 6, 'sh_f': [[32, 20]] * 6,
                'el_n': [[42, 20], [32, 30], [42, 22], [32, 10], [42, 24], [42, 20]],
                'el_f': [[22, 30]] * 6,
                'wr_n': [[44, 34]] * 6, 'wr_f': [[18, 40]] * 6}

    def test_rest_recovery_and_upper_arm_extremes_are_selected(self):
        self.assertEqual(review.shoulder_frames(self.skeleton()), [0, 1, 3, 5])

    def test_angle_wrap_does_not_invent_a_shoulder_extreme(self):
        sk = self.skeleton()
        for name in sk:
            sk[name] = sk[name][:4]
        sk['el_n'] = [[32 + 10 * math.cos(math.radians(a)), 20 + 10 * math.sin(math.radians(a))]
                      for a in (170, 179, -179, -170)]
        self.assertEqual(review.shoulder_frames(sk), [0, 3])

    def test_review_cannot_pass_without_the_shoulder_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = root / 'frames/idle'
            frames.mkdir(parents=True)
            for i in range(6):
                im = Image.new('RGBA', (64, 64))
                ImageDraw.Draw(im).rectangle((22, 10, 42, 48), fill=(30, 90, 130, 255))
                im.save(frames / f'idle_{i:03d}.png')
            doc = {'frame_size': 64, 'pivot': [32, 58], 'clips': {'idle': {'frames': list(range(6)), 'fps': 30, 'loop': True}}}
            trace = {'unit_px': 1., 'traces': {'idle': {'skeleton': self.skeleton()}}}
            (root / 'animations.json').write_text(json.dumps(doc))
            (root / 'rig_trace.json').write_text(json.dumps(trace))
            review.build(tmp)
            index = json.loads((root / 'review/index.json').read_text())
            names = [s['sheet'] for s in index['sheets']]
            self.assertIn('shoulders_00.png', names)
            self.assertIn('arms_00.png', names)
            self.assertTrue((root / 'review/shoulders_00.png').is_file())
            verdict = {'reviewer': 'test', 'sheets': {n: {'verdict': 'pass'} for n in names if n != 'shoulders_00.png'}}
            path = root / 'verdict.json'
            path.write_text(json.dumps(verdict))
            with self.assertRaisesRegex(SystemExit, 'shoulders_00.png'):
                review.record(tmp, str(path))
            verdict['sheets']['shoulders_00.png'] = {'verdict': 'pass'}
            path.write_text(json.dumps(verdict))
            self.assertEqual(review.record(tmp, str(path)), 0)
            del verdict['sheets']['arms_00.png']
            path.write_text(json.dumps(verdict))
            with self.assertRaisesRegex(SystemExit, 'arms_00.png'):
                review.record(tmp, str(path))


if __name__ == '__main__':
    unittest.main()
