import copy
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reference_body_assembly import chain_transform,point,compare_visible_profile,PROFILE_KEYS

class ReferenceChains(unittest.TestCase):
    def test_two_proportions_two_resolutions(self):
        for source in ([[0,0],[10,30],[20,70]],[[0,0],[-3,18],[5,43]]):
            for resolution in (1,4):
                p=np.asarray(source)*resolution
                target=p*1.7+[100,50]
                t=chain_transform(p,target)
                np.testing.assert_allclose([point(t,x) for x in p],target,atol=1e-10)
    def test_different_pose_keeps_lengths_not_target_pose(self):
        p=np.array([[0,0],[0,30],[40,30]])
        target=[[20,20],[20,80],[20,160]]
        t=chain_transform(p,target,preserve_pose=True)
        self.assertEqual(t['scale'],2)
        self.assertEqual(t['angle'],0)
        np.testing.assert_allclose(point(t,p[0]),target[0])
        self.assertNotEqual(point(t,p[-1]),target[-1])
    def test_rotation_aligns_root_tip(self):
        p=np.array([[0,0],[2,30],[0,70]])
        target=p@np.array([[0,1],[-1,0]])+30
        t=chain_transform(p,target)
        np.testing.assert_allclose([point(t,x) for x in p],target,atol=1e-10)
    def test_injected_bad_segment_ratio_rejected(self):
        with self.assertRaisesRegex(ValueError,'incompatible'):
            chain_transform([[0,0],[0,10],[0,20]],[[0,0],[0,3],[0,20]])
    def test_invalid_chains(self):
        for bad in ([[0,0],[0,0],[2,3]],[[0,0],[1,1]],[[0,0],[1,float('nan')],[2,3]],[[0,0],[1,1],[0,0]]):
            with self.subTest(bad=bad),self.assertRaises(ValueError):chain_transform(bad,bad)

class VisibleProfiles(unittest.TestCase):
    def profile(self):
        ys=[0,12,13,38,50,72,73,100,100]
        return {k:dict(point=[10,y],visible=True) for k,y in zip(PROFILE_KEYS,ys)}
    def test_two_proportions_resolution_translation(self):
        for h in (12,17):
            p=self.profile();p['chin']['point'][1]=h
            for scale in (1,5):
                q=copy.deepcopy(p)
                for v in q.values():v['point']=(np.asarray(v['point'])*scale+[30,50]).tolist()
                self.assertTrue(compare_visible_profile(p,q)['geometric_screen_pass'])
    def test_reject_missing_body_even_when_head_matches(self):
        p=self.profile();del p['belt']
        with self.assertRaisesRegex(ValueError,'full visible'):compare_visible_profile(p,p)
    def test_hidden_source_landmark_cannot_substitute_for_visible_belt(self):
        p=self.profile();p['belt']['visible']=False
        with self.assertRaisesRegex(ValueError,'visible in composite'):compare_visible_profile(self.profile(),p)
    def test_enlarged_head_fault_is_detected(self):
        p=self.profile();p['chin']['point'][1]=20
        r=compare_visible_profile(self.profile(),p)
        self.assertFalse(r['geometric_screen_pass']);self.assertIn('head/body ratio differs by more than 15%',r['blockers'])
    def test_same_head_ratio_wrong_body_levels_detected(self):
        p=self.profile();p['belt']['point'][1]=30;p['pelvis']['point'][1]=43
        r=compare_visible_profile(self.profile(),p)
        self.assertFalse(r['geometric_screen_pass']);self.assertTrue(any('belt:' in x for x in r['blockers']))
    def test_nonfinite_inverted_and_crouched_rejected(self):
        for key,y in [('crown',float('nan')),('pelvis',20),('sole_near',120),('knee_near',150),('knee_far',150)]:
            p=self.profile();p[key]['point'][1]=y
            with self.assertRaises(ValueError):compare_visible_profile(self.profile(),p)
    def test_geometric_pass_is_never_visual_approval(self):
        r=compare_visible_profile(self.profile(),self.profile());self.assertEqual(r['visual_approval'],'pending')


