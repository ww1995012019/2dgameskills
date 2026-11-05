"""Opt-in whole rear appendage: pelvic contact and source-preserving carriage.

These are synthetic proportion/scale and fault tests, not real-creature approval.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'game-sprite-animator/scripts'))
import layer_parts as lp
from sprite_anim.layer_slots import BASIC_SLOTS, SLOTS, basic_prompt, prompt
from dev.tests.test_puppet import figure, keyed

class RearAppendage(unittest.TestCase):
    def test_optional_experiment_is_not_a_basic_layer(self):
        self.assertIn('appendage_back',SLOTS)
        self.assertFalse(SLOTS['appendage_back'][2])
        self.assertNotIn('appendage_back',BASIC_SLOTS)
        with self.assertRaisesRegex(ValueError,'unsupported basic layer'):
            basic_prompt('appendage_back')
        self.assertIn('rigid source shape',prompt('appendage_back'))
        self.assertIn('rear biological appendage',prompt('arm_near'))

    def test_detached_and_wrong_body_contact_are_rejected_at_two_scales(self):
        for scale in (1,3):
            parent=np.zeros((120*scale,160*scale),bool)
            parent[10*scale:100*scale,90*scale:110*scale]=True
            tail=np.zeros_like(parent);tail[75*scale:86*scale,10*scale:100*scale]=True
            hip=np.array([100,80])*scale
            layer,report=lp.rear_appendage_binding(tail,parent,hip,100*scale)
            self.assertEqual(layer['follow'],['hip','body_rot'])
            self.assertFalse(report['articulated'])
            tail[:,85*scale:]=False
            with self.assertRaisesRegex(lp.Rejected,'no overlapping pelvic root'):
                lp.rear_appendage_binding(tail,parent,hip,100*scale)
            wrong=np.zeros_like(tail);wrong[10*scale:20*scale,10*scale:100*scale]=True
            with self.assertRaisesRegex(lp.Rejected,'away from the pelvis'):
                lp.rear_appendage_binding(wrong,parent,hip,100*scale)

    def test_two_body_builds_bind_same_rigid_pelvic_extension(self):
        identity=dict(s=1.,deg=0.,dx=0.,dy=0.,cx=0.,cy=0.,error=0.)
        builds=[dict(),dict(hip=(480,960),leg=300,chest=(170,240),head=210,stride=70,width=84)]
        for kw in builds:
            images=figure(**kw);hx,hy=kw.get('hip',(470,880))
            tail=Image.new('RGB',(1024,1536),lp.KEY_COLOR)
            # This valid shorter appendage has a substantial hidden root under
            # the opaque garment. Alpha overlap is not duplicate garment art.
            d=ImageDraw.Draw(tail);d.line([(hx,hy),(hx-130,hy+20),(hx-260,hy-35)],fill=(45,70,65),width=40)
            images['appendage_back']=tail
            layers={n:keyed(v) for n,v in images.items()}
            composite=Image.new('RGBA',(1024,1536))
            for name in SLOTS:
                if name in layers:composite.alpha_composite(Image.fromarray(layers[name]))
            state={}
            with patch.object(lp,'registration',return_value=identity):
                out,spec,_=lp.bind(np.asarray(composite).copy(),layers,diagnostics=state)
            self.assertEqual(next(iter(spec['puppet']['layers'])),'appendage_back')
            data=spec['puppet']['layers']['appendage_back']
            self.assertEqual(data['kind'],'rigid')
            self.assertEqual(data['anchor'],spec['puppet']['joints']['hip'])
            np.testing.assert_array_equal(out['appendage_back'],layers['appendage_back'])
            self.assertEqual(state['rear_appendage']['model'],'rigid_pelvis_follow')

if __name__=='__main__':unittest.main()
