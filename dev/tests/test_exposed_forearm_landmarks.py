"""Visible forearm material locates an elbow independently of sleeve folds."""
import sys
import unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
import layer_parts as lp

class ExposedForearmLandmarks(unittest.TestCase):
    def arm(self,scale=1,rear=False,covered=False):
        points=[(170,60),(115,175),(70,270)] if rear else [(170,60),(230,185),(325,145)]
        shoulder,elbow,wrist=np.array(points,dtype=float)*scale
        art=Image.new('RGBA',(400*scale,360*scale));d=ImageDraw.Draw(art)
        cloth=(40,45,58,255);skin=(230,155,97,255)
        d.line([tuple(shoulder),tuple(elbow)],fill=cloth,width=52*scale)
        r=26*scale;d.ellipse((shoulder[0]-r,shoulder[1]-r,shoulder[0]+r,shoulder[1]+r),fill=cloth)
        d.line([tuple(elbow),tuple(wrist)],fill=cloth if covered else skin,width=34*scale)
        direction=(wrist-elbow)/np.linalg.norm(wrist-elbow)
        cuff=wrist-direction*8*scale
        d.line([tuple(cuff-direction*10*scale),tuple(cuff+direction*6*scale)],fill=cloth,width=42*scale)
        center=wrist+direction*18*scale;rr=20*scale
        d.ellipse((center[0]-rr,center[1]-rr,center[0]+rr,center[1]+rr),fill=skin)
        hint=Image.new('1',art.size);ImageDraw.Draw(hint).ellipse((center[0]-rr,center[1]-rr,center[0]+rr,center[1]+rr),fill=1)
        joints=dict(shoulder=shoulder,elbow=(shoulder+elbow)*.5,wrist=wrist,tip=center+direction*rr)
        return np.asarray(art),np.asarray(hint,dtype=bool),joints,elbow
    def test_elbow_follows_exposed_forearm_on_two_builds(self):
        for scale in (1,2):
            for rear in (False,True):
                art,hand,joints,truth=self.arm(scale,rear)
                inferred=lp.exposed_elbow(art,hand,joints)
                self.assertIsNotNone(inferred)
                self.assertLess(np.linalg.norm(inferred-truth),20*scale)
                self.assertGreater(np.linalg.norm(joints['elbow']-truth),40*scale)
    def test_covered_forearm_cannot_be_invented_from_small_hand(self):
        for rear in (False,True):
            art,hand,joints,truth=self.arm(rear=rear,covered=True)
            self.assertIsNone(lp.exposed_elbow(art,hand,joints))
    def test_no_hint_preserves_legacy_shape_landmark(self):
        a,h,p,_=self.arm();b,k,q,_=self.arm(rear=True)
        n,f,methods=lp.paired_arm_landmarks(a,b,None,None,p,q)
        np.testing.assert_equal(n['elbow'],p['elbow']);np.testing.assert_equal(f['elbow'],q['elbow'])
        self.assertEqual(methods,{'near':'medial','far':'medial'})

if __name__=='__main__':unittest.main()
