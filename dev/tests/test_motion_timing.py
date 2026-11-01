"""Foot contacts and authored loop timing stay continuous when motion is retimed."""
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_motion(mode):
    # Keep the two standalone sprite_anim packages isolated from each other and
    # from modules imported by other test files in unittest discovery.
    name = "_timing_" + mode.replace("-", "_")
    spec = importlib.util.spec_from_file_location(
        name, ROOT / mode / "scripts/sprite_anim/__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return importlib.import_module(name + ".motions")


class MotionTiming(unittest.TestCase):
    def test_gait_horizontal_velocity_matches_at_both_contacts(self):
        for mode in ("game-sprite-animator", "game-shooter-animator"):
            motions = load_motion(mode)
            for clip in motions.build_clips().values():
                if not isinstance(clip, motions.Gait):
                    continue
                with self.subTest(mode=mode, clip=clip.name):
                    eps = 1e-7
                    x = lambda phase: clip.foot(phase)[0]
                    for boundary in (clip.duty, 1.0):
                        center = x(boundary % 1)
                        before = (center - x(boundary - eps)) / (eps * clip.T)
                        after = (x((boundary + eps) % 1) - center) / (eps * clip.T)
                        self.assertAlmostEqual(before, -clip.speed, delta=0.01)
                        self.assertAlmostEqual(after, -clip.speed, delta=0.01)

    def test_custom_loop_retimes_period_keys_and_events_together(self):
        motions = load_motion("game-sprite-animator")
        for explicit_period in (False, True):
            for speed in (0.8, 1.0, 1.3):
                with self.subTest(explicit_period=explicit_period, speed=speed):
                    spec = {"loop": True,
                            "keys": [(0, {"root_x": 0}),
                                     (0.5, {"root_x": 10}), (1, {"root_x": 0})],
                            "events": [(0.5, "marker")]}
                    if explicit_period:
                        spec["period"] = 1.0
                    clip = motions.build_clips(style={"speed": speed},
                                               custom={"loop_test": spec})["loop_test"]
                    self.assertAlmostEqual(clip.duration, 1 / speed)
                    self.assertAlmostEqual(clip.sample(0.5 / speed)["root_x"], 10)
                    self.assertEqual(clip.events, [(0.5 / speed, "marker")])
                    self.assertAlmostEqual(clip.sample(clip.duration - 1e-7)["root_x"],
                                           clip.sample(0)["root_x"], delta=1e-6)

    def test_explicit_loop_rest_interval_scales_with_speed(self):
        motions = load_motion("game-sprite-animator")
        for speed in (0.8, 1.3):
            with self.subTest(speed=speed):
                clip = motions.build_clips(style={"speed": speed}, custom={
                    "loop_test": {"loop": True, "period": 2,
                                  "keys": [(0, {"root_x": 0}),
                                           (0.5, {"root_x": 10}),
                                           (1, {"root_x": 0})]}})["loop_test"]
                self.assertAlmostEqual(clip.duration, 2 / speed)
                self.assertAlmostEqual(clip.sample(1.5 / speed)["root_x"], 0)


if __name__ == "__main__":
    unittest.main()
