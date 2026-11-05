"""Source-preserving neck skinning on two builds, plus an actual moving-mesh fault."""
import copy
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
from sprite_anim.puppet import Puppet, mesh_points, neck_blend_weights
from sprite_anim.art import Canvas
from sprite_anim.rig import Body, full_pose, solve
from sprite_anim.motions import build_clips
from sprite_anim.render import frame_time
from sprite_anim.puppet_check import check_neck
from sprite_anim.layer_slots import REFERENCE_HAND_REPAIR
from layer_parts import neck_material_depth,neck_front_material_mask


def fixture(root, wide=False):
    half, scale = (20, 5.) if wide else (13, 4.)
    head = Image.new('RGBA', (256, 256)); d=ImageDraw.Draw(head)
    d.ellipse((98, 8, 154, 67), fill=(180, 150, 100, 255))
    d.rectangle((124-half, 56, 124+half, 106), fill=(180, 150, 100, 255))
    torso=Image.new('RGBA', (256, 256)); d=ImageDraw.Draw(torso)
    d.rectangle((124-half, 72, 124+half, 116), fill=(180, 150, 100, 255))
    d.rectangle((88, 110, 160, 204), fill=(20, 100, 100, 255))
    head.save(root/'head.png');torso.save(root/'torso.png')
    data=dict(px_per_unit=scale,joints=dict(head_base=[124,76],waist=[124,180]),
              rest_angles=dict(head_rot=0.,chest_rot=0.,body_rot=0.),layers=dict(
        torso=dict(kind='tube',image='torso.png',bones=['waist','head_base'],rest=[[124,180],[124,76]],radius=half),
        head=dict(kind='rigid',image='head.png',follow=['head_base','head_rot'],anchor=[124,76],neck_skin='torso')))
    return dict(_dir=str(root),puppet=data)


