"""A torso must not hide a severed limb in attachment QA."""
import sys
import unittest
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest import mock
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
from sprite_anim import puppet_check as pc
from sprite_anim import puppet as pp
from sprite_anim.art import Canvas
from sprite_anim.rig import Body, full_pose, solve
from sprite_anim.motions import Proc
from sprite_anim.render import GROUND_FRAC


class AttachmentPixels(unittest.TestCase):
    def masks(self, scale=1, width=12):
        limb = Image.new('L', (120 * scale, 140 * scale))
        parent = Image.new('L', limb.size)
        d = ImageDraw.Draw(limb)
        # Offset, curved shoulder cap, not a completely filled root disc.
        d.line([(45 * scale, 30 * scale), (58 * scale, 78 * scale),
                (90 * scale, 112 * scale)], fill=255, width=width * scale)
        ImageDraw.Draw(parent).ellipse((10 * scale, 8 * scale, 62 * scale, 80 * scale), fill=255)
        return np.asarray(limb) / 255., np.asarray(parent) / 255.

    def test_curved_root_and_two_proportions_pass_at_two_scales(self):
        for width in (10, 18):
            for scale in (1, 2):
                limb, parent = self.masks(scale, width)
                self.assertEqual(pc.attachment_faults(limb, parent, np.array([45,30])*scale,
                                                     np.array([58,78])*scale, width*scale/2), [])

    def test_hidden_proximal_strip_fails_while_composite_is_unchanged(self):
        limb, parent = self.masks()
        damaged = limb.copy()
        damaged[44:50] = 0
        self.assertTrue(np.array_equal(np.maximum(limb, parent), np.maximum(damaged, parent)))
        faults = pc.attachment_faults(damaged, parent, (45,30), (58,78), 6)
        self.assertTrue(any('connected same-layer' in fault for fault in faults), faults)

    def test_parent_and_root_faults_are_separate(self):
        limb, parent = self.masks()
        faults = pc.attachment_faults(limb, np.zeros_like(parent), (45,30), (58,78), 6)
        self.assertTrue(any('parent contact' in fault for fault in faults), faults)
        damaged = limb.copy(); damaged[:42] = 0
        faults = pc.attachment_faults(damaged, parent, (45,30), (58,78), 6)
        self.assertTrue(any('root seat' in fault for fault in faults), faults)

    def test_detached_root_island_does_not_count_as_parent_contact(self):
        limb, parent = self.masks()
        limb[43:52] = 0
        self.assertTrue(any('same-layer' in fault for fault in
                            pc.attachment_faults(limb,parent,(45,30),(58,78),6)))


