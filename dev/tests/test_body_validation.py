"""Invalid reusable body data must fail at loading, not corrupt a later action."""
import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'game-sprite-animator/scripts'))
from sprite_anim.rig import Body, solve, full_pose

class BodyValidation(unittest.TestCase):
    def test_nonfinite_invalid_lengths_and_unsafe_soft_ik_are_rejected(self):
        for key, value in [('hip_h',float('nan')),('thigh',-1),('thigh_f',0),
                           ('lo_arm_f',float('inf')),('leg_soft',1),('leg_soft',0),
                           ('leg_soft',-1),('head_size',0),('chest_len',None),
                           ('hip_w',-2),('bulk',True),('foot_wrap',1),
                           ('from_spec',4),('pelvis_lenght',10)]:
            with self.subTest(key=key,value=value), self.assertRaisesRegex(ValueError,'body.'+key):
                Body.from_spec({key:value})
    def test_joint_seats_and_sole_contacts_require_two_finite_coordinates(self):
        for key in ('sh_n_at','hip_f_at','foot_n_heel','foot_f_ball'):
            for value in ([1],[1,2,3],[1,float('nan')],['1',2],True):
                with self.subTest(key=key,value=value), self.assertRaisesRegex(ValueError,key):
                    Body.from_spec({key:value})
    def test_optional_lengths_and_zero_neck_are_valid(self):
        body=Body.from_spec(dict(thigh_f=None,neck_len=0,sh_n_at=[-2,18],foot_wrap=True))
        self.assertEqual(body.leg_bones('f'),body.leg_bones('n'))
        self.assertTrue(all(__import__('math').isfinite(x) for x in solve(full_pose({}),body)['hip']))
    def test_checked_in_character_bodies_remain_accepted(self):
        for file in (ROOT/'game-sprite-animator/assets/characters').rglob('*.json'):
            data=json.loads(file.read_text())
            if isinstance(data,dict) and 'body' in data:
                with self.subTest(file=file):Body.from_spec(data['body'])

if __name__=='__main__':unittest.main()
