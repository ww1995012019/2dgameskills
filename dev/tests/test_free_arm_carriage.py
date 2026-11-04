"""Newly bound free walking arms use measured chains, not a forward weapon pose."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
from known_joint_rig import free_arm_carriage
from sprite_anim.rig import Body, full_pose, solve

class FreeArmCarriage(unittest.TestCase):
    def test_measured_chain_hangs_beneath_own_shoulder(self):
        for upper,lower in ((14,14),(9,15),(18,10)):
            for elbow in (5,25,50,85):
                for lean in (-10,0,8,25):
                    angle=free_arm_carriage(upper,lower,elbow,lean)
                    a=math.radians(angle-lean);b=a+math.radians(elbow)
                    self.assertAlmostEqual(upper*math.sin(a)+lower*math.sin(b),0,places=10)
                    self.assertGreater(upper*math.cos(a)+lower*math.cos(b),0)
    def test_neutral_carriage_is_scale_invariant(self):
        for scale in (.25,1,4):
            self.assertEqual(free_arm_carriage(10*scale,15*scale,35,8),
                             free_arm_carriage(10,15,35,8))
    def test_runtime_keeps_measured_lengths_and_near_hand(self):
        body=Body(up_arm_f=12,lo_arm_f=16)
        reference=full_pose({'arm_f_lo':35,'pelvis':0,'spine':8})
        before=solve(reference,body)
        reference['arm_f_up']=free_arm_carriage(12,16,35,8)
        after=solve(reference,body)
        self.assertEqual(after['wr_n'],before['wr_n'])
        self.assertAlmostEqual(math.dist(after['sh_f'],after['el_f']),12)
        self.assertAlmostEqual(math.dist(after['el_f'],after['wr_f']),16)
        self.assertAlmostEqual(after['sh_f'][0],after['wr_f'][0],places=8)

if __name__=='__main__':unittest.main()
