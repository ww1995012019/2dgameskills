"""The experimental data-driven rig preserves bone geometry and motion boundaries."""
import copy
import importlib.util
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = importlib.util.spec_from_file_location("creature_rig", ROOT / "game-animator/scripts/creature_rig.py")
creature_rig = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(creature_rig)
QA = importlib.util.spec_from_file_location("creature_qa_bounds", ROOT / "game-animator/scripts/qa_creature.py")
qa = importlib.util.module_from_spec(QA)
QA.loader.exec_module(qa)


def config():
    return {"motion": {"period": 0.8, "bob": 3, "pitch": 4}, "bones": [
        {"name": "body", "length": 30, "angle": 0, "parent": None, "tags": ["body"]},
        {"name": "wing_near", "length": 20, "angle": -50, "parent": "body", "anchor": "start",
         "offset": [10, 0], "tags": ["wing"], "limits": [-100, 0], "flap_amplitude": 40},
        {"name": "wing_far", "length": 20, "angle": -50, "parent": "body", "anchor": "start",
         "offset": [10, 0], "tags": ["wing"], "limits": [-100, 0], "flap_amplitude": 40},
        {"name": "tip", "length": 13, "angle": 15, "parent": "wing_near", "tags": ["wing"],
         "limits": [-45, 75], "flap_amplitude": 30, "flap_phase": -20},
    ]}


class CreatureRigTests(unittest.TestCase):
    def test_lengths_attachment_and_loops(self):
        rig = creature_rig.CreatureRig(config())
        for action in creature_rig.FLIGHT_ACTIONS:
            for step in range(21):
                pose = rig.pose(0.8 * step / 20, action)
                for name, (a, b, _) in pose.items():
                    self.assertAlmostEqual(math.dist(a, b), rig.bones[name]["length"], places=8)
                self.assertEqual(pose["tip"][0], pose["wing_near"][1])
                self.assertAlmostEqual(pose["wing_near"][2], pose["wing_far"][2], places=8)
            if action in creature_rig.LOOPS:
                first, last = rig.pose(0, action), rig.pose(0.8, action)
                for name in first:
                    self.assertLess(math.dist(first[name][1], last[name][1]), 1e-8)

    def test_wings_move_and_one_shot_ends(self):
        rig = creature_rig.CreatureRig(config())
        self.assertNotAlmostEqual(rig.pose(0, "flap")["wing_near"][2], rig.pose(0.2, "flap")["wing_near"][2])
        self.assertEqual(rig.pose(0.8, "dive"), rig.pose(5, "dive"))
        self.assertNotEqual(rig.pose(0, "fall")["body"][2], rig.pose(0.8, "fall")["body"][2])

    def test_invalid_graph_and_unreachable_motion_rejected(self):
        bad = config()
        bad["bones"][1]["parent"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown parent"):
            creature_rig.CreatureRig(bad)
        bad = config()
        bad["bones"][1]["parent"] = "tip"
        with self.assertRaisesRegex(ValueError, "cycle"):
            creature_rig.CreatureRig(bad)
        bad = config()
        bad["bones"][1]["flap_amplitude"] = 80
        with self.assertRaisesRegex(ValueError, "exceeds joint limits"):
            creature_rig.CreatureRig(bad)
        bad = config()
        bad["bones"][1]["length"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            creature_rig.CreatureRig(bad)

    def test_different_species_need_only_data(self):
        for segments in (1, 2, 3):
            spec = copy.deepcopy(config())
            spec["bones"] = spec["bones"][:3]
            for i in range(segments - 1):
                spec["bones"].append({"name": f"segment_{i}", "parent": "wing_near" if i == 0 else f"segment_{i-1}",
                                      "length": 12 - i, "angle": 5, "flap_amplitude": 12})
            pose = creature_rig.CreatureRig(spec).pose(0.2, "flap")
            self.assertEqual(len(pose), 3 + segments - 1)

    def test_endpoint_speed_bound_covers_valid_motion(self):
        for period, bob, pitch in ((0.4, 0, 0), (0.8, 3, 4), (2.0, -4, 15)):
            spec = config()
            spec["motion"].update(period=period, bob=bob, pitch=pitch)
            rig = creature_rig.CreatureRig(spec)
            bounds = qa.speed_bounds(rig.bones, rig.motion)
            for action in creature_rig.FLIGHT_ACTIONS:
                for i in range(25):
                    a, b = rig.pose(period * i / 25, action), rig.pose(period * (i + 1) / 25, action)
                    for name in rig.bones:
                        self.assertLessEqual(math.dist(a[name][1], b[name][1]), bounds[name][1] * period / 25 + 1e-8)


if __name__ == "__main__":
    unittest.main()
