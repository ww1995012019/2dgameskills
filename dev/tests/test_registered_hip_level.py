"""Hidden cap positions must not seat a joint outside actual pelvic artwork."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'game-animator/modes/game-sprite-animator/scripts'))
import layer_parts as lp


class RegisteredHipLevel(unittest.TestCase):
    def fixture(self,scale=1):
        parent=np.zeros((100*scale,100*scale),bool)
        parent[45*scale:65*scale,25*scale:75*scale]=True
        near=np.zeros_like(parent);near[40*scale:95*scale,45*scale:78*scale]=True
        far=np.zeros_like(parent);far[20*scale:95*scale,20*scale:57*scale]=True
        roots={'leg_near':np.array([52.,38.])*scale,'leg_far':np.array([40.,38.])*scale}
        return roots,parent,{'leg_near':near,'leg_far':far}

    def test_two_scales_use_real_shared_depth_without_changing_lateral_seats_or_masks(self):
        for scale in (1,2):
            roots,parent,children=self.fixture(scale)
            original={n:p.copy() for n,p in roots.items()}
            images=[parent.copy(),*[m.copy() for m in children.values()]]
            actual,report=lp.registered_hip_level(roots,parent,children,[0.,-1.])
            shifts=[actual[n]-p for n,p in roots.items()]
            np.testing.assert_allclose(shifts[0],shifts[1])
            self.assertLess(report['shift_px'],0.)
            for name,point in actual.items():
                x,y=np.rint(point).astype(int)
                self.assertTrue(parent[y,x] and children[name][y,x])
                self.assertEqual(point[0],roots[name][0])
                np.testing.assert_array_equal(roots[name],original[name])
            for before,after in zip(images,[parent,*children.values()]):
                np.testing.assert_array_equal(before,after)

    def test_valid_registered_seats_are_preserved_exactly(self):
        roots,parent,children=self.fixture()
        for point in roots.values():point[1]=50.
        actual,report=lp.registered_hip_level(roots,parent,children,[0.,-1.])
        self.assertEqual(report['shift_px'],0.)
        for name in roots:np.testing.assert_array_equal(actual[name],roots[name])

    def test_shared_level_follows_the_source_pelvis_axis(self):
        roots,parent,children=self.fixture()
        expected,_=lp.registered_hip_level(roots,parent,children,[0.,-1.])
        turn=lambda point:np.array([point[1],parent.shape[1]-1-point[0]])
        actual,_=lp.registered_hip_level({n:turn(p) for n,p in roots.items()},np.rot90(parent),
            {n:np.rot90(mask) for n,mask in children.items()},[-1.,0.])
        for name in roots:np.testing.assert_allclose(actual[name],turn(expected[name]))

    def test_missing_one_leg_overlap_fails_instead_of_creating_material(self):
        roots,parent,children=self.fixture()
        children['leg_far'][:]=False
        with self.assertRaisesRegex(lp.Rejected,'no common registered opaque hip level'):
            lp.registered_hip_level(roots,parent,children,[0.,-1.])

    def test_nonoverlapping_depths_cannot_pass_as_two_independent_hips(self):
        roots,parent,children=self.fixture()
        children['leg_near'][:50]=False
        children['leg_far'][48:]=False
        with self.assertRaisesRegex(lp.Rejected,'no common registered opaque hip level'):
            lp.registered_hip_level(roots,parent,children,[0.,-1.])


if __name__=='__main__':unittest.main()
