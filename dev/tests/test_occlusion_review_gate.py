"""Candidates require explicit output-bound decisions, never automatic clearance."""
import copy
import json
import sys
import subprocess
from dataclasses import asdict
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
from sprite_anim import occlusion_review as review


class ReviewGate(unittest.TestCase):
    def candidate(self):
        arm=np.zeros((40,40));arm[5:35,15:25]=1
        hand=np.zeros_like(arm,dtype=bool);hand[28:35,12:28]=True
        fore=np.zeros_like(arm,dtype=bool);fore[12:22,12:28]=True
        cover=np.zeros_like(arm);cover[10:27]=1
        row=review.visibility_metrics([('arm_far',arm),('torso',cover)],'arm_far',hand,fore)
        return dict(row,clip='probe',frame=0,supersampling=1)

    def output(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        (root/'sheets').mkdir();Image.new('RGBA',(40,40),'blue').save(root/'sheets/probe.png')
        (root/'animations.json').write_text(json.dumps({'frame_size':40,'clips':{'probe':{'frames':[0]}}}))
        summary=review.write_report(root,[self.candidate()],{'probe':1})
        (root/'rig_trace.json').write_text(json.dumps({'occlusion_review':summary}))
        return root,summary

    def decisions(self,root,verdict='accepted'):
        data=json.loads((root/'occlusion_decisions_template.json').read_text());data['reviewer']='Test visual reviewer'
        for row in data['decisions']:row.update(verdict=verdict,rationale='Synthetic test: examined exact frame, intended overlap.')
        file=root/'supplied_decisions.json';file.write_text(json.dumps(data));return file,data

    def test_candidate_selection_positive_and_negative_boundaries(self):
        row=self.candidate();self.assertTrue(review.is_candidate(row))
        for changes in ({'hand_visible_fraction':.01},{'visible_hand_mass':3.9},
                        {'isolated_hand_mass':7.9},{'forearm_visible_fraction':.26},
                        {'forearm_opaque_occlusion_fraction':.64},
                        {'isolated_hand_forearm_connected':False},
                        {'hand_visible_fraction':None}):
            with self.subTest(changes=changes):self.assertFalse(review.is_candidate(dict(row,**changes)))
        scaled=dict(row,supersampling=2,isolated_hand_mass=row['isolated_hand_mass']*4,
                    visible_hand_mass=row['visible_hand_mass']*4)
        self.assertTrue(review.is_candidate(scaled))

    def test_transparent_occlusion_is_not_a_candidate(self):
        arm=np.ones((20,20));hand=np.zeros_like(arm,dtype=bool);hand[15:]=True
        fore=np.zeros_like(arm,dtype=bool);fore[3:10]=True
        cover=np.zeros_like(arm);cover[:14]=.9
        row=review.visibility_metrics([('arm',arm),('cloth',cover)],'arm',hand,fore)
        self.assertLess(row['forearm_visible_fraction'],.25)
        self.assertFalse(review.is_candidate(row))

    def test_pending_then_explicit_acceptance_then_stale_asset(self):
        root,summary=self.output();self.assertEqual(summary['status'],'review_required')
        self.assertEqual(review.check_current(root),1)
        path,_=self.decisions(root);self.assertEqual(review.record(root,path),0)
        self.assertEqual(review.check_current(root),0)
        Image.new('RGBA',(40,40),'red').save(root/'sheets/probe.png')
        self.assertEqual(review.check_current(root),1)
        self.assertEqual(review.record(root,path),1)

    def test_rejected_candidates_stay_pending_acceptance(self):
        root,_=self.output();path,_=self.decisions(root,'rejected')
        self.assertEqual(review.record(root,path),1)
        self.assertTrue((root/'occlusion_decisions.json').exists())
        self.assertEqual(review.check_current(root),1)

    def test_missing_duplicate_pending_hash_and_rationale_rejected(self):
        root,_=self.output();path,good=self.decisions(root)
        bads=[]
        bad=copy.deepcopy(good);bad['decisions']=[];bads.append(bad)
        bad=copy.deepcopy(good);bad['decisions']*=2;bads.append(bad)
        for key,value in [('rationale',''),('verdict','pending'),('asset_sha256','0'*64),('id','other')]:
            bad=copy.deepcopy(good);bad['decisions'][0][key]=value;bads.append(bad)
        bad=copy.deepcopy(good);bad['output_hash']='0'*64;bads.append(bad)
        bad=copy.deepcopy(good);bad['reviewer']='';bads.append(bad)
        for bad in bads:
            with self.subTest(bad=bad):
                path.write_text(json.dumps(bad));self.assertEqual(review.record(root,path),1)
        self.assertFalse((root/'occlusion_decisions.json').exists())

    def test_no_candidate_is_only_a_scoped_measurement_and_missing_report_fails(self):
        root,_=self.output();summary=review.write_report(root,[],{'probe':1})
        (root/'rig_trace.json').write_text(json.dumps({'occlusion_review':summary}))
        self.assertEqual(summary['status'],'no_candidates');self.assertEqual(review.check_current(root),0)
        (root/'occlusion_review.json').unlink();self.assertEqual(review.check_current(root),1)

    def test_empty_opt_in_summary_cannot_bypass_review(self):
        root,_=self.output()
        (root/'rig_trace.json').write_text('{"occlusion_review": {}}')
        self.assertEqual(review.check_current(root),1)
        (root/'occlusion_review.json').unlink()
        self.assertEqual(review.check_current(root),1)

    def test_report_tamper_and_regeneration_invalidate_acceptance(self):
        root,_=self.output();path,_=self.decisions(root);self.assertEqual(review.record(root,path),0)
        review.write_report(root,[self.candidate()],{'probe':1})
        self.assertFalse((root/'occlusion_decisions.json').exists());self.assertEqual(review.check_current(root),1)
        report=json.loads((root/'occlusion_review.json').read_text());report['candidates']=[]
        (root/'occlusion_review.json').write_text(json.dumps(report));self.assertEqual(review.check_current(root),1)

    def test_generate_opted_in_output_includes_bound_review_scope_without_frames(self):
        from test_attachment_pixels import AttachmentFrameLocations
        fixture=AttachmentFrameLocations();self.addCleanup(fixture.doCleanups)
        renderer,_=fixture.renderer()
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        puppet=renderer.art.puppet;layers={}
        for layer in puppet.layers:
            layer.image.save(root/(layer.name+'.png'))
            data=dict(image=layer.name+'.png',kind=layer.kind,radius=layer.radius,
                      bones=layer.bones,rest=[p.tolist() for p in layer.rest],
                      root_lock=layer.root_lock,source_frame=layer.source_frame)
            if layer.kind=='rigid':data.update(follow=layer.follow,anchor=layer.anchor)
            layers[layer.name]=data
        spec=dict(name='Synthetic gate fixture',weapon='none',cloth=[],body=asdict(renderer.art.body),
                  puppet=dict(px_per_unit=puppet.px_per_unit,attachment_checks=True,
                              joints={k:v.tolist() for k,v in puppet.joints.items()},
                              rest_angles=puppet.rest_angles,layers=layers))
        character=root/'character.json';character.write_text(json.dumps(spec));out=root/'out'
        script=Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts/generate.py'
        subprocess.run([sys.executable,str(script),'--character',str(character),'--size','96','--fps','2',
                        '--clips','idle','--no-fx','--no-frames','--out',str(out)],check=True,capture_output=True)
        report=json.loads((out/'occlusion_review.json').read_text());trace=json.loads((out/'rig_trace.json').read_text())
        self.assertEqual(trace['occlusion_review']['report_id'],report['report_id'])
        self.assertEqual(trace['occlusion_review']['frames_checked'],sum(report['frames'].values()))
        self.assertIn('sheets/idle.png',report['assets']);self.assertFalse((out/'occlusion_decisions.json').exists())
        self.assertEqual(report,review._current_report(out))

    def test_intentional_back_arm_overlap_still_requires_an_explicit_review(self):
        # A visible hand can emerge naturally at the body edge while the middle
        # forearm is behind the body. Numeric selection does not prove a defect.
        root,_=self.output();self.assertEqual(review.check_current(root),1)
        path,decision=self.decisions(root)
        decision['decisions'][0]['rationale']='Viewed exact frame: continuous distal skin emerges at torso edge; intentional back-arm occlusion, no visual separation.'
        path.write_text(json.dumps(decision))
        self.assertEqual(review.record(root,path),0)
        self.assertEqual(review.check_current(root),0)

    def test_legacy_outputs_without_gate_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as root:self.assertEqual(review.check_current(root),0)


if __name__=='__main__':unittest.main()
