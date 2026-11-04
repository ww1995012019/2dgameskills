"""Carriage comparisons retain scoped changes and cannot approve hidden arms."""
import copy
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from free_arm_readability import candidate_specs, summarize
from sprite_anim.rig import Body

class CarriageComparison(unittest.TestCase):
    def spec(self):
        return dict(body={},gait={'walk':{'profile':'natural_walk_v1','arm_f':[1,15,37,5]}},
                    marker={'unchanged':[1,2,3]})
    def test_changes_only_opt_in_free_arm_and_settle(self):
        source=self.spec();saved=copy.deepcopy(source)
        for reach,candidate in candidate_specs(source):
            self.assertLessEqual(abs(reach),.45)
            self.assertEqual(candidate['gait']['walk']['arm_f'][1:],[15,37,5])
            candidate['gait']['walk'].pop('settle_relax_free_arm')
            candidate['gait']['walk']['arm_f']=source['gait']['walk']['arm_f']
            self.assertEqual(candidate,source)
        self.assertEqual(source,saved)
    def test_normalized_reach_transfers_across_proportions_and_scale(self):
        for upper,lower in ((10,16),(18,9)):
            for scale in (.5,2):
                source=self.spec();source['body']={'up_arm_f':upper*scale,'lo_arm_f':lower*scale}
                for reach,candidate in candidate_specs(source):
                    from free_arm_readability import clips_for
                    walk=clips_for(candidate)['walk'];arm=walk.arm_f
                    a=math.radians(arm[0]-walk.pelvis-walk.lean)
                    b=a+math.radians(arm[2])
                    actual=(upper*math.sin(a)+lower*math.sin(b))/(upper+lower)
                    self.assertAlmostEqual(actual,reach)
    def test_relaxed_option_caps_not_increases_source_elbow(self):
        for elbow in (8,37):
            source=self.spec();source['gait']['walk']['arm_f'][2]=elbow
            for _,candidate in candidate_specs(source,'relaxed'):
                self.assertEqual(candidate['gait']['walk']['arm_f'][2],min(20,elbow))
    def test_no_automatic_approval_for_fully_hidden_limb(self):
        result=summarize([dict(hand_visible_fraction=0,forearm_visible_fraction=0)])
        self.assertEqual(result['hand_or_forearm_hidden_frames'],1)
        self.assertEqual(result['visual_approval'],'pending')
        self.assertEqual(result['min_paired_visibility'],0)
    def test_invalid_support_is_not_a_zero_flag_success(self):
        for value in (None,float('nan'),-1,2):
            with self.assertRaises(ValueError):summarize([dict(hand_visible_fraction=value,forearm_visible_fraction=1)])
        with self.assertRaises(ValueError):summarize([])
    def test_reject_implicit_profile_and_unknown_elbow(self):
        with self.assertRaises(ValueError):candidate_specs(dict(body={},gait={}))
        with self.assertRaises(ValueError):candidate_specs(self.spec(),'custom')

if __name__=='__main__':unittest.main()
