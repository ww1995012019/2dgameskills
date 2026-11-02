"""Faults for reference-driven head proportions; no claim of semantic AI vision."""
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import template_puppet as tp
import template_full_character as full
import template_head_proportions as hp
import test_template_full_character as full_tests


def head_fixture(width=1.):
    head=Image.new('RGBA',(1024,1536));d=ImageDraw.Draw(head)
    d.ellipse((390,90,580,255),fill=(50,40,40,255))
    d.polygon([(520,130),(590,170),(610,200),(590,215),(585,250),(545,275),(515,255)],fill=(220,180,150,255))
    d.rectangle((450,240,510,310),fill=(220,180,150,255))
    if width!=1:head=head.transform(head.size,Image.Transform.AFFINE,(1/width,0,500*(1-1/width),0,1,0),Image.Resampling.NEAREST)
    identity=head.copy();d=ImageDraw.Draw(identity);d.rectangle((400,311,580,1400),fill=(40,60,90,255))
    # New art has an extra hidden mounting neck, but unchanged head proportions.
    candidate=head.transform((1280,1280),Image.Transform.AFFINE,(1/3,0,290,0,1/3,60),Image.Resampling.NEAREST)
    d=ImageDraw.Draw(candidate);left=round((450-500)*width+500);right=round((510-500)*width+500)
    d.rectangle(((left-290)*3,700,(right-290)*3,1150),fill=(220,180,150,255))
    return identity,head,candidate


class HeadProportions(unittest.TestCase):
    def test_two_proportions_keep_original_shape_and_reject_squeeze(self):
        for width in (1.,1.22):
            _,ref,art=head_fixture(width);r=np.array(ref)[:,:,3]>128;c=np.array(art)[:,:,3]>128
            self.assertFalse(hp.compare(r,c)['blockers'])
            squeezed=art.resize((640,1280),Image.Resampling.NEAREST)
            self.assertIn('head width/height differs',hp.compare(r,np.array(squeezed)[:,:,3]>128)['blockers'][0])

    def install_fixture(self,profile):
        out=full_tests.FullTemplate.complete_fixture(self,profile)
        identity,head,art=head_fixture(tp.PROFILES[profile]);identity.save(out/'identity_reference.png')
        job=tp.read(out/'job.json');job['source_sha256']=tp.sha(out/'identity_reference.png')
        raw=out/'head/attempt_1/raw.png';art.save(raw)
        job['attempts']['head'][-1].update(state='generated',raw_sha256=tp.sha(raw));tp.write(out/'job.json',job)
        ref=out/'segmented_head.png';head.save(ref)
        hp.install(out,raw,ref,'Synthetic full-image extraction, not real AI art.')
        return out

    def test_two_builds_neck_length_and_collar_do_not_resize_head(self):
        for profile in tp.PROFILES:
            out=self.install_fixture(profile);_,c=tp.validate(out);transforms=full.layout(c)
            images={s:Image.open(full.selected(out,s)[0]).convert('RGBA') for s in full.ORDER}
            a=full.head_mount(images,transforms,c,out)
            self.assertEqual(a['scale'],a['base_scale']);self.assertTrue(a['collar_does_not_control_head_scale'])
            manifest=tp.read(out/'head_reference.json');d=hp.descriptor(np.array(images['head'])[:,:,3]>128)
            self.assertLess(manifest['joints']['head_base'][1],1100) # extra mounting skin is buried
            # Change only collar width. Scale must remain exactly body-derived.
            torso=images['torso'];images['torso']=torso.resize((1150,1024)).transform((1024,1024),Image.Transform.AFFINE,(1,0,63,0,1,0))
            b=full.head_mount(images,full.layout(c),c,out)
            self.assertAlmostEqual(a['scale'],b['scale'])

    def test_stale_candidate_contract_and_unrecorded_redraw_rejected(self):
        out=self.install_fixture('slim');p=out/'head/attempt_1/reference_qualified.png';old=p.read_bytes();p.write_bytes(old+b'changed')
        with self.assertRaisesRegex(ValueError,'candidate changed'):hp.select(out)
        p.write_bytes(old);m=out/'head_reference.json';m.write_bytes(m.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'contract changed'):hp.select(out)
        rogue=out/'unrecorded.png';Image.new('RGBA',(32,32),'red').save(rogue)
        with self.assertRaisesRegex(ValueError,'recorded generated'):hp.install(out,rogue,out/'segmented_head.png','unrecorded')

    def test_head_mask_from_other_identity_rejected(self):
        out=self.install_fixture('compact');ref=Image.open(out/'segmented_head.png');a=np.array(ref);a[a[:,:,3]>128,:3]=1
        wrong=out/'wrong_head.png';Image.fromarray(a).save(wrong)
        with self.assertRaisesRegex(ValueError,'pixels differ'):hp.install(out,out/'head/attempt_1/raw.png',wrong,'wrong identity')

    @unittest.expectedFailure
    def test_known_gap_same_silhouette_does_not_prove_facial_identity(self):
        _,ref,art=head_fixture();blank=np.array(art);blank[blank[:,:,3]>128,:3]=(0,255,0)
        check=hp.compare(np.array(ref)[:,:,3]>128,blank[:,:,3]>128)
        # Inject a blank green face while retaining the valid outline. This
        # missing semantic check must not be presented as an automatic pass.
        self.assertTrue(check['blockers'],'blank face requires semantic review')


if __name__=='__main__':unittest.main()
