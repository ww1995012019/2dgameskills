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
SPRITE_CLIPS = "idle,walk,run,jump_start,jump_rise,attack_1,death,block,block_hit,hurt"
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
    generate(SHOOTER, "commando", "idle,walk,jump_start,death,rifle_aim_0,rifle_fire_0,shotgun_fire_0,walk_fire_0", FIX["shooter"])


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

class TestJointContinuity(Case):
    def test_gait_cycle_cut_short(self):
        frames = self.frames("walk")
        for p in frames[-5:]:
            os.remove(p)
        # Trim the trace and manifest too: detecting a stale sidecar is not sufficient.
        def trim(t):
            def shorten(value):
                if isinstance(value, dict):
                    return {k: shorten(v) for k, v in value.items()}
                return value[:-5] if isinstance(value, list) and len(value) == len(frames) else value
            t["traces"]["walk"] = shorten(t["traces"]["walk"])
        self.edit_json("rig_trace.json", trim)
        self.edit_json("animations.json", lambda d: d["clips"]["walk"].update(frames=d["clips"]["walk"]["frames"][:-5]))
        code, rep = self.qa()
        self.assertEqual(code, 1)
        self.assertFlagged(rep, "walk", "seam", frame=len(frames) - 6)
        self.assertGreater(rep["clips"]["walk"]["joint_seam_ratio"], 2.6)

    def test_wrong_handover_pose(self):
        shutil.copyfile(self.frames("death")[-1], self.frames("jump_start")[0])
        def replace(t):
            for joint, pts in t["traces"]["jump_start"]["joints"].items():
                pts[0] = t["traces"]["death"]["joints"][joint][-1]
        self.edit_json("rig_trace.json", replace)
        code, rep = self.qa()
        self.assertEqual(code, 1)
        t = next(x for x in rep["transitions"] if (x["a"], x["b"]) == ("idle", "jump_start"))
        self.assertEqual(t["status"], "FAIL", t)
        self.assertGreater(t["joint_distance_height"], 0.2)
        self.assertEqual((t["a_frame"], t["b_frame"]), (len(self.frames("idle")) - 1, 0))
        self.assertIn("0", rep["clips"]["jump_start"]["flags"])

    def test_joint_fault_without_pixel_change(self):
        # Prove the new check really reads joints, rather than succeeding on the pixel check.
        def shift(t):
            for pts in t["traces"]["walk"]["joints"].values():
                pts[-1][0] += 100 * t["unit_px"]
        self.edit_json("rig_trace.json", shift)
        code, rep = self.qa()
        self.assertEqual(code, 1)
        self.assertFlagged(rep, "walk", "seam", frame=len(self.frames("walk")) - 1)

    def test_joint_checks_are_scale_independent(self):
        _, original = self.qa()
        def scale(t):
            t["unit_px"] *= 4
            for tr in t["traces"].values():
                for pts in tr["joints"].values():
                    for p in pts:
                        p[0] *= 4
                        p[1] *= 4
        self.edit_json("rig_trace.json", scale)
        code, scaled = self.qa()
        self.assertEqual(code, 0, scaled)
        self.assertEqual(original["clips"]["walk"]["joint_seam_ratio"],
                         scaled["clips"]["walk"]["joint_seam_ratio"])
        self.assertEqual([t["joint_distance_height"] for t in original["transitions"]],
                         [t["joint_distance_height"] for t in scaled["transitions"]])

    def test_legacy_trace_without_joints(self):
        def legacy(t):
            for tr in t["traces"].values():
                tr.pop("joints", None)
        self.edit_json("rig_trace.json", legacy)
        code, rep = self.qa()
        self.assertEqual(code, 0, rep)
        self.assertNotIn("joint_seam_ratio", rep["clips"]["walk"])
        self.assertTrue(all("joint_distance_height" not in t for t in rep["transitions"]))


