"""Fault injection at the QA entry point: unavailable evidence is not a pass."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[2] / 'game-animator/modes/game-sprite-animator/scripts'
spec = importlib.util.spec_from_file_location('qa_evidence_target', SCRIPTS / 'qa_motion.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class EvidenceReporting(unittest.TestCase):
    def run_case(self, trace=None, tags=(), floor_fault=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = root / 'frames' / 'run'
            frames.mkdir(parents=True)
            for i in range(3):
                im = Image.new('RGBA', (24, 24))
                ImageDraw.Draw(im).rectangle((6 + i, 4, 12 + i, 20), fill='green')
                if i==floor_fault:
                    ImageDraw.Draw(im).rectangle((8,20,10,22),fill='green')
                im.save(frames / f'run_{i:03}.png')
            doc=dict(frame_size=24,pivot=[12,24*.86],clips=dict(run=dict(
                frames=[0,1,2],fps=3,loop=True,tags=list(tags),speed_px_s=0)))
            (root / 'animations.json').write_text(json.dumps(doc))
            if trace is not None:
                (root / 'rig_trace.json').write_text(json.dumps(trace))
            # This fixture tests dispatch/reporting. Geometry implementations have
            # separate real-mesh fault tests; no connection checker is mocked here.
            output = io.StringIO()
            with patch.object(qa, 'analyse_rig', return_value={}), \
                 patch.object(qa, 'summarize', return_value=({}, {})), \
                 patch.object(qa, 'skeleton_flags'), contextlib.redirect_stdout(output):
                failed = qa.run_set(directory)
            return failed, json.loads((root / 'qa_report.json').read_text()), output.getvalue()

    @staticmethod
    def trace():
        return dict(traces=dict(run=dict(metrics=[], joints={})), seams=[], unit_px=1.,
                    part_problems=[], bind_warnings=[], bind_gaps={})

    def test_missing_trace_never_claims_binding_parts_or_rig_checks_passed(self):
        failed, report, output = self.run_case()
        self.assertEqual(failed, 0)  # Missing evidence is not invented physical damage.
        self.assertEqual(report['parts']['status'], 'n/a')
        self.assertEqual(report['bind']['status'], 'n/a')
        self.assertEqual(report['evidence']['status'], 'WARN')
        self.assertIn('rig_trace.json', report['evidence']['missing'])
        self.assertFalse(report['scope']['rig_trace_available'])
        for check in ('slide', 'jitter', 'limits', 'clip', 'float', 'bones'):
            self.assertEqual(report['clips']['run'][check], 'n/a')
        self.assertRegex(output, r'run\s+3\s+PASS.*n/a')

    def test_trace_cannot_invent_passes_for_absent_binding_or_part_results(self):
        trace = self.trace()
        for field in ('part_problems', 'bind_warnings', 'bind_gaps'):
            del trace[field]
        _, report, _ = self.run_case(trace)
        self.assertEqual(report['parts']['status'], 'n/a')
        self.assertEqual(report['bind']['status'], 'n/a')
        self.assertEqual(report['evidence']['status'], 'WARN')

    def test_complete_legacy_numeric_evidence_keeps_its_existing_result(self):
        failed, report, _ = self.run_case(self.trace())
        self.assertEqual(failed, 0)
        self.assertEqual(report['parts']['status'], 'PASS')
        self.assertEqual(report['bind']['status'], 'PASS')
        self.assertEqual(report['evidence']['status'], 'PASS')
        self.assertEqual(report['evidence']['missing'], [])

    def test_real_part_failure_is_still_a_failure(self):
        trace = self.trace()
        trace['part_problems'] = ['leg_near: material missing along the thigh']
        failed, report, _ = self.run_case(trace)
        self.assertGreater(failed, 0)
        self.assertEqual(report['parts']['status'], 'FAIL')

    def test_partial_binding_evidence_does_not_hide_a_known_gap(self):
        trace = self.trace()
        del trace['bind_warnings']
        trace['bind_gaps'] = {'run': ['hip']}
        failed, report, _ = self.run_case(trace)
        self.assertGreater(failed, 0)
        self.assertEqual(report['bind']['status'], 'FAIL')
        self.assertEqual(report['evidence']['status'], 'WARN')

    def test_partial_binding_evidence_does_not_hide_known_warnings(self):
        trace = self.trace()
        del trace['bind_gaps']
        trace['bind_warnings'] = ['unverified garment overlap']
        _, report, _ = self.run_case(trace)
        self.assertEqual(report['bind']['status'], 'WARN')
        self.assertEqual(report['bind']['warnings'], trace['bind_warnings'])

    def test_carry_cannot_skip_garment_gate_by_removing_presentation_flags(self):
        for source in ('profile', 'actual_owner'):
            with self.subTest(source=source):
                trace = self.trace()
                if source == 'profile':
                    trace['binding_profile'] = 'side-rifle-carry-v1'
                else:
                    trace['connections'] = dict(bindings=dict(torso=dict(source_upper_carry={})))
                # No connection_review_required/basic marker, reference or valid
                # garment measurements. The real independent gate must reject it.
                failed, report, _ = self.run_case(trace)
                self.assertGreater(failed, 0)
                self.assertEqual(report['connections']['status'], 'FAIL')
                fault = report['connections']['problems'][0]
                self.assertEqual((fault['clip'], fault['frame']), ('run', 0))

    def test_actual_opaque_floor_fault_is_located_even_when_rig_metrics_claim_no_fault(self):
        trace=self.trace();trace['portrait_review_required']=True
        failed,report,_=self.run_case(trace,tags=('ground','tumble'),floor_fault=1)
        self.assertGreater(failed,0)
        clip=report['clips']['run']
        self.assertEqual(clip['painted_floor'],'FAIL')
        self.assertEqual(clip['painted_floor_evidence']['bad_frames'],[1])
        self.assertIn('painted art below ground',clip['flags']['1'])

    def test_floor_fault_in_any_clip_of_a_layered_character_is_located(self):
        # Walk/run boots and landing crouches, not only tumbles: the bone proxy
        # reported no contact fault while painted boot toes sank 2-3 px.
        for tags in (('ground',), ('ground', 'hold_feet'), ()):
            with self.subTest(tags=tags):
                trace=self.trace();trace['binding_profile']='basic-side-v1'
                failed,report,_=self.run_case(trace,tags=tags,floor_fault=2)
                self.assertGreater(failed,0)
                clip=report['clips']['run']
                self.assertEqual(clip['painted_floor'],'FAIL')
                self.assertEqual(clip['painted_floor_evidence']['bad_frames'],[2])
                self.assertIn('painted art below ground',clip['flags']['2'])

    def test_clean_layered_frames_pass_and_procedural_sets_report_not_applicable(self):
        trace=self.trace();trace['portrait_review_required']=True
        failed,report,_=self.run_case(trace,tags=('ground',))
        self.assertEqual(failed,0)
        self.assertEqual(report['clips']['run']['painted_floor'],'PASS')
        # Procedural templates have no painted source; their floor column is
        # not run and must not read as a pass.
        _,report,_=self.run_case(self.trace(),tags=('ground',),floor_fault=1)
        self.assertEqual(report['clips']['run']['painted_floor'],'n/a')


if __name__ == '__main__':
    unittest.main()
