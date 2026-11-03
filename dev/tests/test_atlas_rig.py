"""Atlas separation and material ownership; synthetic checks are not art approval."""
import unittest,tempfile,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import atlas_rig as ar


class AtlasRig(unittest.TestCase):
    def test_eight_components_at_two_scales_keep_their_pixels(self):
        for scale in (1,2):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);im=Image.new('RGBA',(512*scale,768*scale));d=ImageDraw.Draw(im)
                colors=[]
                for i in range(8):
                    x=(i%4*128+10)*scale;y=(i//4*384+40)*scale
                    color=(40+i*20,90+i*9,160-i*12,255);colors.append(color)
                    d.rectangle((x,y,x+80*scale,y+260*scale),fill=color)
                im.save(root/'atlas.png');ar.extract(root/'atlas.png',root/'parts')
                for i,n in enumerate((*ar.TOP,*ar.BOTTOM)):
                    a=np.array(Image.open(root/'parts'/(n+'.png')));on=a[...,3]>0
                    np.testing.assert_array_equal(a[on],np.tile(colors[i],(on.sum(),1)))

    def test_ambiguous_extra_part_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);im=Image.new('RGBA',(512,768));d=ImageDraw.Draw(im)
            for i in range(8):
                x=i%4*128+10;y=i//4*384+40;d.rectangle((x,y,x+80,y+260),fill='white')
            d.rectangle((15,320,115,370),fill='white');im.save(root/'atlas.png')
            with self.assertRaisesRegex(ValueError,'eight'):ar.extract(root/'atlas.png',root/'parts')

    def test_neck_skin_and_neutral_cut_edge_both_leave_the_front_copy(self):
        for skin in ((220,170,130,255),(105,65,40,255)):
            im=Image.new('RGBA',(160,220));d=ImageDraw.Draw(im)
            d.rectangle((20,50,140,210),fill=(30,65,85,255))
            d.rectangle((60,0,100,55),fill=skin)
            d.line((60,3,100,3),fill=(180,180,180,255),width=2)
            d.line((58,1,102,1),fill=(100,100,100,70),width=1)
            before=np.array(im);garment,removed=ar.remove_neck_stub(im);after=np.array(garment)
            self.assertGreater(removed,0)
            self.assertEqual(after[1,80,3],0)
            self.assertEqual(after[3,80,3],0) # implanted cut-edge highlight must not survive
            np.testing.assert_array_equal(before[100:],after[100:])
            np.testing.assert_array_equal(before,np.array(im))

    def test_complete_garment_is_unchanged(self):
        im=Image.new('RGBA',(100,200),(25,55,80,255));out,count=ar.remove_neck_stub(im)
        self.assertEqual(count,0);np.testing.assert_array_equal(np.array(im),np.array(out))

    def test_two_humanoid_drawings_have_supported_measured_limbs(self):
        import test_puppet as fixtures
        for options in ({},dict(hip=(480,960),leg=300,chest=(170,240),head=210,stride=70,width=84)):
            layers=fixtures.figure(**options)
            for name in ('arm_near','arm_far','leg_near','leg_far'):
                image=Image.fromarray(fixtures.keyed(layers[name]));image=image.crop(image.getbbox())
                row=ar.landmarks(image,name)
                keys=('shoulder','elbow','wrist') if name.startswith('arm') else ('hip','knee','ankle')
                lengths=ar.lp.check_limb(name,np.array(image)[...,3]>128,[row[k] for k in keys])
                self.assertGreater(min(lengths),0)


if __name__=='__main__':unittest.main()