class AttachmentFrameLocations(unittest.TestCase):
    def renderer(self, wide=False):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        body = Body.from_spec(dict(chest_len=15 if wide else 21, pelvis_len=9 if wide else 11,
                                   up_arm=12 if wide else 16, lo_arm=11 if wide else 15,
                                   sh_w=4 if wide else 2.4, hip_w=3 if wide else 2.2))
        pose = full_pose(dict(pelvis=0, spine=0, head=0))
        sk = solve(pose, body)
        cv = Canvas(256, 1, 2., GROUND_FRAC, 1, False, (0,0,0))
        layers = {}
        def save(name, image, data):
            image.save(Path(folder.name) / (name + '.png'))
            layers[name] = dict(image=name + '.png', **data)
        width = 15 if wide else 11
        for name, bones in [('arm_near', ['sh_n','el_n','wr_n']),
                            ('arm_far', ['sh_f','el_f','wr_f']),
                            ('leg_near', ['hip_n','kn_n','an_n']),
                            ('leg_far', ['hip_f','kn_f','an_f'])]:
            points = [cv.T(sk[k]) for k in bones]
            image = Image.new('RGBA', (256,256)); d = ImageDraw.Draw(image)
            d.line(points, fill=(90,130,160,255), width=width)
            for x,y in points:
                r = width/2
                d.ellipse((x-r,y-r,x+r,y+r), fill=(90,130,160,255))
            save(name,image,dict(kind='tube',bones=bones,rest=points,radius=width/2,
                                 root_lock=True,source_frame=True))
        hip = cv.T(sk['hip']); neck = cv.T(sk['neck']); waist = cv.T(sk['waist'])
        for name, top, bottom, radius in [('torso',neck,hip,18 if wide else 14),
                                          ('hips',waist,hip,17 if wide else 13)]:
            image=Image.new('RGBA',(256,256));d=ImageDraw.Draw(image)
            d.line([top,bottom],fill=(150,80,100,255),width=radius*2)
            for x,y in (top,bottom):d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=(150,80,100,255))
            save(name,image,dict(kind='rigid',follow=['hip','body_rot'],anchor=hip))
        puppet=pp.Puppet(dict(_dir=folder.name,puppet=dict(px_per_unit=2.,
                         joints={'hip':hip},rest_angles={'body_rot':0},layers=layers)))
        def sample(t):
            return dict(pose,arm_n_up=pose['arm_n_up']+25*np.sin(t*2*np.pi),
                        arm_f_up=pose['arm_f_up']-25*np.sin(t*2*np.pi))
        clip=Proc('walk',1.,sample)
        renderer=SimpleNamespace(size=256,ss=1,unit=2.,art=SimpleNamespace(puppet=puppet,body=body),
                                 cloth_at=lambda clip,t:{})
        return renderer,clip

    def test_two_bound_proportions_have_connected_walk_attachments(self):
        for wide in (False, True):
            with self.subTest(wide=wide):
                renderer, clip = self.renderer(wide)
                self.assertEqual(pc.check_attachments(renderer, clip, 5, 15), [])

    def test_raster_fault_identifies_clip_frame_part_and_root(self):
        renderer, clip = self.renderer()
        real_raster = pp.raster
        frame = -1
        def cloth_at(clip, t):
            nonlocal frame
            frame += 1
            return {}
        renderer.cloth_at = cloth_at

        def broken(layer, verts, mip, w, h):
            output = real_raster(layer, verts, mip, w, h)
            if layer.name == 'arm_near' and frame == 1:
                output[..., 3] = 0
            return output

        with mock.patch.object(pp, 'raster', broken):
            faults = pc.check_attachments(renderer, clip, 3, 15)
        self.assertTrue(any(f.startswith('attachment: arm_near: walk frame 1: root sh_n:')
                            for f in faults), faults)

    def full_oracle(self, renderer, clip, n, fps):
        from sprite_anim.render import frame_time
        puppet = renderer.art.puppet
        cv = Canvas(renderer.size, renderer.ss, renderer.unit, GROUND_FRAC, 1, False, (0,0,0))
        scale = cv.s / puppet.px_per_unit
        definitions = {'arm_near': ('sh_n','el_n',('torso',)),
                       'arm_far': ('sh_f','el_f',('torso',)),
                       'leg_near': ('hip_n','kn_n',('hips','torso')),
                       'leg_far': ('hip_f','kn_f',('hips','torso'))}
        found = {}
        for i in range(n):
            t=frame_time(clip,i,n,fps);pose=full_pose(clip.sample(t));sk=solve(pose,renderer.art.body)
            cv.set_squash(pose['squash'],0.)
            masks={};layers={}
            for layer,verts in puppet.meshes(cv,sk,renderer.cloth_at(clip,t),'ground' in clip.tags):
                layers[layer.name]=layer
                masks[layer.name]=pp.raster(layer,verts,puppet.mip(layer,scale),cv.w,cv.h)[...,3]
            for name,(root,end,parents) in definitions.items():
                if name in found or name not in masks:continue
                parent=np.zeros((cv.h,cv.w))
                for part in parents:
                    if part in masks:parent=np.maximum(parent,masks[part])
                faults=pc.attachment_faults(masks[name],parent,cv.T(sk[root]),cv.T(sk[end]),layers[name].radius*scale)
                if faults:found[name]=f"attachment: {name}: {clip.name} frame {i}: root {root}: {'; '.join(faults)}"
        return list(found.values())

    def test_roi_matches_full_oracle_random_poses_faults_and_canvas_edges(self):
        rng=np.random.default_rng(20261103)
        for scale in (1,2):
            renderer,_=self.renderer(wide=scale==2)
            renderer.ss=scale
            puppet=renderer.art.puppet
            arm=next(layer for layer in puppet.layers if layer.name=='arm_near')
            original=np.array(arm.image)
            for case in range(12):
                pose=full_pose(dict(pelvis=0,spine=0,head=0,
                    root_x=float(rng.choice([-70,-35,0,35,70])),
                    root_y=float(rng.uniform(-15,35)),
                    arm_n_up=float(rng.uniform(-90,90)),arm_f_up=float(rng.uniform(-90,90))))
                clip=Proc('random',1.,lambda t,p=pose:p)
                pixels=original.copy()
                if case%3==0:pixels[int(rng.integers(65,125)):int(rng.integers(130,170)),:,3]=0
                arm.image=Image.fromarray(pixels);puppet.mips.clear()
                with self.subTest(scale=scale,case=case):
                    self.assertEqual(pc.check_attachments(renderer,clip,1,15),self.full_oracle(renderer,clip,1,15))

    def test_roi_pixel_samples_match_full_canvas_after_integer_translation(self):
        renderer,clip=self.renderer()
        puppet=renderer.art.puppet
        rng=np.random.default_rng(99)
        for ss in (1,2):
            cv=Canvas(256,ss,2.,GROUND_FRAC,1,False,(0,0,0));scale=cv.s/puppet.px_per_unit
            sk=solve(full_pose(clip.sample(.21)),renderer.art.body)
            for layer,verts in puppet.meshes(cv,sk,{}):
                full=pp.raster(layer,verts,puppet.mip(layer,scale),cv.w,cv.h)
                for _ in range(3):
                    x0=int(rng.integers(0,cv.w//2));y0=int(rng.integers(0,cv.h//2))
                    x1=int(rng.integers(cv.w//2,cv.w+1));y1=int(rng.integers(cv.h//2,cv.h+1))
                    roi=pp.raster(layer,verts-[x0,y0],puppet.mip(layer,scale),x1-x0,y1-y0)
                    np.testing.assert_array_equal(roi,full[y0:y1,x0:x1])

    def test_outside_roi_connectivity_uses_full_canvas_fallback(self):
        # A real connected U-shaped alpha path leaves the local query rectangle.
        image=Image.new('L',(120,140));draw=ImageDraw.Draw(image)
        draw.line([(45,30),(45,34),(10,34),(10,65),(53,65),(53,40)],fill=255,width=4)
        limb=np.asarray(image)/255.;parent=np.zeros_like(limb);parent[20:36,40:50]=1
        self.assertEqual(pc.attachment_faults(limb,parent,(45,30),(58,78),6),[])
        box=(34,19,66,72);x0,y0,x1,y1=box
        self.assertTrue(pc.attachment_faults(limb[y0:y1,x0:x1],parent[y0:y1,x0:x1],
                                            np.array([45,30])-[x0,y0],np.array([58,78])-[x0,y0],6))
        renderer,clip=self.renderer()
        puppet=renderer.art.puppet
        real_raster=pp.raster
        saw_full=[]
        def detour(layer,verts,mip,w,h):
            result=real_raster(layer,verts,mip,w,h)
            # Model a local component split whose connection runs outside ROI.
            # The full canvas retains the legitimate path and must win.
            if layer.name=='arm_near':
                if w<renderer.size or h<renderer.size:result[...,3]=0
                else:saw_full.append(True)
            return result
        with mock.patch.object(pp,'raster',detour):
            self.assertEqual(pc.check_attachments(renderer,clip,1,15),[])
        self.assertTrue(saw_full)


if __name__ == '__main__':
    unittest.main()
