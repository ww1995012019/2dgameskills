"""Hidden waistband edges and ordinary-run amplitude need independent evidence."""
import copy
import math
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
from sprite_anim import puppet as pp,puppet_check as pc
from sprite_anim.art import Canvas
from sprite_anim.rig import Body,full_pose
from sprite_anim.motions import OrdinaryRun,build_clips,Proc
from sprite_anim.render import GROUND_FRAC
from sprite_anim.integrity import ordinary_run_faults
import test_registered_connections as original


class OrdinaryRunEnvelope(unittest.TestCase):
    def test_two_body_proportions_use_bounded_running_and_consistent_ground_speed(self):
        for body in (Body(),Body(thigh=11.,shin=13.,chest_len=26.,head_size=1.3)):
            with self.subTest(body=body):
                clip=OrdinaryRun(body)
                report=pc.ordinary_run_report(clip,body,21,30)
                self.assertEqual(ordinary_run_faults(report,21),[])
                self.assertAlmostEqual(clip.speed,clip.L/(clip.duty*clip.T))
                self.assertLess(report['stride_ratio'],1.)
                self.assertTrue(any(not any(clip.contacts(i*.001).values()) for i in range(700)))

    def test_sprint_sized_stride_is_rejected_at_the_measured_peak_frame(self):
        body=Body();clip=OrdinaryRun(body);clip.stride(1.5*(body.thigh+body.shin))
        report=pc.ordinary_run_report(clip,body,21,30)
        faults=ordinary_run_faults(report,21)
        peak=max(range(21),key=lambda i:report['samples'][i]['foot_span_ratio'])
        self.assertTrue(any(f['frame']==peak and 'stride_ratio' in f['what'] for f in faults),faults)

    def test_excessive_lift_is_rejected_without_reclassifying_the_style(self):
        body=Body();clip=OrdinaryRun(body);clip.lift=.6*(body.thigh+body.shin)
        report=pc.ordinary_run_report(clip,body,21,30)
        faults=ordinary_run_faults(report,21)
        self.assertTrue(any('lift_ratio' in f['what'] and f['frame']>0 for f in faults),faults)

    def test_sparse_or_replaced_style_evidence_cannot_pass(self):
        body=Body();report=pc.ordinary_run_report(OrdinaryRun(body),body,21,30)
        report['profile']='legacy_run'
        self.assertTrue(ordinary_run_faults(report,21))
        report['samples'].pop()
        with self.assertRaisesRegex(ValueError,'coverage'):ordinary_run_faults(report,21)

    def test_legacy_default_is_preserved_and_basic_profile_is_explicit(self):
        legacy=build_clips()['run']
        self.assertEqual((legacy.L,legacy.lift),(48,19))
        selected=build_clips(gait={'run':{'profile':'ordinary_run_v1'}})['run']
        self.assertIsInstance(selected,OrdinaryRun)
        self.assertLess(selected.L,legacy.L)
        with self.assertRaisesRegex(ValueError,'profile'):
            build_clips(gait={'run':{'profile':'invented'}})


class GarmentMaterial(unittest.TestCase):
    def test_waist_band_collapse_is_not_hidden_by_the_thigh_roi(self):
        case=original.ThighMaterial('runTest');layer,vertices=case.fixture()
        source=vertices.copy()
        strength=np.clip((48-vertices[...,1])/18.,0.,1.)
        vertices[...,0]=60+(vertices[...,0]-60)*(1-.98*strength)
        self.assertEqual(pc.thigh_strain(layer,vertices,1.)['bad_share'],0.)
        report=dict(origin=[0.,0.],up=[0.,-1.],attachment_depth=0.,fade=40.)
        self.assertGreater(pc.garment_strain(layer,vertices,1.,report)['bad_share'],.1)
        self.assertFalse(np.array_equal(source,vertices))

    def test_material_solver_keeps_rigid_frames_and_fixed_waist_vertices(self):
        layer,vertices=original.ThighMaterial('runTest').fixture()
        layer.used=np.ones(layer.vx.shape,bool)
        weights=np.clip((170-layer.vy)/120.,0.,1.)
        solver=pp.GarmentBand(layer,weights)
        for angle,scale in ((.5,.8),(-.8,1.4)):
            c,s=math.cos(angle),math.sin(angle)
            target=vertices@np.array([[c,s],[-s,c]])*scale+[31.,17.]
            solved=solver.solve(target,scale)
            np.testing.assert_allclose(solved,target,atol=1e-7)
            fixed=~solver.movable.reshape(layer.vx.shape)
            np.testing.assert_array_equal(solved[fixed],target[fixed])


