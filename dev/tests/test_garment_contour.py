"""Visible cloth edges must not escape material QA or curl past their owners."""
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'game-animator/modes/game-sprite-animator/scripts'))
from sprite_anim import puppet as pp, puppet_check as pc


def material(width=110, height=220):
    x, y = np.meshgrid(np.arange(0., width+10., 10.), np.arange(0., height+10., 10.))
    j, i = np.indices((y.shape[0]-1, x.shape[1]-1))
    layer = SimpleNamespace(vx=x, vy=y, offset=np.zeros(2),
                            cells=np.column_stack((j.ravel(), i.ravel())),
                            used=np.ones(x.shape, bool),
                            image=Image.new('RGBA', (width+1, height+1), (90, 130, 160, 255)))
    return layer, np.stack((x, y), -1)


class GarmentContour(unittest.TestCase):
    def test_coverage_cache_tracks_in_place_alpha_and_grid_changes(self):
        layer, _ = material(20,20)
        first = pc.material_coverage(layer)
        self.assertIs(pc.material_coverage(layer)[0],first[0])
        layer.image.paste((0,0,0,0),(0,0,21,21))
        self.assertFalse(pc.material_coverage(layer)[0].any())
        ImageDraw.Draw(layer.image).line((19,1,19,19),fill=(90,130,160,255))
        self.assertTrue(pc.material_coverage(layer)[0].any())
        old = pc.material_coverage(layer)[0]
        layer.cells = layer.cells[:1]
        self.assertEqual(len(pc.material_coverage(layer)[0]),2)
        self.assertIsNot(pc.material_coverage(layer)[0],old)
        self.assertFalse(pc.material_coverage(layer)[0].flags.writeable)

    def test_thin_opaque_edge_is_checked_when_triangle_centres_are_transparent(self):
        layer, vertices = material(20, 20)
        layer.image = Image.new('RGBA', (21, 21))
        draw = ImageDraw.Draw(layer.image)
        draw.rectangle((0, 0, 10, 20), fill=(90, 130, 160, 255))
        draw.rectangle((19, 2, 20, 8), fill=(90, 130, 160, 255))
        vertices[:, -1, 0] = 10.1
        report = dict(origin=[0., 0.], up=[0., -1.], attachment_depth=0., fade=20.)
        measured = pc.garment_strain(layer, vertices, 1., report)
        self.assertGreater(measured['bad_share'], 0.)
        self.assertGreater(measured['boundary_bad'], 0)

    def test_rigid_rotation_and_scale_preserve_thin_source_edges(self):
        layer, source = material(20, 20)
        layer.image = Image.new('RGBA', (21, 21))
        ImageDraw.Draw(layer.image).line((19, 1, 19, 19), fill=(90, 130, 160, 255))
        report = dict(origin=[0., 0.], up=[0., -1.], attachment_depth=0., fade=20.)
        for angle, scale in ((.8, .6), (-1.2, 2.1)):
            vertices = pp.rigid(layer.vx, layer.vy, (0., 0.), (17., 29.), angle, scale)
            measured = pc.garment_strain(layer, vertices, scale, report)
            self.assertGreater(measured['samples'], 0)
            self.assertEqual(measured['bad_share'], 0.)
            self.assertEqual(measured['boundary_bad'], 0)

    def test_one_bad_boundary_triangle_is_not_averaged_into_a_large_garment(self):
        layer, vertices = material(200, 400)
        vertices[1, 0, 0] = 9.99
        report = dict(origin=[0., 0.], up=[0., -1.], attachment_depth=0., fade=400.)
        measured = pc.garment_strain(layer, vertices, 1., report)
        self.assertLess(measured['bad_share'], .01)
        self.assertGreater(measured['boundary_bad'], 0)

    def test_two_widths_do_not_curl_material_past_both_attachment_owners(self):
        for width, height, fade in ((110, 300, 210.), (150, 320, 250.)):
            for angle in (-.8, .8):
                with self.subTest(width=width, angle=angle):
                    layer, source = material(width, height)
                    root = np.array([width/2., 20.])
                    phase = np.clip((layer.vy-40.)/fade, 0., 1.)
                    weights = 1-phase*phase*(3-2*phase)
                    solver = pp.GarmentBand(layer, weights)
                    distal = pp.rigid(layer.vx, layer.vy, root, root, angle, 1.)
                    target = distal*(1-weights[..., None])+source*weights[..., None]
                    repaired = solver.solve(target, 1., rotation_limits=(0., angle))
                    src, dest, _, solid = pc.material_triangles(layer, repaired)
                    se = np.stack((src[:, 1]-src[:, 0], src[:, 2]-src[:, 0]), -1)
                    de = np.stack((dest[:, 1]-dest[:, 0], dest[:, 2]-dest[:, 0]), -1)
                    u, _, vh = np.linalg.svd(de @ np.linalg.inv(se))
                    rotation = u @ vh
                    turns = np.arctan2(rotation[:, 1, 0], rotation[:, 0, 0])
                    # A free band may compress, but it cannot turn backwards
                    # into a new hook while both owners turn less than 46 deg.
                    self.assertGreaterEqual(float(turns[solid].min()), min(0., angle)-.03)
                    self.assertLessEqual(float(turns[solid].max()), max(0., angle)+.03)
                    self.assertEqual(pc.material_strain(src, dest, solid, 1.)['bad_share'], 0.)
                    fixed = ~solver.movable.reshape(layer.vx.shape)
                    np.testing.assert_array_equal(repaired[fixed], target[fixed])

    def test_bounded_solver_preserves_rigid_frames_source_pixels_and_angle_wrap(self):
        layer, source = material(80,260)
        phase = np.clip((layer.vy-40.)/160.,0.,1.)
        weights = 1-phase*phase*(3-2*phase)
        solver = pp.GarmentBand(layer,weights)
        original = layer.image.tobytes()
        for angle,scale in ((.5,.7),(-2.9,1.4)):
            target = pp.rigid(layer.vx,layer.vy,(40.,20.),(81.,45.),angle,scale)
            actual = solver.solve(target,scale,rotation_limits=(angle,angle))
            np.testing.assert_allclose(actual,target,atol=1e-7)
        distal = pp.rigid(layer.vx,layer.vy,(40.,20.),(40.,20.),.8,1.)
        target = distal*(1-weights[...,None])+source*weights[...,None]
        expected = solver.solve(target,1.,rotation_limits=(0.,.8))
        angle = 3.05
        rotation = np.array([[math.cos(angle),math.sin(angle)],[-math.sin(angle),math.cos(angle)]])
        actual = solver.solve(target@rotation+[27.,43.],1.,rotation_limits=(angle,angle+.8-math.tau))
        np.testing.assert_allclose(actual,expected@rotation+[27.,43.],atol=1e-6)
        self.assertEqual(layer.image.tobytes(),original)

    def test_nearly_isometric_reversed_material_cannot_pass_as_good_cloth(self):
        layer, _ = material()
        vertices = pp.rigid(layer.vx, layer.vy, (55., 20.), (55., 20.), math.pi, 1.)
        report = dict(origin=[0., 0.], up=[0., -1.], attachment_depth=0., fade=220.)
        measured = pc.garment_strain(layer, vertices, 1., report, rotation_limits=(0., .8))
        self.assertEqual(measured['bad_share'], 0.)
        self.assertEqual(measured['boundary_bad'], 0)
        self.assertGreater(measured['max_turn_error_px'], 1.)

    def test_infeasible_short_wide_band_is_flagged_instead_of_silently_accepted(self):
        layer, source = material(150, 180)
        phase = np.clip((layer.vy-40.)/80., 0., 1.)
        weights = 1-phase*phase*(3-2*phase)
        distal = pp.rigid(layer.vx, layer.vy, (75., 20.), (75., 20.), .8, 1.)
        target = distal*(1-weights[..., None])+source*weights[..., None]
        solver = pp.GarmentBand(layer, weights)
        repaired = solver.solve(target, 1., rotation_limits=(0., .8))
        report = dict(origin=[0., 0.], up=[0., -1.], attachment_depth=40., fade=80.)
        measured = pc.garment_strain(layer, repaired, 1., report, rotation_limits=(0., .8))
        self.assertTrue(measured['boundary_bad'] or measured['max_turn_error_px']>1.
                        or measured['bad_share']>.01)

    def injected_faults(self,kind):
        import test_garment_rims as fixtures
        case = fixtures.HiddenGarmentEdges('runTest')
        renderer, clip = case.renderer(True)
        self.addCleanup(case.doCleanups)
        puppet = renderer.art.puppet
        real = puppet.meshes
        frame = -1
        def advance(*_):
            nonlocal frame
            frame += 1
            return {}
        renderer.cloth_at = advance
        def damaged(*args,**kwargs):
            for layer,vertices in real(*args,**kwargs):
                if layer.name == 'leg_near' and frame == 2:
                    _,_,_,_,edge = pc.material_triangles(layer,vertices,include_boundary=True)
                    j,i = layer.cells.T; w = layer.vx.shape[1]
                    triangles = np.concatenate((np.stack((j*w+i,j*w+i+1,(j+1)*w+i),-1),
                        np.stack(((j+1)*w+i+1,(j+1)*w+i,j*w+i+1),-1)))
                    band = puppet.garment_bindings[layer.name][3]
                    candidates = edge & band.movable[triangles].all(1)
                    self.assertTrue(candidates.any())
                    ids = triangles[np.flatnonzero(candidates)[0]]
                    vertices = vertices.copy()
                    flat = vertices.reshape(-1,2)
                    if kind == 'collapse':
                        a,b,_ = ids
                        flat[a] = flat[b]+.001*(flat[a]-flat[b])
                    else:
                        flat[ids] = 2*flat[ids].mean(0)-flat[ids]
                yield layer,vertices
        with mock.patch.object(puppet,'meshes',damaged):
            faults = pc.check_connections(renderer,clip,4,12)
        return faults

    def test_actual_boundary_and_turn_faults_name_part_clip_and_frame_with_zero_seam_drift(self):
        for kind,label in (('collapse','contour'),('reverse','turn')):
            with self.subTest(kind=kind):
                faults = self.injected_faults(kind)
                self.assertTrue(any(f'garment {label}: leg_near: stride frame 2:' in f for f in faults),faults)
                self.assertFalse(any(f.startswith('connection:') or 'frame 0:' in f for f in faults),faults)


if __name__ == '__main__':
    unittest.main()
