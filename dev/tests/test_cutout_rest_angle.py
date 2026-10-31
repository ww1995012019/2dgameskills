"""Check that source-art orientation is compensated at the joint."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "game-sprite-animator" / "scripts"))
from sprite_anim.art import Canvas, Cutout


class CutoutRestAngle(unittest.TestCase):
    def test_rightward_source_points_down_on_downward_bone(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGBA", (21, 21))
            for x in range(10, 19):
                image.putpixel((x, 10), (255, 0, 0, 255))
            image.save(Path(directory) / "arm.png")
            spec = {"_dir": directory, "px_per_unit": 1, "parts": {
                "arm_f_up": {"image": "arm.png", "pivot": [10, 10], "rest_angle": -90}}}
            canvas = Canvas(64, 1, 1, 0.5, 0, False, (0, 0, 0))
            Cutout(spec).draw(canvas, {"sh_f": (0, 0), "el_f": (0, -10)}, {}, None)
            y, x = np.nonzero(canvas.buf[:, :, 3])
            self.assertGreater(y.max(), 37)
            self.assertLess(abs(x.mean() - 32), 2)


if __name__ == "__main__":
    unittest.main()
