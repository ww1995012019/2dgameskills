"""Measured jumping keeps cloth/arm poses bounded and finite stage handovers closed."""
import math
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'game-animator/modes/game-sprite-animator/scripts'))
from sprite_anim.motions import build_clips, CH
from sprite_anim.rig import Body

CHAIN=('jump_start','jump_rise','jump_apex','fall','land')


class OrdinaryJump(unittest.TestCase):
    def clips(self,body=None,style=None):
        return build_clips(body=body,style=style,gait={'jump':{'profile':'ordinary_jump_v1'}})

    def test_two_body_proportions_keep_finite_seams_and_reference_arm_pose(self):
        for body in (Body(),Body(thigh=11.,shin=13.,hip_h=26.,head_size=1.4)):
            clips=self.clips(body);base=clips['idle'].sample(0.);legs=body.thigh+body.shin
            for name in CHAIN:
                clip=clips[name]
                self.assertFalse(clip.loop)
                for t in np.linspace(0.,clip.duration,31):
                    p=clip.sample(t)
                    self.assertLess(abs(p['root_y']-base['root_y']),.1*legs)
                    self.assertLessEqual(max(p['foot_n_y'],p['foot_f_y']),.12*legs)
                    for side in 'nf':self.assertLess(abs(p['arm_'+side+'_up']-base['arm_'+side+'_up']),20.)
            for a,b in zip(('idle',*CHAIN),(*CHAIN,'idle')):
                end=clips[a].sample(0. if a=='idle' else clips[a].duration)
                start=clips[b].sample(0.)
                np.testing.assert_allclose([end[k] for k in CH],[start[k] for k in CH],atol=1e-9)

    def test_velocity_integrates_to_ground_and_time_scaling_preserves_height(self):
        heights=[]
        for speed in (1.,1.6):
            position=0.;peak=0.
            for name in CHAIN:
                clip=self.clips(Body(),{'speed':speed})[name]
                times=np.linspace(0.,clip.duration,501)
                for a,b in zip(times,times[1:]):
                    position+=(clip.vel(a)[1]+clip.vel(b)[1])*.5*(b-a)
                    peak=max(peak,position)
            self.assertAlmostEqual(position,0.,places=3)
            heights.append(peak)
        self.assertAlmostEqual(*heights,places=3)

    def test_legacy_jumps_are_unchanged_without_the_explicit_profile(self):
        clips=build_clips()
        self.assertTrue(clips['jump_rise'].loop)
        self.assertTrue(clips['fall'].loop)
        self.assertFalse(hasattr(clips['land'],'motion_profile'))
        with self.assertRaisesRegex(ValueError,'gait.jump'):
            build_clips(gait={'jump':{'profile':'unreviewed'}})


if __name__=='__main__':unittest.main()
