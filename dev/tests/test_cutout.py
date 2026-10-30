"""Cut-out pipeline: picture + joints -> parts -> animated set.

The procedural hero stands in for AI art: cut_parts.py renders its reference pose, cuts that
picture, and the cut-out is animated next to the procedural original (dev/cutout_match.py).
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
DEMO = os.path.join(SKILL, "assets", "characters", "cutout_demo")
HERO = os.path.join(SKILL, "assets", "characters", "hero.json")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(ROOT, "dev"))

import cut_parts  # noqa: E402
import cutout_match  # noqa: E402

CLIPS = ["idle", "run", "attack_1", "roll", "death"]
TMP = None


def read_json(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def setUpModule():
    global TMP
    TMP = tempfile.mkdtemp(prefix="cutout_")


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def cut_to(out, img, joints, base=None):
    """Run the cut and write it as cut_parts.py does. Returns (spec path, report)."""
    parts, spec, report, _, _ = cut_parts.cut(img, joints, base)
    os.makedirs(os.path.join(out, "parts"), exist_ok=True)
    for n, (im, _) in parts.items():
        im.save(os.path.join(out, "parts", n + ".png"))
    path = os.path.join(out, "character.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh)
    return path, report


def joint_gaps(spec_path):
    """Worst see-through share of any joint, per clip (cut_parts.check)."""
    _, gaps = cut_parts.check(cutout_match.load(spec_path), clips=CLIPS)
    return {n: max(gaps.get(n, {0: 0.0}).values()) for n in CLIPS}


def match(spec_path):
    return cutout_match.compare(cutout_match.load(spec_path), cutout_match.load(HERO), CLIPS, size=160)


class TestRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, _, cls.joints = cut_parts.template(read_json(HERO), 512)

    def test_cut_reproduces_the_original(self):
        path, report = cut_to(os.path.join(TMP, "rt"), self.img, self.joints, read_json(HERO))
        res = match(path)
        mean = np.mean([r["iou"] for r in res.values()])
        self.assertGreaterEqual(mean, 0.93, res)
        for n, r in res.items():
            self.assertGreaterEqual(r["iou_min"], 0.88, f"{n}: {r}")
        self.assertEqual(report["px_per_unit"], round(report["px_per_unit"], 3))

    def test_plain_background_is_removed(self):
        # Image models often can't give transparency; a flat backdrop must come off cleanly.
        flat = Image.new("RGBA", self.img.size, (236, 232, 222, 255))
        flat.alpha_composite(self.img)
        path, _ = cut_to(os.path.join(TMP, "flat"), flat.convert("RGB"), self.joints, read_json(HERO))
        res = match(path)
        self.assertGreaterEqual(np.mean([r["iou"] for r in res.values()]), 0.9, res)

    def test_rough_marking_stays_whole(self):
        # Joints marked by eye are a few pixels off. Proportions then follow the marks, so
        # likeness to the original drops by design; what must hold is no gaps at the joints
        # and a clean QA run.
        rng = np.random.default_rng(7)
        rough = {k: [v[0] + rng.normal(0, 3), v[1] + rng.normal(0, 3)] for k, v in self.joints.items()}
        clean_path, _ = cut_to(os.path.join(TMP, "clean"), self.img, self.joints, read_json(HERO))
        rough_path, _ = cut_to(os.path.join(TMP, "rough"), self.img, rough, read_json(HERO))
        clean, worse = joint_gaps(clean_path), joint_gaps(rough_path)
        for n in CLIPS:
            self.assertEqual(clean[n], 0.0, f"{n}: a joint shows through even when marked exactly")
            self.assertLessEqual(worse[n], 0.05, f"{n}: up to {worse[n]:.0%} of a joint shows through")
        out = os.path.join(TMP, "rough_set")
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "generate.py"), "--character", rough_path, "--preset",
                        "pixel", "--clips", ",".join(CLIPS), "--out", out], check=True, capture_output=True)
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "qa_motion.py"), out], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout)


class TestMarkingFaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, _, cls.joints = cut_parts.template(read_json(HERO), 512)

    def test_missing_joint(self):
        j = dict(self.joints)
        del j["kn_n"]
        with self.assertRaisesRegex(ValueError, "kn_n"):
            cut_parts.cut(self.img, j)

    def test_joint_outside_picture(self):
        j = dict(self.joints, el_n=[900, 10])
        with self.assertRaisesRegex(ValueError, "el_n.*outside"):
            cut_parts.cut(self.img, j)

    def test_misplaced_elbow_and_knee(self):
        j = dict(self.joints)
        j["el_f"] = [j["el_f"][0] + 40, j["el_f"][1]]
        j["kn_f"] = [j["kn_f"][0], j["kn_f"][1] - 45]
        _, _, report, _, _ = cut_parts.cut(self.img, j)
        text = "\n".join(report["warnings"])
        self.assertIn("el->wr: far side", text)
        self.assertIn("hip->kn: far side", text)

    def test_joint_off_the_character(self):
        j = dict(self.joints, head_top=[10, 10])
        _, _, report, _, _ = cut_parts.cut(self.img, j)
        self.assertTrue(any("head_top is not on the character" in w for w in report["warnings"]), report["warnings"])

    def test_motion_check_catches_what_marking_checks_miss(self):
        # The waist marked high: it has no far-side twin to compare with and stays on the body,
        # so the marking checks stay quiet, but torso and pelvis now hinge in the wrong place.
        j = dict(self.joints)
        j["waist"] = [j["waist"][0], j["waist"][1] - 16]
        parts, spec, report, _, _ = cut_parts.cut(self.img, j)
        marking = [w for w in report["warnings"] if "marked wrong" in w or "not on the character" in w or "foot is" in w]
        self.assertEqual(marking, [])
        out = os.path.join(TMP, "elbows")
        os.makedirs(os.path.join(out, "parts"), exist_ok=True)
        for n, (im, _) in parts.items():
            im.save(os.path.join(out, "parts", n + ".png"))
        spec["_dir"] = out
        _, gaps = cut_parts.check(spec, clips=CLIPS)
        opened = {j_ for js in gaps.values() for j_ in js}
        self.assertTrue(opened, "a hinge 16 px off should open somewhere while moving")

    def test_clean_marking_has_no_marking_warnings(self):
        _, _, report, _, _ = cut_parts.cut(self.img, self.joints)
        bad = [w for w in report["warnings"] if "marked wrong" in w or "not on the character" in w or "foot is" in w]
        self.assertEqual(bad, [])


class TestDemo(unittest.TestCase):
    def test_demo_matches_the_tool(self):
        # The committed example must be what cut_parts.py makes of its source today.
        out = os.path.join(TMP, "demo")
        base = {k: v for k, v in read_json(os.path.join(DEMO, "character.json")).items() if k not in ("parts", "body", "px_per_unit")}
        path, _ = cut_to(out, Image.open(os.path.join(DEMO, "source.png")), read_json(os.path.join(DEMO, "joints.json")), base)
        self.assertEqual(read_json(path), read_json(os.path.join(DEMO, "character.json")))
        for f in sorted(os.listdir(os.path.join(DEMO, "parts"))):
            a = np.asarray(Image.open(os.path.join(DEMO, "parts", f)))
            b = np.asarray(Image.open(os.path.join(out, "parts", f)))
            self.assertTrue(a.shape == b.shape and (a == b).all(), f)

    def test_demo_set_passes_qa(self):
        out = os.path.join(TMP, "demo_set")
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "generate.py"), "--character",
                        os.path.join(DEMO, "character.json"), "--preset", "pixel", "--clips",
                        "idle,walk,run,attack_1,roll,hurt,death", "--out", out], check=True, capture_output=True)
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "qa_motion.py"), out], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("result: 0 FAIL", p.stdout)


if __name__ == "__main__":
    unittest.main()
