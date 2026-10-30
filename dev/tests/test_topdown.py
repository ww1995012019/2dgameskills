"""Eight-direction integration and injected faults; all fixtures are generated from scratch."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "game-topdown-animator"
TMP = None
FIX = None


def setUpModule():
    global TMP, FIX
    TMP = Path(tempfile.mkdtemp(prefix="topdown_tests_"))
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


class TopDown(unittest.TestCase):
    def setUp(self):
        self.out = TMP / self.id().split(".")[-1]
        shutil.copytree(FIX, self.out)

    def edit(self, file, fn):
        p = self.out / file
        doc = json.loads(p.read_text())
        fn(doc)
        p.write_text(json.dumps(doc))

    def qa(self):
        p = subprocess.run(
            [sys.executable, str(SKILL / "scripts/qa_motion.py"), str(self.out)],
            capture_output=True,
            text=True,
        )
        self.assertTrue((self.out / "qa_report.json").exists(), p.stdout + p.stderr)
        return p.returncode, json.loads((self.out / "qa_report.json").read_text())

    def flagged(self, report, clip, check, frame):
        self.assertEqual(report["clips"][clip][check], "FAIL", report["clips"][clip])
        self.assertIn(str(frame), report["clips"][clip]["flags"])

    def test_clean_all_directions(self):
        code, r = self.qa()
        self.assertEqual(code, 0, r)
        self.assertEqual(len(r["clips"]), 48)
        self.assertTrue(
            all(
                all(c[k] == "PASS" for k in ("direction", "phase", "slide", "seam", "limits"))
                for c in r["clips"].values()
            )
        )

    def test_swapped_front_back_pixels(self):
        target = self.out / "frames/walk_down/walk_down_000.png"
        shutil.copyfile(self.out / "frames/walk_up/walk_up_000.png", target)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "walk_down", "direction", 0)

    def test_wrong_direction_label(self):
        self.edit("animations.json", lambda d: d["clips"]["walk_down"].update(direction="up"))
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "walk_down", "direction", 0)

    def test_diagonal_speed_does_not_get_a_free_boost(self):
        def faster(d):
            c = d["clips"]["run_down_right"]
            c["speed_px_s"] *= 2**0.5
            c["velocity_px_s"] = [v * 2**0.5 for v in c["velocity_px_s"]]

        self.edit("animations.json", faster)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "run_down_right", "phase", 0)

    def test_ground_plane_foot_slide(self):
        def slide(d):
            for i, p in enumerate(d["traces"]["walk_up_right"]["feet"]["r"]):
                p[0] += i * 2

        self.edit("rig_trace.json", slide)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "walk_up_right", "slide", 0)

    def test_stretched_bone(self):
        def stretch(d):
            d["traces"]["run_down"]["world"]["knee_r"][2][0] += 12

        self.edit("rig_trace.json", stretch)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "run_down", "limits", 2)

    def test_weapon_is_rigid(self):
        self.edit(
            "rig_trace.json",
            lambda d: d["traces"]["attack_down"]["world"]["blade_tip"][2].__setitem__(2, 150),
        )
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "attack_down", "limits", 2)

    def test_foot_below_floor(self):
        self.edit(
            "rig_trace.json",
            lambda d: d["traces"]["walk_up"]["world"]["foot_r"][3].__setitem__(2, -3),
        )
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "walk_up", "limits", 3)

    def test_direction_phase_shift(self):
        def shift(d):
            tr = d["traces"]["walk_up"]
            tr["world"]["foot_r"] = tr["world"]["foot_r"][2:] + tr["world"]["foot_r"][:2]

        self.edit("rig_trace.json", shift)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "walk_up", "phase", 0)

    def test_locomotion_duplicate_frame(self):
        shutil.copyfile(
            self.out / "frames/walk_right/walk_right_003.png",
            self.out / "frames/walk_right/walk_right_004.png",
        )
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "walk_right", "hold", 4)

    def test_open_loop(self):
        def jump(d):
            for points in d["traces"]["walk_right"]["joints"].values():
                points[-1][0] += 100

        self.edit("rig_trace.json", jump)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(
            r, "walk_right", "seam", len(list((self.out / "frames/walk_right").glob("*.png"))) - 1
        )

    def test_cut_off_art(self):
        p = self.out / "frames/idle_down/idle_down_000.png"
        im = np.array(Image.open(p))
        im[0, 4] = [255, 255, 255, 255]
        Image.fromarray(im).save(p)
        code, r = self.qa()
        self.assertEqual(code, 1)
        self.flagged(r, "idle_down", "bounds", 0)

    def test_exports_restore_every_frame(self):
        p = subprocess.run(
            [sys.executable, str(ROOT / "dev/verify_exports_sprite.py"), str(self.out)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_mirror_about_common_pivot(self):
        a = np.array(Image.open(self.out / "frames/attack_right/attack_right_003.png"))
        b = np.array(Image.open(self.out / "frames/attack_left/attack_left_003.png"))
        expected = np.zeros_like(a)
        expected[:, 1:] = a[:, ::-1][:, :-1]
        np.testing.assert_array_equal(b, expected)

    def test_skill_archive_runs_in_isolation(self):
        with tempfile.TemporaryDirectory(prefix="topdown_installed_") as tmp:
            with zipfile.ZipFile(ROOT / "game-topdown-animator.skill") as z:
                z.extractall(tmp)
            installed = Path(tmp) / "game-topdown-animator"
            out = Path(tmp) / "output"
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            subprocess.run(
                [
                    sys.executable,
                    str(installed / "scripts/generate.py"),
                    "--preset",
                    "pixel48",
                    "--clips",
                    "idle,walk",
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
            self.assertEqual(len(json.loads((out / "animations.json").read_text())["clips"]), 16)

    @unittest.skipUnless(shutil.which("node"), "needs node")
    def test_controller_normalization_phase_and_actions(self):
        p = subprocess.run(
            [
                "node",
                str(ROOT / "dev/test_topdown_controller.js"),
                str(self.out / "animations.json"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
