"""Subset viewport must include delivered art/cloth without a distant unused action."""
from pathlib import Path
import sys,unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'game-sprite-animator/scripts'))
from sprite_anim.motions import build_clips
from sprite_anim.render import Renderer,frame_count,frame_time,to_u8
from sprite_anim.rig import Body

class SelectedFraming(unittest.TestCase):
    def test_two_body_builds_keep_scoped_frames_visible_and_dependencies_intact(self):
        for body in [{},{'thigh':20.,'shin':22.,'chest_len':18.,'head_size':1.1}]:
            spec={'body':body,'weapon':'none','cloth':['cape']}
            custom={'distant':{'keys':[[0,{'root_x':450}],[.4,{'root_x':450}]],'loop':True,'period':.5}}
            registry=build_clips(custom=custom,body=Body.from_spec(body));clips={n:registry[n] for n in ['idle','run','distant']};selected={n:clips[n] for n in ['idle','run']}
            full=Renderer(spec,128,clips=clips);focused=Renderer(spec,128,clips=clips,fit_clips=selected)
            self.assertGreater(focused.unit,full.unit*2)
            self.assertIs(focused.clips['distant'],clips['distant'])
            self.assertIn('distant',focused.bakes)
            for clip in selected.values():
                n=frame_count(clip,30)
                for i in [0,n//4,n//2,n-1]:
                    a=to_u8(focused.render(clip,frame_time(clip,i,n,30),clip.duration/n))[:,:,3]>128
                    ys,xs=np.nonzero(a);self.assertGreater(len(xs),0)
                    self.assertGreater(int(xs.min()),0);self.assertLess(int(xs.max()),127)
                    self.assertGreater(int(ys.min()),0);self.assertLess(int(ys.max()),127)
            # Explicit all-clips fit retains default frame scale and pixels.
            explicit=Renderer(spec,128,clips=clips,fit_clips=clips)
            self.assertEqual(full.unit,explicit.unit)
            np.testing.assert_array_equal(to_u8(full.render(clips['idle'],.3)),to_u8(explicit.render(clips['idle'],.3)))

if __name__=='__main__':unittest.main()
