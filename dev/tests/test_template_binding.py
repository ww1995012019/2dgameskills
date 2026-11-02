"""Known joints + measured grips; synthetic fixtures are not real-art acceptance."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import template_puppet as tp
import template_full_character as full
import template_binding as tb
import test_template_full_character as fixtures
from sprite_anim.rig import Body,full_pose,solve,ankle_with_roll,heel_world,toe_world
from sprite_anim.mathx import rot
from sprite_anim.constraints import foot_low
from sprite_anim.art import hand_grip
from sprite_anim.puppet import Puppet
from sprite_anim import puppet_check as pc
from sprite_anim.motions import build_clips
from sprite_anim.render import Renderer


class TemplateBinding(unittest.TestCase):
    def test_default_grip_is_exactly_previous_formula(self):
        for up in (-65,0,73,135):
            sk=solve(full_pose(dict(arm_n_up=up,arm_n_lo=32)),Body())
            expected=tuple(sk['wr_n'][i]+(sk['wr_n'][i]-sk['el_n'][i])*.14 for i in (0,1))
            self.assertEqual(hand_grip(sk),expected)
            self.assertEqual(sk['weapon_pivot_y'],expected[1])

    def test_measured_grip_follows_forearm_and_all_consumers_agree(self):
        b=Body(weapon_grip_along=.27,weapon_grip_across=.06)
        layer=SimpleNamespace(name='weapon',follow=['wr_n','wep_a'],anchor=[0.,0.],offset=np.zeros(2),vx=np.array([[0.,10.],[0.,10.]]),vy=np.array([[0.,0.],[10.,10.]]))
        puppet=object.__new__(Puppet)
        for up in (-40,20,85):
            sk=solve(full_pose(dict(arm_n_up=up,arm_n_lo=32)),b);wr=np.array(sk['wr_n']);v=wr-sk['el_n']
            expected=wr+v*.27+np.array([-v[1],v[0]])*.06
            np.testing.assert_allclose(hand_grip(sk),expected)
            self.assertEqual(sk['weapon_pivot_y'],hand_grip(sk)[1])
            puppet.rest_angles={'wep_a':sk['wep_a']}
            vertices=puppet.rigid_verts(layer,sk,SimpleNamespace(T=lambda p:p),1.)
            np.testing.assert_allclose(vertices[0,0],expected)
            self.assertGreater(np.linalg.norm(expected-(wr+v*.14)),1.) # implanted old default would miss

    def test_backward_source_elbow_gets_legal_target_without_moving_endpoints(self):
        points=np.array([[0.,0.],[-10.,30.],[-29.,54.]])
        original=points.copy();up,elbow,changed=tb.canonical_arm(points)
        self.assertTrue(changed);self.assertGreater(elbow,0.);np.testing.assert_array_equal(points,original)
        a=np.radians(up);b=np.radians(up+elbow);length=np.linalg.norm(np.diff(points,axis=0),axis=1)
        end=points[0]+[np.sin(a)*length[0]+np.sin(b)*length[1],np.cos(a)*length[0]+np.cos(b)*length[1]]
        np.testing.assert_allclose(end,points[-1],atol=1e-8)

    def test_measured_sole_contacts_drive_roll_trace_and_ground_check(self):
        for heel,ball in (((-5.,-5.6),(11.,-5.6)),((-3.,-6.2),(9.,-6.2))):
            for pitch in (-28.,0.,18.):
                ankle=ankle_with_roll((2.,-heel[1]),pitch,heel,ball)
                sk=dict(an_n=ankle,fr_n=-pitch,foot_n_heel=heel,foot_n_ball=ball)
                expected=[ankle[1]+rot(p,-pitch)[1] for p in (heel,ball)]
                self.assertAlmostEqual(min(expected),0.)
                self.assertAlmostEqual(foot_low(sk,'n'),min(expected))
                self.assertAlmostEqual(min(heel_world(sk,'n')[1],toe_world(sk,'n')[1]),0.)
                old=tuple(sk['an_n'][i]+rot((-4.5,-5.),-pitch)[i] for i in (0,1))
                self.assertNotEqual(heel_world(sk,'n'),old)

    def test_two_foot_shapes_keep_stance_supported_without_crouching(self):
        for length in (11.,14.):
            body=Body(thigh=18.5,shin=18.,ankle_h=5.6,hip_h=43.3,
                foot_n_heel=(-5.,-5.6),foot_n_ball=(length,-5.6),
                foot_f_heel=(-3.,-5.6),foot_f_ball=(length+1.,-5.6))
            clip=build_clips(body=body)['walk'];knees=[];gap=0.
            for i in range(120):
                t=clip.duration*i/120;sk=solve(full_pose(clip.sample(t)),body)
                for side,contact in clip.contacts(t).items():
                    if not contact:continue
                    gap=max(gap,abs(min(heel_world(sk,side)[1],toe_world(sk,side)[1])))
                    if sk['an_'+side][0]>=sk['hip_'+side][0]:
                        a=np.subtract(sk['kn_'+side],sk['hip_'+side]);v=np.subtract(sk['an_'+side],sk['kn_'+side])
                        knees.append(np.degrees(np.arccos(np.clip(a@v/np.linalg.norm(a)/np.linalg.norm(v),-1,1))))
            self.assertLess(np.mean(knees),pc.CROUCH_DEG)
            self.assertLess(gap,.25)
            eps=1e-5;h=lambda t:clip.sample(t)['root_y']
            self.assertAlmostEqual(h(0),h(clip.duration))
            self.assertAlmostEqual((h(eps)-h(0))/eps,(h(0)-h(-eps))/eps,delta=.02)

    def test_two_builds_bind_with_known_joints_and_reject_stale_art(self):
        for profile in tp.PROFILES:
            stage=fixtures.FullTemplate.complete_fixture(self,profile);full.inspect(stage)
            approval={'contract_sha256':tp.sha(stage/'contract.json'),'user_quote':'synthetic fixture acceptance only',
              'assets':{n:tp.sha(stage/n) for n in ('character_draft.png','assembly_report.json','static_checks.json')}}
            tp.write(stage/'static_user_approval.json',approval);out=stage/'motion/rig';tb.bind(stage,out)
            spec=tp.read(out/'character.json');spec['_dir']=str(out);body=Body.from_spec(spec['body']);clips=build_clips(gait=spec['gait'],body=body)
            # Binding cannot replace the supplied source shoulder/elbow/wrist.
            known=tp.read(stage/'assembly_report.json')['joints']['arm_far']
            np.testing.assert_allclose(spec['puppet']['layers']['arm_far']['rest'],[known[n] for n in ('shoulder','elbow','wrist')])
            renderer=Renderer(spec,192,clips={'walk':clips['walk']})
            self.assertEqual(pc.check_layers(renderer.art.puppet),[])
            self.assertEqual(pc.check_motion(renderer,clips['walk'],8,15),[])
            original=stage/'assembled_layers/arm_near.png';original.write_bytes(original.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'assembled layer changed'):tb.approved(stage)


if __name__=='__main__':unittest.main()
