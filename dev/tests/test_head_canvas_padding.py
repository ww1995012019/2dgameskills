"""Integer source-frame rebasing must preserve every known-joint coordinate."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from head_registration import create_reference_candidate, translate_source_frame, rasterize_registered_head


class HeadCanvasPadding(unittest.TestCase):
    def fixture(self, root, scale):
        src = root/'rig'; src.mkdir(); (src/'layers').mkdir()
        pixels = np.zeros((8*scale, 10*scale, 4), dtype=np.uint8)
        pixels[..., 0] = np.arange(10*scale); pixels[..., 1] = 117; pixels[..., 3] = 255
        for name in ('head','leg'):
            Image.fromarray(pixels).save(src/'layers'/f'{name}.png')
        Image.fromarray(pixels).save(root/'head.png')
        p = lambda x, y: [x*scale, y*scale]
        puppet = dict(joints={'hip':p(20,20),'neck':p(20,10)}, rest_angles={'head_rot':0},
                      px_per_unit=scale, rest_arm={'n':[p(11,14),p(12,15)]}, chains={},
                      layers={'head':dict(kind='rigid',image='layers/head.png',offset=p(1,2),anchor=p(20,10),follow=['neck','head_rot']),
                              'leg':dict(kind='tube',image='layers/leg.png',offset=p(-2,39),rest=[p(20,20),p(20,30),p(21,38)],bones=['hip','knee','ankle'],radius=3*scale,source_frame=True,
                                         foot=dict(ankle=p(21,38),shin_dir=[0,1],side='n',blend=2*scale,width=3*scale,rest_angle=0))})
        spec=dict(puppet=puppet,body={'thigh':18,'shin':19},gait={'walk':{'profile':'natural_walk_v1'}})
        (src/'character.json').write_text(json.dumps(spec))
        pts=np.array([[0,0],[6,0],[0,6],[6,6]])*scale
        lm={k:pts.tolist() for k in ('head_source','head_reference','torso_source','torso_reference')}
        return src, spec, lm

    def test_two_sizes_padding_preserves_pixels_metadata_and_entire_old_rectangles(self):
        for scale in (1,3):
            with self.subTest(scale=scale), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);src,spec,lm=self.fixture(root,scale)
                hashes={str(p.relative_to(src)):p.read_bytes() for p in src.rglob('*') if p.is_file()}
                kwargs=dict(landmarks=lm,torso_transform=dict(scale=1,angle=0,offset=[-5*scale,-2*scale]),canvas=(40*scale,40*scale))
                with self.assertRaisesRegex(ValueError,'clip'):
                    create_reference_candidate(src,root/'reject',root/'head.png',**kwargs)
                self.assertFalse((root/'reject').exists())
                output=create_reference_candidate(src,root/'padded',root/'head.png',pad_canvas=True,**kwargs)
                actual=json.loads(output.read_text()); report=json.loads((output.parent/'head_registration.json').read_text())
                shift=report['canvas_padding']['translation']; canvas=report['canvas_padding']['after']
                self.assertEqual(actual['body'],spec['body']); self.assertEqual(actual['gait'],spec['gait'])
                np.testing.assert_allclose(report['unpadded_offset'],[-5.*scale,-2.*scale],atol=1e-12)
                expected=translate_source_frame(spec['puppet'],shift)
                self.assertEqual(actual['puppet']['layers']['leg'],expected['layers']['leg'])
                self.assertEqual(actual['puppet']['joints'],expected['joints'])
                self.assertEqual(actual['puppet']['rest_arm'],expected['rest_arm'])
                self.assertEqual(actual['puppet']['layers']['head']['anchor'],expected['layers']['head']['anchor'])
                self.assertEqual((output.parent/'layers/leg.png').read_bytes(),(src/'layers/leg.png').read_bytes())
                np.testing.assert_array_equal(np.array(Image.open(output.parent/'layers/head_reference.png')),np.array(Image.open(root/'head.png')))
                layer=actual['puppet']['layers']['leg']; at=layer['offset']
                with Image.open(src/layer['image']) as image: size=image.size
                self.assertGreaterEqual(min(at),0); self.assertTrue(all(at[i]+size[i]<=canvas[i] for i in (0,1)))
                with Image.open(output.parent/'source.png') as composite:
                    self.assertEqual(list(composite.size),canvas)
                    box=tuple(int(v) for v in (*at,at[0]+size[0],at[1]+size[1]))
                    with Image.open(src/layer['image']) as image:
                        np.testing.assert_array_equal(np.array(composite.crop(box)),np.array(image))
                self.assertEqual(hashes,{str(p.relative_to(src)):p.read_bytes() for p in src.rglob('*') if p.is_file()})

    def test_fractional_similarity_raster_is_identical_after_integer_rebase(self):
        pixels=np.zeros((14,12,4),dtype=np.uint8)
        pixels[2:12,2:10]=[109,53,21,255]
        pixels[5:8,4:7]=[212,98,45,147]
        im=Image.fromarray(pixels)
        for scale in (.73,1.61):
            transform=dict(scale=scale,angle=17.3,offset=[25.23,19.87])
            a,at=rasterize_registered_head(im,transform,(80,80))
            transform['offset']=(np.array(transform['offset'])+[13,27]).tolist()
            b,bt=rasterize_registered_head(im,transform,(93,107))
            self.assertEqual(a.tobytes(),b.tobytes())
            self.assertEqual(bt,(np.array(at)+[13,27]).tolist())

    def test_translation_is_reversible_and_vectors_lengths_angles_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,spec,_=self.fixture(Path(tmp),2); original=copy.deepcopy(spec['puppet'])
            moved=translate_source_frame(original,[17,31]); restored=translate_source_frame(moved,[-17,-31])
            self.assertEqual(restored,original); self.assertEqual(spec['puppet'],original)
            self.assertEqual(moved['layers']['leg']['foot']['shin_dir'],[0,1])
            np.testing.assert_array_equal(np.diff(moved['layers']['leg']['rest'],axis=0),np.diff(original['layers']['leg']['rest'],axis=0))

    def test_unknown_coordinate_fields_and_chains_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,spec,_=self.fixture(Path(tmp),1)
            for location,key,value in [('puppet','chains',{'cape':{}}),('puppet','future_origin',[1,2]),('layer','future_anchor',[1,2]),('foot','future_toe',[1,2]),('layer','kind','cloth')]:
                p=copy.deepcopy(spec['puppet']); target=p if location=='puppet' else p['layers']['leg'] if location=='layer' else p['layers']['leg']['foot']; target[key]=value
                with self.subTest(location=location,key=key), self.assertRaisesRegex(ValueError,'support'):
                    translate_source_frame(p,[1,2])

    def test_invalid_translation_and_nonfinite_source_coordinate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,spec,_=self.fixture(Path(tmp),1)
            for shift in ([.5,1],[float('nan'),1],[1]):
                with self.assertRaises(ValueError):translate_source_frame(spec['puppet'],shift)
            spec['puppet']['joints']['hip']=[float('inf'),0]
            with self.assertRaises(ValueError):translate_source_frame(spec['puppet'],[1,2])
