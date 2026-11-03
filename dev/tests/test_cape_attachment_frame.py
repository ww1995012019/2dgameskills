"""Cape seams stay on the upper torso when the spine bends on different builds."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
import layer_parts as lp
from sprite_anim.mathx import rot

class CapeAttachmentFrame(unittest.TestCase):
    def test_sewn_root_tracks_thorax_instead_of_pelvis(self):
        # Tall/slim and short/broad torsos. Source coordinates are arbitrary;
        # articulation must preserve attachment in either build and orientation.
        for hip,waist,neck in [((200,500),(200,400),(200,190)),((380,650),(360,510),(320,340))]:
            hip,waist,neck=map(lambda p:np.asarray(p,dtype=float),(hip,waist,neck))
            spine=neck-waist;root=waist+spine*.7+np.array([-55.,0.])
            body_rest=lp.angle_up(hip,waist);chest_rest=lp.angle_up(waist,neck)
            joint,frame,base,rest_rot=lp.trailing_frame(root,hip,waist,neck,body_rest,chest_rest)
            local=rot(tuple((root-base)*[1,-1]),-rest_rot)
            for chest_turn in (-45,0,55):
                angles={'body_rot':body_rest,'chest_rot':chest_rest+chest_turn}
                current=waist*[1,-1]+rot(local,angles[frame])
                expected=waist*[1,-1]+rot(tuple((root-waist)*[1,-1]),chest_turn)
                np.testing.assert_allclose(current,expected,atol=1e-9)
                self.assertEqual(joint,'waist')
    def test_lower_sash_still_follows_pelvis(self):
        hip=np.array([200.,500.]);waist=np.array([200.,400.]);neck=np.array([200.,200.])
        joint,frame,base,rest_rot=lp.trailing_frame(np.array([140.,450.]),hip,waist,neck,0.,12.)
        self.assertEqual((joint,frame,rest_rot),('hip','body_rot',0.))
        np.testing.assert_equal(base,hip)

if __name__=='__main__':unittest.main()