class HiddenGarmentEdges(unittest.TestCase):
    def renderer(self,wide=False):
        case=original.RegisteredConnections('runTest');r,_=case.renderer(wide)
        self.addCleanup(case.doCleanups)
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        p=r.art.puppet;indexed={l.name:l for l in p.layers};layers={};factor=4
        for name in ('arm_far','leg_far','leg_near','hips','torso','arm_near'):
            l=indexed[name]
            l.image.resize(tuple(v*factor for v in l.image.size),Image.Resampling.NEAREST).save(Path(folder.name)/(name+'.png'))
            data=dict(kind=l.kind,image=name+'.png',offset=(l.offset*factor).tolist(),
                      radius=l.radius*factor,source_frame=l.source_frame)
            if l.kind=='rigid':data.update(follow=l.follow,anchor=(np.asarray(l.anchor)*factor).tolist())
            else:data.update(bones=l.bones,rest=[(x*factor).tolist() for x in l.rest],root_lock=l.root_lock)
            if name.startswith('leg_'):data['pelvis_garment']='hips'
            if name=='torso':data['pelvis_skin']='hips'
            layers[name]=data
        r.art.puppet=pp.Puppet(dict(_dir=folder.name,puppet=dict(px_per_unit=p.px_per_unit*factor,
            joints={n:(v*factor).tolist() for n,v in p.joints.items()},rest_angles=p.rest_angles,layers=layers)))
        return r,Proc('stride',1.,lambda t:full_pose(dict(hp=0.)))

    def test_two_proportions_keep_the_original_hidden_rims_covered(self):
        for wide in (False,True):
            with self.subTest(wide=wide):
                r,c=self.renderer(wide)
                self.assertEqual(pc.check_connections(r,c,3,12),[])
                self.assertTrue(all(row['exposed']==0 for rows in r.connection_checks['stride']['edge_visibility'].values() for row in rows))

    def test_alpha_visibility_fault_is_located_even_with_zero_connection_drift(self):
        r,c=self.renderer(True);p=r.art.puppet;real_meshes=p.meshes;real_raster=pp.raster
        frame=-1;center=None
        def cloth(*_):
            nonlocal frame
            frame+=1;return {}
        r.cloth_at=cloth
        def meshes(cv,sk,cloth,ground_contact=False,**kw):
            nonlocal center
            current=list(real_meshes(cv,sk,cloth,ground_contact,**kw));parts={l.name:(l,v) for l,v in current}
            points={n:pp.mesh_points(parts[n][0],parts[n][1],binding[2]['source_points']) for n,binding in p.garment_bindings.items()}
            lo=np.maximum(0,np.floor(np.vstack(list(points.values())).min(0)).astype(int)-3)
            center=points['leg_far'][0]-lo
            yield from current
        def raster(layer,verts,mip,w,h):
            result=real_raster(layer,verts,mip,w,h)
            if frame==2 and layer.name in ('hips','torso','leg_near'):
                yy,xx=np.mgrid[:h,:w];result[(xx-center[0])**2+(yy-center[1])**2<16,3]=0.
            return result
        with mock.patch.object(p,'meshes',meshes),mock.patch.object(pp,'raster',raster):
            faults=pc.check_connections(r,c,3,12)
        self.assertTrue(any('garment edge: leg_far: stride frame 2:' in f for f in faults),faults)
        self.assertFalse(any(f.startswith('connection:') or 'frame 0:' in f for f in faults),faults)


class GarmentReviewEvidence(unittest.TestCase):
    def fixture(self,registered=False):
        import test_pelvic_visual_gate as visual
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);root=Path(folder.name)
        doc,trace=visual.fixture(root,clips=('run',),count=4)
        if registered:
            import json
            trace['connections']={'method':'registered_garment_surfaces_v3'}
            (root/'rig_trace.json').write_text(json.dumps(trace));visual.review.build(root)
        index,verdict=visual.accepted(root)
        return visual.review,root,index,verdict

    def test_hidden_edges_and_requested_motion_style_cannot_be_skipped(self):
        review,root,index,verdict=self.fixture()
        entry=next(e for e in index['sheets'] if e['sheet'].startswith('hips_'))
        for name in ('hidden_garment_edges','motion_style_match'):
            row=copy.deepcopy(verdict['sheets'][entry['sheet']]);del row['checks'][name]
            with self.subTest(check=name),self.assertRaisesRegex(ValueError,name):
                review.validate_checklist(entry['sheet'],row,entry)

    def test_registered_waist_macros_cannot_be_deleted_or_removed_from_index(self):
        review,root,index,_=self.fixture(True)
        name=next(e['sheet'] for e in index['sheets'] if e['sheet'].startswith('garment_edges_'))
        (root/'review'/name).unlink()
        with self.assertRaisesRegex(ValueError,'missing required'):review.validate_index(root,index)
        index['sheets']=[e for e in index['sheets'] if e['sheet']!=name]
        index['required_sheets'].remove(name)
        with self.assertRaisesRegex(ValueError,'missing or unexpected'):review.validate_index(root,index)


if __name__=='__main__':unittest.main()
