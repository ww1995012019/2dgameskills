"""A bound free arm must retain its carried side through idle and handovers."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
from sprite_anim.constraints import LIMITS
from sprite_anim.motions import CH, build_clips
from sprite_anim.rig import Body, full_pose, solve


class IdleCarriedArm(unittest.TestCase):
    def profiles(self):
        # Different shoulder seats, arm lengths and reference elbow bends.
        return (
            (Body(sh_f_at=(-3.5, 19.8), up_arm=9.6, lo_arm=11.9,
                  pelvis_len=14.2, chest_len=23.9), [-19.4, 1.8, 1.86, 2.6]),
            (Body(sh_f_at=(-6, 22.5), up_arm=14.6, lo_arm=12.9,
                  pelvis_len=12.5, chest_len=21), [-23.8, 1.8, 8.02, 2.6]),
        )

    def test_free_hands_remain_behind_the_waist_on_different_bodies(self):
        for body, arm in self.profiles():
            with self.subTest(arm=arm):
                old = build_clips(body=body)['idle']
                new = build_clips(body=body, gait={'idle': {'arm_f': arm}})['idle']
                old_sk = solve(full_pose(old.sample(old.duration * 0.49)), body)
                self.assertGreater(old_sk['wr_f'][0], old_sk['waist'][0])
                for i in range(73):
                    t = new.duration * i / 72
                    sk = solve(full_pose(new.sample(t)), body)
                    self.assertLess(sk['wr_f'][0], sk['waist'][0] - 1)
                    # Keep the actual weapon hand and body untouched.
                    before = solve(full_pose(old.sample(t)), body)
                    self.assertEqual(sk['wr_n'], before['wr_n'])
                    self.assertEqual(sk['hip'], before['hip'])
                    self.assertGreaterEqual(new.sample(t)['arm_f_lo'], LIMITS['elbow'][0])
                    self.assertLessEqual(new.sample(t)['arm_f_lo'], LIMITS['elbow'][1])

    def test_near_straight_elbow_breathes_without_reversing(self):
        for bend in (0, 1.86, 167, 168):
            clips = build_clips(style={'bounce': 2},
                                gait={'idle': {'arm_f': [-20, 1.8, bend, 2.6]}})
            idle = clips['idle']
            values = [idle.sample(idle.duration * i / 100)['arm_f_lo'] for i in range(101)]
            self.assertGreaterEqual(min(values), LIMITS['elbow'][0] - 1e-9)
            self.assertLessEqual(max(values), LIMITS['elbow'][1] + 1e-9)
            self.assertAlmostEqual(idle.sample(0)['arm_f_lo'], idle.sample(idle.duration)['arm_f_lo'])
            if 0 < bend < 168:
                self.assertGreater(max(values) - min(values), 0.1)
            look = build_clips(body=Body(), gait={'idle': {'arm_f': [-20, 1.8, bend, 2.6]}})['idle_look']
            values = [look.sample(look.duration * i / 100)['arm_f_lo'] for i in range(101)]
            self.assertGreaterEqual(min(values), LIMITS['elbow'][0] - 1e-9)
            self.assertLessEqual(max(values), LIMITS['elbow'][1] + 1e-9)

    def test_action_endpoints_share_the_new_idle_pose(self):
        clips = build_clips(gait={'idle': {'arm_f': [-19.4, 1.8, 1.86, 2.6]}})
        idle0 = clips['idle'].sample(0)
        for name in ('attack_1', 'cast'):
            clip = clips[name]
            for channel in ('arm_f_up', 'arm_f_lo'):
                index = CH.index(channel)
                self.assertEqual(clip.curve.v[0, index], idle0[channel])
                self.assertEqual(clip.curve.v[-1, index], idle0[channel])
            self.assertEqual(clip.next, 'idle')

    def test_empty_profile_preserves_existing_clips(self):
        old, new = build_clips(), build_clips(gait={'idle': {}})
        for name in old:
            for frac in (0, 0.2, 0.6, 1):
                self.assertEqual(old[name].sample(old[name].duration * frac),
                                 new[name].sample(new[name].duration * frac))

    def test_invalid_profiles_are_rejected(self):
        for profile in ({'bob': 1}, {'arm_f': [1, 2, 3]},
                        {'arm_f': [1, -2, 3, 4]}, {'arm_f': [1, 2, -3, 4]},
                        {'arm_f': [1, 2, 169, 4]}, {'arm_f': [1, 2, 3, math.inf]},
                        {'arm_f': [True, 2, 3, 4]}):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                build_clips(gait={'idle': profile})


if __name__ == '__main__':
    unittest.main()
