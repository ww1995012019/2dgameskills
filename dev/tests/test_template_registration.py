"""Registration must fix aspect errors without hiding extra art or weakening gates."""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from template_registration import fit,warp
from template_puppet import geometry,silhouette_metrics,RULES


class TemplateRegistration(unittest.TestCase):
    def test_recovers_aspect_error_on_two_profiles(self):
        for profile in ('slim','compact'):
            with self.subTest(profile=profile):
                mask,joints=geometry('leg_near',profile)
                pixels=np.zeros((1024,1024,4),np.uint8);pixels[mask]=(40,50,70,255)
                distorted=warp(Image.fromarray(pixels),[.94,1.04,25,-15],1024)
                result,report=fit(distorted,mask,joints,RULES)
                metrics=silhouette_metrics(np.asarray(result)[:,:,3]>128,mask,joints)
                self.assertGreaterEqual(metrics['core_coverage'],RULES['core_coverage'])
                self.assertGreaterEqual(metrics['inside_envelope'],RULES['inside_envelope'])
                self.assertTrue(all(v>=.98 for v in metrics['anchor_coverage'].values()))
                sx,sy,dx,dy=report['parameters']
                self.assertLessEqual(max(abs(sx-1),abs(sy-1)),.12)
                self.assertLessEqual(max(abs(dx),abs(dy)),1024*.08)
                self.assertEqual(report['clipped_source_pixels'],0)

    def test_warp_reports_pixels_that_would_be_clipped(self):
        # An edge fragment may never be removed by a fit and treated as accepted art.
        mask,joints=geometry('torso');pixels=np.zeros((1024,1024,4),np.uint8)
        pixels[mask]=(40,50,70,255);pixels[0:10,0:1024]=(200,0,0,255)
        result,report=fit(Image.fromarray(pixels),mask,joints,RULES)
        if report['clipped_source_pixels']==0:
            m=silhouette_metrics(np.asarray(result)[:,:,3]>128,mask,joints)
            self.assertLess(m['inside_envelope'],RULES['inside_envelope'])
        self.assertFalse(report['silhouette_clipping'])
        self.assertFalse(report['per_joint_deformation'])


if __name__=='__main__':unittest.main()
