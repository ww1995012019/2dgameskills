"""Degenerate IK targets must retain real bone lengths and a stable bend."""
import importlib
import importlib.util
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_rig(mode):
    name = "_degenerate_" + mode.replace("-", "_")
    spec = importlib.util.spec_from_file_location(
        name, ROOT / mode / "scripts/sprite_anim/__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return importlib.import_module(name + ".rig")


class DegenerateIK(unittest.TestCase):
    def test_coincident_targets_keep_both_bone_lengths(self):
        for mode in ("game-sprite-animator", "game-shooter-animator"):
            rig = load_rig(mode)
            for l1, l2 in ((19, 18), (14, 14), (0.02, 0.01)):
                for bend in (-1, 1):
                    with self.subTest(mode=mode, lengths=(l1, l2), bend=bend):
                        root = (7, -3)
                        mid, end = rig.two_bone(root, root, l1, l2, bend)
                        self.assertAlmostEqual(math.dist(root, mid), l1)
                        self.assertAlmostEqual(math.dist(mid, end), l2)

    def test_subprecision_target_noise_does_not_flip_the_limb(self):
        for mode in ("game-sprite-animator", "game-shooter-animator"):
            rig = load_rig(mode)
            for bend in (-1, 1):
                with self.subTest(mode=mode, bend=bend):
                    expected = rig.two_bone((0, 0), (0, 0), 19, 18, bend)
                    for target in ((1e-10, 0), (-1e-10, 0), (0, 1e-10), (0, -1e-10)):
                        actual = rig.two_bone((0, 0), target, 19, 18, bend)
                        for before, after in zip(expected, actual):
                            self.assertLess(math.dist(before, after), 1e-6)

    def test_regular_and_unreachable_targets_keep_lengths(self):
        for mode in ("game-sprite-animator", "game-shooter-animator"):
            rig = load_rig(mode)
            for target in ((3, -20), (0, -100), (0.001, 0)):
                for l1, l2 in ((19, 18), (0.02, 0.01)):
                    with self.subTest(mode=mode, target=target, lengths=(l1, l2)):
                        mid, end = rig.two_bone((0, 0), target, l1, l2, 1)
                        self.assertAlmostEqual(math.dist((0, 0), mid), l1)
                        self.assertAlmostEqual(math.dist(mid, end), l2)


if __name__ == "__main__":
    unittest.main()
