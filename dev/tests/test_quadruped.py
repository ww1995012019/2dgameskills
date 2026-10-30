"""Fresh four-foot fixtures and physical/playback fault injection."""

import json, os, shutil, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "game-quadruped-animator"
TMP = None
FIX = None


def setUpModule():
    global TMP, FIX
    TMP = Path(tempfile.mkdtemp(prefix="quadruped_tests_"))
    FIX = TMP / "clean"
    subprocess.run(
        [
            sys.executable,
            str(SKILL / "scripts/generate.py"),
            "--preset",
            "pixel48",
            "--out",
            str(FIX),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, str(SKILL / "scripts/qa_motion.py"), str(FIX)],
        check=True,
        capture_output=True,
    )


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class Quadruped(unittest.TestCase):
    def setUp(self):
        self.out = TMP / self.id().split(".")[-1]
        shutil.copytree(FIX, self.out)

    def edit(self, file, fn):
        p = self.out / file
        d = json.loads(p.read_text())
        fn(d)
        p.write_text(json.dumps(d))

    def qa(self):
        p = subprocess.run(
            [sys.executable, str(SKILL / "scripts/qa_motion.py"), str(self.out)],
            capture_output=True,
            text=True,
        )
        self.assertTrue((self.out / "qa_report.json").exists(), p.stdout + p.stderr)
        return p.returncode, json.loads((self.out / "qa_report.json").read_text())

    def flagged(self, r, clip, check, i):
        self.assertEqual(r["clips"][clip][check], "FAIL", r["clips"][clip])
        self.assertIn(str(i), r["clips"][clip]["flags"])

    def test_clean_four_loops(self):
        code, r = self.qa()
        self.assertEqual(code, 0, r)
        self.assertEqual(
            set(r["clips"]), {"idle", "walk", "trot", "run", "attack", "hurt", "death"}
        )

    def test_each_paw_can_detect_sliding(self):
        for leg in ("hind_near", "hind_far", "front_near", "front_far"):
            with self.subTest(leg=leg):
                p = self.out / "rig_trace.json"
                original = p.read_text()
                d = json.loads(original)
                for i, point in enumerate(d["traces"]["walk"]["feet"][leg]):
                    point[0] += i * 2
                p.write_text(json.dumps(d))
                code, r = self.qa()
                self.assertEqual(code, 1)
                self.assertEqual(r["clips"]["walk"]["slide"], "FAIL")
                self.assertTrue(
                    any(leg in x for a in r["clips"]["walk"]["flags"].values() for x in a)
                )
                p.write_text(original)

    def test_planted_paw_hover(self):
        def hover(d):
            for point in d["traces"]["walk"]["feet"]["front_near"]:
                point[1] += 3

        self.edit("rig_trace.json", hover)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.assertEqual(r["clips"]["walk"]["slide"], "FAIL")

    def test_three_segment_leg_stretch(self):
        self.edit(
            "rig_trace.json",
            lambda d: d["traces"]["trot"]["world"]["hind_near_ankle"][2].__setitem__(0, 100),
        )
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "trot", "limits", 2)

    def test_inverted_knee_with_correct_lengths(self):
        def flip(d):
            tr = d["traces"]["walk"]["world"]
            a = np.array(tr["hind_near_root"][2])
            b = np.array(tr["hind_near_bend"][2])
            c = np.array(tr["hind_near_ankle"][2])
            u = (c - a) / np.linalg.norm(c - a)
            on_axis = a + u * np.dot(b - a, u)
            tr["hind_near_bend"][2] = (2 * on_axis - b).tolist()

        self.edit("rig_trace.json", flip)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "walk", "limits", 2)

    def test_tail_root_detaches(self):
        self.edit(
            "rig_trace.json", lambda d: d["traces"]["idle"]["world"]["tail_0"][3].__setitem__(0, 0)
        )
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "idle", "tail", 3)

    def test_tail_crosses_floor(self):
        self.edit(
            "rig_trace.json", lambda d: d["traces"]["run"]["world"]["tail_5"][2].__setitem__(1, -2)
        )
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "run", "tail", 2)

    def test_open_joint_loop(self):
        def jump(d):
            for points in d["traces"]["walk"]["joints"].values():
                points[-1][0] += 100

        self.edit("rig_trace.json", jump)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "walk", "seam", len(list((self.out / "frames/walk").glob("*.png"))) - 1)

    def test_nonfinite_joint(self):
        self.edit(
            "rig_trace.json",
            lambda d: d["traces"]["walk"]["world"]["front_far_bend"][2].__setitem__(
                0, float("nan")
            ),
        )
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "walk", "structure", 2)

    def test_wrong_trot_contacts(self):
        self.edit(
            "rig_trace.json",
            lambda d: d["traces"]["trot"]["contacts"]["front_near"].__setitem__(0, False),
        )
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "trot", "gait", 0)

    def test_missing_footstep(self):
        self.edit("animations.json", lambda d: d["clips"]["run"]["events"].pop())
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "run", "gait", 0)

    def test_repeated_gait_frame(self):
        shutil.copyfile(
            self.out / "frames/walk/walk_002.png", self.out / "frames/walk/walk_003.png"
        )
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "walk", "hold", 3)

    def test_clipped_frame(self):
        p = self.out / "frames/idle/idle_000.png"
        f = np.array(Image.open(p))
        f[0, 2] = [255, 255, 255, 255]
        Image.fromarray(f).save(p)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "idle", "bounds", 0)

    def test_fractional_tail_sampling_attaches(self):
        subprocess.run(
            [
                sys.executable,
                str(SKILL / "scripts/generate.py"),
                "--preset",
                "pixel48",
                "--fps",
                "24",
                "--out",
                str(self.out),
            ],
            check=True,
            capture_output=True,
        )
        code, r = self.qa()
        self.assertEqual(code, 0, r)

    def test_combat_events_and_terminal_death(self):
        d = json.loads((self.out / "animations.json").read_text())
        for n in ("attack", "hurt", "death"):
            self.assertFalse(d["clips"][n]["loop"])
        self.assertEqual([e["name"] for e in d["clips"]["attack"]["events"]], ["hit_on", "hit_off"])
        self.assertIsNone(d["clips"]["death"]["next"])
        self.assertEqual(d["clips"]["hurt"]["next"], "idle")

    def test_jaw_floor_fault(self):
        self.edit(
            "rig_trace.json",
            lambda d: d["traces"]["death"]["world"]["muzzle"][3].__setitem__(1, -3),
        )
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "death", "limits", 3)

    def test_attack_window_fault(self):
        self.edit("animations.json", lambda d: d["clips"]["attack"]["events"].pop())
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "attack", "gait", 0)

    def test_recovery_pose_fault(self):
        def jump(d):
            for key, points in d["traces"]["hurt"]["joints"].items():
                points[-1][0] += 100

        self.edit("rig_trace.json", jump)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.assertTrue(any(t["status"] == "FAIL" for t in r["transitions"]))

    def test_exports_restore_frames(self):
        p = subprocess.run(
            [sys.executable, str(ROOT / "dev/verify_exports_sprite.py"), str(self.out)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_runtime_controller(self):
        p = subprocess.run(
            [
                "node",
                str(ROOT / "dev/test_quadruped_controller.js"),
                str(self.out / "animations.json"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_isolated_skill_archive(self):
        with tempfile.TemporaryDirectory(prefix="quadruped_install_") as tmp:
            with zipfile.ZipFile(ROOT / "game-quadruped-animator.skill") as z:
                z.extractall(tmp)
            installed = Path(tmp) / "game-quadruped-animator"
            out = Path(tmp) / "out"
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            subprocess.run(
                [
                    sys.executable,
                    str(installed / "scripts/generate.py"),
                    "--preset",
                    "pixel48",
                    "--out",
                    str(out),
                ],
                cwd=tmp,
                env=env,
                check=True,
                capture_output=True,
            )
            p = subprocess.run(
                [sys.executable, str(installed / "scripts/qa_motion.py"), str(out)],
                cwd=tmp,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
