"""Raised hood islands cannot stand in for the actual neck attachment."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
import layer_parts as lp

class HoodNeckContact(unittest.TestCase):
    def build(self,scale=1,broad=False):
        torso=np.zeros((240*scale,240*scale),bool)
        def fill(mask,x0,y0,x1,y1):mask[y0*scale:y1*scale,x0*scale:x1*scale]=True
        neck_width=35 if broad else 24
        fill(torso,70,85,180,210)
        fill(torso,65,55,105,95) # high rear hood island
        fill(torso,125,55,125+neck_width,95)
        head=np.zeros_like(torso)
        fill(head,113,10,180,60)
        fill(head,122,45,128+neck_width,92)
        return head,torso
    def test_two_builds_and_scales_keep_real_neck_contact(self):
        for scale in (1,3):
            for broad in (False,True):
                with self.subTest(scale=scale,broad=broad):
                    head,torso=self.build(scale,broad)
                    self.assertGreaterEqual(lp.neck_coverage(head,torso),.95)
                    self.assertEqual(lp.seat_head(head,torso),(0,0))
                    lp.check_neck_contact({'head':head,'torso':torso})
                    row,cols,_=lp.neck_core(torso)
                    self.assertGreaterEqual(cols.min(),125*scale)
    def test_real_gap_and_single_corner_are_still_refused(self):
        for broad in (False,True):
            head,torso=self.build(broad=broad)
            row,cols,_=lp.neck_core(torso)
            for broken in (np.zeros_like(head),head.copy()):
                broken[row,cols]=False
                broken[row,cols[0]]=True
                with self.assertRaisesRegex(lp.Rejected,'neck overlap'):
                    lp.check_neck_contact({'head':broken,'torso':torso})
    def test_frontmost_stray_pixel_cannot_replace_neck(self):
        head,torso=self.build();row,_,_=lp.neck_core(torso)
        torso[row,210]=True
        self.assertGreaterEqual(lp.neck_coverage(head,torso),.95)
        row,cols,_=lp.neck_core(torso)
        self.assertLess(cols.max(),180)

if __name__=='__main__':unittest.main()
