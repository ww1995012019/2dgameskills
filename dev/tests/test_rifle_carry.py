"""Source-preserving two-hand carry: pose invariants, scope and injected damage."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'game-sprite-animator/scripts'))
import character_workflow as cw
import layer_parts as lp
from sprite_anim.layer_slots import BASIC_PROFILE,RIFLE_PROFILE,rifle_prompt,hand_prompt
from sprite_anim.rifle_carry import configure_binding,upper_pixels,apply_carry,validate_carry,rigidity_report
from sprite_anim.rig import Body,full_pose,solve
from sprite_anim.mathx import rot
from sprite_anim.motions import build_clips,Gait
from sprite_anim.render import frame_count
from sprite_anim.puppet import Layer,rigid
import test_registered_connections as connection_fixtures
from sprite_anim.integrity import connection_report_faults


def fixture(scale=1.):
    h,w=260,260
    image=np.zeros((h,w,4),np.uint8)
    image[10:230,40:220]=[80,110,70,255]
    def rect(x0,y0,x1,y1):
        out=np.zeros_like(image);out[y0:y1,x0:x1]=[80,110,70,255];return out
    layers=dict(torso=rect(75,40,125,225),head=rect(80,10,120,52),
                arm_near=rect(90,75,158,143),arm_far=rect(100,80,195,143),
                hand_near_hint=rect(145,110,160,130),hand_far_hint=rect(180,108,200,130))
    near=np.array([[100,80],[100,140],[155,120]],float)
    far=np.array([[104,82],[128,136],[190,118]],float)
    ppu=2./scale
    spec=dict(puppet=dict(px_per_unit=ppu,joints=dict(waist=[100,180],head_base=[100,50]),
        rest_angles=dict(chest_rot=0.),layers={
          'torso':dict(kind='tube',rest=[[100,180],[100,50]]),
          'arm_near':dict(rest=near.tolist()),'arm_far':dict(rest=far.tolist())}),
        body=dict(up_arm=float(np.linalg.norm(near[1]-near[0])/ppu),
                  lo_arm=float(np.linalg.norm(near[2]-near[1])/ppu),neck_len=0.),
        gait=dict(idle={},run=dict(profile='ordinary_run_v2')))
    return image,layers,spec,near,far


class SourceCarry(unittest.TestCase):
    def test_two_proportions_keep_both_hands_on_one_chest_space_surface(self):
        for scale in (.7,1.4):
            with self.subTest(scale=scale):
                ref,layers,spec,near,far=fixture(scale)
                configure_binding(ref,layers,spec,{})
                body=Body.from_spec(spec['body']);carry=spec['gait']['carry'];ppu=spec['puppet']['px_per_unit']
                for chest in (-8.,0.,12.):
                    sk=solve(apply_carry(full_pose(dict(pelvis=0.,spine=chest)),carry),body)
                    for side,source in (('n',near),('f',far)):
                        delta=(source[2]-np.array([100,180]))*np.array([1,-1])/ppu
                        expected=np.array(sk['waist'])+rot(tuple(delta),sk['chest_rot'])
                        np.testing.assert_allclose(sk['wr_'+side],expected,atol=1e-8)

    def test_upper_capture_never_paints_or_recolours_the_reference(self):
        ref,layers,_,_,_=fixture();captured=upper_pixels(ref,layers)
        selected=captured[...,3]>0
        np.testing.assert_array_equal(captured[selected],ref[selected])
        self.assertFalse(captured[230:,...,3].any())

    def test_capture_preserves_real_torso_owned_neck_overlap(self):
        ref,layers,_,_,_=fixture();captured=upper_pixels(ref,layers)
        self.assertGreater(captured[45,100,3],0)
        self.assertEqual(captured[20,100,3],0)

    def test_arms_become_declared_source_group_inputs_not_duplicate_draws(self):
        ref,layers,spec,_,_=fixture();state={};configure_binding(ref,layers,spec,state)
        self.assertEqual(spec['weapon'],'rifle')
        self.assertEqual(spec['puppet']['layers']['arm_near']['draw_owner'],'torso')
        self.assertEqual(spec['puppet']['layers']['arm_far']['draw_owner'],'torso')
        self.assertEqual(state['source_upper_carry']['separate_weapon_generation'],'not_used')

    def test_no_room_below_the_hands_is_rejected(self):
        ref,layers,spec,_,_=fixture();layers['torso'][150:,:,3]=0
        with self.assertRaisesRegex(ValueError,'clearance'):configure_binding(ref,layers,spec,{})

    def test_leg_and_head_motion_are_retained_by_the_carry(self):
        ref,layers,spec,_,_=fixture();configure_binding(ref,layers,spec,{})
        pose=dict(root_y=3.,foot_n_x=5.,foot_f_y=7.,head=-4.,sh=1.)
        actual=apply_carry(pose,spec['gait']['carry'])
        self.assertEqual({k:actual[k] for k in pose if k!='sh'}, {k:v for k,v in pose.items() if k!='sh'})
        self.assertEqual(pose['sh'],1.)
        self.assertEqual(actual['sh'],0.)

    def test_run_keeps_paired_samples_and_actual_support_profile(self):
        ref,layers,spec,_,_=fixture();configure_binding(ref,layers,spec,{})
        clips=build_clips(gait=spec['gait'],body=Body.from_spec(spec['body']))
        self.assertIsInstance(clips['run'],Gait)
        self.assertEqual(frame_count(clips['run'],30)%2,0)
        for name in ('idle','run'):
            values=[clips[name].sample(clips[name].duration*i/11) for i in range(11)]
            self.assertTrue(all(v['sh']==0 for v in values))
            self.assertEqual(len({v['arm_f_up'] for v in values}),1)

    def test_bad_or_nonfinite_carry_configuration_is_refused(self):
        with self.assertRaises(ValueError):validate_carry({'profile':'unreviewed'})
        ref,layers,spec,_,_=fixture();configure_binding(ref,layers,spec,{})
        spec['gait']['carry']['arm_f_lo']=float('nan')
        with self.assertRaisesRegex(ValueError,'finite'):validate_carry(spec['gait']['carry'])

    def test_basic_scope_cannot_silently_admit_rifles(self):
        with self.assertRaises(lp.Rejected):cw.prepare('missing.png','unused',weapon='rifle')
        with self.assertRaises(lp.Rejected):cw.prepare('missing.png','unused',weapon='none',profile=RIFLE_PROFILE)
        self.assertNotIn('weapon',cw.slots(dict(profile=RIFLE_PROFILE,weapon='rifle')))
        self.assertIn('weapon',cw.slots(dict(profile=BASIC_PROFILE,weapon='sword')))

    def test_rifle_roles_are_not_selected_by_screen_left_right(self):
        self.assertIn('PISTOL GRIP',rifle_prompt('arm_near'))
        self.assertIn('FORE-END',rifle_prompt('arm_far'))
        self.assertIn('ENTIRE FOREARM',hand_prompt())


class ActualMaterialRigidity(unittest.TestCase):
    def fixture(self):
        layer=Layer.__new__(Layer);layer.offset=np.zeros(2);layer.gx=layer.gy=np.arange(0,81,10,dtype=float)
        layer.vx,layer.vy=np.meshgrid(layer.gx,layer.gy)
        layer.image=Image.new('RGBA',(80,80),(30,70,120,255))
        layer.source_upper_carry=dict(protected_y=70.)
        puppet=SimpleNamespace(joints=dict(waist=np.array([40.,70.])),rest_angles=dict(chest_rot=0.),px_per_unit=1.)
        cv=SimpleNamespace(s=1.,T=lambda p:tuple(p));sk=dict(waist=(60.,90.),chest_rot=13.)
        vertices=rigid(layer.vx,layer.vy,puppet.joints['waist'],sk['waist'],np.deg2rad(13.),1.)
        return puppet,layer,vertices,cv,sk

    def test_rigid_transport_measures_actual_mesh(self):
        p,l,v,cv,sk=self.fixture();r=rigidity_report(p,{'torso':(l,v)},cv,sk,1)
        self.assertLess(r['max_error_px'],1e-10)
        self.assertGreater(r['samples'],100)

    def test_a_shifted_material_is_rejected_by_the_original_one_pixel_limit(self):
        p,l,v,cv,sk=self.fixture();v=v+np.array([4.,0.]);r=rigidity_report(p,{'torso':(l,v)},cv,sk,1)
        self.assertGreater(r['max_error_px'],1.)

    def test_a_sheared_rifle_surface_cannot_pass_as_a_rigid_group(self):
        p,l,v,cv,sk=self.fixture();v=v.copy();v[...,0]+=(l.vy-30)*.3
        self.assertGreater(rigidity_report(p,{'torso':(l,v)},cv,sk,1)['max_error_px'],1.)


class CarryEvidence(unittest.TestCase):
    def setUp(self):
        base=connection_fixtures.ConnectionEvidence();base.setUp();self.addCleanup(base.doCleanups)
        self.root,self.doc,self.trace=base.root,base.doc,base.trace
        self.trace['binding_profile']=RIFLE_PROFILE
        data=self.trace['connections']
        data['draw_owners']={'arm_near':'torso','arm_far':'torso'}
        data['bindings']['torso']['source_upper_carry']=dict(profile='source_upper_rifle_v1',protected_y=80.,blend_end_y=120.)
        data['clips']['idle']['carried_upper']=[dict(method='source_upper_rifle_v1',samples=128,max_error_px=0.) for _ in range(2)]

    def faults(self):return connection_report_faults(self.root,self.doc,self.trace)

    def test_complete_actual_surface_evidence_passes(self):self.assertEqual(self.faults(),[])

    def test_a_shift_locates_the_exported_clip_and_exact_frame(self):
        self.trace['connections']['clips']['idle']['carried_upper'][1]['max_error_px']=4.
        self.assertEqual([(r['clip'],r['frame'],r['part']) for r in self.faults()],[('idle',1,'carry')])

    def test_missing_rows_or_declared_owner_cannot_pass(self):
        original=copy.deepcopy(self.trace)
        for target in ('carried_upper','draw_owners','source_upper_carry'):
            self.trace=copy.deepcopy(original)
            if target=='carried_upper':del self.trace['connections']['clips']['idle'][target]
            elif target=='draw_owners':del self.trace['connections'][target]
            else:del self.trace['connections']['bindings']['torso'][target]
            self.assertTrue(self.faults(),target)

    def test_invalid_or_empty_actual_material_samples_are_refused(self):
        row=self.trace['connections']['clips']['idle']['carried_upper'][1]
        for value in (True,-1.,float('nan')):
            row['max_error_px']=value;self.assertTrue(self.faults())
        row.update(max_error_px=0.,samples=0);self.assertTrue(self.faults())

    def test_removing_presentation_flags_cannot_remove_registered_carry_gate(self):
        self.trace.pop('binding_profile');self.trace.pop('connection_review_required')
        del self.trace['connections']['clips']['idle']['carried_upper']
        self.assertTrue(self.faults())

    def test_existing_rgba_hash_gate_remains_required_for_carried_art(self):
        Image.new('RGBA',(32,40),(255,0,0,255)).save(self.root/'frames/idle/idle_001.png')
        self.assertTrue(any(r['frame']==1 and r['part']=='frame' for r in self.faults()))


class ActualDrawOwner(unittest.TestCase):
    def quality_fixture(self,blur_owner):
        from sprite_anim.puppet_check import check_layers
        ramp=np.broadcast_to(np.linspace(0,200,72,dtype=np.uint8)[None,:,None],(72,72,3))
        blurry=Image.fromarray(np.concatenate((ramp,np.full((72,72,1),255,np.uint8)),axis=2))
        sharp=np.zeros((72,72,4),np.uint8);sharp[...,3]=255
        sharp[::2,...,:3]=240;sharp=Image.fromarray(sharp)
        owner=SimpleNamespace(name='torso',draw_owner=None,source_upper_carry={'profile':'source_upper_rifle_v1'},image=blurry if blur_owner else sharp)
        arms=[SimpleNamespace(name='arm_'+name,draw_owner='torso',bones=('sh_'+side,'el_'+side,'wr_'+side),image=blurry)
              for name,side in [('far','f'),('near','n')]]
        return check_layers(SimpleNamespace(layers=[arms[0],owner,arms[1]]))

    def test_blurred_actual_carried_material_still_fails_original_quality_gate(self):
        self.assertTrue(any('smear: torso:' in s for s in self.quality_fixture(True)))

    def test_nonrendered_reconstruction_does_not_replace_actual_source_quality(self):
        self.assertEqual(self.quality_fixture(False),[])

    def test_part_measurement_uses_owner_mesh_and_cannot_fill_an_actual_hole(self):
        from sprite_anim.puppet import measured_surface
        owner=SimpleNamespace(name='torso',offset=np.zeros(2),image=Image.new('RGBA',(40,40),(30,80,120,255)),source_upper_carry={'profile':'source_upper_rifle_v1'})
        image=np.array(owner.image);image[10:20,10:20,3]=0;owner.image=Image.fromarray(image)
        arm=SimpleNamespace(name='arm_near',draw_owner='torso',offset=np.array([5,5]),image=Image.new('RGBA',(20,20),'white'))
        mesh=np.array([[[1.,2.]]]);phantom=mesh+30
        puppet=SimpleNamespace(mip=lambda layer,scale:np.array(layer.image))
        surface,vertices,masked=measured_surface(puppet,{'torso':(owner,mesh),'arm_near':(arm,phantom)},'arm_near',1.)
        self.assertIs(surface,owner);self.assertIs(vertices,mesh)
        self.assertEqual(masked[15,15,3],0);self.assertEqual(masked[6,6,3],255)
        self.assertEqual(np.array(arm.image)[10,10,3],255)

    def test_new_carry_review_requires_all_frames_and_complete_playback(self):
        module=importlib.util.spec_from_file_location('rifle_visual_review',ROOT/'game-animator/modes/game-sprite-animator/scripts/visual_review.py')
        review=importlib.util.module_from_spec(module);module.loader.exec_module(review)
        doc={'clips':{'run':{'frames':list(range(22)),'fps':30,'loop':True,'frame_multiple':2}}}
        entry=review.carry_entries(doc,{'binding_profile':RIFLE_PROFILE})[0]
        self.assertEqual([p['frame'] for p in entry['poses']],list(range(22)))
        self.assertEqual(entry['playback'][0]['duration_ms'],740)
        row={'verdict':'pass','checks':{name:dict(status='pass',evidence='seen') for name in review.checks_for_sheet(entry['sheet'])}}
        with self.assertRaisesRegex(ValueError,'every required pose'):
            review.validate_checklist(entry['sheet'],row,entry)
        row['checks']['carry_rigidity']['observations']=[dict(clip=p['clip'],frame=p['frame'],evidence='grips remain joined') for p in entry['poses']]
        with self.assertRaisesRegex(ValueError,'playback'):
            review.validate_checklist(entry['sheet'],row,entry)

    def test_visual_carry_requirement_survives_a_missing_presentation_flag(self):
        module=importlib.util.spec_from_file_location('rifle_required_review',ROOT/'game-animator/modes/game-sprite-animator/scripts/visual_review.py')
        review=importlib.util.module_from_spec(module);module.loader.exec_module(review)
        doc={'clips':{'idle':{'frames':[0,1],'fps':30,'loop':True}}}
        trace={'connections':{'bindings':{'torso':{'source_upper_carry':{'profile':'source_upper_rifle_v1'}}}}}
        self.assertEqual(len(review.carry_entries(doc,trace)),1)


if __name__=='__main__':unittest.main()
