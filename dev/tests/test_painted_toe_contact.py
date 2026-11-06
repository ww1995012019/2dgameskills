"""Basic bindings roll each boot on its own painted toe, on two synthetic builds.

Before this, the binding kept the generic ball 6.5 units ahead of the ankle.
A longer painted boot then pivoted on a point inside its sole and its toe sank
2-3 native pixels under the floor at heel-off, while the bone proxy reported
no contact fault. These are numeric fixtures, not visual acceptance.
"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'game-animator/modes/game-sprite-animator/scripts'))
import character_workflow as cw  # noqa: E402
from sprite_anim.motions import build_clips  # noqa: E402
from sprite_anim.rig import Body, FOOT_BALL, FOOT_HEEL, full_pose, solve, toe_world  # noqa: E402
import test_character_workflow as tcw  # noqa: E402


def bind(root, short):
    case = tcw.CharacterWorkflow()
    case.root, case.source = root, root/'input.png'
    Image.new('RGB', (64, 64), 'navy').save(case.source)
    case.job = root/('short' if short else 'tall')
    case.prepare()
    layers, hip = case.fixture(short)
    case.reference(layers)
    case.layers(layers, hip)
    identity = dict(s=1., deg=0., dx=0., dy=0., cx=0., cy=0., error=0.)
    with patch.object(cw.lp, 'registration', return_value=identity):
        cw.bind_job(case.job)
    return cw.read_json(case.job/'rig/character.json')


class PaintedToeContact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.specs = {short: bind(Path(cls.tmp.name), short) for short in (False, True)}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def clips(self, spec, measured=True):
        body = dict(spec['body'])
        if not measured:
            body.pop('foot_n_ball'); body.pop('foot_f_ball')
        body = Body.from_spec(body)
        return body, build_clips(spec.get('style'), gait=spec['gait'], body=body)

    @staticmethod
    def lowest_toe(clip, body, painted):
        low = np.inf
        for t in np.linspace(0, clip.duration, 121):
            sk = solve(full_pose(clip.sample(t)), body)
            for side in 'nf':
                sk['foot_'+side+'_ball'] = painted[side]
                low = min(low, toe_world(sk, side)[1])
        return low

    def test_binding_measures_each_toe_and_keeps_the_generic_heel(self):
        for short, spec in self.specs.items():
            with self.subTest(short=short):
                body = spec['body']
                for side in 'nf':
                    ball = body['foot_'+side+'_ball']
                    self.assertEqual(len(ball), 2)
                    self.assertAlmostEqual(ball[1], FOOT_HEEL[1], delta=.25)
                    self.assertGreater(ball[0], FOOT_HEEL[0])
                    # The heel is placed by construction; measuring it as well
                    # would switch walk/idle to the measured-sole hip height.
                    self.assertIsNone(body.get('foot_'+side+'_heel'))
        # The short build's boot is far longer than the generic foot.
        self.assertGreater(self.specs[True]['body']['foot_n_ball'][0], FOOT_BALL[0] + 3)

    def test_painted_toe_stays_on_the_floor_through_walk_and_run(self):
        for short, spec in self.specs.items():
            body, clips = self.clips(spec)
            painted = {s: tuple(spec['body']['foot_'+s+'_ball']) for s in 'nf'}
            # A planted flat sole sits where its measured toe height puts it
            # (about 0.1 unit off the generic sole plane, under one pixel).
            # Rolling must never take the toe lower than that.
            flat = min(0., *(painted[s][1]-FOOT_BALL[1] for s in 'nf'))
            for name in ('walk', 'run'):
                with self.subTest(short=short, clip=name):
                    self.assertGreaterEqual(self.lowest_toe(clips[name], body, painted), flat-1e-6)

    def test_generic_pivot_reproduces_the_sunken_toe(self):
        # Fault reproduction: the old binding (no measured toe) drives the same
        # painted toe under the floor, so the passing test above is meaningful.
        spec = self.specs[True]
        body, clips = self.clips(spec, measured=False)
        painted = {s: tuple(spec['body']['foot_'+s+'_ball']) for s in 'nf'}
        self.assertLess(self.lowest_toe(clips['walk'], body, painted), -1.)

    def test_hip_height_and_idle_are_unchanged(self):
        for short, spec in self.specs.items():
            with self.subTest(short=short):
                _, measured = self.clips(spec)
                _, generic = self.clips(spec, measured=False)
                for t in np.linspace(0, measured['walk'].duration, 27):
                    self.assertEqual(measured['walk'].sample(t)['root_y'], generic['walk'].sample(t)['root_y'])
                for t in np.linspace(0, measured['idle'].duration, 13):
                    self.assertEqual(measured['idle'].sample(t), generic['idle'].sample(t))

    def test_toe_off_keeps_the_authored_ankle_rise(self):
        spec = self.specs[True]
        body, measured = self.clips(spec)
        generic_body, generic = self.clips(spec, measured=False)
        def highest_stance_ankle(clip, body):
            # Toe-off only: the planted foot before it leaves the ground.
            heights = []
            for t in np.linspace(0, clip.duration, 241):
                if clip.contacts(t)['n']:
                    heights.append(solve(full_pose(clip.sample(t)), body)['an_n'][1])
            return max(heights)
        self.assertAlmostEqual(highest_stance_ankle(measured['walk'], body),
                               highest_stance_ankle(generic['walk'], generic_body), delta=.35)


if __name__ == '__main__':
    unittest.main()