class TestShooterJointContinuity(TestJointContinuity):
    skill, fixture = SHOOTER, "shooter"

    def test_firing_combo_still_checks_gait(self):
        def shift(t):
            for joint in ("an_n", "an_f", "kn_n", "kn_f", "hip"):
                t["traces"]["walk_fire_0"]["joints"][joint][-1][0] += 20 * t["unit_px"]
        self.edit_json("rig_trace.json", shift)
        code, rep = self.qa()
        self.assertEqual(code, 1)
        self.assertFlagged(rep, "walk_fire_0", "seam", frame=len(self.frames("walk_fire_0")) - 1)
        self.assertLess(rep["clips"]["walk_fire_0"]["joint_seam_height"], 0.2)
        self.assertGreater(rep["clips"]["walk_fire_0"]["joint_gait_seam_ratio"], 2.6)

    def test_recoil_wrap_still_rejects_large_pose_jump(self):
        code, clean = self.qa()
        self.assertEqual(code, 0, clean)
        self.assertEqual(clean["clips"]["shotgun_fire_0"]["joint_seam_mode"], "shot_impulse")
        def jump(t):
            for pts in t["traces"]["shotgun_fire_0"]["joints"].values():
                pts[-1][0] += 100 * t["unit_px"]
        self.edit_json("rig_trace.json", jump)
        code, rep = self.qa()
        self.assertEqual(code, 1)
        self.assertFlagged(rep, "shotgun_fire_0", "seam", frame=len(self.frames("shotgun_fire_0")) - 1)


class TestGuardRecovery(Case):
    def test_declared_resume_pose_is_continuous(self):
        code, rep = self.qa()
        self.assertEqual(code, 0, rep)
        edge = next(t for t in rep["transitions"] if (t["a"], t["b"]) == ("block_hit", "block"))
        self.assertEqual(edge["status"], "PASS", edge)
        self.assertEqual(edge["b_frame"], len(self.frames("block")) - 1)
        self.assertLess(edge["joint_distance_height"], 0.01)

    def test_resume_frame_tracks_target_fps_override(self):
        subprocess.run([sys.executable, os.path.join(SPRITE, "scripts", "generate.py"),
                        "--character", os.path.join(SPRITE, "assets", "characters", "hero.json"),
                        "--preset", "pixel", "--clips", "idle,block,block_hit,hurt",
                        "--fps-override", "block=60", "--out", self.d], check=True, capture_output=True)
        with open(os.path.join(self.d, "animations.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertGreater(len(doc["clips"]["block"]["frames"]), 3)
        self.assertEqual(doc["clips"]["block_hit"]["next_frame"], len(doc["clips"]["block"]["frames"]) - 1)
        code, rep = self.qa()
        self.assertEqual(code, 0, rep)
        edge = next(t for t in rep["transitions"] if (t["a"], t["b"]) == ("block_hit", "block"))
        self.assertEqual(edge["status"], "PASS", edge)
        self.assertLess(edge["joint_distance_height"], 0.01)

    def test_replaying_entry_is_still_reported(self):
        self.edit_json("animations.json", lambda d: d["clips"]["block_hit"].update(next_frame=0))
        _, rep = self.qa()
        edge = next(t for t in rep["transitions"] if (t["a"], t["b"]) == ("block_hit", "block"))
        self.assertEqual(edge["status"], "WARN", edge)
        self.assertEqual(edge["b_frame"], 0)
        self.assertIn("0", rep["clips"]["block"]["flags"])

    def test_wrong_hold_pose_is_still_rejected(self):
        def corrupt(t):
            for joint, points in t["traces"]["block"]["joints"].items():
                points[-1] = t["traces"]["death"]["joints"][joint][-1]
        self.edit_json("rig_trace.json", corrupt)
        code, rep = self.qa()
        self.assertEqual(code, 1)
        edge = next(t for t in rep["transitions"] if (t["a"], t["b"]) == ("block_hit", "block"))
        self.assertEqual(edge["status"], "FAIL", edge)
        self.assertIn(str(len(self.frames("block")) - 1), rep["clips"]["block"]["flags"])

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_preview_guarded_hits_and_release(self):
        p = subprocess.run(["node", os.path.join(ROOT, "dev", "test_sprite_demo.js"),
                            os.path.join(self.d, "preview.html")], capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("sprite guard recovery: OK", p.stdout)

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_preview_detects_replayed_guard_entry(self):
        path = os.path.join(self.d, "preview.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        import re
        html, count = re.subn(r'"next_frame":\s*\d+', '"next_frame": 0', html)
        self.assertEqual(count, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        p = subprocess.run(["node", os.path.join(ROOT, "dev", "test_sprite_demo.js"), path],
                           capture_output=True, text=True, timeout=30)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("without replaying entry", p.stderr)


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
