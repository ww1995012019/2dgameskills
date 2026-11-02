"""Full-stage template/lineage tests, not AI artwork acceptance."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import template_puppet as tp
import template_full_character as full


class FullTemplate(unittest.TestCase):
    def complete_fixture(self,profile):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        src=root/'source.png';Image.new('RGB',(64,64),'navy').save(src)
        parent=root/'parent';tp.prepare(src,parent,'Synthetic geometry fixture.',profile)
        def fill(slot,mask,folder):
            a=np.zeros((1024,1024,4),np.uint8);a[mask]=(70,90,110,255)
            raw=root/(slot+'.png');Image.fromarray(a).save(raw);tp.begin(folder,slot);tp.ingest(folder,slot,raw)
        for slot in tp.SLOTS:fill(slot,tp.geometry(slot,profile)[0],parent)
        child=parent/'full';full.prepare(parent,child,'Full synthetic geometry fixture.')
        for slot in full.EXTRAS:fill(slot,full.geometry(slot,profile)[0],child)
        return child

    def test_new_part_templates_are_connected_on_two_builds(self):
        for profile in tp.PROFILES:
            for slot in full.EXTRAS:
                with self.subTest(profile=profile,slot=slot):
                    mask,joints=full.geometry(slot,profile)
                    self.assertEqual(ndi.label(mask)[1],1)
                    self.assertFalse((ndi.binary_fill_holes(mask)&~mask).any())
                    metrics=tp.silhouette_metrics(mask,mask,joints)
                    self.assertTrue(all(v>=.98 for v in metrics['anchor_coverage'].values()))

    def test_imported_budgets_cannot_be_reopened(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'identity.png';Image.new('RGB',(64,64),'navy').save(src)
            parent=root/'parent';tp.prepare(src,parent,'Synthetic fixture, not generated character art.')
            for slot in tp.SLOTS:
                mask,_=tp.geometry(slot)
                a=np.zeros((1024,1024,4),np.uint8);a[mask]=(50,70,90,255)
                raw=root/(slot+'.png');Image.fromarray(a).save(raw)
                tp.begin(parent,slot);tp.ingest(parent,slot,raw)
            job=tp.read(parent/'job.json');job['phase']='blocked';tp.write(parent/'job.json',job)
            before=tp.sha(parent/'job.json');child=parent/'full'
            full.prepare(parent,child,'Full synthetic identity; no inherited three-part scope restrictions.')
            for slot in tp.SLOTS:
                with self.assertRaisesRegex(ValueError,'imported'):
                    tp.begin(child,slot)
            self.assertEqual(tp.sha(parent/'job.json'),before)
            self.assertEqual(set(tp.read(child/'job.json')['attempts']),set(full.EXTRAS))
            tp.begin(child,'head')
            self.assertEqual(len(tp.read(child/'job.json')['attempts']['head']),1)
            imported=child/'imports/torso.png';original=imported.read_bytes();imported.write_bytes(original+b'changed')
            with self.assertRaisesRegex(ValueError,'imported part changed'):
                full.selected(child,'torso')

    def test_full_layout_matches_hand_and_neck_anchors(self):
        for profile in tp.PROFILES:
            c={'imported':{s:{'joints':tp.geometry(s,profile)[1]} for s in tp.SLOTS},
               'slots':{s:{'joints':full.geometry(s,profile)[1]} for s in full.EXTRAS}}
            transforms=full.layout(c)
            def at(slot,key):
                s,o=transforms[slot];j=(c['imported'] if slot in c['imported'] else c['slots'])[slot]['joints']
                return o+np.array(j[key])*s
            np.testing.assert_allclose(at('weapon','grip'),at('arm_near','grip'))
            np.testing.assert_allclose(at('head','head_base'),at('torso','neck'))
            self.assertLess(at('leg_far','ankle')[0],at('leg_near','ankle')[0])
            self.assertLess(full.ORDER.index('arm_far'),full.ORDER.index('torso'))
            self.assertLess(full.ORDER.index('weapon'),full.ORDER.index('arm_near'))
            self.assertLess(full.ORDER.index('hips'),full.ORDER.index('leg_far'))
            self.assertLess(full.ORDER.index('hips'),full.ORDER.index('leg_near'))

    def test_static_attachments_on_two_complete_builds(self):
        for profile in tp.PROFILES:
            with self.subTest(profile=profile):
                out=self.complete_fixture(profile);report=full.inspect(out)
                self.assertEqual(report['status'],'static_numerical_checks_met',report)
                self.assertFalse(report['full_character_bound'])
                self.assertTrue(all(v>=.95 for v in report['attachments'].values()))
                self.assertFalse(any(report['clipped_source_pixels'].values()))
                mounted=tp.read(out/'assembly_report.json')['head_mount']
                self.assertGreaterEqual(mounted['coverage'],.95)
                self.assertLessEqual(mounted['scale'],mounted['base_scale']*1.25)

    def test_detached_neck_and_empty_grip_are_located(self):
        out=self.complete_fixture('slim')
        head=out/'head/attempt_1/registered.png';original=head.read_bytes()
        a=np.array(Image.open(head));a[580:,:,3]=0;Image.fromarray(a).save(head)
        p=out/'head/attempt_1/geometry_report.json';g=tp.read(p);g['registered_sha256']=tp.sha(head);tp.write(p,g)
        bad=full.inspect(out)
        self.assertEqual(bad['status'],'blocked')
        self.assertIn('neck',[v['part'] for v in bad['errors']])
        head.write_bytes(original);g['registered_sha256']=tp.sha(head);tp.write(p,g)
        weapon=out/'weapon/attempt_1/registered.png';a=np.array(Image.open(weapon));y,x=np.indices(a.shape[:2])
        a[(x-450)**2+(y-800)**2<25**2,3]=0;Image.fromarray(a).save(weapon)
        p=out/'weapon/attempt_1/geometry_report.json';g=tp.read(p);g['registered_sha256']=tp.sha(weapon);tp.write(p,g)
        bad=full.inspect(out)
        self.assertIn('hand_weapon',[v['part'] for v in bad['errors']])

    def test_wrong_hip_depth_is_rejected(self):
        out=self.complete_fixture('slim');c=tp.read(out/'contract.json');j=tp.read(out/'job.json')
        c['order'].remove('hips');c['order'].insert(c['order'].index('torso'),'hips')
        tp.write(out/'contract.json',c);j['contract_sha256']=tp.sha(out/'contract.json');tp.write(out/'job.json',j)
        self.assertIn('layer_order',full.inspect(out)['part_blockers'])


if __name__=='__main__':unittest.main()
