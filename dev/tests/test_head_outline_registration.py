"""Head outline registration survives changes in face shading without hiding drift."""
import sys,unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
import layer_parts as lp

class HeadOutlineRegistration(unittest.TestCase):
    def art(self,size):
        im=Image.new('RGBA',(size,size));ImageDraw.Draw(im).ellipse((size*.3,size*.12,size*.65,size*.6),fill=(220,150,100,255));return np.asarray(im)
    def test_two_head_sizes_keep_original_outline(self):
        for size in (160,320):
            a=self.art(size);ref=a.copy();ref[ref[...,3]>0,:3]=(180,110,65)
            wrong=dict(s=.86,deg=6.,dx=1.,dy=-10.,cx=size*.5,cy=size*.3,error=.1)
            fit=lp.registered_head(a,ref,wrong)
            self.assertEqual((fit['s'],fit['deg'],fit['dx'],fit['dy']),(1.,0.,0.,0.))
    def test_real_head_drift_uses_searched_fit(self):
        for size in (160,320):
            a=self.art(size);fit=dict(s=1.,deg=0.,dx=12.,dy=8.,cx=0.,cy=0.,error=0.)
            ref=lp.placed(a,fit,(size,size))
            self.assertEqual(lp.registered_head(a,ref,fit),fit)

if __name__=='__main__':unittest.main()
