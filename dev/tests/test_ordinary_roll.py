"""A measured roll keeps source posture, closed handovers and rigid body-space tuck."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'game-animator/modes/game-sprite-animator/scripts'))
from sprite_anim.motions import build_clips,CH
from sprite_anim.rig import Body,full_pose,solve
from sprite_anim.mathx import rot
from sprite_anim.constraints import low_points


class OrdinaryRoll(unittest.TestCase):
    def clips(self,body,style=None):
        return build_clips(body=body,style=style,gait={'roll':{'profile':'ordinary_roll_v1'}})

    def test_two_proportions_complete_one_turn_and_return_to_the_accepted_pose(self):
        for body in (Body(),Body(thigh=11.,shin=13.,hip_h=26.,head_size=1.4,foot_wrap=True)):
            for speed in (1.,3.):
                with self.subTest(body=body,speed=speed):
                    clips=self.clips(body,{'speed':speed});r=clips['roll'];idle=clips['idle'].sample(0.)
                    self.assertFalse(r.loop)
                    self.assertEqual((r.prev,r.next),('idle','idle'))
                    start,end=r.sample(0.),r.sample(r.duration)
                    np.testing.assert_allclose([start[k] for k in CH],[idle[k] for k in CH],atol=1e-10)
                    for k in CH:
                        self.assertAlmostEqual(end[k],idle[k]+(360. if k=='root_rot' else 0.),places=9)
                    angles=[r.sample(t)['root_rot'] for t in np.linspace(0,r.duration,151)]
                    self.assertGreaterEqual(min(np.diff(angles)),-1e-10)
                    for t in np.linspace(0,r.duration,151):
                        sk=solve(full_pose(r.sample(t)),body)
                        self.assertGreaterEqual(min(low_points(sk,body).values()),-1e-8)
                        for side in 'nf':
                            for a,b,length in [('hip_','kn_',body.leg_bones(side)[0]),('kn_','an_',body.leg_bones(side)[1])]:
                                self.assertAlmostEqual(np.linalg.norm(np.subtract(sk[a+side],sk[b+side])),length,places=8)

    def test_whole_body_contact_does_not_repose_the_legs_during_the_spin(self):
        for body in (Body(foot_wrap=True),Body(thigh=11.,shin=13.,hip_h=26.,head_size=1.4)):
            clip=self.clips(body)['roll'];reference=None
            for t in (.27,.35,.48,.61,.72,.76):
                p=clip.sample(t);sk=solve(full_pose(p),body)
                local=np.array([rot(tuple(np.subtract(sk[k],sk['hip'])),-p['root_rot'])
                                for k in ('kn_n','kn_f','an_n','an_f','sh_n','el_n','wr_n','head_base')])
                if reference is not None:np.testing.assert_allclose(local,reference,atol=1e-8)
                reference=local

    def test_tuck_folds_the_shins_without_extreme_thigh_root_swing(self):
        for body in (Body(),Body(thigh=11.,shin=13.,hip_h=26.,head_size=1.4)):
            clips=self.clips(body);rest=solve(full_pose(clips['idle'].sample(0.)),body)
            p=clips['roll'].sample(.48);sk=solve(full_pose(p),body)
            for side in 'nf':
                a=np.subtract(sk['hip_'+side],sk['kn_'+side]);b=np.subtract(sk['an_'+side],sk['kn_'+side])
                interior=np.degrees(np.arccos(np.clip(a@b/np.linalg.norm(a)/np.linalg.norm(b),-1,1)))
                self.assertAlmostEqual(interior,90.,places=7)
                before=np.subtract(rest['kn_'+side],rest['hip_'+side])
                after=rot(tuple(np.subtract(sk['kn_'+side],sk['hip_'+side])),-p['root_rot'])
                self.assertGreater(before@after/np.linalg.norm(before)/np.linalg.norm(after),.99)

    def test_style_retimes_translation_without_changing_travel_distance(self):
        distances=[]
        for speed in (1.,1.6,3.):
            clip=self.clips(Body(),{'speed':speed})['roll']
            ts=np.linspace(0,clip.duration,3001);velocity=np.array([clip.vel(t) for t in ts])
            self.assertTrue(np.all(velocity[:,1]==0.))
            distances.append(np.sum((velocity[:-1,0]+velocity[1:,0])*.5*np.diff(ts)))
        np.testing.assert_allclose(distances,distances[0],atol=1e-3)

    def test_opt_in_preserves_other_clips_and_rejects_unknown_profiles(self):
        legacy=build_clips(body=Body());fitted=self.clips(Body())
        self.assertFalse(hasattr(legacy['roll'],'motion_profile'))
        for name in ('idle','run','jump_start','jump_rise','jump_apex','fall','land'):
            for t in np.linspace(0,legacy[name].duration,9):
                np.testing.assert_array_equal([legacy[name].sample(t)[k] for k in CH],
                                              [fitted[name].sample(t)[k] for k in CH])
        with self.assertRaisesRegex(ValueError,'gait.roll'):
            build_clips(gait={'roll':{'profile':'unknown'}})


if __name__=='__main__':unittest.main()
