"""Phase-aware pose handovers, not proof of contact-constrained locomotion."""
import math
import unittest
import sys
from pathlib import Path
from test_natural_walk_profile import body_fixture
from sprite_anim.motions import build_clips
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walk_transition_diagnostic import PhaseTransition, bind_idle, transition_from, transition_to
from sprite_anim.rig import solve


class WalkTransitions(unittest.TestCase):
    def clips(self, **kw):
        b = body_fixture(**kw)
        clips = build_clips(body=b, gait={'walk': {'profile': 'natural_walk_v1'}})
        bind_idle(clips['idle'], b)
        return b, clips

    def assert_seam(self, clip, t, body):
        eps = 1e-6
        a, b, c = [solve(clip.sample(t+d), body) for d in (-eps, 0, eps)]
        for joint in ('hip', 'neck', 'wr_n', 'wr_f', 'kn_n', 'kn_f', 'an_n', 'an_f'):
            left = [(b[joint][k]-a[joint][k])/eps for k in (0, 1)]
            right = [(c[joint][k]-b[joint][k])/eps for k in (0, 1)]
            self.assertLess(math.dist(a[joint], c[joint]), .001, joint)
            self.assertLess(math.dist(left, right), .03, (t, joint, left, right))

    def test_diagnostic_blend_arbitrary_phase_start_stop_preserve_solved_positions_and_velocities(self):
        for long_boot, unequal in ((False, False), (True, False), (True, True)):
            body, clips = self.clips(long_boot=long_boot, unequal=unequal)
            idle, walk = clips['idle'], clips['walk']
            for phase in (0., .037, .1, .25, .5, .6, .75, .95, 1.29):
                for duration in (.12, .25, .51):
                    for clip in (transition_from(walk, idle, .71, phase*walk.duration, duration),
                                 transition_to(walk, idle, phase*walk.duration, .71, duration)):
                        self.assertEqual(clip.sample(0), clip.source.sample(clip.source_time))
                        for t in (clip.duration, clip.duration+1.42):
                            self.assertEqual(clip.sample(t), clip.target.sample(clip.target_time+t))
                        for t in (0, clip.duration):
                            self.assert_seam(clip, t, body)

    def test_diagnostic_blend_interrupted_start_can_reverse_without_freezing_or_restart(self):
        body, clips = self.clips(long_boot=True, unequal=True)
        idle, walk = clips['idle'], clips['walk']
        start = transition_from(walk, idle, .47, .37, .4)
        for interrupted_at in (.001, .08, .231, .399):
            stop = PhaseTransition(start, idle, body, interrupted_at, .9, .3)
            self.assertEqual(stop.sample(0), start.sample(interrupted_at))
            self.assert_seam(stop, 0, body)
            self.assert_seam(stop, .3, body)
            restart = transition_from(walk, stop, .113, .37, .28)
            self.assert_seam(restart, 0, body)
            self.assert_seam(restart, .28, body)

    def test_diagnostic_blend_solver_parameter_and_movement_velocity_are_blended(self):
        body, clips = self.clips()
        idle, walk = clips['idle'], clips['walk']
        start = transition_from(walk, idle, .7, .2, .4)
        self.assertEqual(start.vel(0), idle.vel(.7))
        self.assertEqual(start.vel(.4), walk.vel(.6))
        self.assertAlmostEqual(start.vel(.2)[0], walk.speed/2)
        self.assertAlmostEqual(start.sample(.2)['_leg_soft'], (body.leg_soft+.997)/2)
        self.assertEqual(start.contacts(.2), {})
        self.assertEqual(start.contacts(.4), walk.contacts(.6))

    def test_diagnostic_blend_finite_dense_samples_and_fixed_bone_lengths(self):
        body, clips = self.clips(long_boot=True, unequal=True)
        for phase in (.04, .31, .59, .81):
            clip = transition_to(clips['walk'], clips['idle'], phase, .19)
            for i in range(101):
                p = clip.sample(clip.duration*i/100)
                self.assertTrue(all(math.isfinite(v) for v in p.values()))
                sk = solve(p, body)
                for side in 'nf':
                    for a, b, length in (('hip', 'kn', body.leg_bones(side)[0]),
                                         ('kn', 'an', body.leg_bones(side)[1])):
                        self.assertAlmostEqual(math.dist(sk[a+'_'+side], sk[b+'_'+side]), length)

    def test_diagnostic_blend_transition_rejects_other_actions_and_other_bodies(self):
        body, clips = self.clips()
        other_body, other = self.clips(scale=2.)
        for source in (clips['attack_1'], clips['run'], other['idle'], other['walk']):
            with self.assertRaisesRegex(ValueError, 'matching idle/body'):
                transition_from(clips['walk'], source, .2)

    def test_grounded_stop_resume_preserves_world_contacts_at_arbitrary_phase(self):
        from sprite_anim.rig import heel_world, toe_world
        for options in ({}, {'long_boot': True}, {'long_boot': True, 'unequal': True}):
            body, clips = self.clips(**options)
            walk = clips['walk']
            for phase in (0., .037, .1, .25, .5, .6, .75, .95, 1.29):
                stop = walk.stop(phase*walk.duration)
                self.assertGreaterEqual(stop.duration, .3-1e-12)
                self.assertLess(stop.duration, .3+walk.duration+1e-12)
                self.assertTrue(all(stop.contacts(stop.duration).values()))
                self.assertEqual(stop.sample(stop.duration), stop.sample(stop.duration+10))
                self.assertEqual(stop.hold().sample(17), stop.sample(stop.duration))
                self.assertEqual(stop.resume().sample(0), stop.sample(stop.duration))
                for ramp in (stop, stop.resume()):
                    self.assert_seam(ramp, 0, body)
                    self.assert_seam(ramp, ramp.duration, body)
                    eps = 1e-6
                    for frame in range(200):
                        t = frame*ramp.duration/200
                        a, b = solve(ramp.sample(t), body), solve(ramp.sample(t+eps), body)
                        for side, planted in ramp.contacts(t).items():
                            if not planted or not ramp.contacts(t+eps)[side]: continue
                            point = min((heel_world, toe_world), key=lambda fn: fn(a, side)[1])
                            p, q = point(a, side), point(b, side)
                            self.assertAlmostEqual(p[1], 0, delta=1e-8)
                            self.assertAlmostEqual(q[0]+ramp.displacement(t+eps),
                                                   p[0]+ramp.displacement(t), delta=1e-8)
                            self.assertGreaterEqual(ramp.phase_rate(t), 0)
                            self.assertLessEqual(ramp.phase_rate(t), 1)

    def test_constant_speed_root_injection_exposes_stop_sliding(self):
        from sprite_anim.rig import heel_world, toe_world
        body, clips = self.clips(long_boot=True, unequal=True)
        walk = clips['walk']; stop = walk.stop(.23)
        t = stop.duration*.8; eps = 1e-6
        a, b = solve(stop.sample(t), body), solve(stop.sample(t+eps), body)
        side = next(s for s, planted in stop.contacts(t).items() if planted)
        point = min((heel_world, toe_world), key=lambda fn: fn(a, side)[1])
        p,q = point(a,side),point(b,side)
        wrong_velocity = (q[0]-p[0])/eps + walk.speed
        self.assertGreater(abs(wrong_velocity), .8*walk.speed)
        correct_velocity = (q[0]-p[0]+stop.displacement(t+eps)-stop.displacement(t))/eps
        self.assertAlmostEqual(correct_velocity, 0., delta=1e-6)

    def test_settle_and_reverse_preserve_support_and_joint_continuity(self):
        from sprite_anim.motions import GroundedGaitHold
        from sprite_anim.rig import heel_world, toe_world
        for options in ({}, {'long_boot': True, 'unequal': True},
                        {'long_boot': True, 'unequal': True, 'scale': .35},
                        {'long_boot': True, 'unequal': True, 'scale': 2.8}):
            body, clips = self.clips(**options)
            walk = clips['walk']
            for phase in (.04, .05, .52, .55):
                hold = GroundedGaitHold(walk, phase*walk.duration)
                settle = hold.settle(.25)
                flat = settle.hold()
                reverse = flat.resume(.25)
                self.assertEqual(settle.sample(0), hold.sample(0))
                self.assertEqual(settle.sample(.25), flat.sample(0))
                self.assertEqual(reverse.sample(.25), hold.sample(0))
                self.assertEqual(reverse.resume().sample(0), hold.sample(0))
                self.assertEqual(reverse.hold().sample(0), hold.sample(0))
                for side in 'nf': self.assertEqual(flat.sample(0)['foot_'+side+'_p'], 0.)
                for clip in (settle, reverse):
                    for t in (0., clip.duration): self.assert_seam(clip, t, body)
                    baseline = solve(hold.sample(0), body)
                    for i in range(101):
                        t = i*clip.duration/100
                        sk = solve(clip.sample(t), body)
                        self.assertEqual(clip.displacement(t), 0.)
                        self.assertEqual(clip.vel(t), (0., 0.))
                        self.assertTrue(all(clip.contacts(t).values()))
                        for side in 'nf':
                            pitch = hold.sample(0)['foot_'+side+'_p']
                            point = heel_world if pitch > 0 else toe_world
                            self.assertLess(math.dist(point(sk,side),point(baseline,side)), 1e-8)
                            self.assertGreaterEqual(min(heel_world(sk,side)[1],toe_world(sk,side)[1]), -1e-8)
                        for key,value in reverse.sample(t).items():
                            self.assertAlmostEqual(value, settle.sample(clip.duration-t)[key], places=10)

    def test_settle_rejects_swing_support_and_unsafe_api_order(self):
        from sprite_anim.motions import GroundedGaitHold
        _, clips = self.clips()
        walk = clips['walk']
        with self.assertRaisesRegex(ValueError, 'double support'):
            GroundedGaitHold(walk, .3*walk.duration)
        for invalid in (0., -1., True, float('nan'), float('inf')):
            with self.assertRaisesRegex(ValueError, 'settle duration'):
                walk.standing().settle(invalid)
        settle = walk.standing().settle()
        with self.assertRaisesRegex(ValueError, 'reverse settle'):
            settle.resume()
        with self.assertRaisesRegex(ValueError, 'already settled'):
            settle.hold().settle()

    def test_production_exposes_only_grounded_transition_api(self):
        import sprite_anim.motions as motions
        clips = build_clips(body=body_fixture(), gait={'walk': {'profile': 'natural_walk_v1'}})
        self.assertFalse(hasattr(motions, 'PhaseTransition'))
        self.assertFalse(hasattr(clips['walk'], 'transition_from'))
        self.assertFalse(hasattr(clips['walk'], 'transition_to'))
        self.assertFalse(hasattr(clips['idle'], '_transition_body'))

    def test_grounded_clock_is_frame_rate_independent(self):
        _, clips = self.clips()
        for ramp in (clips['walk'].stop(.31), clips['walk'].standing().resume()):
            for count in (7, 24, 30, 60, 144):
                travel = sum(ramp.displacement((i+1)*ramp.duration/count)-
                             ramp.displacement(i*ramp.duration/count) for i in range(count))
                self.assertAlmostEqual(travel, ramp.displacement(ramp.duration))
            eps = 1e-5
            for t in (0., ramp.duration):
                left = (ramp.phase_rate(t)-ramp.phase_rate(t-eps))/eps
                right = (ramp.phase_rate(t+eps)-ramp.phase_rate(t))/eps
                self.assertAlmostEqual(left, right, delta=1e-6)

    def test_initial_locomotion_idle_is_grounded_and_resumes_continuously(self):
        body, clips = self.clips(long_boot=True, unequal=True)
        idle = clips['walk'].standing()
        self.assertTrue(all(idle.contacts(0).values()))
        self.assertEqual(idle.sample(0), idle.sample(100))
        start = idle.resume()
        self.assertEqual(start.sample(0), idle.sample(0))
        self.assert_seam(start, 0, body)
        self.assert_seam(start, start.duration, body)
        self.assertEqual(start.vel(0), (0., 0.))
        self.assertAlmostEqual(start.vel(start.duration)[0], clips['walk'].speed)

    def test_diagnostic_blend_reject_invalid_times_and_durations(self):
        body, clips = self.clips()
        for field, invalid in (('duration', (0, -1, True, float('inf'), float('nan'))),
                               ('source_time', (True, float('inf'), float('nan'))),
                               ('target_time', (True, float('inf'), float('nan')))):
            for v in invalid:
                args = dict(source_time=.1, target_time=.2, duration=.3)
                args[field] = v
                with self.assertRaisesRegex(ValueError, 'transition.'+field):
                    PhaseTransition(clips['walk'], clips['idle'], body, **args)


if __name__ == '__main__':
    unittest.main()
