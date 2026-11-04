"""Occlusion diagnostics distinguish physical tears, hidden hands and thin paths."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from occlusion_readability import visibility_metrics


class OcclusionReadability(unittest.TestCase):
    def fixture(self,scale=1):
        arm=np.zeros((40*scale,40*scale));arm[5*scale:35*scale,15*scale:25*scale]=1
        hand=np.zeros_like(arm,dtype=bool);hand[28*scale:35*scale,12*scale:28*scale]=True
        fore=np.zeros_like(arm,dtype=bool);fore[12*scale:22*scale,12*scale:28*scale]=True
        return arm,hand,fore

    def test_unoccluded_and_layer_order_at_two_scales(self):
        for scale in (1,2):
            arm,hand,fore=self.fixture(scale)
            cover=np.ones_like(arm)
            row=visibility_metrics([('torso',cover),('arm',arm)],'arm',hand,fore)
            self.assertEqual(row['hand_visible_fraction'],1)
            self.assertEqual(row['forearm_visible_fraction'],1)
            self.assertTrue(all(row['visible_hand_forearm_connected'].values()))

    def test_visible_hand_with_hidden_forearm_is_not_a_physical_tear(self):
        arm,hand,fore=self.fixture();cover=np.zeros_like(arm);cover[10:27]=1
        row=visibility_metrics([('arm',arm),('torso',cover)],'arm',hand,fore)
        self.assertTrue(row['isolated_hand_forearm_connected'])
        self.assertEqual(row['hand_visible_fraction'],1)
        self.assertEqual(row['forearm_visible_fraction'],0)
        self.assertFalse(any(row['visible_hand_forearm_connected'].values()))
        self.assertEqual(row['forearm_occluders'],{'torso':1})

    def test_hidden_hand_has_zero_visibility_not_floating_hand_evidence(self):
        arm,hand,fore=self.fixture()
        row=visibility_metrics([('arm',arm),('robe',np.ones_like(arm))],'arm',hand,fore)
        self.assertEqual(row['visible_hand_mass'],0)
        self.assertEqual(row['visible_hand_pixels'],0)

    def test_thin_visible_bridge_needs_metrics_not_only_connectivity(self):
        arm,hand,fore=self.fixture();cover=np.zeros_like(arm);cover[10:27]=1;cover[:,19]=0
        row=visibility_metrics([('arm',arm),('torso',cover)],'arm',hand,fore)
        self.assertTrue(row['visible_hand_forearm_connected']['0.5'])
        self.assertAlmostEqual(row['forearm_visible_fraction'],.1)
        self.assertEqual(row['hand_visible_fraction'],1)

    def test_transparency_is_reported_without_binary_pose_rejection(self):
        arm,hand,fore=self.fixture();cover=np.zeros_like(arm);cover[10:27]=.7
        row=visibility_metrics([('arm',arm),('cloth',cover)],'arm',hand,fore)
        self.assertAlmostEqual(row['forearm_visible_fraction'],.3)
        self.assertTrue(row['visible_hand_forearm_connected']['0.25'])
        self.assertFalse(row['visible_hand_forearm_connected']['0.5'])

    def test_physical_source_gap_remains_distinguishable(self):
        arm,hand,fore=self.fixture();arm[24:26]=0
        row=visibility_metrics([('arm',arm)],'arm',hand,fore)
        self.assertFalse(row['isolated_hand_forearm_connected'])
        self.assertEqual(row['forearm_visible_fraction'],1)

    def test_occluder_attribution_uses_frontmost_material(self):
        arm,hand,fore=self.fixture();cover=np.ones_like(arm)
        row=visibility_metrics([('arm',arm),('torso',cover),('cloak',cover*.5)],'arm',hand,fore)
        self.assertEqual(row['forearm_occluders'],{'cloak':.5,'torso':.5})


if __name__=='__main__':unittest.main()
