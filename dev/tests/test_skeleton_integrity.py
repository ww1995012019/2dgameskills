"""Is the skeleton really in the picture? Fault injection for the pixel checks behind it.

A real character passed every check with its upper arm gone and a scrap of sleeve floating beside
it: the joint numbers were perfect and the torso hid the hole. So each fault here breaks the art,
not the numbers, and the check must name the part, or the clip and frame.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPRITE = os.path.join(ROOT, "game-sprite-animator")
SHOOTER = os.path.join(ROOT, "game-shooter-animator")
TOPDOWN = os.path.join(ROOT, "game-topdown-animator")
QUADRUPED = os.path.join(ROOT, "game-quadruped-animator")
CREATURE = os.path.join(ROOT, "game-animator")
DEMO = os.path.join(SPRITE, "assets", "characters", "cutout_demo")
sys.path.insert(0, os.path.join(SPRITE, "scripts"))

import cut_parts  # noqa: E402
from sprite_anim.integrity import components, empty_bones, floating_pieces, islands, strip_gap  # noqa: E402
from sprite_anim.part_check import check_parts  # noqa: E402
from sprite_anim.rig import Body  # noqa: E402

TMP = None


def setUpModule():
    global TMP
    TMP = tempfile.mkdtemp(prefix="skeleton_")


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def read_json(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def demo_copy(name):
    d = os.path.join(TMP, name)
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(DEMO, d)
    spec = read_json(os.path.join(d, "character.json"))
    spec["_dir"] = d
    return d, spec


def problems(spec):
    return check_parts(spec, Body.from_spec(spec.get("body")))


def edit_alpha(d, spec, part, change):
    path = os.path.join(d, spec["parts"][part]["image"])
    a = np.asarray(Image.open(path).convert("RGBA")).copy()
    change(a)
    Image.fromarray(a, "RGBA").save(path)


def paste_blob(path, x, y, r=6):
    a = np.asarray(Image.open(path).convert("RGBA")).copy()
    a[y - r:y + r, x - r:x + r] = (255, 0, 255, 255)
    Image.fromarray(a, "RGBA").save(path)


def qa(script, out):
    p = subprocess.run([sys.executable, script, out], capture_output=True, text=True)
    with open(os.path.join(out, "qa_report.json"), encoding="utf-8") as fh:
        return p, json.load(fh)


class TestPixels(unittest.TestCase):
    def test_components_join_diagonals(self):
        m = np.zeros((6, 6), bool)
        m[1, 1] = m[2, 2] = True
        m[4, 5] = True
        self.assertEqual(len(np.unique(components(m))) - 1, 2)

    def test_floating_piece_found_and_hairline_ignored(self):
        a = np.zeros((100, 100), np.uint8)
        a[20:80, 30:60] = 255
        self.assertEqual(floating_pieces(a, 1.5), [])
        hair = a.copy()
        hair[40:50, 61:66] = 255      # 1 px gap: two parts barely apart, not a floater
        self.assertEqual(floating_pieces(hair, 1.5), [])
        a[40:50, 75:85] = 255
        pieces = floating_pieces(a, 1.5)
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0][1:], (79, 44))

    def test_specks_and_soft_shadows_are_not_floaters(self):
        a = np.zeros((100, 100), np.uint8)
        a[20:80, 30:60] = 255
        a[5, 5] = 255                 # antialiasing crumb
        a[90:96, 70:90] = 65          # a contact shadow's alpha
        self.assertEqual(floating_pieces(a, 1.5), [])

    def test_bone_with_nothing_on_it(self):
        a = np.zeros((100, 100), np.uint8)
        a[10:90, 48:52] = 255
        skeleton = {"a": [[50, 10]], "b": [[50, 90]]}
        self.assertEqual(empty_bones(a, skeleton, [("a", "b")], 1.0, 0), [])
        a[30:60, 48:52] = 0
        found = empty_bones(a, skeleton, [("a", "b")], 1.0, 0)
        self.assertEqual(found[0][0], "a->b")
        self.assertGreater(found[0][1], 0.3)

    def test_strip_gap_measures_the_hole(self):
        m = np.zeros((100, 40), bool)
        m[:, 18:22] = True
        self.assertEqual(strip_gap(m, (20, 0), (0.0, 1.0), 100, 3), 0)
        m[30:60] = False
        self.assertAlmostEqual(strip_gap(m, (20, 0), (0.0, 1.0), 100, 3), 0.3, places=2)

    def test_islands_respect_a_bridge(self):
        m = np.zeros((60, 20), bool)
        m[:30, 8:12] = True
        m[40:50, 8:12] = True
        self.assertEqual(len(islands(m)), 1)
        bridge = np.zeros_like(m)
        bridge[29:41, 8:12] = True
        self.assertEqual(islands(m, bridge), [])


class TestParts(unittest.TestCase):
    def test_demo_parts_are_whole(self):
        _, spec = demo_copy("clean")
        self.assertEqual(problems(spec), [])

    def test_missing_part(self):
        _, spec = demo_copy("missing")
        del spec["parts"]["arm_n_lo"]
        self.assertTrue(any(p.startswith("arm_n_lo: part is missing") for p in problems(spec)))

    def test_missing_weapon_only_counts_when_it_has_one(self):
        _, spec = demo_copy("noweapon")
        del spec["parts"]["weapon"]
        self.assertTrue(any(p.startswith("weapon: part is missing") for p in problems(spec)))
        spec["weapon"] = "none"
        self.assertEqual(problems(spec), [])

    def test_missing_file(self):
        d, spec = demo_copy("nofile")
        os.remove(os.path.join(d, spec["parts"]["leg_n_lo"]["image"]))
        self.assertTrue(any("not found" in p for p in problems(spec)))

    def test_empty_image(self):
        d, spec = demo_copy("empty")
        edit_alpha(d, spec, "torso", lambda a: a.__setitem__((..., 3), 0))
        self.assertTrue(any(p.startswith("torso: image is empty") for p in problems(spec)))

    def test_limb_with_its_middle_gone(self):
        # What the broken cut left: both joint caps, nothing between them, so a loose piece too.
        d, spec = demo_copy("broken")
        pivot, ppu = spec["parts"]["arm_n_up"]["pivot"], spec["px_per_unit"]
        span = spec["body"]["up_arm"] * ppu

        def cut_middle(a):
            a[int(pivot[1] + span * 0.3):int(pivot[1] + span * 0.75), :, 3] = 0

        edit_alpha(d, spec, "arm_n_up", cut_middle)
        found = [p for p in problems(spec) if p.startswith("arm_n_up")]
        self.assertTrue(any("has no art" in p for p in found), found)
        self.assertTrue(any("cut off from the part" in p for p in found), found)

    def test_loose_piece_in_a_part(self):
        d, spec = demo_copy("loose")
        path = os.path.join(d, spec["parts"]["torso"]["image"])
        im = Image.open(path).convert("RGBA")
        wide = Image.new("RGBA", (im.width + 30, im.height))
        wide.paste(im)
        wide.save(path)
        paste_blob(path, im.width + 20, im.height // 2, 4)
        self.assertTrue(any(p.startswith("torso:") and "cut off" in p for p in problems(spec)))

    def test_pivot_off_the_art(self):
        _, spec = demo_copy("pivot")
        spec["parts"]["hand_n"]["pivot"] = [-200, -200]
        self.assertTrue(any(p.startswith("hand_n: no art at its pivot") for p in problems(spec)))

    def test_shortened_weapon(self):
        d, spec = demo_copy("short")
        pivot = spec["parts"]["weapon"]["pivot"]

        def cut_tip(a):
            a[:int(pivot[1] - spec["parts"]["weapon"]["length"] * spec["px_per_unit"] * 0.6), :, 3] = 0

        edit_alpha(d, spec, "weapon", cut_tip)
        self.assertTrue(any(p.startswith("weapon:") and "has no art" in p for p in problems(spec)))

    def test_part_scale_changes_the_span(self):
        # A part drawn at scale 0.5 has twice the image pixels per rig unit.
        _, spec = demo_copy("scale")
        spec["parts"]["arm_n_up"]["scale"] = 0.5
        self.assertTrue(any(p.startswith("arm_n_up") and "has no art" in p for p in problems(spec)))

    def test_check_command_fails_on_a_broken_part(self):
        d, spec = demo_copy("command")
        os.remove(os.path.join(d, spec["parts"]["arm_n_up"]["image"]))
        p = subprocess.run([sys.executable, os.path.join(SPRITE, "scripts", "cut_parts.py"), "check", "--character",
                            os.path.join(d, "character.json")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("arm_n_up", p.stdout)


class TestCutter(unittest.TestCase):
    """The three cutter faults behind the swordsman, each on the demo picture."""

    @classmethod
    def setUpClass(cls):
        cls.img = Image.open(os.path.join(DEMO, "source.png")).convert("RGBA")
        cls.joints = read_json(os.path.join(DEMO, "joints.json"))

    def cut(self, img, joints):
        parts, spec, report, _, _ = cut_parts.cut(img, joints, {})
        out = os.path.join(TMP, "cut_" + self.id().rsplit(".", 1)[-1])
        os.makedirs(os.path.join(out, "parts"), exist_ok=True)
        for n, (im, _) in parts.items():
            im.save(os.path.join(out, "parts", n + ".png"))
        spec["_dir"] = out
        return spec

    def test_limb_lying_on_the_body_keeps_its_middle(self):
        # With no pixels of its own the part has no colours to compare, and it used to lose
        # everything to any neighbour: a limb reduced to its two joint caps.
        joints = dict(self.joints)
        joints["sh_n"], joints["el_n"] = joints["neck"], joints["waist"]
        spec = self.cut(self.img, joints)
        self.assertFalse([p for p in problems(spec) if p.startswith("arm_n_up") and "has no art" in p])

    def test_long_blade_survives_being_turned_upright(self):
        # Grip near the top of a picture wider than it is tall: upright, the blade leaves the canvas.
        w, h = self.img.size
        pic = Image.new("RGBA", (w * 3, h))
        pic.paste(self.img)
        joints = dict(self.joints)
        gx, gy = joints["weapon_grip"]
        joints["weapon_tip"] = [gx + w * 2, gy]
        a = np.asarray(pic).copy()
        y0, x0 = int(gy) - 3, int(gx)
        a[y0:y0 + 6, x0:x0 + w * 2] = (200, 220, 255, 255)
        spec = self.cut(Image.fromarray(a, "RGBA"), joints)
        self.assertFalse([p for p in problems(spec) if p.startswith("weapon") and "has no art" in p])

    def test_scrap_behind_the_grip_stays_out_of_the_weapon(self):
        # The capsule runs back past the fist; a scrap there is inside it but not part of the blade.
        gx, gy = self.joints["weapon_grip"]
        tx, ty = self.joints["weapon_tip"]
        back = (gx - (tx - gx) * 0.25, gy - (ty - gy) * 0.25)
        a = np.asarray(self.img).copy()
        x, y = int(back[0]), int(back[1])
        a[y - 3:y + 3, x - 3:x + 3] = (0, 255, 0, 255)
        ppu = self.joints and cut_parts.cut(self.img, self.joints, {})[1]["px_per_unit"]
        self.assertGreater(np.hypot(back[0] - gx, back[1] - gy) / ppu, cut_parts.GRIP_REACH + 2)
        spec = self.cut(Image.fromarray(a, "RGBA"), self.joints)
        self.assertFalse([p for p in problems(spec) if p.startswith("weapon") and "cut off" in p])


class TestWeaponReach(unittest.TestCase):
    def test_framing_sees_a_cut_weapon_at_its_real_length(self):
        # A long spear used to be framed at the drawn spear's fixed reach, so its tip left the frame.
        from sprite_anim.art import CharacterArt
        from sprite_anim.mathx import add, scale
        from sprite_anim.motions import build_clips
        from sprite_anim.rig import full_pose, solve
        from sprite_anim.art import hand_grip
        d, spec = demo_copy("reach")
        spec["weapon"] = "spear"
        spec["parts"]["weapon"]["length"] = 90.0
        art = CharacterArt(spec)
        self.assertEqual(art.body.weapon_front, 90.0)
        sk = solve(full_pose(build_clips(None, None)["idle"].sample(0.0)), art.body)
        tip = art.blade_points(sk)[1]
        want = add(hand_grip(sk), scale(sk["wep_dir"], 90.0))
        self.assertAlmostEqual(tip[0], want[0], places=6)
        self.assertAlmostEqual(tip[1], want[1], places=6)

    def test_procedural_weapon_keeps_its_fixed_reach(self):
        from sprite_anim.art import CharacterArt, WEAPON_REACH, WEAPON_GRIP
        art = CharacterArt({"weapon": "spear"})
        self.assertEqual(art.body.weapon_front, WEAPON_REACH["spear"][0] - WEAPON_GRIP["spear"])


class TestSpriteQa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = os.path.join(TMP, "hero")
        subprocess.run([sys.executable, os.path.join(SPRITE, "scripts", "generate.py"), "--character",
                        os.path.join(SPRITE, "assets", "characters", "hero.json"), "--preset", "pixel", "--clips",
                        "idle,run,attack_1", "--no-fx", "--out", cls.base], check=True, capture_output=True)

    def setUp(self):
        self.d = os.path.join(TMP, "s_" + self.id().rsplit(".", 1)[-1])
        shutil.rmtree(self.d, ignore_errors=True)
        shutil.copytree(self.base, self.d)
        self.script = os.path.join(SPRITE, "scripts", "qa_motion.py")

    def test_clean_set_passes(self):
        p, report = qa(self.script, self.d)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(report["clips"]["run"]["float"], "PASS")
        self.assertEqual(report["clips"]["run"]["bones"], "PASS")
        self.assertEqual(report["parts"]["status"], "PASS")

    def test_floating_scrap(self):
        paste_blob(os.path.join(self.d, "frames", "run", "run_003.png"), 8, 8, 2)
        p, report = qa(self.script, self.d)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(report["clips"]["run"]["float"], "FAIL")
        self.assertTrue(any("floating" in m for m in report["clips"]["run"]["flags"]["3"]))

    def test_limb_erased_from_a_frame(self):
        trace = read_json(os.path.join(self.d, "rig_trace.json"))["traces"]["idle"]["skeleton"]
        path = os.path.join(self.d, "frames", "idle", "idle_002.png")
        a = np.asarray(Image.open(path).convert("RGBA")).copy()
        a[int(trace["hip_n"][2][1]):, :, 3] = 0          # both legs gone below the hips
        Image.fromarray(a, "RGBA").save(path)
        p, report = qa(self.script, self.d)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(report["clips"]["idle"]["bones"], "FAIL")
        self.assertTrue(any("kn_n->an_n" in m for m in report["clips"]["idle"]["flags"]["2"]))

    def test_smear_frames_may_leave_the_blade(self):
        trace = read_json(os.path.join(self.d, "rig_trace.json"))["traces"]["attack_1"]
        frame = trace["smear"].index(True)
        paste_blob(os.path.join(self.d, "frames", "attack_1", f"attack_1_{frame:03d}.png"), 8, 8, 2)
        _, report = qa(self.script, self.d)
        self.assertEqual(report["clips"]["attack_1"]["float"], "PASS")

    def test_old_trace_reports_na_not_pass(self):
        path = os.path.join(self.d, "rig_trace.json")
        trace = read_json(path)
        for tr in trace["traces"].values():
            del tr["skeleton"], tr["smear"]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(trace, fh)
        _, report = qa(self.script, self.d)
        self.assertEqual(report["clips"]["run"]["bones"], "n/a")
        self.assertEqual(report["clips"]["run"]["float"], "n/a")

    def test_broken_part_fails_the_whole_set(self):
        d, spec = demo_copy("qa_part")
        os.remove(os.path.join(d, spec["parts"]["arm_n_lo"]["image"]))
        del spec["parts"]["arm_n_lo"]
        spec.pop("_dir")
        with open(os.path.join(d, "character.json"), "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        out = os.path.join(d, "set")
        subprocess.run([sys.executable, os.path.join(SPRITE, "scripts", "generate.py"), "--character",
                        os.path.join(d, "character.json"), "--preset", "pixel", "--clips", "idle", "--no-fx",
                        "--out", out], check=True, capture_output=True)
        p, report = qa(self.script, out)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(report["parts"]["status"], "FAIL")
        self.assertTrue(any("arm_n_lo" in m for m in report["parts"]["problems"]))


class TestOtherModes(unittest.TestCase):
    def test_shooter(self):
        out = os.path.join(TMP, "commando")
        subprocess.run([sys.executable, os.path.join(SHOOTER, "scripts", "generate.py"), "--character",
                        os.path.join(SHOOTER, "assets", "characters", "commando.json"), "--preset", "pixel", "--clips",
                        "idle,walk,rifle_aim_0", "--out", out], check=True, capture_output=True)
        script = os.path.join(SHOOTER, "scripts", "qa_motion.py")
        p, report = qa(script, out)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(report["clips"]["walk"]["bones"], "PASS")     # legs only, by layer
        paste_blob(os.path.join(out, "frames", "walk", "walk_002.png"), 6, 6, 2)
        p, report = qa(script, out)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(report["clips"]["walk"]["float"], "FAIL")
        self.assertTrue(any("floating" in m for m in report["clips"]["walk"]["flags"]["2"]))

    @unittest.expectedFailure
    def test_shooter_scrap_during_a_reload(self):
        # Known gap: fire and action clips throw casings and magazines clear of the body, and the
        # check can't tell those from a broken scrap, so such clips report float n/a.
        out = os.path.join(TMP, "commando_reload")
        subprocess.run([sys.executable, os.path.join(SHOOTER, "scripts", "generate.py"), "--character",
                        os.path.join(SHOOTER, "assets", "characters", "commando.json"), "--preset", "pixel", "--clips",
                        "rifle_reload", "--out", out], check=True, capture_output=True)
        paste_blob(os.path.join(out, "frames", "rifle_reload", "rifle_reload_002.png"), 6, 6, 2)
        _, report = qa(os.path.join(SHOOTER, "scripts", "qa_motion.py"), out)
        self.assertEqual(report["clips"]["rifle_reload"]["float"], "FAIL")

    def test_topdown(self):
        out = os.path.join(TMP, "topdown")
        subprocess.run([sys.executable, os.path.join(TOPDOWN, "scripts", "generate.py"), "--out", out], check=True, capture_output=True)
        script = os.path.join(TOPDOWN, "scripts", "qa_motion.py")
        p, report = qa(script, out)
        self.assertEqual(p.returncode, 0, p.stdout)     # includes the soft foot shadows
        paste_blob(os.path.join(out, "frames", "walk_up", "walk_up_001.png"), 8, 8, 7)
        p, report = qa(script, out)
        self.assertEqual(report["clips"]["walk_up"]["float"], "FAIL")
        self.assertTrue(any("floating" in m for m in report["clips"]["walk_up"]["flags"]["1"]))

    def test_quadruped(self):
        out = os.path.join(TMP, "wolf")
        subprocess.run([sys.executable, os.path.join(QUADRUPED, "scripts", "generate.py"), "--out", out], check=True, capture_output=True)
        script = os.path.join(QUADRUPED, "scripts", "qa_motion.py")
        p, report = qa(script, out)
        self.assertEqual(p.returncode, 0, p.stdout)
        path = os.path.join(out, "frames", "walk", "walk_001.png")
        a = np.asarray(Image.open(path).convert("RGBA")).copy()
        pivot = read_json(os.path.join(out, "animations.json"))["pivot"]
        a[pivot[1] - round(a.shape[0] * 0.13):, :, 3] = 0     # every leg gone below the knee
        Image.fromarray(a, "RGBA").save(path)
        p, report = qa(script, out)
        self.assertEqual(report["clips"]["walk"]["bones"], "FAIL")
        self.assertTrue(any("nothing drawn" in m for m in report["clips"]["walk"]["flags"]["1"]))

    def creature(self, name, change=None):
        spec = read_json(os.path.join(CREATURE, "assets", "creatures", "flight_example.json"))
        d = os.path.join(TMP, name)
        os.makedirs(d, exist_ok=True)
        if change:
            change(spec, d)
        config = os.path.join(d, "creature.json")
        with open(config, "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        out = os.path.join(d, "set")
        subprocess.run([sys.executable, os.path.join(CREATURE, "scripts", "generate_creature.py"), "--config", config, "--out", out],
                       check=True, capture_output=True)
        return out

    def test_creature_frames(self):
        out = self.creature("creature_ok")
        script = os.path.join(CREATURE, "scripts", "qa_creature.py")
        p, report = qa(script, out)
        self.assertEqual(p.returncode, 0, p.stdout)
        clip = next(iter(report["clips"]))
        paste_blob(os.path.join(out, "frames", clip, f"{clip}_001.png"), 8, 8, 4)
        p, report = qa(script, out)
        self.assertEqual(p.returncode, 1)
        self.assertTrue(any("floating" in m for m in report["clips"][clip]["flags"]["1"]))

    def test_creature_png_part_with_a_hole(self):
        def broken(spec, d):
            bone = next(b for b in spec["bones"] if b["name"] == "wing_near")
            ppu = 4.0
            a = np.zeros((40, int(bone["length"] * ppu) + 20, 4), np.uint8)
            a[14:26, 5:] = (120, 160, 180, 255)
            a[14:26, 30:75] = 0
            Image.fromarray(a, "RGBA").save(os.path.join(d, "wing.png"))
            spec["parts"]["wing_near"] = {"image": "wing.png", "pivot": [5, 20], "pixels_per_unit": ppu}

        out = self.creature("creature_broken", broken)
        p, report = qa(os.path.join(CREATURE, "scripts", "qa_creature.py"), out)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(report["parts"]["status"], "FAIL")
        self.assertTrue(any(m.startswith("wing_near") and "has no art" in m for m in report["parts"]["problems"]))


if __name__ == "__main__":
    unittest.main()
