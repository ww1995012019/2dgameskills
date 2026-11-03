"""Known-joint binding measures each limb, head and grip by general rules, on two body types.

Far limbs keep their own measured lengths (shared near lengths stretched them up to 25%),
both feet still stand, a folded backward arm is refused, a tilted head measures like an upright
one, the grip tolerance follows the arm's size and alpha palette PNGs bind like RGBA.
"""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import template_full_character as full
import template_puppet as tp
import test_template_full_character as fixtures
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
import bind_known_joints as entry
import known_joint_rig as kr
from sprite_anim import puppet_check as pc
from sprite_anim.motions import build_clips
from sprite_anim.render import Renderer
from sprite_anim.rig import Body, full_pose, heel_world, solve, toe_world

CHAINS = {'leg_near': ('n', ('hip', 'knee', 'ankle'), ('hip_', 'kn_', 'an_')),
          'leg_far': ('f', ('hip', 'knee', 'ankle'), ('hip_', 'kn_', 'an_')),
          'arm_near': ('n', ('shoulder', 'elbow', 'wrist'), ('sh_', 'el_', 'wr_')),
          'arm_far': ('f', ('shoulder', 'elbow', 'wrist'), ('sh_', 'el_', 'wr_'))}


def far_scaled(case, profile, k):
    """The template fixture with its far arm/leg scaled by k: the leg about its sole, the arm about
    its shoulder, so the art is a consistent figure whose far limbs differ from the near ones."""
    stage = fixtures.FullTemplate.complete_fixture(case, profile)
    full.inspect(stage)
    joints = json.loads(json.dumps(tp.read(stage / 'assembly_report.json')['joints']))
    for slot in ('leg_far', 'arm_far'):
        path = stage / 'assembled_layers' / (slot + '.png')
        with Image.open(path) as image:
            image = image.convert('RGBA')
        ys, xs = np.nonzero(np.asarray(image)[..., 3] > 128)
        px, py = (float(xs.mean()), float(ys.max())) if slot == 'leg_far' else joints[slot]['shoulder']
        image.transform(image.size, Image.AFFINE, (1 / k, 0, px - px / k, 0, 1 / k, py - py / k),
                        resample=Image.BICUBIC).save(path)
        joints[slot] = {n: [px + k * (p[0] - px), py + k * (p[1] - py)] for n, p in joints[slot].items()}
    job = dict(name=f'{profile}-{k}', order=list(full.ORDER), joints=joints,
               layers={n: f'assembled_layers/{n}.png' for n in full.ORDER})
    tp.write(stage / 'input.json', job)
    return stage, job


def length_ratios(spec, joints, clip, times):
    """Runtime limb length over its art length, per limb and sampled time."""
    body = Body.from_spec(spec['body'])
    ppu = spec['puppet']['px_per_unit']
    out = {s: [] for s in CHAINS}
    for t in times:
        sk = solve(full_pose(clip.sample(float(t))), body)
        for slot, (side, keys, names) in CHAINS.items():
            art = sum(math.dist(joints[slot][keys[i]], joints[slot][keys[i + 1]]) for i in range(2))
            run = sum(math.dist(sk[names[i] + side], sk[names[i + 1] + side]) for i in range(2))
            out[slot].append(run * ppu / art)
    return out


class FarLimbLengths(unittest.TestCase):
    def test_far_limbs_keep_measured_length_and_both_feet_stand_on_two_builds(self):
        for profile in tp.PROFILES:
            for k in (0.87, 1.13):
                with self.subTest(profile=profile, k=k):
                    stage, job = far_scaled(self, profile, k)
                    entry.bind(stage / 'input.json', stage / 'rig')
                    spec = tp.read(stage / 'rig/character.json')
                    spec['_dir'] = str(stage / 'rig')
                    body = Body.from_spec(spec['body'])
                    clips = build_clips(body=body, gait=spec['gait'])
                    for name in ('idle', 'walk'):
                        ratios = length_ratios(spec, job['joints'], clips[name],
                                               np.linspace(0, clips[name].duration, 12))
                        for slot, values in ratios.items():
                            np.testing.assert_allclose(values, 1., atol=.01, err_msg=f'{name} {slot}')
                    sk = solve(full_pose(clips['idle'].sample(0.)), body)
                    for side in 'nf':
                        sole = min(heel_world(sk, side)[1], toe_world(sk, side)[1])
                        self.assertLess(abs(sole), .5, f'idle {side} sole {sole:.3f}')
                    renderer = Renderer(spec, 192, clips={n: clips[n] for n in ('idle', 'walk')})
                    self.assertEqual(pc.check_layers(renderer.art.puppet), [])
                    for name in ('idle', 'walk'):
                        self.assertEqual(pc.check_motion(renderer, clips[name], 8, 15), [])
                    # Fault: without the far lengths the far limbs stretch by about 1/k.
                    legacy = dict(spec, body={n: v for n, v in spec['body'].items() if not n.endswith('_f')})
                    stretched = length_ratios(legacy, job['joints'], clips['idle'], [0.])
                    self.assertGreater(abs(stretched['arm_far'][0] - 1), .08)
                    self.assertGreater(abs(stretched['leg_far'][0] - 1), .08)

    def test_rigs_without_far_lengths_solve_as_before(self):
        body = Body()
        self.assertEqual(body.leg_bones('f'), (body.thigh, body.shin))
        self.assertEqual(body.arm_bones('f'), (body.up_arm, body.lo_arm))
        sk = solve(full_pose({}), body)
        self.assertAlmostEqual(math.dist(sk['sh_f'], sk['el_f']), body.up_arm)
        self.assertAlmostEqual(math.dist(sk['hip_f'], sk['kn_f']), body.thigh)


