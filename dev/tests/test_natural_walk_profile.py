"""Body-derived upright walking; numerical checks do not replace visual approval."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
from sprite_anim.motions import Gait, NaturalWalk, build_clips
from sprite_anim.rig import Body, heel_world, solve, toe_world


def body_fixture(scale=1., long_boot=False, unequal=False):
    leg = (20., 17.) if unequal else (18.5, 18.5)
    far = (18.8, 17.7) if unequal else leg
    ball = 10.5 if long_boot else 6.5
    return Body(thigh=leg[0]*scale, shin=leg[1]*scale,
                thigh_f=far[0]*scale, shin_f=far[1]*scale,
                up_arm=11.*scale, lo_arm=14.*scale,
                up_arm_f=12.*scale, lo_arm_f=13.*scale,
                hip_h=43.*scale, ankle_h=5.*scale, hip_w=2.*scale,
                pelvis_len=11.*scale, chest_len=21.*scale, neck_len=0.,
                sh_w=2.4*scale, sh_n_at=(-4.*scale, 16.*scale),
                sh_f_at=(-5.*scale, 16.*scale),
                hip_n_at=(1.2*scale, 0.),
                hip_f_at=(-1.2*scale, (sum(far)-sum(leg))*scale),
                foot_n_heel=(-4.5*scale, -5.*scale),
                foot_n_ball=(ball*scale, -5.*scale),
                foot_f_heel=(-4.5*scale, -5.*scale),
                foot_f_ball=((ball+.4)*scale, -5.*scale))


def natural(body):
    return build_clips(body=body, gait={'walk': {'profile': 'natural_walk_v1'}})['walk']


def knee_angle(sk, side, body):
    a, b = body.leg_bones(side)
    reach = math.dist(sk['hip_'+side], sk['an_'+side])
    return 180 - math.degrees(math.acos(max(-1., min(1., (a*a+b*b-reach*reach)/(2*a*b)))))


class NaturalWalkProfile(unittest.TestCase):
    def test_opt_in_does_not_change_default_gaits_or_other_actions(self):
        legacy = build_clips(body=Body())
        fitted = build_clips(body=Body(), gait={'walk': {'profile': 'natural_walk_v1'}})
        self.assertIs(type(legacy['walk']), Gait)
        self.assertIs(type(fitted['walk']), NaturalWalk)
        for name in legacy:
            if name != 'walk':
                for phase in (0., .13, .55, .93):
                    self.assertEqual(legacy[name].sample(phase*legacy[name].duration),
                                     fitted[name].sample(phase*fitted[name].duration))
        with self.assertRaisesRegex(ValueError, 'unknown profile'):
            build_clips(gait={'walk': {'profile': 'unrecognized'}})

    def test_natural_period_matches_24_and_30_fps_without_rounding_drift(self):
        clip = natural(body_fixture())
        for fps, frames in ((24, 20), (30, 25)):
            self.assertEqual(round(clip.duration*fps), frames)
            self.assertAlmostEqual(clip.duration, frames/fps)

    def test_planted_soles_are_stationary_in_world_space_and_grounded(self):
        for long_boot, unequal in ((False, False), (True, False), (True, True)):
            body = body_fixture(long_boot=long_boot, unequal=unequal)
            clip = natural(body)
            eps = clip.duration * 1e-6
            for frame in range(240):
                t = clip.duration * frame / 240
                now = solve(clip.sample(t), body)
                after = solve(clip.sample(t+eps), body)
                for side, planted in clip.contacts(t).items():
                    if not planted or not clip.contacts(t+eps)[side]:
                        continue
                    point = min((heel_world, toe_world), key=lambda fn: fn(now, side)[1])
                    a, b = point(now, side), point(after, side)
                    with self.subTest(boot=long_boot, unequal=unequal, frame=frame, side=side):
                        self.assertAlmostEqual(a[1], 0., delta=1e-8)
                        self.assertAlmostEqual((b[0]-a[0])/eps + clip.speed, 0., delta=1e-6)

    def test_support_extends_and_swing_flexes_for_different_proportions(self):
        for long_boot, unequal in ((False, False), (True, False), (True, True)):
            body = body_fixture(long_boot=long_boot, unequal=unequal)
            clip = natural(body)
            stance, swing = [], []
            for frame in range(240):
                t = clip.duration * frame / 240
                sk = solve(clip.sample(t), body)
                for side, contact in clip.contacts(t).items():
                    (stance if contact else swing).append(knee_angle(sk, side, body))
                    for start, end, length in (('hip', 'kn', body.leg_bones(side)[0]),
                                               ('kn', 'an', body.leg_bones(side)[1]),
                                               ('sh', 'el', body.arm_bones(side)[0]),
                                               ('el', 'wr', body.arm_bones(side)[1])):
                        self.assertAlmostEqual(math.dist(sk[start+'_'+side], sk[end+'_'+side]), length)
            self.assertLess(sum(stance)/len(stance), 24.)
            self.assertLess(max(stance), 42.)
            self.assertGreater(max(swing), 45.)
            self.assertLess(max(swing), 80.)

    def test_scale_invariance_includes_footpaths_height_arms_and_speed(self):
        reference_body = body_fixture(long_boot=True, unequal=True)
        reference = natural(reference_body)
        for scale in (.35, 2.8):
            body = body_fixture(scale=scale, long_boot=True, unequal=True)
            clip = natural(body)
            self.assertAlmostEqual(clip.speed, reference.speed*scale)
            for frame in range(20):
                t = frame*clip.duration/20
                a, b = solve(reference.sample(t), reference_body), solve(clip.sample(t), body)
                for joint in ('hip', 'neck', 'wr_n', 'wr_f', 'kn_n', 'kn_f', 'an_n', 'an_f'):
                    for axis in (0, 1):
                        self.assertAlmostEqual(a[joint][axis]*scale, b[joint][axis], places=8)

    def test_loop_and_contact_changes_preserve_joint_velocity(self):
        body = body_fixture(long_boot=True, unequal=True)
        clip = natural(body)
        eps = 1e-6
        for phase in (0., .1, .5, .6, 1.):
            t = phase*clip.duration
            before, now, after = (solve(clip.sample(t+d), body) for d in (-eps, 0., eps))
            for joint in ('hip', 'wr_n', 'wr_f', 'kn_n', 'kn_f', 'an_n', 'an_f'):
                left = [(now[joint][k]-before[joint][k])/eps for k in (0, 1)]
                right = [(after[joint][k]-now[joint][k])/eps for k in (0, 1)]
                self.assertLess(math.dist(left, right), .03, (phase, joint))
        self.assertEqual(clip.sample(0.), clip.sample(clip.duration))

    def test_both_arms_move_without_large_free_hand_sweep(self):
        body = body_fixture(long_boot=True)
        clip = natural(body)
        motion = {s: [] for s in 'nf'}
        for frame in range(120):
            sk = solve(clip.sample(frame*clip.duration/120), body)
            for side in 'nf':
                motion[side].append(sk['wr_'+side][0] - sk['sh_'+side][0])
        for side in 'nf':
            span = max(motion[side])-min(motion[side])
            self.assertGreater(span, .2*sum(body.arm_bones(side)))
            self.assertLess(span, .5*sum(body.arm_bones(side)))

    def test_legacy_soft_ik_injection_would_detach_a_planted_foot(self):
        body = body_fixture(long_boot=True)
        clip = natural(body)
        pose = clip.sample(clip.duration*.3)
        supported = solve(pose, body)
        pose.pop('_leg_soft')
        detached = solve(pose, body)
        self.assertAlmostEqual(min(heel_world(supported, 'n')[1], toe_world(supported, 'n')[1]), 0.)
        self.assertGreater(min(heel_world(detached, 'n')[1], toe_world(detached, 'n')[1]), .1)

    def test_toe_directly_below_ankle_remains_finite(self):
        body = Body(foot_n_ball=(0., -5.), foot_f_ball=(0., -5.))
        clip = natural(body)
        self.assertTrue(all(math.isfinite(v) for v in clip.sample(.2).values()))

    @unittest.expectedFailure
    def test_direct_idle_walk_switch_is_not_yet_a_continuous_transition(self):
        """Known gap: sprite player jumps to frame 0, with no start/stop scheduler.

        A continuous gait loop does not imply continuous idle-to-walk or an
        arbitrary-phase stop. Keep this separate from the gait loop assertions.
        """
        errors = []
        for long_boot, unequal in ((False, False), (True, False), (True, True)):
            body = body_fixture(long_boot=long_boot, unequal=unequal)
            clips = build_clips(body=body, gait={'walk': {'profile': 'natural_walk_v1'}})
            idle = solve(clips['idle'].sample(0.), body)
            for phase in (0., .25, .5, .75, .95):
                walk = solve(clips['walk'].sample(phase*clips['walk'].duration), body)
                errors.extend(math.dist(idle[j], walk[j]) for j in
                              ('hip', 'neck', 'wr_n', 'wr_f', 'an_n', 'an_f'))
        self.assertLess(max(errors), .25)


if __name__ == '__main__':
    unittest.main()
