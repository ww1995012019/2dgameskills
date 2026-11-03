"""Attached rear equipment must not enlarge the hidden waist completion."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
import layer_parts as lp

class EquippedTorsoCore(unittest.TestCase):
    def test_backpack_cannot_widen_core_on_two_builds(self):
        for center,width in ((150,32),(180,56)):
            torso=np.zeros((300,360),bool);torso[50:240,center-width:center+width+1]=True
            waist=np.array([center,180.]);base=lp.waist_half_width(torso,waist)
            packed=torso.copy();packed[90:210,center-width-70:center-width+1]=True
            self.assertLessEqual(lp.waist_half_width(packed,waist),base)
            half=lp.HIPS_WIDTH*lp.waist_half_width(packed,waist)
            self.assertGreaterEqual(center-half,center-width)
    def test_disjoint_hood_uses_neck_root_instead_of_rear_equipment(self):
        for offset in (0,40):
            t=np.zeros((300,360),bool);t[100:240,100+offset:220+offset]=True
            t[50:110,90+offset:130+offset]=True
            t[50:110,160+offset:194+offset]=True
            root=lp.torso_attachment(t);row,cols,_=lp.neck_core(t)
            self.assertAlmostEqual(root[0],cols.mean());self.assertEqual(root[1],row)
            self.assertGreater(root[0],160+offset)
    def test_single_neck_keeps_existing_attachment(self):
        t=np.zeros((250,250),bool);t[30:200,100:140]=True
        old,_=lp.root_and_tip(t);np.testing.assert_equal(lp.torso_attachment(t),old)

if __name__=='__main__':unittest.main()