class MeasuredParts(unittest.TestCase):
    def test_folded_backward_arm_is_refused_but_a_folded_forward_arm_is_kept(self):
        # Rig convention: forearm angle minus upper-arm angle < 0 is a backward elbow.
        backward = [[0., 0.], [8., 20.], [-.5, .3]]      # wrist folded back onto the shoulder: -178.5
        with self.assertRaisesRegex(ValueError, 'nearly coincide'):
            kr.canonical_arm(backward)
        forward = [[0., 0.], [-8., 20.], [.5, .3]]       # folded the legal way: +178.5
        self.assertFalse(kr.canonical_arm(forward)[2])
        self.assertTrue(kr.canonical_arm([[0., 0.], [8., 20.], [0., 40.]])[2])   # still mirrored

    def test_head_length_is_the_same_tilted_on_two_head_shapes(self):
        yy, xx = np.mgrid[0:400, 0:400]
        for rx, ry in ((60, 80), (90, 70)):
            neck = np.array([200., 300.])
            lengths = []
            for deg in (0, 25, -30):
                a = math.radians(deg)
                axis = np.array([math.sin(a), -math.cos(a)])
                centre = neck + axis * ry
                u, v = xx - centre[0], yy - centre[1]
                along, across = u * axis[0] + v * axis[1], u * axis[1] - v * axis[0]
                lengths.append(kr.head_length((along / ry) ** 2 + (across / rx) ** 2 <= 1, neck))
            np.testing.assert_allclose(lengths, lengths[0], rtol=.02)
            self.assertAlmostEqual(lengths[0], 2 * ry, delta=2)

    def test_grip_tolerance_follows_arm_size(self):
        arm = lambda s: {'shoulder': [0, 0], 'elbow': [0, 50 * s], 'wrist': [0, 100 * s]}
        self.assertEqual(entry.grip_tolerance(arm(.5)), entry.GRIP_MIN_PX)
        self.assertAlmostEqual(entry.grip_tolerance(arm(4)), 8.)
        self.assertAlmostEqual(entry.grip_tolerance(arm(8)) / entry.grip_tolerance(arm(4)), 2.)

    def test_alpha_palette_layers_bind_like_rgba(self):
        stage = fixtures.FullTemplate.complete_fixture(self, 'slim')
        full.inspect(stage)
        joints = tp.read(stage / 'assembly_report.json')['joints']
        layers = {n: f'assembled_layers/{n}.png' for n in full.ORDER}
        palette_layers = dict(layers)
        for name in ('arm_far', 'leg_far'):
            # One colour on a transparent background, saved once as RGBA and once as a palette PNG.
            with Image.open(stage / layers[name]) as image:
                solid = np.asarray(image.convert('RGBA'))[..., 3] > 128
            rgba = np.zeros(solid.shape + (4,), np.uint8)
            rgba[solid] = (70, 90, 110, 255)
            Image.fromarray(rgba).save(stage / (name + '-rgba.png'))
            indexed = Image.fromarray(solid.astype(np.uint8), 'P')
            indexed.putpalette([0, 0, 0, 70, 90, 110])
            indexed.save(stage / (name + '-p.png'), transparency=0)
            layers[name], palette_layers[name] = name + '-rgba.png', name + '-p.png'
        tp.write(stage / 'rgba.json', dict(name='p', layers=layers, joints=joints, order=list(full.ORDER)))
        tp.write(stage / 'palette.json', dict(name='p', layers=palette_layers, joints=joints, order=list(full.ORDER)))
        entry.bind(stage / 'rgba.json', stage / 'rgba')
        entry.bind(stage / 'palette.json', stage / 'palette')
        self.assertEqual(tp.read(stage / 'rgba/character.json')['body'],
                         tp.read(stage / 'palette/character.json')['body'])
        for name in ('arm_far', 'leg_far'):
            with Image.open(stage / 'rgba/layers' / (name + '.png')) as a, \
                    Image.open(stage / 'palette/layers' / (name + '.png')) as b:
                np.testing.assert_array_equal(np.asarray(a), np.asarray(b))
        Image.new('RGB', (40, 40)).save(stage / 'opaque.png')
        layers['head'] = 'opaque.png'
        tp.write(stage / 'opaque.json', dict(name='p', layers=layers, joints=joints, order=list(full.ORDER)))
        with self.assertRaisesRegex(ValueError, 'alpha channel'):
            entry.bind(stage / 'opaque.json', stage / 'opaque')


if __name__ == '__main__':
    unittest.main()