class NeckSkin(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_two_builds_preserve_source_pixels_and_skull_while_the_neck_bends(self):
        for wide in (False,True):
            spec=fixture(self.root,wide);p=Puppet(spec);images=[l.image.tobytes() for l in p.layers]
            head=next(l for l in p.layers if l.name=='head')
            cv=Canvas(256,1,3.,.88,1.,False,(0,0,0))
            for turn in (-30,0,30):
                sk=solve(full_pose(dict(head=turn,spine=14)),Body(neck_len=0.))
                meshes=dict((l.name,v) for l,v in p.meshes(cv,sk,{}))
                rigid=p.rigid_verts(head,sk,cv,cv.s/p.px_per_unit)
                skull=(head.vy<56)&head.used
                np.testing.assert_array_equal(meshes['head'][skull],rigid[skull])
                self.assertGreater(float(np.max(np.abs(meshes['head']-rigid))),.1)
            self.assertEqual(images,[l.image.tobytes() for l in p.layers])

    def test_used_only_matches_the_full_unrelaxed_mesh_exactly(self):
        p=Puppet(fixture(self.root));cv=Canvas(256,1,3.,.88,1.,False,(0,0,0))
        sk=solve(full_pose(dict(head=-18,spine=20)),Body(neck_len=0.))
        full={l.name:(l,v) for l,v in p.meshes(cv,sk,{},relax=False)}
        for layer,verts in p.meshes(cv,sk,{},relax=False,used_only=True):
            np.testing.assert_array_equal(verts,full[layer.name][1][layer.used])

    def test_triangle_mapping_matches_each_half_of_the_native_raster_cell(self):
        layer=types.SimpleNamespace(offset=np.array([10.,20.]),gx=np.array([0.,10.]),gy=np.array([0.,10.]))
        verts=np.array([[[0.,0.],[20.,0.]],[[0.,10.],[25.,15.]]])
        np.testing.assert_allclose(mesh_points(layer,verts,[[12.,22.],[18.,28.]]),[[4.,2.],[19.,11.]])

    def test_missing_opaque_overlap_is_rejected(self):
        p=Puppet(fixture(self.root));head,torso=p.layers[1],p.layers[0]
        torso.image=Image.new('RGBA',(256,256))
        with self.assertRaisesRegex(ValueError,'no registered opaque'):
            neck_blend_weights(head,torso,[124,76],[124,180])

    def test_incorrect_parent_or_draw_order_is_rejected(self):
        spec=fixture(self.root);spec['puppet']['layers']['head']['neck_skin']='absent'
        with self.assertRaisesRegex(ValueError,'tube torso'):Puppet(spec)
        spec=fixture(self.root);spec['puppet']['layers']=dict(reversed(list(spec['puppet']['layers'].items())))
        p=Puppet(spec);cv=Canvas(256,1,3.,.88,1.,False,(0,0,0));sk=solve(full_pose({}),Body(neck_len=0.))
        with self.assertRaisesRegex(ValueError,'precede head'):list(p.meshes(cv,sk,{}))

    def test_measured_seam_passes_and_a_rigid_neck_fault_names_run_frame_four(self):
        p=Puppet(fixture(self.root))
        body=Body(neck_len=0.,chest_len=float(np.linalg.norm(p.joints['head_base']-p.joints['waist']))/p.px_per_unit)
        clip=build_clips(body=body)['run'];n,fps=12,20
        r=types.SimpleNamespace(size=256,ss=1,unit=4.,art=types.SimpleNamespace(puppet=p,body=body),cloth_at=lambda c,t:{})
        self.assertEqual(check_neck(r,clip,n,fps),[])
        original=p.meshes;at=frame_time(clip,4,n,fps)
        def broken(cv,sk,cloth,*args,**kwargs):
            for layer,verts in original(cv,sk,cloth,*args,**kwargs):
                if layer.name=='head' and cloth.get('fault'):
                    verts=p.rigid_verts(layer,sk,cv,cv.s/p.px_per_unit)
                yield layer,verts
        p.meshes=broken;r.cloth_at=lambda c,t:dict(fault=abs(t-at)<1e-10)
        errors=check_neck(r,clip,n,fps)
        self.assertTrue(any('run frame 4:' in value for value in errors),errors)
        self.assertEqual(r.neck_checks['run']['worst_frame'],4)

    def test_legacy_rigid_heads_are_unchanged_without_the_explicit_binding(self):
        spec=fixture(self.root);del spec['puppet']['layers']['head']['neck_skin'];p=Puppet(spec)
        self.assertFalse(p.neck_bindings)


class HeadResponse(unittest.TestCase):
    def test_response_is_looping_bounded_and_changes_only_head_channel(self):
        body=Body(head_size=.7)
        default=build_clips(body=body)
        active=build_clips(body=body,gait={name:dict(head_response='neck_inertia_v1') for name in ('idle','walk','run')})
        for name in ('idle','walk','run'):
            a,b=default[name],active[name];difference=[]
            for t in np.linspace(0,b.duration,41):
                old,new=a.sample(t),b.sample(t)
                self.assertEqual({k:v for k,v in old.items() if k!='head'},{k:v for k,v in new.items() if k!='head'})
                difference.append(abs(new['head']-old['head']))
            self.assertGreater(max(difference),.1)
            self.assertLess(max(difference),8.)
            self.assertAlmostEqual(b.sample(0.)['head'],b.sample(b.duration)['head'])
        self.assertEqual(default['idle'].sample(0.),active['idle'].sample(0.))
        for name in ('attack_1','hurt','block'):
            for t in np.linspace(0,default[name].duration,7):
                self.assertEqual(default[name].sample(t),active[name].sample(t))

    def test_response_rejects_unknown_profiles_and_wrong_clip_types(self):
        for gait in ({'run':dict(head_response='bad')},{'idle':dict(head_response=True)},{'hurt':dict(head_response='neck_inertia_v1')}):
            with self.subTest(gait=gait),self.assertRaises(ValueError):build_clips(gait=gait)

    def test_reference_repair_keeps_registration_and_a_holding_hand(self):
        self.assertIn('EMPTY HAND',REFERENCE_HAND_REPAIR)
        self.assertIn('same full canvas',REFERENCE_HAND_REPAIR)
        self.assertIn('original secure grip',REFERENCE_HAND_REPAIR)


class NeckMaterialDepth(unittest.TestCase):
    def test_two_material_palettes_choose_the_original_front_collar(self):
        for skin,cloth in (((180,150,100,255),(20,100,100,255)),((70,65,80,255),(130,35,25,255))):
            head=Image.new('RGBA',(64,64));torso=Image.new('RGBA',(64,64))
            ImageDraw.Draw(head).rectangle((24,4,40,42),fill=skin)
            ImageDraw.Draw(torso).rectangle((18,25,46,59),fill=cloth)
            reference=Image.alpha_composite(head,torso)
            front,report=neck_material_depth(np.asarray(head),np.asarray(torso),np.asarray(reference),[32,24],[32,56])
            self.assertTrue(front);self.assertGreater(report['front_pixels'],0)
            front,_=neck_material_depth(np.asarray(head),np.asarray(torso),np.asarray(Image.alpha_composite(torso,head)),[32,24],[32,56])
            self.assertFalse(front)

    def test_ambiguous_equal_materials_do_not_reorder_the_skull(self):
        a=np.full((64,64,4),180,dtype=np.uint8);a[...,3]=255
        front,_=neck_material_depth(a,a,a,[32,24],[32,56]);self.assertFalse(front)

    def test_actual_raster_hides_the_internal_neck_extension_with_existing_collar_pixels(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);spec=fixture(root)
            head=Image.open(root/'head.png').convert('RGBA');ImageDraw.Draw(head).rectangle((111,90,137,112),fill=(180,150,100,255));head.save(root/'head.png')
            torso=Image.open(root/'torso.png').convert('RGBA')
            ImageDraw.Draw(torso).rectangle((111,72,137,94),fill=(200,170,120,255))
            ImageDraw.Draw(torso).rectangle((88,95,160,204),fill=(20,100,100,255));torso.save(root/'torso.png')
            reference=Image.alpha_composite(head,torso)
            mask,_=neck_front_material_mask(np.asarray(head),np.asarray(torso),np.asarray(reference),[124,76],[124,180])
            self.assertTrue(mask[104,124]);self.assertFalse(mask[90,124])
            Image.fromarray(mask.astype('uint8')*255,'L').save(root/'front-mask.png')
            spec['puppet']['layers']['torso']['front_mask']='front-mask.png'
            p=Puppet(spec);body=Body(neck_len=0.,chest_len=104/p.px_per_unit)
            cv=Canvas(256,1,2.,.88,1.,False,(0,0,0));sk=solve(full_pose({}),body)
            meshes={l.name:(l,v) for l,v in p.meshes(cv,sk,{})}
            layer,verts=meshes['torso'];point=mesh_points(layer,verts,[[124.,104.]])[0]
            p.draw(cv,sk,{})
            x,y=np.rint(point).astype(int)
            np.testing.assert_array_equal(cv.buf[y,x,:3],[20,100,100])
            child,child_verts=meshes['head'];bare=mesh_points(child,child_verts,[[124.,90.]])[0];bx,by=np.rint(bare).astype(int)
            np.testing.assert_array_equal(cv.buf[by,bx,:3],[180,150,100])
            del spec['puppet']['layers']['torso']['front_mask'];bad=Puppet(spec)
            other=Canvas(256,1,2.,.88,1.,False,(0,0,0));bad.draw(other,sk,{})
            self.assertGreater(float(np.linalg.norm(other.buf[y,x,:3].astype(float)-cv.buf[y,x,:3])),20.)


if __name__=='__main__':unittest.main()
