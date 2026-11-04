"""Candidate extraction is source preservation, never anatomical completeness."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
spec=importlib.util.spec_from_file_location('source_region_layers',Path(__file__).parents[1]/'source_region_layers.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class SourceRegions(unittest.TestCase):
    def test_two_sizes_roundtrip_exported_files(self):
        for w,h in ((42,71),(83,45)):
            with self.subTest(size=(w,h)),tempfile.TemporaryDirectory() as d:
                p=Path(d); rng=np.random.default_rng(3)
                rgb=rng.integers(0,256,(h,w,3),dtype=np.uint8)
                rgb[:h//2,:w//2]=[240,235,223]
                Image.fromarray(rgb).save(p/'source.png')
                report=m.export(p/'source.png',p/'layers',colors=4,max_regions=5)
                rebuilt=Image.new('RGBA',(w,h)); ownership=np.zeros((h,w),int)
                for layer in report['layers']:
                    piece=Image.open(p/'layers'/layer['file']).convert('RGBA');x,y=layer['offset']
                    ownership[y:y+piece.height,x:x+piece.width]+=np.array(piece)[:,:,3]>0
                    rebuilt.alpha_composite(piece,(x,y))
                np.testing.assert_array_equal(np.array(rebuilt)[:,:,:3],rgb)
                self.assertTrue((ownership==1).all())
                self.assertEqual(report['status'],'needs_semantic_review_not_bindable')
                self.assertTrue(all(l['hidden_surface_pixels']==0 for l in report['layers']))
    def test_overlaps_and_holes_fail(self):
        mask=np.ones((5,7),bool)
        with self.assertRaisesRegex(ValueError,'exactly once'):m.validate_partition([mask,mask],mask.shape)
        with self.assertRaisesRegex(ValueError,'exactly once'):m.validate_partition([~mask],mask.shape)
    def test_empty_or_different_shape_masks_fail(self):
        for masks in ([],[np.ones((3,4),bool)],[np.ones((5,7),np.uint8)]):
            with self.assertRaises(ValueError):m.validate_partition(masks,(5,7))
    def test_deterministic_and_input_unmodified(self):
        rgb=np.random.default_rng(2).integers(0,256,(30,20,3),dtype=np.uint8);old=rgb.copy()
        a=m.partition(rgb,3,5);b=m.partition(rgb,3,5)
        np.testing.assert_array_equal(rgb,old)
        for x,y in zip(a,b):np.testing.assert_array_equal(x,y)
if __name__=='__main__':unittest.main()
