"""Render and rotate user-supplied parts at their configured joint pivots."""
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "game-animator/scripts"))
from creature_render import CreatureRenderer
from creature_rig import CreatureRig


class CreatureRenderTests(unittest.TestCase):
    def test_image_rotates_about_joint_and_stays_transparent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.png"
            image = Image.new("RGBA", (12, 6))
            for x in range(2, 10):
                image.putpixel((x, 2), (255, 30, 10, 255))
            image.save(path)
            spec = {"bones": [{"name": "wing", "parent": None, "length": 8, "angle": 90}],
                    "view": {"units": 120}, "parts": {"wing": {"image": "part.png", "pivot": [2, 2], "pixels_per_unit": 1}}}
            rig = CreatureRig(spec)
            image = CreatureRenderer(rig, spec, directory, 120).render(rig.pose(0, "glide"))
            bbox = image.getchannel("A").getbbox()
            self.assertIsNotNone(bbox)
            self.assertGreater(bbox[3] - bbox[1], 5)
            self.assertLess(bbox[2] - bbox[0], 4)
            self.assertLessEqual(bbox[1], 61)
            self.assertGreaterEqual(bbox[3], 67)
            self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_draw_order_and_invalid_parts(self):
        spec = {"bones": [{"name": "body", "parent": None, "length": 10},
                          {"name": "overlay", "parent": "body", "anchor": "start", "length": 10}],
                "view": {"units": 120}, "parts": {"body": {"color": "red", "width": 4},
                                                           "overlay": {"color": "blue", "width": 4}},
                "draw_order": ["body", "overlay"]}
        rig = CreatureRig(spec)
        image = CreatureRenderer(rig, spec, ".", 120).render(rig.pose(0, "glide"))
        self.assertEqual(image.getpixel((65, 60))[:3], (0, 0, 255))
        spec["draw_order"] = ["body", "body"]
        with self.assertRaisesRegex(ValueError, "draw_order"):
            CreatureRenderer(rig, spec, ".", 120)


if __name__ == "__main__":
    unittest.main()