class ExtentReview(unittest.TestCase):
    def test_oversized_boot_detected_despite_matching_leg_length(self):
        from reference_body_assembly import compare_extent
        r=compare_extent([[1,407],[137,407]],[[398,1255],[548,1255]],{'scale':1.63})
        self.assertFalse(r['diagnostic_pass']);self.assertGreater(r['relative_deviation'],.4)
    def test_rotation_does_not_change_extent(self):
        from reference_body_assembly import compare_extent
        r=compare_extent([[0,0],[10,0]],[[20,20],[20,40]],{'scale':2,'angle':90})
        self.assertTrue(r['diagnostic_pass'])
    def test_invalid_extent_rejected(self):
        from reference_body_assembly import compare_extent
        for source,ref,s in [([[0,0],[0,0]],[[0,0],[1,1]],1),([[0,0],[1,1]],[[0,0],[1,1]],0),([[0,0],[1,float('nan')]],[[0,0],[1,1]],1)]:
            with self.assertRaises(ValueError):compare_extent(source,ref,{'scale':s})

class AssemblyContract(unittest.TestCase):
    def fixture(self,root):
        import hashlib,json
        from PIL import Image,ImageDraw
        from reference_body_assembly import TOP,BOTTOM
        parts=root/'parts';parts.mkdir();reference=root/'reference.png'
        Image.new('RGBA',(200,240)).save(reference)
        for n in (*TOP,*BOTTOM):
            im=Image.new('RGBA',(30,60));ImageDraw.Draw(im).rectangle((5,5,25,55),fill=(50,100,150,255));im.save(parts/(n+'.png'))
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        rigid={}
        for n,offset in [('head',[60,10]),('torso',[60,60]),('hips',[60,110])]:
            rigid[n]=[dict(label=l,source=s,reference=(np.asarray(s)+offset).tolist(),visible=True) for l,s in zip(['collar_back','collar_front','lower'],[[5,5],[25,5],[15,50]])]
        a=dict(name='synthetic',head_attachment='cap_cover',reference_sha256=sha(reference),source_sha256={p.stem:sha(p) for p in parts.glob('*.png')},rigid=rigid,hips_joints={'hip':[15,40],'waist':[15,10]},chains={n:[[60,80],[60,100],[60,120]] for n in ('arm_near','arm_far','leg_near','leg_far')},weapon_relative_to_arm={'length_ratio':1.,'source_extent':[[15,5],[15,55]],'angle_degrees':0.,'grip':[15,40]},order=list((*TOP,*BOTTOM)))
        return parts,reference,a
    def measured(self,image,n):
        if n.startswith('arm'):return dict(shoulder=[15,10],elbow=[15,30],wrist=[15,50],grip=[15,50])
        if n.startswith('leg'):return dict(hip=[15,10],knee=[15,30],ankle=[15,50],heel=[5,55],toe=[25,55])
        return {}
    def test_real_raster_path_preserves_sources_and_refuses_overwrite(self):
        import tempfile,json
        from unittest.mock import patch
        from reference_body_assembly import assemble_reference
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);parts,ref,a=self.fixture(root);before={p:p.read_bytes() for p in parts.glob('*.png')}
            with patch('reference_body_assembly.landmarks',side_effect=self.measured):
                manifest=assemble_reference(parts,ref,a,root/'out')
                self.assertTrue(manifest.exists());self.assertTrue((root/'out/assembled.png').exists())
                with self.assertRaisesRegex(ValueError,'new directory'):assemble_reference(parts,ref,a,root/'out')
            self.assertEqual(before,{p:p.read_bytes() for p in before})
            self.assertEqual(json.loads((root/'out/reference_assembly.json').read_text())['visual_approval'],'pending')
    def test_changed_hash_hidden_anchor_and_clipping_leave_no_output(self):
        import tempfile
        from unittest.mock import patch
        from reference_body_assembly import assemble_reference
        for failure in ('hash','hidden','clipping','name','nan_hip','head_attachment','opaque'):
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);parts,ref,a=self.fixture(root)
                if failure=='opaque':
                    from PIL import Image
                    Image.new('RGB',(30,60),'white').save(parts/'head.png')
                if failure=='hash':a['source_sha256']['head']='wrong'
                if failure=='name':del a['name']
                if failure=='head_attachment':del a['head_attachment']
                if failure=='nan_hip':a['hips_joints']['hip']=[float('nan'),40]
                if failure=='hidden':a['rigid']['hips'][0]['visible']=False
                if failure=='clipping':
                    for p in a['rigid']['head']:p['reference'][0]-=100
                with patch('reference_body_assembly.landmarks',side_effect=self.measured),self.assertRaises(ValueError):
                    assemble_reference(parts,ref,a,root/'out')
                self.assertFalse((root/'out').exists())

