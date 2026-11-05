"""Hip seam failures and unreviewed binding evidence cannot become a visual pass.

Synthetic frames verify coverage and provenance. They do not demonstrate that a
checkerboard, alpha metric or recorded assertion can recognize real anatomy.
"""
import copy
import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pelvic_review_gate', ROOT/'shared/scripts/visual_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def fixture(root, clips=('idle', 'crouch', 'land'), count=12):
    doc = dict(frame_size=96, pivot=[48, 92], clips={})
    trace = dict(unit_px=.8, traces={})
    for name in clips:
        doc['clips'][name] = dict(frames=list(range(count)), fps=30, loop=False,
                                 source_frames=[0 if i < count//2 else 1 for i in range(count)])
        sk = {key: [] for key in review.PELVIS_JOINTS}
        path = root/'frames'/name; path.mkdir(parents=True)
        for frame in range(count):
            down = 12 if frame == 4 else 0
            spread = 13 if frame == 9 else 0
            points = dict(waist=[48, 39 + down], neck=[48, 17 + down],
                          hip_n=[41, 43 + down], hip_f=[55, 43 + down],
                          kn_n=[37 - spread, 66], kn_f=[59 + spread, 66],
                          an_n=[35 - spread, 91], an_f=[61 + spread, 91])
            if frame == 8:
                points['an_n'] = [46, 55]
            image = Image.new('RGBA', (96, 96)); draw = ImageDraw.Draw(image)
            draw.rectangle((38, 17 + down, 58, 47 + down), fill=(35, 95, 160, 255))
            for side in 'nf':
                draw.line([tuple(points[k + side]) for k in ('hip_', 'kn_', 'an_')], fill=(205, 195, 170, 255), width=9)
            image.save(path/f'{name}_{frame:03d}.png')
            for key in sk:
                sk[key].append(points[key])
        trace['traces'][name] = dict(skeleton=sk)
    (root/'animations.json').write_text(json.dumps(doc))
    (root/'rig_trace.json').write_text(json.dumps(trace))
    Image.new('RGBA', (24, 24), 'blue').save(root/'atlas.png')
    (root/'atlas.json').write_text('{"frames":{}}')
    (root/'sheets').mkdir(); Image.new('RGBA', (24, 24), 'blue').save(root/'sheets/idle.png')
    (root/'preview.html').write_text('<html>synthetic preview</html>')
    review.build(root)
    return doc, trace


def accepted(root):
    index = json.loads((root/'review/index.json').read_text())
    template = json.loads((root/'review/verdict_template.json').read_text())
    template['reviewer'] = 'Synthetic fault-injection fixture'
    for row in template['sheets'].values():
        row['verdict'] = 'pass'
        for name, check in row['checks'].items():
            check.update(status='pass', evidence='Synthetic fixture inspected; no claim about real art')
            for observation in check.get('observations', []):
                observation['evidence'] = f"{observation['clip']} frame {observation['frame']}: fixture hip/waist path inspected"
            for playback in check.get('playback', []):
                playback['evidence'] = f"{playback['clip']}: synthetic complete playback inspected"
    return index, template


class PelvicGate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.doc, self.trace = fixture(self.root)
        self.index, self.verdict = accepted(self.root)
        self.hips = next(row['sheet'] for row in self.index['sheets'] if row['sheet'].startswith('hips_'))

    def record(self, value=None):
        path = self.root/'verdict.json'; path.write_text(json.dumps(value or self.verdict))
        return review.record(self.root, path)

    def test_each_clip_contributes_its_own_static_crouch_spread_and_switch_poses(self):
        poses = [p for row in self.index['sheets'] if row['sheet'].startswith('hips_') for p in row['poses']]
        for clip in self.doc['clips']:
            frames = {p['frame'] for p in poses if p['clip'] == clip}
            self.assertTrue({0, 11, 4, 5, 6, 7, 8, 9}.issubset(frames), (clip, frames))
        self.assertEqual(self.index['schema_version'], review.REVIEW_SCHEMA)

    def test_more_than_eight_clips_do_not_drop_the_remaining_hips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); names = tuple(f'clip_{i}' for i in range(10))
            fixture(root, names, 2)
            index = json.loads((root/'review/index.json').read_text())
            covered = {p['clip'] for row in index['sheets'] for p in row.get('poses', [])}
            self.assertEqual(covered, set(names))

    def test_template_is_pending_and_cannot_clear_a_review(self):
        pending = json.loads((self.root/'review/verdict_template.json').read_text())
        with self.assertRaisesRegex(SystemExit, 'reviewer'):
            self.record(pending)
        self.assertEqual(review.check_current(self.root), 1)

    def test_current_complete_matching_verdict_passes(self):
        self.assertEqual(self.record(), 0)
        self.assertEqual(review.check_current(self.root), 0)

    def test_required_alignment_and_pelvis_checks_cannot_be_missing_or_skipped(self):
        for name in review.PELVIS_CHECKS:
            missing = copy.deepcopy(self.verdict); del missing['sheets'][self.hips]['checks'][name]
            with self.assertRaisesRegex(SystemExit, name): self.record(missing)
            skipped = copy.deepcopy(self.verdict); skipped['sheets'][self.hips]['checks'][name]['status'] = 'not_applicable'
            with self.assertRaisesRegex(SystemExit, 'cannot be skipped'): self.record(skipped)

    def test_each_selected_frame_needs_specific_evidence_once(self):
        for mutation in ('omit', 'blank', 'duplicate', 'unknown'):
            value = copy.deepcopy(self.verdict)
            rows = value['sheets'][self.hips]['checks']['pelvis_continuity']['observations']
            if mutation == 'omit': rows.pop()
            elif mutation == 'blank': rows[0]['evidence'] = ''
            elif mutation == 'duplicate': rows.append(copy.deepcopy(rows[0]))
            else: rows[0]['frame'] = 999
            with self.subTest(mutation=mutation), self.assertRaisesRegex(SystemExit, 'pelvis_continuity'):
                self.record(value)

    def test_missing_physical_sheet_fails_closed(self):
        (self.root/'review'/self.hips).unlink()
        with self.assertRaisesRegex(SystemExit, 'missing required review sheet'):
            self.record()

    def test_removing_sheet_and_required_manifest_entry_cannot_bypass_coverage(self):
        index = copy.deepcopy(self.index)
        index['sheets'] = [entry for entry in index['sheets'] if entry['sheet'] != self.hips]
        index['required_sheets'].remove(self.hips)
        (self.root/'review/index.json').write_text(json.dumps(index))
        del self.verdict['sheets'][self.hips]
        with self.assertRaisesRegex(SystemExit, 'required review sheets'):
            self.record()

    def test_clip_without_trace_or_a_required_hip_cannot_build_or_pass(self):
        for missing in ('file', 'hip_f'):
            trace = copy.deepcopy(self.trace)
            if missing == 'file': (self.root/'rig_trace.json').unlink(missing_ok=True)
            else:
                del trace['traces']['crouch']['skeleton'][missing]
                (self.root/'rig_trace.json').write_text(json.dumps(trace))
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'complete rendered pelvis/leg trace'):
                review.build(self.root)
            self.assertEqual(review.check_current(self.root), 1)

    def test_unresolved_crotch_gap_is_a_blocker_and_never_passes(self):
        row = self.verdict['sheets'][self.hips]
        row['issues'] = [dict(id='open-crotch', category='pelvis_gap', severity='blocker', resolved=False,
                              clip='crouch', frame=4, what='Synthetic injected garment opening at the crotch')]
        with self.assertRaisesRegex(SystemExit, 'unresolved issue'):
            self.record()
        row['verdict'] = 'fail'; row['checks']['pelvis_continuity']['status'] = 'fail'
        self.assertEqual(self.record(), 1)
        self.assertEqual(review.check_current(self.root), 1)
        row['issues'][0]['severity'] = 'polish'
        with self.assertRaisesRegex(SystemExit, 'must be blocker'):
            self.record()

    def test_changes_to_delivered_atlas_sheet_preview_or_index_invalidate_pass(self):
        originals = {name: (self.root/name).read_bytes() for name in ('atlas.png', 'atlas.json', 'sheets/idle.png', 'preview.html', 'review/index.json')}
        for name, content in originals.items():
            self.assertEqual(self.record(), 0)
            path = self.root/name
            if name.endswith('.png'): Image.new('RGBA', (24, 24), 'red').save(path)
            elif name == 'review/index.json':
                value = json.loads(content); value['sheets'][0]['clips'] = []
                path.write_text(json.dumps(value))
            else: path.write_bytes(content + b' changed')
            with self.subTest(asset=name): self.assertEqual(review.check_current(self.root), 1)
            path.write_bytes(content)

    def test_saved_pass_cannot_skip_required_checks_on_recheck(self):
        self.record()
        report = json.loads((self.root/'visual_report.json').read_text())
        del report['sheets'][self.hips]['checks']['rig_alignment']
        (self.root/'visual_report.json').write_text(json.dumps(report))
        self.assertEqual(review.check_current(self.root), 1)

    def test_failed_or_invalid_optional_binding_audit_blocks_generic_visual_pass(self):
        for status in ('fail', 'invalid'):
            (self.root/'binding_audit.json').write_text(json.dumps(dict(schema_version=1, status=status)))
            review.build(self.root); self.index, self.verdict = accepted(self.root)
            with self.subTest(status=status):
                self.assertEqual(self.record(), 1)
                self.assertEqual(review.check_current(self.root), 1)

    def test_registered_binding_source_sheets_cannot_be_left_out_or_skipped(self):
        name = 'binding_review_sources.png'
        Image.new('RGBA', (20, 20), 'blue').save(self.root/name)
        (self.root/'binding_audit.json').write_text(json.dumps(dict(status='fail', review_sheets=[name])))
        review.build(self.root); self.index, self.verdict = accepted(self.root)
        self.assertIn(name, self.verdict['sheets'])
        del self.verdict['sheets'][name]
        with self.assertRaisesRegex(SystemExit, name): self.record()
        self.index, self.verdict = accepted(self.root)
        self.verdict['sheets'][name]['checks']['binding_registration']['status'] = 'not_applicable'
        with self.assertRaisesRegex(SystemExit, 'cannot be skipped'): self.record()

    def test_binding_numeric_pass_without_visual_source_sheets_is_not_reviewable(self):
        (self.root/'binding_audit.json').write_text(json.dumps(dict(status='pass', review_sheets=[])))
        with self.assertRaisesRegex(ValueError, 'source/registration visual review sheets'):
            review.build(self.root)

    def test_required_external_skin_audit_cannot_be_bypassed_by_removing_the_report(self):
        trace = copy.deepcopy(self.trace); trace['binding_audit_required'] = True
        (self.root/'rig_trace.json').write_text(json.dumps(trace))
        review.build(self.root); self.index, self.verdict = accepted(self.root)
        self.assertEqual(self.record(), 1)
        self.assertEqual(review.check_current(self.root), 1)

    def test_subset_binding_numbers_do_not_clear_the_complete_animation_scope(self):
        name = 'binding_review_sources.png'; Image.new('RGBA', (20, 20), 'blue').save(self.root/name)
        (self.root/'binding_audit.json').write_text(json.dumps(dict(status='pass', review_sheets=[name],
            scope=dict(clip_frames={'idle': 1}))))
        review.build(self.root); self.index, self.verdict = accepted(self.root)
        self.assertEqual(self.record(), 1)
        self.assertEqual(review.check_current(self.root), 1)

    def measured_fixture(self, matching):
        from dev.tests.test_skin_binding_audit import SkinBindingAudit, audit
        case = SkinBindingAudit(); self.addCleanup(case.doCleanups)
        root, manifest, _ = case.fixture()
        self.assertEqual(audit.write_audit(manifest)['status'], 'pass')
        fixture(root, clips=('idle', 'crouch'), count=1)
        if matching:
            for clip in ('idle', 'crouch'):
                with Image.open(root/f'{clip}.png') as image:
                    image.save(root/f'frames/{clip}/{clip}_000.png', compress_level=0)
            review.build(root)
        index, verdict = accepted(root)
        path = root/'verdict.json'; path.write_text(json.dumps(verdict))
        return root, path, audit

    def test_matching_clip_counts_do_not_allow_other_rendered_frame_pixels(self):
        root, path, audit = self.measured_fixture(matching=False)
        with patch.dict(sys.modules, {'audit_skin_binding': audit}):
            self.assertEqual(audit.audit_current(root/'binding_audit.json'), 0)
            self.assertEqual(review.binding_gate(root), 1)
            self.assertEqual(review.record(root, path), 1)
            self.assertEqual(review.check_current(root), 1)

    def test_identical_reviewed_rgba_can_match_a_different_lossless_encoding(self):
        root, path, audit = self.measured_fixture(matching=True)
        original, reviewed = root/'idle.png', root/'frames/idle/idle_000.png'
        self.assertNotEqual(original.read_bytes(), reviewed.read_bytes())
        self.assertEqual(review.pixel_hash(original), review.pixel_hash(reviewed))
        with patch.dict(sys.modules, {'audit_skin_binding': audit}):
            self.assertEqual(review.binding_gate(root), 0)
            self.assertEqual(review.record(root, path), 0)
            self.assertEqual(review.check_current(root), 0)

    def test_changing_a_failed_report_to_pass_cannot_erase_the_open_issue_registry(self):
        row = self.verdict['sheets'][self.hips]
        row.update(verdict='fail', issues=[dict(id='known-gap', category='pelvis_gap', severity='blocker', resolved=False,
                                              clip='idle', frame=0, what='Synthetic known open seam')])
        row['checks']['pelvis_continuity']['status'] = 'fail'
        self.assertEqual(self.record(), 1)
        report = json.loads((self.root/'visual_report.json').read_text())
        report.update(status='pass', open_issues=0, open_blockers=0)
        report['sheets'][self.hips].update(verdict='pass', issues=[])
        report['sheets'][self.hips]['checks']['pelvis_continuity']['status'] = 'pass'
        (self.root/'visual_report.json').write_text(json.dumps(report))
        self.assertEqual(review.check_current(self.root), 1)
        # The registry independently blocks clearing the report and its archive.
        (self.root/'review/history'/f'{report["review_id"]}.json').write_text(json.dumps(report))
        self.assertEqual(review.check_current(self.root), 1)

    def test_current_report_must_match_its_archived_record(self):
        self.assertEqual(self.record(), 0)
        report = json.loads((self.root/'visual_report.json').read_text())
        report['sheets'][self.hips]['checks']['rig_alignment']['evidence'] = 'Changed only the saved assertion'
        (self.root/'visual_report.json').write_text(json.dumps(report))
        self.assertEqual(review.check_current(self.root), 1)

    def test_unrecognized_layer_metadata_cannot_exempt_a_body_from_its_trace(self):
        for layer in ('full', 'torso', True, 1):
            doc = copy.deepcopy(self.doc); doc['clips']['idle']['layer'] = layer
            (self.root/'animations.json').write_text(json.dumps(doc))
            (self.root/'rig_trace.json').unlink(missing_ok=True)
            with self.subTest(layer=layer), self.assertRaisesRegex(ValueError, 'only upper/lower'):
                review.build(self.root)


if __name__ == '__main__':
    unittest.main()
