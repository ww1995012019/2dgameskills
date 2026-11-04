"""A grip is a shared orientation and pivot, not merely two coincident points."""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sprite_anim.rig import Body, full_pose, solve
from sprite_anim.mathx import rot
from sprite_anim.puppet import lock_tip


class WeaponHandFrame(unittest.TestCase):
    def test_two_proportions_share_palm_and_handle_frame_across_motion(self):
        for length, along, across in [(12., .30, .12), (19., .44, -.20)]:
            for fore in (-35., 5., 55.):
                for wrist in (-20., 0., 20.):
                    b = Body(lo_arm=length, weapon_hand_angle=17.,
                             weapon_grip_along=along, weapon_grip_across=across)
                    sk = solve(full_pose(dict(arm_n_up=fore-25., arm_n_lo=25.,
                                              wep=17.+wrist)), b)
                    self.assertAlmostEqual(sk['wep_a'] - sk['fa_n'],17.+wrist)
                    self.assertAlmostEqual(sk['hand_n_turn'], wrist)
                    v = np.subtract(sk['wr_n'],sk['el_n'])
                    offset = v*along+np.array([-v[1],v[0]])*across
                    expected = np.array(sk['wr_n'])+rot(offset,-wrist)
                    np.testing.assert_allclose(sk['weapon_grip'],expected,atol=1e-10)

    def test_distal_mesh_and_weapon_palm_share_exact_transform(self):
        # Fist points lie distal to the wrist, so the transition only affects forearm.
        layer = SimpleNamespace(rest=[np.array([0.,0.]),np.array([0.,100.])],
                                vx=np.array([10.,20.]),vy=np.array([130.,140.]),
                                offset=np.array([0.,0.]), radius=15.)
        points=[np.array([20.,30.]),np.array([20.,130.])]
        for turn in (-25.,0.,25.):
            vertices=lock_tip(layer,np.zeros((2,2)),points,1.,turn=math.radians(turn))
            for i,(x,y) in enumerate(zip(layer.vx,layer.vy)):
                # rot is clockwise in y-up; screen matrix is opposite convention.
                expected=np.array(points[-1])+rot((x,y-100.),-turn)
                np.testing.assert_allclose(vertices[i],expected,atol=1e-10)

    def test_ground_correction_moves_hand_with_blade(self):
        b=Body(weapon_hand_angle=15.,weapon_front=45.,weapon_grip_along=.4,
               weapon_grip_across=.15)
        sk=solve(full_pose(dict(wep=15.)),b)
        self.assertGreater(abs(sk['hand_n_turn']),1.)
        self.assertAlmostEqual(sk['hand_n_turn'],sk['wep_a']-sk['fa_n']-15.)
        tip_y=sk['weapon_grip'][1]-math.cos(math.radians(sk['wep_a']))*45.
        self.assertGreaterEqual(tip_y,b.weapon_margin-1e-6)

    def test_extreme_authored_wrist_is_limited_and_reported(self):
        sk=solve(full_pose(dict(wep=130.)),Body(weapon_hand_angle=10.))
        self.assertLessEqual(abs(sk['hand_n_turn']),35.)
        self.assertGreater(max(sk['excess']),0.)

    def test_legacy_rig_keeps_zero_hand_turn_and_original_palm(self):
        sk=solve(full_pose(dict(wep=110.)),Body())
        self.assertEqual(sk['hand_n_turn'],0.)
        expected=np.array(sk['wr_n'])+.14*np.subtract(sk['wr_n'],sk['el_n'])
        np.testing.assert_array_equal(expected,sk['weapon_grip'])

    def test_binding_opt_in_exports_source_relative_angle(self):
        import template_full_character as full
        import template_puppet as tp
        import test_template_full_character as fixtures
        import bind_known_joints as entry
        for profile in tp.PROFILES:
            stage=fixtures.FullTemplate.complete_fixture(self, profile)
            full.inspect(stage)
            report=tp.read(stage/'assembly_report.json')
            job=dict(name='Grasp frame '+profile, order=full.ORDER,
                     layers={n:f'assembled_layers/{n}.png' for n in full.ORDER},
                     joints=report['joints'], weapon_hand_binding=True)
            tp.write(stage/'hand-frame.json',job)
            entry.bind(stage/'hand-frame.json',stage/'grasp-frame')
            spec=tp.read(stage/'grasp-frame/character.json')
            wr,el=spec['puppet']['rest_arm']['n']
            fore=math.degrees(math.atan2(wr[0]-el[0],wr[1]-el[1]))
            self.assertAlmostEqual(spec['body']['weapon_hand_angle'],
                                   spec['puppet']['rest_angles']['wep_a']-fore)
            self.assertTrue(spec['puppet']['layers']['arm_near']['tip_lock'])

    def test_low_carry_is_opt_in_scaled_and_rejects_conflicting_overrides(self):
        from sprite_anim.motions import NaturalWalk, build_clips
        for length in (9.,17.):
            b=Body(up_arm=length,lo_arm=length*1.2,weapon_hand_angle=15.)
            c=NaturalWalk(b,1.,carry={'arm_n':[-4,0,35,0]})
            original=c.arm_n
            c.low_weapon_carry()
            self.assertLess(c.arm_n[1],original[1])
            self.assertLess(c.arm_n[3],original[3])
            self.assertLess(c.arm_n[0],original[0])
            self.assertEqual(c.arm_n[2],original[2])
        for walk in ({'profile':'natural_walk_v1','held_weapon_carry':'wrong'},
                     {'held_weapon_carry':'low'},
                     {'profile':'natural_walk_v1','held_weapon_carry':'low','arm_n':[0,1,20,1]}):
            with self.assertRaisesRegex(ValueError,'held_weapon_carry'):
                build_clips(body=Body(weapon_hand_angle=15.),gait={'walk':walk})
        with self.assertRaisesRegex(ValueError,'weapon_hand_angle'):
            build_clips(body=Body(),gait={'walk':{'profile':'natural_walk_v1','held_weapon_carry':'low'}})

    def test_invalid_hand_angle_is_rejected(self):
        for value in (True,float('nan'),float('inf'),'15'):
            with self.assertRaisesRegex(ValueError,'weapon_hand_angle'):
                Body.from_spec(dict(weapon_hand_angle=value))

if __name__=='__main__':unittest.main()
