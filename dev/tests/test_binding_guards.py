"""Fault injection for inferred bones, hand contact, rejection artifacts and transient QA."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
import layer_parts as lp
from sprite_anim import puppet_check as pc


class BindingGuards(unittest.TestCase):
    def test_supported_bones_on_two_scales_and_missing_middle(self):
        for scale in (1, 3):
            mask = np.zeros((120*scale, 80*scale), bool)
            mask[5*scale:110*scale, 30*scale:50*scale] = True
            pts = np.array([(40, 10), (40, 55), (40, 100)]) * scale
            lengths = lp.check_limb('arm_far', mask, pts)
            np.testing.assert_allclose(lengths, [45*scale]*2)
            mask[35*scale:75*scale] = False
            with self.assertRaisesRegex(lp.Rejected, 'arm_far:.*leaves'):
                lp.check_limb('arm_far', mask, pts)

    def test_collapsed_joint_and_nonfinite_rejected(self):
        for points in ([(10, 10), (10, 11), (10, 90)], [(10, 10), (np.nan, 50), (10, 90)]):
            with self.assertRaisesRegex(lp.Rejected, 'proportions'):
                lp.check_limb('leg_near', np.ones((100, 100), bool), points)

    def test_pair_detects_one_bad_segment_even_with_equal_total_length(self):
        lp.check_pair('arm', np.array([50, 50]), np.array([48, 52]))
        with self.assertRaisesRegex(lp.Rejected, 'arm: near/far bone'):
            lp.check_pair('arm', np.array([50, 50]), np.array([30, 70]))

    def test_weapon_contact_and_grip_on_two_scales(self):
        for scale in (1, 3):
            arm = np.zeros((120*scale, 100*scale), bool)
            arm[5*scale:96*scale, 40*scale:61*scale] = True
            joints = {k: np.array(p)*scale for k, p in dict(elbow=(50, 40), wrist=(50, 80), tip=(50, 95)).items()}
            weapon = np.zeros_like(arm)
            weapon[10*scale:110*scale, 49*scale:53*scale] = True
            lp.check_grip(arm, weapon, joints)
            with self.assertRaisesRegex(lp.Rejected, 'no contact'):
                lp.check_grip(arm, np.roll(weapon, 40*scale, axis=1), joints)
            # A blade can touch the fingers while the inferred pivot is in empty space.
            weapon[:] = False
            weapon[93*scale:96*scale, 40*scale:61*scale] = True
            with self.assertRaisesRegex(lp.Rejected, 'grip misses'):
                lp.check_grip(arm, weapon, joints)

    def test_rejected_bind_overwrites_previous_diagnostics(self):
        ref = np.zeros((32, 32, 4), np.uint8)
        state = {}
        with self.assertRaises(lp.Rejected):
            lp.bind(ref, {}, diagnostics=state)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'bind_report.json').write_text('{"status":"ok"}')
            Image.new('RGBA', (1, 1)).save(path/'layers_check.png')
            lp.save_diagnostics(folder, ref, state)
            report = json.loads((path/'bind_report.json').read_text())
            self.assertEqual(report['status'], 'rejected')
            self.assertIn('missing layers', report['reason'])
            with Image.open(path/'layers_check.png') as im:
                self.assertEqual(im.size, (32, 32))

    def test_registered_hand_measures_two_fist_proportions_and_scales(self):
        for scale in (1, 3):
            for reach, half_width in ((24, 6), (40, 10)):
                with self.subTest(scale=scale, reach=reach):
                    arm = np.zeros((160*scale, 160*scale), bool)
                    arm[20*scale:(80+reach)*scale, (80-half_width)*scale:(81+half_width)*scale] = True
                    hand = np.zeros_like(arm)
                    hand[80*scale:(80+reach)*scale] = arm[80*scale:(80+reach)*scale]
                    weapon = np.zeros_like(arm)
                    row = (80+reach-6)*scale
                    weapon[row:row+2*scale, 20*scale:140*scale] = True
                    joints = {k: np.array(p, float)*scale for k, p in
                              dict(elbow=(80, 20), wrist=(80, 80), tip=(80, 80+reach)).items()}
                    # The drawn handle crosses the palm, away from the old guessed pivot.
                    with self.assertRaisesRegex(lp.Rejected, 'grip misses'):
                        lp.check_grip(arm, weapon, joints)
                    grip = lp.measured_hand_grip(arm, weapon, joints, hand)
                    self.assertTrue((arm & hand & weapon)[int(grip[1]), int(grip[0])])
                    frame = lp.measured_grip_frame(grip, grip+np.array([40, -90])*scale, joints)
                    v = (joints['wrist']-joints['elbow'])*[1, -1]
                    mapped = v*frame['weapon_grip_along']+np.array([-v[1], v[0]])*frame['weapon_grip_across']
                    np.testing.assert_allclose(mapped, (grip-joints['wrist'])*[1, -1], atol=1e-10)

    def test_registered_hand_rejects_forearm_contact_and_displaced_hint(self):
        arm = np.zeros((120, 100), bool)
        arm[5:101, 40:61] = True
        hand = np.zeros_like(arm)
        hand[80:101, 40:61] = True
        joints = {k: np.array(p, float) for k, p in
                  dict(elbow=(50, 40), wrist=(50, 80), tip=(50, 100)).items()}
        weapon = np.zeros_like(arm)
        weapon[65:68, 20:80] = True
        with self.assertRaisesRegex(lp.Rejected, 'registered hand'):
            lp.measured_hand_grip(arm, weapon, joints, hand)
        weapon[:] = False
        weapon[90:93, 20:80] = True
        with self.assertRaisesRegex(lp.Rejected, 'registered hand'):
            lp.measured_hand_grip(arm, weapon, joints, np.roll(hand, 40, axis=1))

    def test_cli_writes_current_diagnostics_when_binding_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            ref = np.zeros((32, 32, 4), np.uint8)
            args = ['layer_parts.py', 'bind', '--image', 'unused.png',
                    '--layers', folder, '--out', folder]
            with patch.object(sys, 'argv', args), patch.object(lp, 'reference', return_value=ref), patch.object(lp, 'check_reference_review', return_value={}):
                with self.assertRaisesRegex(SystemExit, 'missing layers'):
                    lp.main()
            report = json.loads((Path(folder)/'bind_report.json').read_text())
            self.assertEqual(report['status'], 'rejected')
            self.assertTrue((Path(folder)/'bind_joints.png').is_file())

    def test_short_collapse_is_reported_despite_healthy_median(self):
        ratios = np.ones((30, 2))
        ratios[8:12, 0] = 0.1
        self.assertGreater(np.median(ratios), pc.ARM_SPACING_SHARE)
        self.assertEqual(pc.spacing_fault(ratios, 30), 8)
        ratios[9:12] = 1
        self.assertIsNone(pc.spacing_fault(ratios, 30))

    def test_motion_qa_reports_clip_and_start_frame(self):
        from types import SimpleNamespace
        from sprite_anim.rig import Body
        from sprite_anim.motions import build_clips
        arms = [SimpleNamespace(name=name, rest=rest, radius=1) for name, rest in (
            ('arm_near', [(0, 0), (0, 10), (0, 20)]),
            ('arm_far', [(10, 0), (10, 10), (10, 20)]))]
        puppet = SimpleNamespace(layers=arms, px_per_unit=1, meshes=lambda *a: [])
        renderer = SimpleNamespace(art=SimpleNamespace(puppet=puppet, body=Body()),
                                   size=128, ss=1, unit=1., cloth_at=lambda *a: {})
        values = [np.array([10., 10.])] + [np.array([1., 1.])]*4 + [np.array([10., 10.])]*25
        with patch.object(pc, 'arm_spacing', side_effect=values):
            errors = pc.check_motion(renderer, build_clips()['idle'], 29, 30)
        self.assertTrue(any('arm_spacing: idle' in e and 'frame 0' in e for e in errors), errors)
