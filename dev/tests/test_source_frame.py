"""A supplied bent drawing must not be deformed simply by binding it."""
import math
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
from sprite_anim.puppet import Layer, blur, untangle, EASE_PASSES


class SourceFrame(unittest.TestCase):
    def layer(self, root, points, offset=(0, 0), enabled=True):
        image = Image.new('RGBA', (180, 180))
        draw = ImageDraw.Draw(image)
        draw.line([tuple(p) for p in points], fill=(170, 50, 80, 255), width=35)
        for x, y in points:
            draw.ellipse((x-16, y-16, x+16, y+16), fill=(170, 50, 80, 255))
        image.save(Path(root) / 'limb.png')
        return Layer('limb', dict(kind='tube', image='limb.png', radius=20,
                     offset=list(offset), rest=(np.array(points)+offset).tolist(),
                     source_frame=enabled), root)

    def test_unchanged_pose_retains_source_vertices_including_offset_and_relaxation(self):
        with tempfile.TemporaryDirectory() as root:
            for points in ([[40,20],[50,90],[130,130]], [[60,20],[95,90],[50,150]],
                           [[90,15],[60,90],[95,155]], [[70,15],[70,90],[70,155]]):
                for offset in ((0,0), (231,417)):
                    layer = self.layer(root, points, offset)
                    expected = np.stack([layer.vx+offset[0], layer.vy+offset[1]], -1)
                    actual = layer.mapped(layer.rest, 1.)
                    np.testing.assert_allclose(actual, expected, atol=1e-8)
                    actual = untangle(blur(actual, EASE_PASSES), layer.cells)
                    np.testing.assert_allclose(actual, expected, atol=1e-8)

    def test_rigid_rotation_translation_and_scale_preserve_source_shape(self):
        with tempfile.TemporaryDirectory() as root:
            layer = self.layer(root, [[40,20],[50,90],[130,130]], (231,417))
            source = np.stack([layer.vx+layer.offset[0], layer.vy+layer.offset[1]], -1)
            for angle in (-2.8, -.7, 0, 1.8):
                r = np.array([[math.cos(angle),-math.sin(angle)],
                              [math.sin(angle),math.cos(angle)]])
                for scale in (.3, 1, 2.7):
                    points = np.asarray(layer.rest) @ r.T * scale + [21,-13]
                    expected = source @ r.T * scale + [21,-13]
                    actual = layer.mapped(points, scale)
                    np.testing.assert_allclose(actual, expected, atol=1e-7)
                    np.testing.assert_array_equal(layer.mapped(points, scale, layer.used), actual[layer.used])

    def test_degenerate_source_chain_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, 'consecutive joints distinct'):
                self.layer(root, [[40,20],[40,20],[130,130]])

    def test_old_binding_exposes_the_fault_and_remains_opt_in(self):
        with tempfile.TemporaryDirectory() as root:
            layer = self.layer(root, [[40,20],[50,90],[130,130]], enabled=False)
            source = np.stack([layer.vx, layer.vy], -1)
            self.assertGreater(np.linalg.norm(layer.mapped(layer.rest,1)-source,axis=-1)[layer.used].max(), 5)
            self.assertFalse(layer.source_frame)

    def test_new_bending_still_moves_and_compresses_the_inside(self):
        with tempfile.TemporaryDirectory() as root:
            layer = self.layer(root, [[60,20],[60,90],[60,155]])
            target = [np.array(p,dtype=float) for p in [[60,20],[60,90],[115,120]]]
            actual = layer.mapped(target,1.)
            self.assertTrue(np.isfinite(actual).all())
            self.assertGreater(np.linalg.norm(actual-np.stack([layer.vx,layer.vy],-1),axis=-1).max(), 10)


if __name__ == '__main__': unittest.main()
