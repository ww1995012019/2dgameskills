import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from head_registration import fit_similarity,register_head,rasterize_registered_head,create_reference_candidate

class HeadRegistration(unittest.TestCase):
    def test_two_proportions_and_resolutions(self):
        for proportions in ([1,1],[1.4,.7]):
            for resolution in (1,3):
                head=np.array([[0,0],[4,1],[2,5],[1,2]])*proportions*resolution
                torso=np.array([[0,0],[9,2],[2,12],[7,8]])*resolution
                h_ref=head*.8+[30,10];t_ref=torso*1.2+[20,30]
                actual=register_head(head,h_ref,torso,t_ref,torso_transform=dict(scale=2.4,angle=0,offset=[100,200]))
                self.assertAlmostEqual(actual['scale'],1.6)
                np.testing.assert_allclose(actual['offset'],[120,160],atol=1e-10)
                self.assertAlmostEqual(actual['angle'],0)
    def test_rotation_is_preserved(self):
        pts=np.array([[0,0],[10,1],[2,12],[8,9]])
        r=np.array([[0,-1],[1,0]])
        result=fit_similarity(pts,2*(pts@r.T)+[30,40])
        self.assertAlmostEqual(result['scale'],2)
        self.assertAlmostEqual(result['angle'],90)
    def test_injected_bad_landmark_rejected_at_both_scales(self):
        for scale in (1,10):
            pts=np.array([[0,0],[10,1],[2,12],[8,9]])*scale
            bad=pts.copy();bad[2]+=[10*scale,0]
            with self.assertRaisesRegex(ValueError,'inconsistent'):fit_similarity(pts,bad)
    def test_ambiguous_or_nonfinite_inputs_rejected(self):
        for pts in ([[0,0],[1,1]],[[0,0],[1,1],[2,2]],[[0,0],[1,1],[2,float('nan')]]):
            with self.assertRaises(ValueError):fit_similarity(pts,pts)
    def test_reflection_is_not_silently_accepted(self):
        pts=np.array([[0,0],[10,1],[2,12],[8,9]])
        with self.assertRaisesRegex(ValueError,'inconsistent'):fit_similarity(pts,pts*[-1,1])

class RasterRegistration(unittest.TestCase):
    def test_source_preserved_and_canvas_clipping_rejected(self):
        from PIL import Image
        im=Image.new('RGBA',(12,15),(170,120,80,255));before=im.tobytes()
        out,offset=rasterize_registered_head(im,dict(scale=1,angle=0,offset=[20,30]),(100,100))
        self.assertEqual(out.tobytes(),before);self.assertEqual(offset,[20,30]);self.assertEqual(im.tobytes(),before)
        with self.assertRaisesRegex(ValueError,'clip'):
            rasterize_registered_head(im,dict(scale=1,angle=0,offset=[-1,30]),(100,100))
    def test_rotation_preserves_pixel_centers_and_crop(self):
        from PIL import Image
        a=np.zeros((15,12,4),dtype=np.uint8);a[...,3]=255;a[...,0]=np.arange(12);a[...,1]=np.arange(15)[:,None]
        im=Image.fromarray(a);before=im.tobytes()
        out,offset=rasterize_registered_head(im,dict(scale=1,angle=90,offset=[40,30]),(100,100))
        self.assertEqual(offset,[26,30])
        np.testing.assert_array_equal(np.asarray(out),np.asarray(im.transpose(Image.Transpose.ROTATE_270)))
        self.assertEqual(before,im.tobytes())
    def test_malformed_transforms_rejected(self):
        from PIL import Image
        im=Image.new('RGBA',(12,15),'white');pts=[[0,0],[10,0],[0,10]]
        for transform in ({},{'scale':0,'angle':0,'offset':[20,30]},{'scale':1,'angle':float('nan'),'offset':[20,30]},{'scale':1,'angle':0,'offset':[20]},{'scale':1,'angle':0,'offset':[20,float('inf')]}):
            with self.subTest(transform=transform):
                with self.assertRaises(ValueError):rasterize_registered_head(im,transform,(100,100))
                with self.assertRaises(ValueError):register_head(pts,pts,pts,pts,torso_transform=transform)
        with self.assertRaises(ValueError):rasterize_registered_head(im,dict(scale=1,angle=0,offset=[20,30]),(100,-1))
    def test_candidate_changes_only_head_and_keeps_source(self):
        import json,tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'rig';src.mkdir();(src/'layers').mkdir()
            Image.new('RGBA',(12,15),'gold').save(src/'layers/torso.png')
            Image.new('RGBA',(12,15),'white').save(root/'head.png')
            spec={'puppet':{'layers':{'head':{'kind':'rigid','image':'old.png','offset':[0,0],'anchor':[40,50]},'torso':{'image':'layers/torso.png'}}},'body':{'head':4},'gait':{'walk':{'speed':2}}}
            (src/'character.json').write_text(json.dumps(spec));before=(src/'character.json').read_bytes()
            pts=[[0,0],[10,0],[0,10],[10,10]]
            landmarks=dict(head_source=pts,head_reference=pts,torso_source=pts,torso_reference=pts)
            result=create_reference_candidate(src,root/'new',root/'head.png',landmarks=landmarks,torso_transform=dict(scale=1,angle=0,offset=[20,30]),canvas=(100,100))
            actual=json.loads(result.read_text());self.assertEqual(actual['body'],spec['body']);self.assertEqual(actual['gait'],spec['gait'])
            self.assertEqual(actual['puppet']['layers']['torso'],spec['puppet']['layers']['torso'])
            self.assertEqual(actual['puppet']['layers']['head']['anchor'],[40,50])
            self.assertEqual((src/'character.json').read_bytes(),before)
            self.assertEqual((root/'new/layers/torso.png').read_bytes(),(src/'layers/torso.png').read_bytes())
            with self.assertRaisesRegex(ValueError,'new version'):
                create_reference_candidate(src,root/'new',root/'head.png',landmarks=landmarks,torso_transform=dict(scale=1,angle=0,offset=[20,30]),canvas=(100,100))

if __name__=='__main__':unittest.main()
