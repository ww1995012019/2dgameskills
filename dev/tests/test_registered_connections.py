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
from sprite_anim.integrity import connection_report_faults,THIGH_DEFORMATION_LIMITS,GARMENT_EDGE_LIMITS


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
        good=dict(samples=30,bad_share=0.,min_scale=1.,max_scale=1.,min_area=1.,max_area=1.,
                  boundary_samples=10,boundary_bad=0,max_turn_error_px=0.)
        self.trace={'connection_review_required':True,'connections':dict(method='registered_garment_surfaces_v3',shape_limits=THIGH_DEFORMATION_LIMITS.copy(),edge_limits=GARMENT_EDGE_LIMITS.copy(),
            bindings={n:{'source_points':[[2,2],[4,2],[2,5],[4,5]],'parent':'hips',
                         'method':'registered_pelvis_overlap' if n=='torso' else 'registered_garment_rim_v1',
                         **({} if n=='torso' else {'source_joint':[3,3],'origin':[3,3],'up':[0.,-1.],
                            'attachment_depth':0.,'fade':12.,'occluders':['hips','torso'] if n=='leg_near' else ['leg_near','hips','torso']})} for n in parts},
            clips={'idle':{'frames':2,'parts':{n:[0.,0.] for n in parts},
                           'shape_parts':{n:[good.copy(),good.copy()] for n in ('leg_near','leg_far')},
                           'garment_shapes':{n:[good.copy(),good.copy()] for n in ('leg_near','leg_far')},
                           'edge_visibility':{n:[dict(samples=4,exposed=0,exposed_indices=[]) for _ in range(2)] for n in ('leg_near','leg_far')}}},frame_hashes={'idle':hashes})}
        reference=self.root/'binding_reference.png';Image.new('RGBA',(32,40),(40,80,130,255)).save(reference)
        self.trace['connections']['source_reference_sha256']=hashlib.sha256(reference.read_bytes()).hexdigest()

    def faults(self):return connection_report_faults(self.root,self.doc,self.trace)

    def test_complete_evidence_passes(self):self.assertEqual(self.faults(),[])

    def test_zero_drift_cannot_omit_thigh_shape_measurements(self):
        del self.trace['connections']['clips']['idle']['shape_parts']
        self.assertTrue(self.faults())

    def test_old_welded_leg_evidence_is_not_current_acceptance(self):
        self.trace['connections']['method']='registered_pelvis_overlap'
        self.assertTrue(self.faults())

    def test_rotating_socket_evidence_cannot_omit_hidden_clothing_edges(self):
        self.trace['connections']['method']='registered_articulations_v2'
        self.assertTrue(self.faults())

    def test_zero_drift_does_not_clear_an_exposed_original_cut_edge(self):
        self.trace['connections']['clips']['idle']['edge_visibility']['leg_far'][1].update(
            exposed=1,exposed_indices=[2])
        faults=self.faults()
        self.assertEqual([(f['clip'],f['frame'],f['part']) for f in faults],[('idle',1,'leg_far')])
        self.assertIn('hidden garment',faults[0]['what'])

    def test_waist_deformation_cannot_be_omitted_or_cleared_by_a_good_thigh(self):
        row=self.trace['connections']['clips']['idle']
        row['garment_shapes']['leg_near'][1].update(bad_share=.4,min_scale=.02)
        self.assertTrue(any(f['frame']==1 and 'waist garment' in f['what'] for f in self.faults()))
        del row['garment_shapes']
        self.assertTrue(self.faults())

    def test_boundary_fault_cannot_be_averaged_away_or_replaced_with_old_evidence(self):
        row=self.trace['connections']['clips']['idle']['garment_shapes']['leg_near'][1]
        row.update(boundary_bad=1,bad_share=.001)
        faults=self.faults()
        self.assertTrue(any(f['clip']=='idle' and f['frame']==1 and f['part']=='leg_near'
                            and 'boundary' in f['what'] for f in faults),faults)
        row['boundary_bad']=0
        for field in ('boundary_samples','boundary_bad','max_turn_error_px'):
            value=row.pop(field)
            with self.subTest(missing=field):self.assertTrue(self.faults())
            row[field]=value

    def test_positive_areas_and_zero_drift_cannot_clear_a_backwards_waist_turn(self):
        row=self.trace['connections']['clips']['idle']['garment_shapes']['leg_far'][1]
        row['max_turn_error_px']=2.5
        faults=self.faults()
        self.assertEqual([(f['clip'],f['frame'],f['part']) for f in faults],[('idle',1,'leg_far')])
        self.assertIn('turns beyond',faults[0]['what'])

    def test_invalid_boundary_and_turn_measurements_fail_closed(self):
        row=self.trace['connections']['clips']['idle']['garment_shapes']['leg_near'][0]
        original=row.copy()
        for field,value in (('boundary_samples',True),('boundary_samples',0),
                            ('boundary_samples',31),('boundary_bad',-1),('boundary_bad',11),
                            ('max_turn_error_px',float('nan')),('max_turn_error_px',True),
                            ('max_turn_error_px',-1.)):
            row.update(original);row[field]=value
            with self.subTest(field=field,value=value):self.assertTrue(self.faults())

    def test_a_shared_surface_cannot_be_mislabelled_as_a_rotating_thigh(self):
        self.trace['connections']['bindings']['leg_near']['method']='registered_pelvis_overlap'
        self.assertTrue(self.faults())

    def test_positive_triangle_area_and_zero_drift_do_not_clear_a_collapsed_thigh(self):
        self.trace['connections']['clips']['idle']['shape_parts']['leg_far'][1].update(
            bad_share=.5,min_scale=.01,min_area=.01)
        faults=self.faults()
        self.assertTrue(any(x['clip']=='idle' and x['frame']==1 and x['part']=='leg_far' for x in faults),faults)

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


