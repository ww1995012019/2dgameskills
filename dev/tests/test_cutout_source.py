"""Cut-out parts held against the picture they were cut from.

Found on a real AI picture: a limb's round cap was filled past the silhouette with dark stripes of
stretched outline, and the head's cap copied half the face into the torso. Both parts were whole and
connected, so the frame and part checks passed them. These tests lay parts back on the source.
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
SKILL = os.path.join(ROOT, "game-sprite-animator")
SCRIPTS = os.path.join(SKILL, "scripts")
HERO = os.path.join(SKILL, "assets", "characters", "hero.json")
DEMO = os.path.join(SKILL, "assets", "characters", "cutout_demo")
sys.path.insert(0, SCRIPTS)

import cut_parts  # noqa: E402
import visual_review  # noqa: E402
from sprite_anim.part_check import check_source, in_picture  # noqa: E402


def read_json(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def thin_limbs(img, joints):
    """A slim character: marks stay, but legs narrower than the rig's default radius, as on a
    long-legged AI picture, so a cap sized for the rig reaches past the art."""
    a = np.asarray(img).copy()
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    keep_y = min(joints["hip_n"][1], joints["hip_f"][1])
    # Distance to the nearest leg bone, so slimming one bone leaves the others' art alone.
    d = np.min([cut_parts.seg_dist(xx, yy, tuple(joints[s]), tuple(joints[e]))
                for side in "nf" for s, e in ((f"hip_{side}", f"kn_{side}"), (f"kn_{side}", f"an_{side}"))], axis=0)
    above_ankle = yy < max(joints["an_n"][1], joints["an_f"][1])
    # 3 px against a cap of about 10: thin enough that the old cap's overhang is over the check's 3%.
    a[(d > 3) & (yy > keep_y) & above_ankle, 3] = 0
    return Image.fromarray(a, "RGBA")


def small_head(img, joints, share=0.34):
    """The same body with the head redrawn smaller, sitting on the same neck."""
    bx, by = joints["head_base"]
    tx, ty = joints["head_top"]
    h = img.height
    y_cut = int(by)
    head = img.crop((0, 0, img.width, y_cut))
    small = head.resize((max(1, round(head.width * share)), max(1, round(head.height * share))), Image.LANCZOS)
    out = img.copy()
    out.paste((0, 0, 0, 0), (0, 0, img.width, y_cut))
    x = round(bx - bx * share)
    y = y_cut - small.height
    out.alpha_composite(small, (x, y))
    j = dict(joints, head_top=[bx + (tx - bx) * share, by + (ty - by) * share])
    assert y >= 0 and y + small.height <= h
    return out, j


class SourceCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="cutout_source_")
        cls.img, _, cls.joints = cut_parts.template(read_json(HERO), 512)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def cut(self, name, img=None, joints=None):
        out = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(out, "parts"), exist_ok=True)
        img = img or self.img
        parts, spec, report, _, _ = cut_parts.cut(img, joints or self.joints, read_json(HERO))
        for n, (im, _) in parts.items():
            im.save(os.path.join(out, "parts", n + ".png"))
        img.convert("RGBA").save(os.path.join(out, spec["source_image"]))
        with open(os.path.join(out, "character.json"), "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        spec["_dir"] = out
        return spec, report


class TestCutStaysOnThePicture(SourceCase):
    def test_every_part_lands_where_it_was_cut(self):
        spec, _ = self.cut("place")
        im = Image.open(os.path.join(spec["_dir"], "parts", "torso.png")).convert("RGBA")
        part = spec["parts"]["torso"]
        back = in_picture(im.getchannel("A"), part["pivot"], part["from"], self.img.size)
        src = np.asarray(self.img)[..., 3] > 24
        self.assertGreater((back & src).sum() / back.sum(), 0.97)

    def test_a_clean_cut_passes(self):
        self.assertEqual(check_source(self.cut("clean")[0]), [])

    def test_slim_limbs_get_no_invented_pixels(self):
        # The cap must not paint past the silhouette, however much narrower the art is than the rig.
        spec, _ = self.cut("slim", thin_limbs(self.img, self.joints))
        self.assertEqual([p for p in check_source(spec) if "not in the source" in p], [])

    def test_a_slim_limb_is_told_which_radius_to_use(self):
        _, report = self.cut("slimwarn", thin_limbs(self.img, self.joints))
        self.assertTrue(any("_radius" in w and "leg_n_lo" in w for w in report["warnings"]), report["warnings"])

    def test_the_default_proportions_get_no_radius_advice(self):
        _, report = self.cut("defaultwarn")
        self.assertEqual([w for w in report["warnings"] if "_radius" in w], [])

    def test_head_is_not_copied_into_the_torso(self):
        # The cap's size came from the legs' scale, so a real-proportioned head was small next to
        # it. The fixture redraws the hero's head at a third of its size, on the same neck.
        img, joints = small_head(self.img, self.joints)
        spec, _ = self.cut("smallhead", img, joints)
        self.assertEqual([p for p in check_source(spec) if "second face" in p], [])


class TestSourceFaults(SourceCase):
    """Fault injection: each check must catch a planted problem and name the part."""

    def test_painted_past_the_silhouette_is_caught(self):
        spec, _ = self.cut("painted")
        path = os.path.join(spec["_dir"], "parts", "leg_n_lo.png")
        im = Image.open(path).convert("RGBA")
        pad = 60
        wide = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad))
        wide.paste(im, (pad, pad))
        a = np.asarray(wide).copy()
        a[pad:pad + 50, :pad - 4] = (90, 40, 30, 255)
        Image.fromarray(a, "RGBA").save(path)
        p = spec["parts"]["leg_n_lo"]["pivot"]
        spec["parts"]["leg_n_lo"]["pivot"] = [p[0] + pad, p[1] + pad]
        found = check_source(spec)
        self.assertTrue(any(m.startswith("leg_n_lo:") and "not in the source" in m for m in found), found)

    def test_second_face_is_caught(self):
        spec, _ = self.cut("twoface")
        head = spec["parts"]["head"]
        torso = spec["parts"]["torso"]
        im = Image.open(os.path.join(spec["_dir"], "parts", "head.png")).convert("RGBA")
        back = in_picture(im.getchannel("A"), head["pivot"], head["from"], self.img.size)
        t_path = os.path.join(spec["_dir"], "parts", "torso.png")
        t = Image.open(t_path).convert("RGBA")
        # Rebuild the torso image with the head's pixels added, in the torso's own turned frame.
        w, h = self.img.size
        margin = 700
        roomy = Image.new("RGBA", (w + 2 * margin, h + 2 * margin))
        full = np.zeros((h, w, 4), np.uint8)
        full[back] = (200, 170, 150, 255)
        roomy.paste(Image.fromarray(full, "RGBA"), (margin, margin))
        centre = (torso["from"]["pivot"][0] + margin, torso["from"]["pivot"][1] + margin)
        turned = roomy.rotate(torso["from"]["angle"], center=centre)
        turned.alpha_composite(t, (round(centre[0] - torso["pivot"][0]), round(centre[1] - torso["pivot"][1])))
        box = turned.getbbox()
        turned.crop(box).save(t_path)
        torso["pivot"] = [centre[0] - box[0], centre[1] - box[1]]
        found = check_source(spec)
        self.assertTrue(any(m.startswith("torso:") and "second face" in m for m in found), found)

    def test_a_rig_without_a_source_is_skipped_not_passed_by_accident(self):
        spec, _ = self.cut("nosource")
        os.remove(os.path.join(spec["_dir"], spec["source_image"]))
        self.assertEqual(check_source(spec), [])


class TestBindReachesQA(unittest.TestCase):
    """A set must not read 0 FAIL, 0 WARN while the cut's report says otherwise."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="cutout_bind_")
        cls.rig = os.path.join(cls.tmp, "rig")
        shutil.copytree(DEMO, cls.rig)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_qa(self, report):
        with open(os.path.join(self.rig, "bind_report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh)
        out = os.path.join(self.tmp, "set")
        shutil.rmtree(out, ignore_errors=True)
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "generate.py"), "--character",
                        os.path.join(self.rig, "character.json"), "--preset", "pixel", "--clips", "idle,walk",
                        "--no-fx", "--out", out], check=True, capture_output=True)
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "qa_motion.py"), out], capture_output=True, text=True)
        return p, read_json(os.path.join(out, "qa_report.json"))

    def test_a_warning_from_the_cut_is_counted(self):
        p, qa = self.run_qa({"warnings": ["sh->el: far side is 132% of the near side"], "gaps": {}})
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(qa["bind"]["status"], "WARN")
        self.assertIn("far side is 132%", p.stdout)
        self.assertRegex(p.stdout, r"result: 0 FAIL, [1-9]\d* WARN")

    def test_a_joint_the_cut_saw_open_fails_and_names_the_clip(self):
        p, qa = self.run_qa({"warnings": [], "gaps": {"attack_1": {"neck": 0.2}}})
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertEqual(qa["bind"]["status"], "FAIL")
        self.assertIn("gap: attack_1", p.stdout)

    def test_a_partial_run_says_so(self):
        p, qa = self.run_qa({"warnings": [], "gaps": {}})
        self.assertEqual(qa["scope"]["clips_checked"], 2)
        self.assertGreater(qa["scope"]["clips_total"], 2)
        self.assertIn(f"scope: 2 of {qa['scope']['clips_total']} clips", p.stdout)

    def test_check_runs_at_the_size_it_is_given(self):
        sheet = os.path.join(self.tmp, "sized.png")
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "cut_parts.py"), "check", "--character",
                        os.path.join(self.rig, "character.json"), "--out", sheet, "--size", "96"],
                       capture_output=True)
        self.assertEqual(Image.open(sheet).width, 6 * 96)

    def test_check_replaces_a_stale_report(self):
        with open(os.path.join(self.rig, "bind_report.json"), "w", encoding="utf-8") as fh:
            json.dump({"warnings": [], "gaps": {"walk": {"neck": 0.5}}, "part_problems": ["old"]}, fh)
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "cut_parts.py"), "check", "--character",
                        os.path.join(self.rig, "character.json"), "--out", os.path.join(self.tmp, "sheet.png")],
                       check=True, capture_output=True)
        report = read_json(os.path.join(self.rig, "bind_report.json"))
        self.assertEqual((report["gaps"], report["part_problems"]), ({}, []))


class TestReviewCrop(unittest.TestCase):
    def test_a_small_character_fills_the_cell_with_its_ground(self):
        im = Image.new("RGBA", (256, 256))
        im.paste((255, 255, 255, 255), (110, 120, 160, 214))
        left, top, right, bottom = visual_review.crop_box([im], 256, 216)
        self.assertEqual(right - left, bottom - top)
        self.assertLess(right - left, 120)
        self.assertLessEqual(top, 120)
        self.assertGreater(bottom, 216)

    def test_a_character_that_fills_its_frame_is_left_alone(self):
        im = Image.new("RGBA", (64, 64))
        im.paste((255, 255, 255, 255), (0, 0, 64, 64))
        self.assertEqual(visual_review.crop_box([im], 64, 50), (0, 0, 64, 64))

    def test_an_empty_clip_is_left_alone(self):
        self.assertEqual(visual_review.crop_box([Image.new("RGBA", (64, 64))], 64, 50), (0, 0, 64, 64))


if __name__ == "__main__":
    unittest.main()
