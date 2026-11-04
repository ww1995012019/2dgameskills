"""Fault injection for required neck/hand evidence, not an anatomy classifier.

The two builds are synthetic. An explicit review can reject a seam or stiff
motion even when alpha contact and non-zero head rotation would pass.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'game-sprite-animator/scripts'))
import character_workflow as workflow
from sprite_anim import layer_slots as prompts
from sprite_anim import puppet_check
import numpy as np
from test_pelvic_visual_gate import fixture, accepted

module = importlib.util.spec_from_file_location('neck_hand_review', ROOT/'shared/scripts/visual_review.py')
review = importlib.util.module_from_spec(module)
module.loader.exec_module(review)


class NeckHandReview(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.doc, self.trace = fixture(self.root, ('idle', 'run'), 12)
        for clip, tr in self.trace['traces'].items():
            sk = tr['skeleton']
            for key, point in dict(el_n=[67, 35], wr_n=[77, 24], el_f=[26, 39], wr_f=[18, 48]).items():
                sk[key] = [[point[0] + (4 if i == 7 else 0), point[1]] for i in range(12)]
            tr['head_motion'] = dict(head_world_deg=[i * .1 for i in range(12)],
                                     chest_world_deg=[i * .2 for i in range(12)],
                                     relative_deg=[0, 0, -2, 0, 0, 0, 0, 0, 3, 0, 0, 0])
        self.trace.update(head_size=.4, portrait_review_required=True)
        (self.root/'rig_trace.json').write_text(json.dumps(self.trace))
        review.build(self.root)
        self.index, self.verdict = accepted(self.root)
        self.neck = next(e for e in self.index['sheets'] if e['sheet'].startswith('neck_'))
        self.hands = next(e for e in self.index['sheets'] if e['sheet'].startswith('hands_'))

    def record(self, value=None):
        path = self.root/'verdict.json'; path.write_text(json.dumps(value or self.verdict))
        return review.record(self.root, path)

    def test_two_builds_get_both_hands_and_head_motion_extremes_without_global_truncation(self):
        for proportions in (.4, 1.1):
            trace = copy.deepcopy(self.trace); trace['head_size'] = proportions
            rows = review.detail_rows(self.doc, trace, 'neck')
            for clip in self.doc['clips']:
                frames = {p['frame'] for name, _, poses in rows if name == clip for p in poses}
                self.assertTrue({0, 11, 2, 8}.issubset(frames))
            self.assertEqual(len(review.detail_boxes(trace['traces']['run']['skeleton'], trace, 'hands')), 2)
        self.assertEqual(self.record(), 0)
        self.assertEqual(review.check_current(self.root), 0)

    def test_all_frames_and_original_duration_are_present_in_playback(self):
        for entry in (self.neck, self.hands):
            for meta in entry['playback']:
                self.assertEqual(meta['frame_count'], 12)
                self.assertEqual(meta['duration_ms'], 400)
                with Image.open(self.root/'review'/meta['file']) as image:
                    duration = 0
                    for i in range(image.n_frames):
                        image.seek(i); duration += image.info['duration']
                    self.assertEqual(duration, 400)

    def test_new_checks_cannot_be_omitted_or_skipped(self):
        for entry, names in ((self.neck, review.NECK_CHECKS), (self.hands, review.HAND_CHECKS)):
            for name in names:
                for fault in ('missing', 'skipped'):
                    value = copy.deepcopy(self.verdict)
                    checks = value['sheets'][entry['sheet']]['checks']
                    if fault == 'missing': del checks[name]
                    else: checks[name]['status'] = 'not_applicable'
                    with self.subTest(name=name, fault=fault), self.assertRaisesRegex(SystemExit, name):
                        self.record(value)

    def test_every_selected_clip_frame_needs_concrete_evidence(self):
        for entry, name in ((self.neck, 'neck_continuity'), (self.hands, 'hand_pose_naturalness')):
            value = copy.deepcopy(self.verdict)
            value['sheets'][entry['sheet']]['checks'][name]['observations'].pop()
            with self.subTest(name=name), self.assertRaisesRegex(SystemExit, name): self.record(value)

    def test_static_pose_observations_cannot_replace_temporal_review(self):
        for entry, name in ((self.neck, 'head_motion_naturalness'), (self.hands, 'hand_pose_naturalness')):
            for fault in ('missing', 'blank', 'wrong_file', 'duplicate'):
                value = copy.deepcopy(self.verdict)
                check = value['sheets'][entry['sheet']]['checks'][name]
                if fault == 'missing': del check['playback']
                elif fault == 'blank': check['playback'][0]['evidence'] = ''
                elif fault == 'wrong_file': check['playback'][0]['file'] = 'unreviewed.gif'
                else: check['playback'].append(copy.deepcopy(check['playback'][0]))
                with self.subTest(name=name, fault=fault), self.assertRaisesRegex(SystemExit, name): self.record(value)

    def test_missing_playback_or_tampered_coverage_cannot_pass(self):
        path = self.root/'review'/self.neck['playback'][0]['file']
        path.unlink()
        with self.assertRaisesRegex(SystemExit, 'missing required playback'): self.record()

    def test_replaced_playback_invalidates_recorded_pass(self):
        self.assertEqual(self.record(), 0)
        path = self.root/'review'/self.hands['playback'][0]['file']
        Image.new('RGB', (16, 16), 'red').save(path)
        self.assertEqual(review.check_current(self.root), 1)

    def test_removing_detail_sheet_and_index_entry_cannot_remove_requirement(self):
        index = copy.deepcopy(self.index)
        name = self.hands['sheet']
        index['sheets'] = [e for e in index['sheets'] if e['sheet'] != name]
        index['required_sheets'].remove(name)
        (self.root/'review/index.json').write_text(json.dumps(index))
        with self.assertRaisesRegex(SystemExit, 'required review sheets'): self.record()

    def test_altered_pose_or_temporal_metadata_is_rejected(self):
        for fault in ('pose', 'fps', 'count'):
            index = copy.deepcopy(self.index)
            row = next(e for e in index['sheets'] if e['sheet'] == self.neck['sheet'])
            if fault == 'pose': row['poses'][0]['frame'] = 999
            else: row['playback'][0]['fps' if fault == 'fps' else 'frame_count'] = 999
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, 'coverage'):
                review.validate_index(self.root, index)

    def test_missing_native_wrist_track_fails_closed(self):
        del self.trace['traces']['run']['skeleton']['wr_f']
        with self.assertRaisesRegex(ValueError, 'run.*hands.*wr_f'):
            review.detail_scope(self.doc, self.trace, 'hands')

    def test_wrong_angle_track_length_cannot_select_fake_extremes(self):
        self.trace['traces']['run']['head_motion']['relative_deg'] = [0]
        with self.assertRaisesRegex(ValueError, 'relative_deg'):
            review.detail_rows(self.doc, self.trace, 'neck')

    def test_old_schema_cannot_keep_an_old_pass(self):
        index = copy.deepcopy(self.index); index['schema_version'] = 2
        with self.assertRaisesRegex(ValueError, 'stale or unversioned'): review.validate_index(self.root, index)

    def test_known_seam_stiff_head_and_unnatural_hand_are_blockers_at_actual_clip_frame(self):
        for category, entry, check in (('neck_seam', self.neck, 'neck_continuity'),
                                       ('stiff_head', self.neck, 'head_motion_naturalness'),
                                       ('unnatural_hand', self.hands, 'hand_pose_naturalness'),
                                       ('broken_wrist', self.hands, 'wrist_continuity')):
            value = copy.deepcopy(self.verdict)
            row = value['sheets'][entry['sheet']]
            row['verdict'] = 'fail'; row['checks'][check]['status'] = 'fail'
            row['issues'] = [dict(id=category, category=category, severity='blocker', resolved=False,
                                  clip='run', frame=2, what='Injected visual finding at run frame 2')]
            with self.subTest(category=category):
                self.assertEqual(self.record(value), 1)
                report = json.loads((self.root/'visual_report.json').read_text())
                self.assertEqual(report['status'], 'fail')
                recorded = report['sheets'][entry['sheet']]['issues'][0]
                self.assertEqual((recorded['clip'], recorded['frame']), ('run', 2))
            # Independent fault cases, not an attempt to resolve unchanged pixels.
            (self.root/'review/issue_registry.json').unlink()


class AnatomyPrompts(unittest.TestCase):
    def test_both_reference_routes_constrain_natural_hands_and_continuous_neck(self):
        for prompt in (prompts.REFERENCE, prompts.basic_reference_prompt('hero', 'painted', 'sword')):
            self.assertIn(prompts.NATURAL_HANDS, prompt)
            self.assertIn(prompts.NATURAL_NECK, prompt)
        for slot in ('arm_near', 'arm_far'):
            for prompt in (prompts.prompt(slot), prompts.basic_prompt(slot)):
                self.assertIn('neutral wrist', prompt)
                self.assertIn('secure closed grip', prompt)
                self.assertIn('species', prompt)

    def test_neck_requirements_apply_to_head_and_torso_in_both_routes(self):
        for slot in ('head', 'torso'):
            for prompt in (prompts.prompt(slot), prompts.basic_prompt(slot)):
                self.assertIn('flared triangular skin flap', prompt)
                self.assertIn('outside/front of a collar or scarf', prompt)
        self.assertNotIn('navy', prompts.basic_prompt('torso'))

    def test_hints_preserve_the_finished_hand_and_do_not_repose_fingers(self):
        for slot in prompts.HAND_HINTS:
            prompt = prompts.basic_prompt(slot)
            self.assertIn('FINISHED', prompt)
            self.assertNotIn(prompts.NATURAL_HANDS, prompt)
            self.assertIn('never invent a different hand', prompt)

    def test_source_and_layer_reviews_require_specific_anatomy_checks(self):
        self.assertIn('natural_neck_attachment', workflow.lp.REFERENCE_CHECKS)
        self.assertIn('natural_hand_pose', workflow.lp.REFERENCE_CHECKS)
        for slot in ('head', 'torso'):
            self.assertIn('natural_neck_attachment', workflow.layer_checks(slot))
        for slot in ('arm_near', 'arm_far', *prompts.HAND_HINTS):
            self.assertIn('natural_hand_pose', workflow.layer_checks(slot))
        self.assertNotIn('natural_hand_pose', workflow.layer_checks('leg_near'))
        self.assertEqual(workflow.MAX_ATTEMPTS, 3)


class NumericalLimits(unittest.TestCase):
    @unittest.expectedFailure
    def test_static_alpha_contact_cannot_reject_a_painted_triangular_neck_cut(self):
        """Known gap: the numeric contact test sees alpha, not a painted cut over a collar."""
        torso = Image.new('RGBA', (64, 64)); head = Image.new('RGBA', (64, 64))
        ImageDraw.Draw(torso).rectangle((28, 24, 43, 60), fill=(130, 40, 35, 255))
        draw = ImageDraw.Draw(head)
        draw.rectangle((30, 6, 42, 34), fill=(150, 140, 125, 255))
        draw.polygon([(26, 24), (48, 40), (42, 25)], fill=(150, 140, 125, 255))
        draw.line([(26, 24), (48, 40)], fill='black', width=2)
        masks = {name: np.asarray(image)[..., 3] > 128 for name, image in (('head', head), ('torso', torso))}
        with self.assertRaises(workflow.lp.Rejected): workflow.lp.check_neck_contact(masks)

    @unittest.expectedFailure
    def test_preserved_detail_cannot_distinguish_relaxed_from_spider_like_fingers(self):
        """Known gap: equally sharp finger art can still have an unnatural gesture."""
        images = []
        for splayed in (False, True):
            mask = Image.new('L', (80, 80)); draw = ImageDraw.Draw(mask)
            draw.ellipse((28, 35, 54, 62), fill=255)
            for i in range(4):
                tip = (5 + i * 22, 5) if splayed else (35 + i * 5, 26 + i * 3)
                draw.line([(35 + i * 5, 43), tip], fill=255, width=5)
            yy, xx = np.indices((80, 80)); pattern = 40 + ((xx + yy) % 2) * 160
            rgba = np.dstack((pattern, pattern, pattern, np.asarray(mask))).astype('uint8')
            images.append(puppet_check.edge_energy(rgba))
        self.assertLess(images[1], puppet_check.HAND_DETAIL * images[0])


if __name__ == '__main__':
    unittest.main()