class AssemblyRecovery(unittest.TestCase):
    fixture=AssemblyContract.fixture
    measured=AssemblyContract.measured
    def test_write_failure_leaves_no_partial_destination(self):
        import tempfile
        from unittest.mock import patch
        from reference_body_assembly import assemble_reference
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);parts,ref,a=self.fixture(root)
            with patch('reference_body_assembly.landmarks',side_effect=self.measured),patch('PIL.Image.Image.save',side_effect=OSError('disk failure')):
                with self.assertRaisesRegex(OSError,'disk failure'):assemble_reference(parts,ref,a,root/'out')
            self.assertFalse((root/'out').exists());self.assertEqual(list(root.glob('.body-assembly-*')),[])
    def test_arm_source_resolution_does_not_change_weapon_size(self):
        import tempfile,json,hashlib
        from unittest.mock import patch
        from PIL import Image
        from reference_body_assembly import assemble_reference
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);parts,ref,a=self.fixture(root)
            with patch('reference_body_assembly.landmarks',side_effect=self.measured):assemble_reference(parts,ref,a,root/'one')
            for n in ('arm_near','arm_far'):
                path=parts/(n+'.png')
                with Image.open(path) as im:scaled=im.resize((im.width*2,im.height*2),Image.Resampling.NEAREST)
                scaled.save(path);a['source_sha256'][n]=hashlib.sha256(path.read_bytes()).hexdigest()
            def measured(image,n):
                result=self.measured(image,n)
                return {k:(np.asarray(v)*(2 if n.startswith('arm') else 1)).tolist() for k,v in result.items()}
            with patch('reference_body_assembly.landmarks',side_effect=measured):assemble_reference(parts,ref,a,root/'two')
            first=json.loads((root/'one/reference_assembly.json').read_text());second=json.loads((root/'two/reference_assembly.json').read_text())
            self.assertAlmostEqual(first['transforms']['weapon']['scale'],second['transforms']['weapon']['scale'])
            np.testing.assert_allclose(first['transforms']['weapon']['offset'],second['transforms']['weapon']['offset'])

