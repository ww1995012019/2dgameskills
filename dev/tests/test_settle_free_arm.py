"""Opt-in free-arm relaxation preserves grounded reversible entry/exit."""
import math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
from sprite_anim.motions import build_clips,GroundedGaitSettle
from sprite_anim.rig import Body,solve,heel_world,toe_world

class SettleFreeArm(unittest.TestCase):
    def walks(self):
        body=Body();base={'profile':'natural_walk_v1','arm_f':[13,13,8,4]}
        normal=build_clips(body=body,gait={'walk':base})['walk']
        fitted=build_clips(body=body,gait={'walk':dict(base,settle_relax_free_arm=True)})['walk']
        return body,normal,fitted
    def test_walking_and_default_clips_unchanged(self):
        body,normal,fitted=self.walks()
        for i in range(40):self.assertEqual(normal.sample(i*normal.duration/40),fitted.sample(i*fitted.duration/40))
    def test_entry_reverse_and_hold_pixel_pose_contract(self):
        body,normal,walk=self.walks()
        for phase in (.05,.55):
            t=phase*walk.duration;settle=GroundedGaitSettle(walk,t);reverse=GroundedGaitSettle(walk,t,reverse=True)
            self.assertEqual(settle.sample(0),walk.sample(t))
            self.assertEqual(settle.sample(settle.duration),settle.hold().sample(8))
            self.assertEqual(reverse.sample(reverse.duration),walk.sample(t))
            for i in range(21):
                u=settle.duration*i/20
                for k,v in settle.sample(u).items():self.assertAlmostEqual(v,reverse.sample(settle.duration-u)[k])
    def test_only_free_arm_changes_against_ordinary_settle(self):
        body,normal,walk=self.walks()
        for phase in (.05,.55):
            t=phase*walk.duration;a=GroundedGaitSettle(normal,t);b=GroundedGaitSettle(walk,t)
            for i in range(21):
                time=a.duration*i/20;p,q=a.sample(time),b.sample(time)
                for k,v in p.items():
                    if k not in ('arm_f_up','arm_f_lo'):self.assertEqual(v,q[k])
                x,y=solve(p,body),solve(q,body)
                for side in ('n','f'):
                    for foot in (heel_world,toe_world):self.assertEqual(foot(x,side),foot(y,side))
                    self.assertAlmostEqual(math.dist(y['sh_'+side],y['el_'+side]),body.arm_bones(side)[0])
                    self.assertAlmostEqual(math.dist(y['el_'+side],y['wr_'+side]),body.arm_bones(side)[1])
                self.assertEqual(x['wr_n'],y['wr_n'])
            p=b.sample(b.duration)
            self.assertAlmostEqual(p['arm_f_up']-p['pelvis']-p['spine'],walk.arm_f[0]-walk.pelvis-walk.lean)
            self.assertAlmostEqual(p['arm_f_lo'],walk.arm_f[2])
    def test_invalid_or_legacy_flag_rejected(self):
        for gait in ({'walk':{'settle_relax_free_arm':True}},{'run':{'settle_relax_free_arm':True}},{'walk':{'profile':'natural_walk_v1','settle_relax_free_arm':1}}):
            with self.assertRaisesRegex(ValueError,'explicit boolean'):build_clips(gait=gait)

if __name__=='__main__':unittest.main()
