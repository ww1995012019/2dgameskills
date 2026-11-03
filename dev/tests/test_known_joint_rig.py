"""Zero-generation binding, input faults and rigid-hand invariants."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import template_full_character as full
import template_puppet as tp
import test_template_full_character as fixtures
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
import bind_known_joints as entry
from sprite_anim.puppet import Layer, lock_tip, rigid
from sprite_anim.render import Renderer
from sprite_anim.rig import Body, solve, full_pose
from sprite_anim.motions import build_clips
from sprite_anim import puppet_check as pc


class KnownRig(unittest.TestCase):
    def test_two_profiles_bind_without_inference_or_hand_hint_images(self):
        for profile in tp.PROFILES:
            stage = fixtures.FullTemplate.complete_fixture(self, profile)
            full.inspect(stage)
            report = tp.read(stage/'assembly_report.json')
            for weapon in (True, False):
                order = [n for n in full.ORDER if weapon or n != 'weapon']
                manifest = stage/'input.json'
                layers = {n: f'assembled_layers/{n}.png' for n in order}
                job = dict(name='Synthetic '+profile, layers=layers, joints=report['joints'], order=order)
                if profile == 'compact' and not weapon:
                    with Image.open(stage/layers['head']) as head_image:
                        job['canvas'] = list(head_image.size)
                    for name, relative in layers.items():
                        with Image.open(stage/relative) as image:
                            box = image.getbbox()
                            cropped = stage/(name+'-cropped.png')
                            image.crop(box).save(cropped)
                        job['layers'][name] = dict(image=cropped.name, offset=list(box[:2]))
                tp.write(manifest, job)
                paths = {n: stage/(p['image'] if isinstance(p,dict) else p) for n,p in layers.items()}
                before = {n: entry.digest(p) for n,p in paths.items()}
                out = stage/('armed' if weapon else 'unarmed')
                entry.bind(manifest, out)
                self.assertEqual(before, {n: entry.digest(p) for n,p in paths.items()})
                provenance = tp.read(out/'provenance.json')
                self.assertEqual(provenance['image_generation_calls'], 0)
                self.assertFalse(provenance['final_visual_pass'])
                spec = tp.read(out/'character.json');spec['_dir'] = str(out)
                self.assertEqual(spec['weapon'], 'sword' if weapon else 'none')
                clips = build_clips(body=Body.from_spec(spec['body']), gait=spec['gait'])
                knees=[]
                for t in np.linspace(0,clips['idle'].duration,24):
                    sk=solve(full_pose(clips['idle'].sample(float(t))),Body.from_spec(spec['body']))
                    for side in 'nf':
                        a=np.subtract(sk['kn_'+side],sk['hip_'+side]);v=np.subtract(sk['an_'+side],sk['kn_'+side])
                        knees.append(np.degrees(np.arccos(np.clip(a@v/np.linalg.norm(a)/np.linalg.norm(v),-1,1))))
                self.assertLess(np.mean(knees),pc.CROUCH_DEG)
                renderer = Renderer(spec, 192, clips={n:clips[n] for n in ('idle','walk')})
                self.assertEqual(pc.check_layers(renderer.art.puppet), [])
                for name in ('idle','walk'):
                    self.assertEqual(pc.check_motion(renderer, clips[name], 8, 15), [])
                with self.assertRaisesRegex(ValueError,'destination exists'):
                    entry.bind(manifest,out)
            job['joints']['arm_near']['wrist']=[float('nan'),0]
            tp.write(manifest,job)
            with self.assertRaisesRegex(ValueError,'finite'):
                entry.bind(manifest,stage/'invalid')
            self.assertFalse((stage/'invalid').exists())

    def test_invalid_manifest_never_leaves_an_accepted_rig(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            image=Image.new('RGBA',(40,40))
            image.paste((70,90,110,255),(5,5,35,35));image.save(root/'part.png')
            names=sorted(entry.REQUIRED)
            joints={n:{k:[15.,15.] for k in keys} for n,keys in entry.JOINTS.items()}
            job=dict(layers={n:'part.png' for n in names},order=names,joints=joints)
            manifest=root/'input.json';out=root/'rig'
            for fault,message in [('order','exactly once'),('canvas','clip'),('joint','finite')]:
                bad=json.loads(json.dumps(job))
                if fault=='order':bad['order']=names+[names[0]]
                elif fault=='canvas':bad['canvas']=[20,20]
                else:bad['joints']['head']['head_base']=[float('nan'),15.]
                manifest.write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError,message):entry.bind(manifest,out)
                self.assertFalse(out.exists())
                self.assertFalse(list(root.glob('.rig-*')))

    def test_hand_shape_is_rigid_under_large_elbow_bends(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp)/'arm.png'
            Image.new('RGBA',(100,160),(60,90,130,255)).save(image)
            layer = Layer('arm',dict(kind='tube',image='arm.png',rest=[[40,10],[40,65],[40,115]],radius=10),tmp)
            source = layer.vx + layer.offset[0], layer.vy + layer.offset[1]
            for angle in (-1.1,-.5,0,.7,1.5):
                points=[np.array([50.,20.]),np.array([50.,75.]),np.array([50+50*np.sin(angle),75+50*np.cos(angle)])]
                warped=layer.mapped(points,1.)
                protected=lock_tip(layer,warped,points,1.)
                expected=rigid(*source,layer.rest[-1],points[-1],-angle,1.)
                distal=layer.vy>=115
                np.testing.assert_allclose(protected[distal],expected[distal],atol=1e-10)
                at_root=lock_tip(layer, warped, points, 1., root=True)
                a=points[0]-points[1]
                root_angle=np.arctan2(a[1],a[0])-np.arctan2(-55.,0.)
                root_expected=rigid(*source,layer.rest[0],points[0],root_angle,1.)
                np.testing.assert_allclose(at_root[layer.vy<=10],root_expected[layer.vy<=10],atol=1e-10)
                # Removing the protection must expose the bend-induced distortion.
                if abs(angle)>.5:
                    self.assertGreater(np.max(abs(warped[distal]-expected[distal])),.01)


if __name__=='__main__':unittest.main()