class ThighMaterial(unittest.TestCase):
    def fixture(self):
        x,y=np.meshgrid(np.arange(0.,121.,10.),np.arange(0.,241.,10.))
        j,i=np.indices((len(y)-1,x.shape[1]-1));cells=np.column_stack((j.ravel(),i.ravel()))
        layer=SimpleNamespace(vx=x,vy=y,offset=np.zeros(2),cells=cells,
            rest=[np.array([60.,30.]),np.array([60.,210.])],radius=20.,
            image=Image.new('RGBA',(121,241),(90,130,160,255)))
        return layer,np.stack((x,y),-1)

    def test_rigid_thighs_preserve_width_at_two_rotations_and_scales(self):
        for angle,scale in ((.8,.7),(-1.2,2.3)):
            layer,v=self.fixture();c,s=np.cos(angle),np.sin(angle)
            transformed=(v@np.array([[c,s],[-s,c]]))*scale+np.array([31.,-17.])
            row=pc.thigh_strain(layer,transformed,scale)
            self.assertGreater(row['samples'],10);self.assertEqual(row['bad_share'],0.)
            self.assertAlmostEqual(row['min_scale'],1.,places=5)

    def test_positive_area_cannot_hide_width_collapse(self):
        layer,v=self.fixture();v[...,0]*=.03
        self.assertFalse(pp.flipped(v,layer.cells).any())
        row=pc.thigh_strain(layer,v,1.)
        self.assertGreater(row['min_area'],0.);self.assertEqual(row['bad_share'],1.)

    def test_area_preserving_shear_is_also_rejected(self):
        layer,v=self.fixture();v[...,0]+=6*v[...,1]
        row=pc.thigh_strain(layer,v,1.)
        self.assertAlmostEqual(row['min_area'],1.);self.assertEqual(row['bad_share'],1.)

    def test_thigh_socket_rotates_instead_of_being_welded_to_pelvis(self):
        case=RegisteredConnections('runTest');self.addCleanup(case.doCleanups)
        r,clip=case.renderer(True);p=r.art.puppet;layers={l.name:l for l in p.layers}
        p.socket_bindings={}
        for name in ('leg_near','leg_far'):
            child=layers[name];p.pelvis_bindings.pop(name)
            child.root_lock=True
            p.socket_bindings[name]=(layers['hips'],None,pp.joint_socket_binding(child,layers['hips']))
        faults=pc.check_connections(r,clip,5,12)
        self.assertEqual(faults,[])
        self.assertEqual(set(r.connection_checks['stride']['shape_parts']),{'leg_near','leg_far'})

    def test_rigid_but_wrong_pelvis_rotation_fails_at_its_actual_frame(self):
        case=RegisteredConnections('runTest');self.addCleanup(case.doCleanups)
        r,clip=case.renderer(True);p=r.art.puppet;layers={l.name:l for l in p.layers}
        p.socket_bindings={}
        for name in ('leg_near','leg_far'):
            child=layers[name];p.pelvis_bindings.pop(name);child.root_lock=True
            p.socket_bindings[name]=(layers['hips'],None,pp.joint_socket_binding(child,layers['hips']))
        real=p.meshes;frame=-1
        def advance(*_):
            nonlocal frame
            frame+=1;return {}
        r.cloth_at=advance
        def welded(*args,**kwargs):
            for layer,verts in real(*args,**kwargs):
                if layer.name=='leg_far' and frame==2:
                    # A rigid 90-degree turn keeps every triangle's area and
                    # thickness. It is still the wrong anatomical rotation.
                    center=verts.mean((0,1));q=verts-center
                    verts=np.stack((-q[...,1],q[...,0]),-1)+center
                yield layer,verts
        with mock.patch.object(p,'meshes',welded):faults=pc.check_connections(r,clip,5,12)
        self.assertTrue(any('leg_far: stride frame 2:' in x for x in faults),faults)
        self.assertFalse(any('frame 0:' in x for x in faults),faults)
