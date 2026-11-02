"""Template/ledger faults on two synthetic builds, never AI art acceptance."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import template_puppet as tp


class TemplatePuppet(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source=self.root/'source.png';Image.new('RGB',(64,64),'navy').save(self.source)

    def prepare(self,profile='slim'):
        out=self.root/profile
        tp.prepare(self.source,out,'Synthetic geometry fixture, not character art.',profile)
        return out

    def raw_fixture(self,slot='torso',profile='slim',alter=None):
        mask,_=tp.geometry(slot,profile)
        if alter:mask=alter(mask.copy())
        a=np.zeros((tp.SIZE,tp.SIZE,4),np.uint8);a[mask]=(40,50,70,255)
        path=self.root/(slot+'-'+profile+'.png');Image.fromarray(a).save(path)
        return path

    def test_two_profiles_have_complete_connected_parts_and_known_joints(self):
        for profile in tp.PROFILES:
            for slot in tp.SLOTS:
                with self.subTest(profile=profile,slot=slot):
                    mask,joints=tp.geometry(slot,profile)
                    self.assertEqual(ndi.label(mask)[1],1)
                    self.assertFalse((ndi.binary_fill_holes(mask)&~mask).any())
                    m=tp.silhouette_metrics(mask,mask,joints)
                    self.assertEqual(m['core_coverage'],1)
                    self.assertTrue(all(v>=.98 for v in m['anchor_coverage'].values()))

    def test_stump_is_detected_at_wrist_and_hand(self):
        mask,joints=tp.geometry('arm_near');stump=mask.copy();stump[550:]=False
        metrics=tp.silhouette_metrics(stump,mask,joints)
        self.assertLess(metrics['core_coverage'],tp.RULES['core_coverage'])
        self.assertEqual(metrics['anchor_coverage']['wrist'],0)
        self.assertEqual(metrics['anchor_coverage']['grip'],0)

    def test_extra_thigh_branch_and_internal_hole_are_reported(self):
        mask,joints=tp.geometry('leg_near');bad=mask.copy()
        bad[260:350,480:830]=True;bad[200:210,450:460]=False
        metrics=tp.silhouette_metrics(bad,mask,joints)
        self.assertLess(metrics['inside_envelope'],tp.RULES['inside_envelope'])
        self.assertGreater(metrics['enclosed_transparent_pixels'],0)

    def test_changed_source_contract_guide_or_mask_is_rejected(self):
        out=self.prepare()
        for file in [out/'identity_reference.png',out/'contract.json',out/'torso/guide.png',out/'torso/structure_mask.png']:
            old=file.read_bytes();file.write_bytes(old+b' ')
            try:
                with self.assertRaisesRegex(ValueError,'changed'):
                    tp.begin(out,'torso')
            finally:file.write_bytes(old)

    def test_attempt_limit_preserves_existing_failures(self):
        out=self.prepare();raw=self.raw_fixture(alter=lambda m:np.zeros_like(m))
        for _ in range(tp.LIMIT):
            tp.begin(out,'torso');report=tp.ingest(out,'torso',raw)
            self.assertEqual(report['status'],'blocked')
        with self.assertRaisesRegex(ValueError,'limit|blocker'):
            tp.begin(out,'torso')
        self.assertEqual(len(tp.read(out/'job.json')['attempts']['torso']),3)
        self.assertTrue((out/'torso/attempt_1/raw.png').exists())

    def test_no_forced_clipping_or_auto_visual_pass(self):
        out=self.prepare();tp.begin(out,'arm_near')
        raw=self.raw_fixture('arm_near',alter=lambda m:self.add_fragment(m))
        report=tp.ingest(out,'arm_near',raw)
        exported=np.asarray(Image.open(out/'arm_near/attempt_1/registered.png'))[:,:,3]>128
        self.assertGreater(ndi.label(exported)[1],1)
        self.assertIn('art_outside_part_envelope',report['blockers'])
        self.assertFalse(report['binding_approved'])
        self.assertFalse(report['silhouette_forced_to_template'])

    @staticmethod
    def add_fragment(mask):
        mask[80:150,800:870]=True
        return mask

    def test_preview_is_marked_draft_and_has_self_contained_assets(self):
        out=self.prepare()
        for slot in tp.SLOTS:
            tp.begin(out,slot);tp.ingest(out,slot,self.raw_fixture(slot))
        result=tp.preview(out);report=tp.read(out/'draft_report.json')
        self.assertEqual(result['status'],'draft_requires_revision')
        self.assertFalse(report['binding_performed'])
        self.assertFalse(report['animations_generated'])
        page=(out/'preview.html').read_text(encoding='utf-8')
        self.assertIn('data:image/png;base64,',page)
        self.assertIn('尚未通过绑定验收',page)
        self.assertNotIn('__PAYLOAD__',page)

    def test_existing_art_repair_does_not_reset_a_closed_budget(self):
        out=self.prepare()
        def missing_shin(mask):
            mask[580:800]=False
            return mask
        raw=self.raw_fixture('leg_near',alter=missing_shin)
        for _ in range(tp.LIMIT):
            tp.begin(out,'leg_near');tp.ingest(out,'leg_near',raw)
        before=tp.read(out/'job.json');source=out/'leg_near/attempt_3/registered.png'
        original_hash=tp.sha(source)
        report=tp.repair(out,'leg_near')
        self.assertEqual(report['status'],'blocked')
        self.assertEqual(tp.read(out/'job.json'),before)
        self.assertEqual(tp.sha(source),original_hash)
        with self.assertRaisesRegex(ValueError,'limit|blocker'):
            tp.begin(out,'leg_near')

    def test_derived_repair_hash_is_verified_before_display(self):
        out=self.prepare();tp.begin(out,'leg_near');tp.ingest(out,'leg_near',self.raw_fixture('leg_near'))
        tp.repair(out,'leg_near');path,_=tp.selected_part(out,'leg_near')
        path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'stale|changed'):
            tp.selected_part(out,'leg_near')

    def test_stale_motion_cannot_be_embedded_in_current_preview(self):
        out=self.prepare()
        for slot in tp.SLOTS:
            tp.begin(out,slot);tp.ingest(out,slot,self.raw_fixture(slot))
        (out/'motion_probe').mkdir()
        tp.write(out/'motion_probe/report.json',{'parts':{'arm_near':{
            'source_file':'arm_near/attempt_1/registered.png','source_sha256':'old art hash'}}})
        with self.assertRaisesRegex(ValueError,'motion test is stale'):
            tp.preview(out)


if __name__=='__main__':unittest.main()
