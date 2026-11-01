"""Grounded weapons stop on their current side without moving the hand."""
import importlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from dev.tests.test_rig_degeneracy import load_rig


class WeaponContacts(unittest.TestCase):
    def setUp(self):
        self.rig = load_rig("game-sprite-animator")
        self.constraints = importlib.import_module(self.rig.__package__ + ".constraints")
        self.body = self.rig.Body(weapon_front=80, weapon_back=8)

    def clip(self, angle, height=lambda t: 0, loop=False):
        def sample(t):
            p = self.rig.full_pose({"root_y": height(t)})
            sk = self.rig.solve(p, self.body)
            p["wep"] = angle(t) - sk["fa_n"]
            return p
        return SimpleNamespace(name="contact", duration=1, loop=loop, sample=sample,
                               prev=None, next=None, cloth_ref=None, weapon=None,
                               vel=lambda t: (0, 0), tags=set(), layer="full")

    def bake(self, clip):
        self.constraints.bake_weapon_contacts(
            {clip.name: clip}, self.body, self.rig.solve, self.rig.full_pose)

    def test_reference_keeps_both_weapon_ends_above_floor(self):
        clamp = self.constraints.ground_clamp
        for start in (-80, 80, 280, 440):
            previous = start
            for angle in range(-100, 101):
                result = clamp(angle, 10, 30, 12, reference=previous)
                self.assertLess(abs(result - previous), 40)
                cosine = math.cos(math.radians(result))
                self.assertGreaterEqual(10 - 30 * cosine, 2.8 - 1e-8)
                self.assertGreaterEqual(10 + 12 * cosine, 2.8 - 1e-8)
                previous = result

    def test_crossing_zero_stops_without_moving_either_hand(self):
        clip = self.clip(lambda t: -5 + 10 * t)
        original = clip.sample
        self.bake(clip)
        previous = None
        for i in range(481):
            t = i / 480
            sk = self.rig.solve(clip.sample(t), self.body)
            authored = self.rig.solve(original(t), self.body)
            self.assertEqual(sk["wr_n"], authored["wr_n"])
            self.assertEqual(sk["wr_f"], authored["wr_f"])
            self.assertLess(sk["wep_a"], 0)
            if previous is not None:
                self.assertLess(abs(sk["wep_a"] - previous), 1)
            previous = sk["wep_a"]

    def test_lifting_the_grip_releases_contact_without_a_snap(self):
        clip = self.clip(lambda t: -5 + 10 * min(1, t * 3),
                         height=lambda t: max(0, t - 0.5) * 240)
        self.bake(clip)
        values = [self.rig.solve(clip.sample(i / 480), self.body)["wep_a"]
                  for i in range(481)]
        self.assertLess(values[0], 0)
        self.assertAlmostEqual(values[-1], 5)
        self.assertLess(max(abs(b - a) for a, b in zip(values, values[1:])), 5)

    def test_shallow_contact_also_stops_at_zero(self):
        sk = self.rig.solve(self.rig.full_pose({}), self.body)
        self.body.weapon_front = ((sk["weapon_pivot_y"] - self.body.weapon_margin)
                                  / math.cos(math.radians(10)))
        self.body.weapon_back = 0
        clip = self.clip(lambda t: -1 + 2 * t)
        self.bake(clip)
        self.assertLess(self.rig.solve(clip.sample(1), self.body)["wep_a"], 0)

    def test_loop_closes_and_random_access_does_not_change_contact(self):
        clip = self.clip(lambda t: -5 * math.cos(math.tau * t), loop=True)
        self.bake(clip)
        expected = {t: clip.sample(t)["_weapon_angle"] for t in (0, 0.25, 0.5, 0.75, 1)}
        for t in (0.75, 0, 1, 0.5, 0.25):
            self.assertEqual(clip.sample(t)["_weapon_angle"], expected[t])
        self.assertEqual(expected[0], expected[1])
        self.assertTrue(all(a < 0 for a in expected.values()))

    def test_unaffected_clip_is_not_wrapped(self):
        clip = self.clip(lambda t: 90)
        original = clip.sample
        self.bake(clip)
        self.assertIs(clip.sample, original)

    def test_renderer_and_geometry_use_the_same_baked_contact(self):
        mode = Path(self.rig.__file__).resolve().parents[2]
        character = "commando" if "gun_ik" in self.rig.REST else "hero"
        spec = json.loads((mode / f"assets/characters/{character}.json").read_text())
        spec["cloth"] = []
        clip = self.clip(lambda t: -5 + 10 * t, height=lambda t: -15)
        original = clip.sample
        renderer_module = importlib.import_module(self.rig.__package__ + ".render")
        renderer = renderer_module.Renderer(spec, 48, pixel=True, clips={clip.name: clip})
        self.assertTrue(hasattr(clip, "_weapon_source"))
        for t in (0, 0.5, 1):
            sk = self.rig.solve(clip.sample(t), renderer.art.body)
            authored = self.rig.solve(original(t), renderer.art.body)
            self.assertEqual(sk["wr_n"], authored["wr_n"])
            self.assertLess(sk["wep_a"], 0)
            self.assertGreater(renderer.render(clip, t)[..., 3].sum(), 0)


class ShooterWeaponContacts(WeaponContacts):
    def setUp(self):
        self.rig = load_rig("game-shooter-animator")
        self.constraints = importlib.import_module(self.rig.__package__ + ".constraints")
        self.body = self.rig.Body(weapon_front=80, weapon_back=8)

    def test_gun_ik_is_not_overridden_by_a_lower_body_contact(self):
        pose = self.rig.full_pose({"gun_ik": 1, "far_ik": 1, "aim": 45})
        expected = self.rig.solve(pose, self.body)
        actual = self.rig.solve(dict(pose, _weapon_angle=-90), self.body)
        self.assertEqual(actual["wep_a"], expected["wep_a"])
        self.assertEqual(actual["wr_n"], expected["wr_n"])
        self.assertEqual(actual["wr_f"], expected["wr_f"])


if __name__ == "__main__":
    unittest.main()
