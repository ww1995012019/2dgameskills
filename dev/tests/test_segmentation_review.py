import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
spec=importlib.util.spec_from_file_location('review_segmentation',Path(__file__).parents[1]/'review_segmentation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class SegmentationReview(unittest.TestCase):
    def fixture(self,p,w=9,h=13):
        rgb=np.random.default_rng(42).integers(0,256,(h,w,3),dtype=np.uint8)
        Image.fromarray(rgb).save(p/'source.png')
        a=np.zeros((h,w),np.uint8);a[2:8,1:6]=255
        b=np.zeros_like(a);b[5:11,4:8]=255
        for name,mask in [('a',a),('b',b)]:Image.fromarray(mask).save(p/(name+'.png'))
        (p/'select.json').write_text(json.dumps([dict(name='</script><img>',mask='a.png',model_score=.99),dict(name='second',mask='b.png',model_score=.1)]))
        return rgb,a,b
    def test_two_canvas_shapes_actual_files_and_overlap(self):
        for w,h in [(9,13),(17,12)]:
            with tempfile.TemporaryDirectory() as d:
                p=Path(d);rgb,a,b=self.fixture(p,w,h)
                report=m.export(p/'source.png',p/'select.json',p/'out')
                composite=Image.new('RGBA',(w,h))
                for layer in report['layers']:
                    image=Image.open(p/'out'/layer['file'])
                    self.assertEqual(image.size,(w,h));self.assertEqual(layer['offset'],[0,0])
                    self.assertEqual(layer['semantic_confidence'],'unverified')
                    composite.alpha_composite(image)
                actual=np.array(composite);union=(a>0)|(b>0)
                np.testing.assert_array_equal(actual[union,:3],rgb[union])
                np.testing.assert_array_equal(actual[:,:,3]>0,union)
                np.testing.assert_array_equal(actual,np.array(Image.open(p/'out'/'visible-composite.png')))
                self.assertEqual(report['proof']['overlap_pixels'],int(((a>0)&(b>0)).sum()))
                self.assertFalse(report['binding_gate']['allowed'])
                self.assertEqual(report['proof']['hidden_surface_pixels'],0)
                html=(p/'out'/'review.html').read_text();self.assertNotIn('</script><img>',html)
                self.assertIn('\\u003c/script>',html)
                self.assertNotIn('__OWNERSHIP_LOGIC__',html)
                self.assertNotIn('__PAYLOAD__',html)
                self.assertIn('class OwnershipReview',html)
                self.assertIn('Download ownership JSON',html)
    def test_invalid_masks_fail_before_output(self):
        for value,shape in [(127,(13,9)),(255,(12,9)),(0,(13,9))]:
            with tempfile.TemporaryDirectory() as d:
                p=Path(d);self.fixture(p);Image.fromarray(np.full(shape,value,np.uint8)).save(p/'a.png')
                with self.assertRaises(ValueError):m.export(p/'source.png',p/'select.json',p/'out')
                self.assertFalse((p/'out').exists())
    def test_invalid_score_and_empty_selection(self):
        for score in [1.1,-.2,float('nan'),True,'high']:
            with tempfile.TemporaryDirectory() as d:
                p=Path(d);self.fixture(p)
                (p/'select.json').write_text(json.dumps([dict(mask='a.png',model_score=score)]))
                with self.assertRaises(ValueError):m.export(p/'source.png',p/'select.json',p/'out')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.fixture(p);(p/'select.json').write_text('[]')
            with self.assertRaises(ValueError):m.export(p/'source.png',p/'select.json',p/'out')

if __name__=='__main__':unittest.main()
