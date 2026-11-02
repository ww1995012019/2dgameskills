"""Cage deformation faults; synthetic fixtures are not real-character acceptance."""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from template_mesh_fit import deform,MAX_LOCAL_STRETCH,MAX_EDGE_SHIFT
from template_puppet import geometry,silhouette_metrics,RULES


def picture(mask):
    a=np.zeros((*mask.shape,4),np.uint8);a[mask]=(80,110,150,255)
    return Image.fromarray(a)


class TemplateMeshFit(unittest.TestCase):
    def test_two_profiles_correct_a_taper_without_folding_or_painting(self):
        for profile in ('slim','compact'):
            with self.subTest(profile=profile):
                target,joints=geometry('leg_near',profile)
                source=target.copy()
                # A narrower complete calf, independently of the real character.
                for y in range(610,770):
                    row=np.flatnonzero(source[y]);source[y,row[-18:]]=False
                before=silhouette_metrics(source,target,joints)
                result,report=deform(picture(source),target)
                mask=np.asarray(result)[:,:,3]>128
                after=silhouette_metrics(mask,target,joints)
                self.assertGreater(after['core_coverage'],before['core_coverage'])
                self.assertGreaterEqual(after['core_coverage'],RULES['core_coverage'])
                self.assertGreaterEqual(after['inside_envelope'],RULES['inside_envelope'])
                self.assertTrue(all(v>=.98 for v in after['anchor_coverage'].values()))
                self.assertGreaterEqual(report['min_horizontal_jacobian'],1)
                self.assertLessEqual(report['max_horizontal_jacobian'],MAX_LOCAL_STRETCH)
                self.assertLessEqual(report['max_edge_displacement_px'],MAX_EDGE_SHIFT)
                self.assertEqual(report['clipped_source_pixels'],0)
                np.testing.assert_array_equal(np.asarray(result)[:,:,:3][mask],np.tile([80,110,150],(mask.sum(),1)))

    def test_missing_shin_cannot_be_invented(self):
        target,joints=geometry('leg_near');source=target.copy();source[580:800]=False
        result,_=deform(picture(source),target);mask=np.asarray(result)[:,:,3]>128
        self.assertFalse(mask[580:800].any())
        self.assertLess(silhouette_metrics(mask,target,joints)['core_coverage'],RULES['core_coverage'])

    def test_extra_thigh_branch_is_not_cut_off(self):
        target,joints=geometry('leg_near');source=target.copy();source[250:350,450:840]=True
        result,report=deform(picture(source),target);mask=np.asarray(result)[:,:,3]>128
        self.assertTrue(mask[280,820])
        self.assertLess(silhouette_metrics(mask,target,joints)['inside_envelope'],RULES['inside_envelope'])
        self.assertFalse(report['silhouette_clipping'])

    def test_internal_hole_is_not_filled(self):
        target,_=geometry('leg_near');source=target.copy();source[220:245,440:465]=False
        result,report=deform(picture(source),target);mask=np.asarray(result)[:,:,3]>128
        self.assertGreater((ndi.binary_fill_holes(mask)&~mask).sum(),0)
        self.assertFalse(report['alpha_filled'])


if __name__=='__main__':unittest.main()
