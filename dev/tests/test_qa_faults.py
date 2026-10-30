"""Fault injection: break a generated set on purpose and check the QA names the fault and the frame.

    python -m unittest discover -s dev/tests -v

A clean set must come out with no FAIL first, so each test proves the QA reacts to the fault it
plants and not to something already there. Runs qa_motion.py and the export verifiers as
subprocesses, the way users run them.
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
SPRITE_CLIPS = "idle,walk,run,jump_start,jump_rise,attack_1,death"
TMP = None
FIX = {}


def generate(skill, character, clips, out):
    subprocess.run([sys.executable, os.path.join(skill, "scripts", "generate.py"), "--character",
                    os.path.join(skill, "assets", "characters", character + ".json"), "--preset", "pixel",
                    "--clips", clips, "--out", out], check=True, capture_output=True)


def setUpModule():
    global TMP
    TMP = tempfile.mkdtemp(prefix="qa_faults_")
    FIX["sprite"] = os.path.join(TMP, "hero")
    generate(SPRITE, "hero", SPRITE_CLIPS, FIX["sprite"])
    FIX["shooter"] = os.path.join(TMP, "commando")
    generate(SHOOTER, "commando", "idle,rifle_aim_0,rifle_fire_0", FIX["shooter"])


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class Case(unittest.TestCase):
    skill, fixture = SPRITE, "sprite"

    def setUp(self):
        self.d = os.path.join(TMP, self.id().rsplit(".", 1)[-1])
        shutil.rmtree(self.d, ignore_errors=True)
        shutil.copytree(FIX[self.fixture], self.d)

    def qa(self):
        p = subprocess.run([sys.executable, os.path.join(self.skill, "scripts", "qa_motion.py"), self.d],
                           capture_output=True, text=True)
        with open(os.path.join(self.d, "qa_report.json"), encoding="utf-8") as fh:
            return p.returncode, json.load(fh)

    def frames(self, clip):
        d = os.path.join(self.d, "frames", clip)
        return [os.path.join(d, f) for f in sorted(os.listdir(d))]

    def edit_json(self, name, fn):
        path = os.path.join(self.d, name)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        fn(doc)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def assertFlagged(self, report, clip, check, frame=None):
        r = report["clips"][clip]
        self.assertEqual(r[check], "FAIL", f"{clip}.{check} should FAIL, report: {r}")
        if frame is not None:
            self.assertIn(str(frame), r["flags"], f"frame {frame} not flagged in {clip}: {r['flags']}")


class TestClean(Case):
    def test_sprite_clean(self):
        code, rep = self.qa()
        self.assertEqual(code, 0, rep)

    def test_shooter_clean(self):
        self.skill, self.fixture = SHOOTER, "shooter"
        self.setUp()
        code, rep = self.qa()
        self.assertEqual(code, 0, rep)


class TestFrameFaults(Case):
    """Faults visible in the pixels alone: qa_motion also runs these on any PNG sequence."""

    def test_repeated_frame(self):
        f = self.frames("walk")
        shutil.copyfile(f[4], f[5])
        code, rep = self.qa()
        self.assertEqual(code, 1)
        self.assertFlagged(rep, "walk", "hold")

    def test_loop_seam_break(self):
        for p in self.frames("idle")[-8:]:        # the breath now jumps back to the start
            os.remove(p)
        _, rep = self.qa()
        self.assertFlagged(rep, "idle", "seam")

    @unittest.expectedFailure
    def test_gait_cycle_cut_short(self):
        # Known gap: in a walk every step already changes most of the silhouette, so the pixel
        # seam ratio stays under 1.7 however many frames are cut. Needs a joint-space seam check.
        for p in self.frames("walk")[-5:]:
            os.remove(p)
        _, rep = self.qa()
        self.assertFlagged(rep, "walk", "seam")

    def test_skipped_inbetweens(self):
        for p in self.frames("idle")[8:20]:
            os.remove(p)
        _, rep = self.qa()
        self.assertIn(rep["clips"]["idle"]["spike"], ("WARN", "FAIL"), rep["clips"]["idle"])

    def test_cut_by_frame_edge(self):
        p = self.frames("run")[3]
        im = np.asarray(Image.open(p).convert("RGBA"))
        Image.fromarray(np.roll(im, im.shape[1] // 2, axis=1)).save(p)
        _, rep = self.qa()
        self.assertFlagged(rep, "run", "bounds", frame=3)
        self.assertEqual(rep["clips"]["run"]["cut_frames"], [3])

    @unittest.expectedFailure
    def test_wrong_handover_pose(self):
        # Known gap: the transition ratio divides by the faster clip's typical step, and pixel
        # change saturates once silhouettes stop overlapping. Handing the death pose to jump_start
        # scores about 1.5 against a 2.5 limit. Needs the joint-space check as well.
        shutil.copyfile(self.frames("death")[-1], self.frames("jump_start")[0])
        _, rep = self.qa()
        t = {(x["a"], x["b"]): x for x in rep["transitions"]}
        self.assertEqual(t[("idle", "jump_start")]["status"], "FAIL", t)


class TestRigFaults(Case):
    """Faults in the skeleton, planted in rig_trace.json, the data the QA reads them from."""

    def trace(self, fn):
        self.edit_json("rig_trace.json", fn)

    def test_foot_slides_while_planted(self):
        def slide(t):
            heel = t["traces"]["walk"]["feet"]["n"]["heel"]
            ball = t["traces"]["walk"]["feet"]["n"]["ball"]
            for i in range(len(heel)):
                heel[i][0] += 3.0 * i
                ball[i][0] += 3.0 * i
        self.trace(slide)
        _, rep = self.qa()
        self.assertFlagged(rep, "walk", "slide")

    def test_planted_foot_wobbles(self):
        def wobble(t):
            for key in ("heel", "ball"):
                pts = t["traces"]["idle"]["feet"]["f"][key]
                for i in range(len(pts)):
                    pts[i][0] += 1.2 * (i % 2)
                    pts[i][1] += 1.2 * (i % 2)
        self.trace(wobble)
        _, rep = self.qa()
        self.assertFlagged(rep, "idle", "jitter")

    def test_bone_stretched(self):
        self.trace(lambda t: t["traces"]["run"]["metrics"][2].update(bone_err=0.8))
        _, rep = self.qa()
        self.assertFlagged(rep, "run", "limits", frame=2)

    def test_knee_flips(self):
        def flip(t):
            m = t["traces"]["walk"]["metrics"][6]
            m["knee_dir"] = [-m["knee_dir"][0], m["knee_dir"][1]]
            m["knee"] = [30.0, m["knee"][1]]
            t["traces"]["walk"]["metrics"][5]["knee"][0] = 30.0
        self.trace(flip)
        _, rep = self.qa()
        self.assertFlagged(rep, "walk", "limits", frame=6)

    def test_weapon_through_ground(self):
        self.trace(lambda t: t["traces"]["attack_1"]["metrics"][4].update(weapon_ground=4.0))
        _, rep = self.qa()
        self.assertFlagged(rep, "attack_1", "clip", frame=4)

    def test_weapon_parked_over_face(self):
        def park(t):
            for m in t["traces"]["idle"]["metrics"][:12]:
                m["weapon_head"] = 4.0
        self.trace(park)
        _, rep = self.qa()
        self.assertFlagged(rep, "idle", "clip", frame=0)


class TestShooterFaults(Case):
    skill, fixture = SHOOTER, "shooter"

    def test_hand_off_the_gun(self):
        def drift(t):
            gaps = t["traces"]["rifle_aim_0"]["gaps"]
            gaps[len(gaps) // 2] = [g + 3.0 for g in gaps[len(gaps) // 2]]
        self.edit_json("rig_trace.json", drift)
        _, rep = self.qa()
        self.assertFlagged(rep, "rifle_aim_0", "grip")

    def test_shot_without_flash(self):
        def dark(t):
            tr = t["traces"]["rifle_fire_0"]
            tr["flash"][tr["shots"][0]] = 0.0
        self.edit_json("rig_trace.json", dark)
        _, rep = self.qa()
        self.assertFlagged(rep, "rifle_fire_0", "cadence")


class TestExportFaults(Case):
    def verify(self, script="verify_exports_sprite.py"):
        return subprocess.run([sys.executable, os.path.join(ROOT, "dev", script), self.d], capture_output=True, text=True)

    def test_clean_exports_verify(self):
        p = self.verify()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("OK", p.stdout)

    def test_atlas_frame_out_of_bounds(self):
        def push(doc):
            f = next(iter(doc["frames"].values()))
            f["frame"]["x"] = doc["meta"]["size"]["w"]
        self.edit_json("atlas.json", push)
        p = self.verify()
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertIn("AssertionError", p.stderr)

    def test_atlas_region_points_at_wrong_pixels(self):
        self.edit_json("animations.json", lambda d: d["regions"][0].update(x=d["regions"][0]["x"] + 3))
        p = self.verify()
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertRegex(p.stdout, r"atlas rebuild: \d+/\d+ frames identical")
        self.assertNotIn("OK", p.stdout)


if __name__ == "__main__":
    unittest.main()