class ReviewedAttachments(unittest.TestCase):
    fixture=AssemblyContract.fixture
    measured=AssemblyContract.measured
    def test_explicit_grasp_point_and_axis_replace_palm_center(self):
        import tempfile,json
        from unittest.mock import patch
        from reference_body_assembly import assemble_reference,point
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);parts,ref,a=self.fixture(root);a['hand_registration']={'point':[20,45],'axis':[[18,40],[22,50]]}
            with patch('reference_body_assembly.landmarks',side_effect=self.measured):assemble_reference(parts,ref,a,root/'out')
            report=json.loads((root/'out/reference_assembly.json').read_text());manifest=json.loads((root/'out/input.json').read_text())
            expected=point(report['transforms']['arm_near'],[20,45])
            np.testing.assert_allclose(manifest['joints']['weapon']['grip'],expected)
            np.testing.assert_allclose(manifest['joints']['arm_near']['grip'],expected)
    def test_bad_grip_fails_without_output(self):
        import tempfile
        from unittest.mock import patch
        from reference_body_assembly import assemble_reference
        for grip,axis in [([float('nan'),20],[[0,0],[1,1]]),([50,50],[[0,0],[1,1]]),([20,20],[[1,1],[1,1]])]:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);parts,ref,a=self.fixture(root);a['hand_registration']={'point':grip,'axis':axis}
                with patch('reference_body_assembly.landmarks',side_effect=self.measured),self.assertRaises(ValueError):assemble_reference(parts,ref,a,root/'out')
                self.assertFalse((root/'out').exists())
    def garment(self,parts,a):
        import shutil,hashlib
        shutil.copy2(parts/'hips.png',parts/'garment_front.png')
        a['source_sha256']['garment_front']=hashlib.sha256((parts/'garment_front.png').read_bytes()).hexdigest()
        a['front_garment']={'owner':'torso','hips_behind_legs':True}
        a['rigid']['garment_front']=copy.deepcopy(a['rigid']['hips'])
        a['order']=['arm_far','hips','leg_far','leg_near','head','torso','weapon','arm_near']
    def test_front_garment_becomes_torso_art_without_extra_runtime_layer(self):
        import tempfile,json
        from unittest.mock import patch
        from reference_body_assembly import assemble_reference
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);parts,ref,a=self.fixture(root);self.garment(parts,a)
            with patch('reference_body_assembly.landmarks',side_effect=self.measured):assemble_reference(parts,ref,a,root/'out')
            manifest=json.loads((root/'out/input.json').read_text());self.assertNotIn('garment_front',manifest['layers'])
            with Image.open(root/'out/layers/torso.png') as im:self.assertGreater(im.getbbox()[3],160)
    def test_inconsistent_front_ownership_order_fails_without_output(self):
        import tempfile
        from unittest.mock import patch
        from reference_body_assembly import assemble_reference
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);parts,ref,a=self.fixture(root);self.garment(parts,a);a['order'].remove('hips');a['order'].append('hips')
            with patch('reference_body_assembly.landmarks',side_effect=self.measured),self.assertRaisesRegex(ValueError,'hips behind'):
                assemble_reference(parts,ref,a,root/'out')
            self.assertFalse((root/'out').exists())

class FreeArmReferenceCarriage(unittest.TestCase):
    def test_preserves_body_relative_reach_for_two_bodies_and_scales(self):
        from reference_body_assembly import derive_free_arm_carriage
        from sprite_anim.motions import build_clips
        from sprite_anim.rig import Body
        import math
        for upper,lower in [(10,15),(18,12)]:
            results=[]
            for scale in (1,3):
                b=Body(up_arm_f=upper*scale,lo_arm_f=lower*scale)
                c=build_clips(body=b,gait={'idle':{'arm_f':[20,2,12,1]},'walk':{'profile':'natural_walk_v1'}})
                before=tuple(c['walk'].arm_f);override,report=derive_free_arm_carriage(c['idle'],c['walk'],b)
                a=math.radians(override[0]-c['walk'].pelvis-c['walk'].lean);e=math.radians(override[2])
                reach=(upper*math.sin(a)+lower*math.sin(a+e))/(upper+lower)
                self.assertAlmostEqual(reach,report['forward_reach_fraction'])
                self.assertEqual(tuple(c['walk'].arm_f),before)
                results.append(override)
            np.testing.assert_allclose(results[0],results[1])
    def test_unrelaxed_or_undersampled_rest_rejected(self):
        from reference_body_assembly import derive_free_arm_carriage
        from sprite_anim.motions import build_clips
        from sprite_anim.rig import Body
        b=Body();c=build_clips(body=b,gait={'idle':{'arm_f':[85,0,10,0]},'walk':{'profile':'natural_walk_v1'}})
        with self.assertRaisesRegex(ValueError,'relaxed'):derive_free_arm_carriage(c['idle'],c['walk'],b)
        with self.assertRaisesRegex(ValueError,'eight'):derive_free_arm_carriage(c['idle'],c['walk'],b,2)

if __name__=='__main__':unittest.main()
