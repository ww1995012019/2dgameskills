"""Actual source alpha contact and independent native-pixel penetration tests."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'game-animator/modes/game-sprite-animator/scripts'))
from sprite_anim.painted_ground import PaintedGround,painted_floor
from sprite_anim.rig import Body,full_pose,solve
from sprite_anim.motions import build_clips


class PaintedContact(unittest.TestCase):
    def test_boundary_follows_opaque_material_and_invalidates_after_source_alpha_change(self):
        layer=SimpleNamespace(name='head',kind='rigid',image=Image.new('RGBA',(4,4),(60,80,100,255)),
                              offset=np.zeros(2),gx=np.array([0.,4.]),gy=np.array([0.,4.]))
        vertices=np.array([[[0.,-3.],[4.,-3.]],[[0.,1.],[4.,1.]]])
        puppet=SimpleNamespace(layers=[layer],meshes=lambda *args:iter([(layer,vertices)]))
        probe=PaintedGround(puppet,Body())
        self.assertAlmostEqual(probe(full_pose({})),-.5)
        layer.image.putalpha(Image.fromarray(np.array([[255]*4,[0]*4,[0]*4,[0]*4],np.uint8)))
        self.assertAlmostEqual(probe(full_pose({})),2.5)

    def test_native_floor_faults_keep_frame_identity_and_world_limit_at_two_scales(self):
        for scale in (1,2):
            frames=np.zeros((3,48*scale,48*scale,4),np.float32)
            frames[:,10*scale:39*scale,15*scale:30*scale,3]=1.
            self.assertEqual(painted_floor(frames,40*scale,2*scale)['status'],'PASS')
            frames[1,40*scale:44*scale,18*scale:22*scale,3]=1.
            result=painted_floor(frames,40*scale,2*scale)
            self.assertEqual(result['status'],'FAIL')
            self.assertEqual(result['bad_frames'],[1])
            self.assertEqual(result['limit_px'],2*scale)
            frames[1,40*scale:44*scale,:,3]=.2
            self.assertEqual(painted_floor(frames,40*scale,2*scale)['status'],'PASS')

    def test_source_roll_uses_one_group_contact_with_no_competing_foot_clamp(self):
        for body in (Body(),Body(thigh=11.,shin=13.,hip_h=26.,head_size=1.4)):
            c=build_clips(body=body,gait={'roll':{'profile':'ordinary_roll_v1'}})['roll']
            self.assertNotIn('_whole_body_floor',c.sample(.48))
            def probe(pose):
                sk=solve(full_pose(pose),body)
                return min(sk[k][1] for k in ('head_base','kn_n','kn_f','an_n','an_f'))-12.*body.head_size
            c.ground_probe=probe
            for time in (.35,.48,.61):
                p=c.sample(time)
                self.assertTrue(p['_whole_body_floor'])
                self.assertAlmostEqual(probe(p),.25,places=8)


if __name__=='__main__':unittest.main()
