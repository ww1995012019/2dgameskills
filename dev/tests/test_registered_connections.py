"""Fault injection for full garment attachments and output-bound evidence.

These measurements detect geometric separation, not the semantic colour of cloth.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'game-sprite-animator/scripts'))
import test_attachment_pixels as fixtures
from sprite_anim import puppet as pp,puppet_check as pc
from sprite_anim.art import Canvas
from sprite_anim.rig import full_pose,solve
from sprite_anim.motions import Proc
from sprite_anim.render import GROUND_FRAC
from sprite_anim.integrity import connection_report_faults


class RegisteredConnections(unittest.TestCase):
    def renderer(self,wide=False):
        case=fixtures.AttachmentFrameLocations('runTest')
        r,_=case.renderer(wide);self.addCleanup(case.doCleanups)
        p=r.art.puppet;cv=Canvas(r.size,1,r.unit,GROUND_FRAC,1,False,(0,0,0))
        pose=full_pose({});sk=solve(pose,r.art.body)
        p.joints['waist']=np.asarray(cv.T(sk['waist']))
        layers={layer.name:layer for layer in p.layers}
        torso=layers['torso'];torso.kind='tube';torso.bones=['hip','waist','neck']
        torso.rest=[np.asarray(cv.T(sk[k])) for k in torso.bones]
        torso.source_frame=True;torso.bind_curve()
        p.pelvis_bindings={}
        for name in ('torso','leg_near','leg_far'):
            child=layers[name]
            seat,distal=(p.joints['hip'],p.joints['waist']) if name=='torso' else child.rest[:2]
            weights,report=pp.pelvis_blend_weights(child,layers['hips'],seat,distal)
            p.pelvis_bindings[name]=(layers['hips'],weights,report)
        clip=Proc('stride',1.,lambda t:dict(pose,foot_n_x=4+5*np.sin(t*6.28),
                  foot_f_x=-4-5*np.sin(t*6.28),spine=4*np.sin(t*6.28)))
        return r,clip

    def test_two_proportions_keep_full_registered_connections(self):
        for wide in (False,True):
            with self.subTest(wide=wide):
                r,clip=self.renderer(wide)
                self.assertEqual(pc.check_connections(r,clip,7,12),[])
                self.assertEqual(set(r.connection_checks['stride']['parts']),{'torso','leg_near','leg_far'})
                self.assertTrue(all(len(v)==7 for v in r.connection_checks['stride']['parts'].values()))

    def test_outer_attachment_tear_names_part_clip_and_exact_frame(self):
        r,clip=self.renderer();p=r.art.puppet;real=p.meshes;frame=-1
        def advance(*_):
            nonlocal frame
            frame+=1;return {}
        r.cloth_at=advance
        def broken(*args,**kwargs):
            for layer,verts in real(*args,**kwargs):
                if layer.name=='leg_far' and frame==2:
                    verts=verts.copy()
                    # Only one side moves: a centre point can still be connected.
                    left=layer.vx < np.median(layer.vx)
                    verts[left,0]-=5
                yield layer,verts
        with mock.patch.object(p,'meshes',broken):
            faults=pc.check_connections(r,clip,5,12)
        self.assertTrue(any('leg_far: stride frame 2:' in x for x in faults),faults)
        self.assertFalse(any('frame 0:' in x for x in faults),faults)

    def test_torso_waist_shift_is_also_checked(self):
        r,clip=self.renderer(True);p=r.art.puppet;real=p.meshes
        def broken(*args,**kwargs):
            for layer,verts in real(*args,**kwargs):
                yield layer,verts+np.array([0.,4.]) if layer.name=='torso' else verts
        with mock.patch.object(p,'meshes',broken):faults=pc.check_connections(r,clip,2,12)
        self.assertTrue(any('torso: stride frame 0:' in x for x in faults),faults)

    def test_missing_one_attachment_cannot_pass(self):
        r,clip=self.renderer();del r.art.puppet.pelvis_bindings['leg_far']
        self.assertIn('missing full pelvis',pc.check_connections(r,clip,2,12)[0])

    def test_source_without_overlap_is_rejected_instead_of_stretched(self):
        r,_=self.renderer();p=r.art.puppet;parent,_,_=p.pelvis_bindings['leg_near']
        parent.image=Image.new('RGBA',parent.image.size)
        child=next(x for x in p.layers if x.name=='leg_near')
        with self.assertRaisesRegex(ValueError,'lacks registered pelvis overlap'):
            pp.pelvis_blend_weights(child,parent,*child.rest[:2])

    def test_area_projection_unfolds_mesh_without_moving_pinned_seam(self):
        x,y=np.meshgrid(np.arange(3,dtype=float),np.arange(3,dtype=float))
        vertices=np.stack((x,y),-1);vertices[1,1]=[1.,-1.]
        cells=np.array([[0,0],[0,1],[1,0],[1,1]])
        pinned=np.zeros((3,3),bool);pinned[0]=True;pinned[2]=True
        self.assertTrue(pp.flipped(vertices,cells).any())
        solved=pp.untangle(vertices,cells,pinned=pinned)
        np.testing.assert_array_equal(solved[pinned],vertices[pinned])
        self.assertFalse(pp.flipped(solved,cells).any())

    def test_connection_solver_never_repaints_source_pixels(self):
        r,clip=self.renderer(True)
        before={x.name:x.image.tobytes() for x in r.art.puppet.layers}
        pc.check_connections(r,clip,5,12)
        self.assertEqual(before,{x.name:x.image.tobytes() for x in r.art.puppet.layers})

    @unittest.expectedFailure
    def test_painted_high_waistband_requires_semantic_review(self):
        """Known gap: connected source art can paint trousers too high.

        Recolour a synthetic torso's opaque upper region as trouser fabric,
        preserving all source geometry. Contact cannot recognize garment
        identity/height. Keep source_garment_registration mandatory instead
        of claiming that a zero-drift report certifies clothing placement.
        """
        r,clip=self.renderer(True)
        torso=next(x for x in r.art.puppet.layers if x.name=='torso')
        pixels=np.asarray(torso.image).copy()
        upper=np.indices(pixels.shape[:2])[0] < pixels.shape[0]//2
        pixels[upper & (pixels[...,3]>128),:3]=(70,75,95)
        torso.image=Image.fromarray(pixels,'RGBA')
        self.assertTrue(pc.check_connections(r,clip,2,12),
                        'painted garment height needs semantic source comparison')


class ConnectionEvidence(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        (self.root/'frames/idle').mkdir(parents=True)
        hashes=[]
        for i in range(2):
            image=Image.new('RGBA',(32,40),(40+i,80,130,255));image.save(self.root/f'frames/idle/idle_{i:03d}.png')
            hashes.append(hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest())
        parts=('torso','leg_near','leg_far')
        self.doc={'clips':{'idle':{'frames':[0,1]}}}
        self.trace={'connection_review_required':True,'connections':dict(method='registered_pelvis_overlap',
            bindings={n:{'source_points':[[2,2],[4,2],[2,5],[4,5]]} for n in parts},
            clips={'idle':{'frames':2,'parts':{n:[0.,0.] for n in parts}}},frame_hashes={'idle':hashes})}
        reference=self.root/'binding_reference.png';Image.new('RGBA',(32,40),(40,80,130,255)).save(reference)
        self.trace['connections']['source_reference_sha256']=hashlib.sha256(reference.read_bytes()).hexdigest()

    def faults(self):return connection_report_faults(self.root,self.doc,self.trace)

    def test_complete_evidence_passes(self):self.assertEqual(self.faults(),[])

    def test_missing_report_frames_and_parts_fail_closed(self):
        for fault in ('report','frame','part','sample'):
            original=copy.deepcopy(self.trace)
            if fault=='report':del self.trace['connections']
            elif fault=='frame':self.trace['connections']['clips']['idle']['parts']['torso'].pop()
            elif fault=='part':del self.trace['connections']['clips']['idle']['parts']['leg_far']
            else:self.trace['connections']['bindings']['torso']['source_points']=[]
            with self.subTest(fault=fault):self.assertTrue(self.faults())
            self.trace=original

    def test_two_pixel_tear_is_not_dilated_away(self):
        self.trace['connections']['clips']['idle']['parts']['leg_near'][1]=2.
        faults=self.faults();self.assertEqual([(f['clip'],f['frame'],f['part']) for f in faults],[('idle',1,'leg_near')])

    def test_colour_only_pixel_replacement_invalidates_measurements(self):
        Image.new('RGBA',(32,40),(240,90,30,255)).save(self.root/'frames/idle/idle_001.png')
        self.assertTrue(any(f['frame']==1 and 'different RGBA' in f['what'] for f in self.faults()))

    def test_nonfinite_or_negative_measurements_fail(self):
        for value in (float('nan'),float('inf'),-1.,True):
            self.trace['connections']['clips']['idle']['parts']['torso'][0]=value
            with self.subTest(value=value):self.assertTrue(self.faults())

    def test_basic_profile_cannot_disable_missing_connection_report(self):
        self.trace['binding_profile']='basic-side-v1';self.trace['connection_review_required']=False
        del self.trace['connections']
        self.assertTrue(self.faults())

    def test_replaced_source_reference_invalidates_approval(self):
        Image.new('RGBA',(32,40),(200,30,20,255)).save(self.root/'binding_reference.png')
        self.assertTrue(any('different registered source' in f['what'] for f in self.faults()))

    def test_visual_gate_rejects_missing_data_even_if_status_is_forged(self):
        import visual_review
        (self.root/'animations.json').write_text(json.dumps(self.doc))
        self.trace['connections']['status']='PASS';del self.trace['connections']['frame_hashes']
        (self.root/'rig_trace.json').write_text(json.dumps(self.trace))
        self.assertEqual(visual_review.binding_gate(self.root),1)
