"""Actual support height, paired steps and native-frame faults must be checked."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image,ImageDraw,ImageFilter

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'game-sprite-animator/scripts'))
from sprite_anim.motions import OrdinaryRun,LegacyOrdinaryRun
from sprite_anim.rig import Body
from sprite_anim.puppet_check import ordinary_run_report
from sprite_anim.integrity import ordinary_run_faults,rendered_run_faults
from sprite_anim.render import frame_count,playback_speed
from sprite_anim.export import gif_durations


class RunSupportRhythm(unittest.TestCase):
    def test_two_proportions_have_small_equal_half_cycles_with_apex_in_flight(self):
        for body in (Body(),Body(thigh=11.,shin=13.,hip_n_at=(2.,3.),hip_f_at=(-2.,3.))):
            clip=OrdinaryRun(body);report=ordinary_run_report(clip,body,22,30)
            self.assertEqual(ordinary_run_faults(report,22),[])
            heights=np.array([x['pelvis_y_ratio'] for x in report['rhythm']['phase_samples']])
            np.testing.assert_allclose(heights[:120],heights[120:],atol=1e-12)
            self.assertLess(np.ptp(heights),.03)

    def test_actual_legacy_bounce_fails_even_with_a_small_declared_bob_and_current_label(self):
        body=Body();clip=LegacyOrdinaryRun(body,bounce=.8);clip.profile='ordinary_run_v2'
        report=ordinary_run_report(clip,body,22,30)
        self.assertLess(report['bob_ratio'],.05)
        faults=ordinary_run_faults(report,22)
        self.assertTrue(any('actual pelvis height range' in f['what'] for f in faults),faults)
        self.assertTrue(any('vertical phase acceleration' in f['what'] for f in faults),faults)

    def test_unequal_halves_are_located_without_an_excessive_declared_bob(self):
        body=Body();clip=OrdinaryRun(body);real=clip.sample
        def sample(t):
            p=real(t);p['root_y']+=.012*(body.thigh+body.shin)*math.sin(math.tau*t/clip.T);return p
        clip.sample=sample
        report=ordinary_run_report(clip,body,24,30)
        faults=ordinary_run_faults(report,24)
        self.assertTrue(any(f['frame'] in (6,18) and 'half-step height mismatch' in f['what'] for f in faults),faults)

    def test_abrupt_body_drop_is_located_in_the_actual_exported_frame(self):
        body=Body();clip=OrdinaryRun(body);real=clip.sample
        def sample(t):
            p=real(t)
            if 5/24<=t/clip.T<6/24:p['root_y']+=.04*(body.thigh+body.shin)
            return p
        clip.sample=sample;faults=ordinary_run_faults(ordinary_run_report(clip,body,24,30),24)
        self.assertTrue(any(f['frame']==5 and 'vertical frame step' in f['what'] for f in faults),faults)

    def test_paired_sampling_keeps_equal_support_counts_and_retimed_ground_travel(self):
        clip=OrdinaryRun(Body())
        for fps in (12,15,24,30,60):
            n=frame_count(clip,fps);self.assertEqual(n%2,0)
            states=[clip.contacts(clip.T*i/n) for i in range(n)]
            self.assertEqual(sum(x['n'] for x in states),sum(x['f'] for x in states))
            self.assertAlmostEqual(playback_speed(clip,fps)*n/fps,clip.speed*clip.T)
        self.assertEqual(frame_count(clip,30),22)

    def test_odd_export_and_missing_phase_evidence_cannot_pass(self):
        clip=OrdinaryRun(Body());report=ordinary_run_report(clip,Body(),21,30)
        self.assertTrue(any('half-step frame counts' in f['what'] for f in ordinary_run_faults(report,21)))
        report['rhythm']['phase_samples'].pop()
        with self.assertRaisesRegex(ValueError,'full-cycle'):ordinary_run_faults(report,21)

    def test_gif_quantization_repeats_identical_timing_for_both_steps(self):
        durations=gif_durations(22,30,2)
        self.assertEqual(durations[:11],durations[11:])
        self.assertEqual(sum(durations),740)
        with self.assertRaises(ValueError):gif_durations(21,30,2)


class NativeRunFrames(unittest.TestCase):
    def frames(self,jump=False):
        out=[]
        for i in range(22):
            top=20+round(2*math.cos(4*math.pi*i/22))+(12 if jump and i==8 else 0)
            image=Image.new('RGBA',(100,140));ImageDraw.Draw(image).rectangle((35,top,65,110),fill=(60,80,100,255))
            out.append(np.asarray(image))
        return out

    def test_small_symmetric_rendered_motion_passes(self):
        self.assertEqual(rendered_run_faults(self.frames(),80),[])

    def test_rendered_jump_is_located_independently_of_pose_parameters(self):
        faults=rendered_run_faults(self.frames(True),80)
        self.assertTrue(any(f['clip']=='run' and f['frame']==8 and 'rendered vertical frame step' in f['what'] for f in faults),faults)


class HandContext(unittest.TestCase):
    def fixture(self):
        import test_attachment_pixels as fixture
        from sprite_anim.art import Canvas
        from sprite_anim.motions import Proc
        from sprite_anim.rig import full_pose,solve
        from sprite_anim.render import GROUND_FRAC
        case=fixture.AttachmentFrameLocations('runTest');r,_=case.renderer();self.addCleanup(case.doCleanups)
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        puppet=r.art.puppet
        for layer in puppet.layers:
            if layer.name.startswith('arm_'):
                pixels=np.array(layer.image);yy,xx=np.indices(pixels.shape[:2])
                stripes=np.where((xx//2)%2,230,25).astype(np.uint8)
                pixels[...,:3]=stripes[...,None];layer.image=Image.fromarray(pixels)
                layer.tip_lock=True
                side='n' if layer.name=='arm_near' else 'f'
                puppet.rest_arm[side]=(tuple(layer.rest[-1]),tuple(layer.rest[-2]))
        puppet.mips.clear()
        ref=Image.new('RGBA',(256,256))
        for layer in puppet.layers:ref.alpha_composite(layer.image,tuple(int(v) for v in layer.offset))
        ref.save(Path(folder.name)/'source.png')
        pose=full_pose(dict(pelvis=0,spine=0,head=0));clip=Proc('run',.7,lambda t:pose)
        cv=Canvas(256,1,2.,GROUND_FRAC,1,False,(0,0,0));puppet.draw(cv,solve(pose,r.art.body),{})
        actual=Image.new('RGBA',(256,256),(100,100,100,255));actual.alpha_composite(Image.fromarray(cv.buf))
        spec={'_dir':folder.name,'puppet':{'source':'source.png'}}
        return r,spec,clip,actual

    def test_flat_clothing_context_does_not_dilute_the_same_hand_detail(self):
        from sprite_anim.puppet_check import check_hands
        r,spec,clip,image=self.fixture();frames=[np.asarray(image)]*4
        self.assertEqual(check_hands(r,spec,clip,frames,30),[])
        for layer in r.art.puppet.layers:
            if layer.name.startswith('arm_'):layer.tip_lock=False
        self.assertTrue(check_hands(r,spec,clip,frames,30),'The legacy crop includes opaque flat context.')

    def test_blurring_the_actual_hand_still_fails_at_the_original_limit(self):
        from sprite_anim.puppet_check import check_hands,HAND_DETAIL
        r,spec,clip,image=self.fixture();frames=[np.asarray(image.filter(ImageFilter.GaussianBlur(4)))]*4
        self.assertEqual(HAND_DETAIL,.55)
        self.assertTrue(any('hand:' in f for f in check_hands(r,spec,clip,frames,30)))


class SupportReviewGate(unittest.TestCase):
    def test_full_cycle_plot_playback_and_observations_cannot_be_removed(self):
        import test_pelvic_visual_gate as visual
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);doc,trace=visual.fixture(root,clips=('run',),count=4)
            doc['clips']['run']['frame_multiple']=2
            trace['traces']['run']['skeleton'].setdefault('hip',trace['traces']['run']['skeleton']['hip_n'])
            trace['connections']=dict(method='registered_garment_surfaces_v3',ordinary_run=dict(samples=[
                dict(near_contact=i<2,far_contact=i>=2) for i in range(4)]))
            (root/'animations.json').write_text(json.dumps(doc));(root/'rig_trace.json').write_text(json.dumps(trace))
            visual.review.build(root);index=json.load(open(root/'review/index.json'));template=json.load(open(root/'review/verdict_template.json'))
            entry=next(e for e in index['sheets'] if e['sheet']=='run_support_00.png')
            self.assertEqual([p['frame'] for p in entry['poses']],list(range(4)))
            row=copy.deepcopy(template['sheets']['run_support_00.png']);row['verdict']='pass'
            for check in row['checks'].values():
                check.update(status='pass',evidence='Synthetic fixture for schema enforcement.')
                for o in check.get('observations',[]):o['evidence']='Fixture pose.'
                for o in check.get('playback',[]):o['evidence']='Fixture playback.'
            visual.review.validate_checklist('run_support_00.png',row,entry)
            row['checks']['support_rhythm']['observations'].pop()
            with self.assertRaisesRegex(ValueError,'every required pose'):
                visual.review.validate_checklist('run_support_00.png',row,entry)
            (root/'review/run_support_motion_000.gif').unlink()
            with self.assertRaisesRegex(ValueError,'support playback'):visual.review.validate_index(root,index)


if __name__=='__main__':unittest.main()
