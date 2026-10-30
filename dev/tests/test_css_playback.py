"""Plays the exported sprites.css in Chromium and checks every frame against the source PNG.

Needs Node and Playwright with Chromium; skipped when they are missing.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def has_playwright():
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@unittest.skipUnless(has_playwright(), "needs node and playwright")
class TestCssPlayback(unittest.TestCase):
    def play(self, skill, character, clips, tamper=None):
        """Generate, optionally edit sprites.css, play it. Returns (frame errors, frames checked)."""
        tmp = tempfile.mkdtemp(prefix="css_")
        self.addCleanup(shutil.rmtree, tmp, True)
        out, shots = os.path.join(tmp, "set"), os.path.join(tmp, "shots")
        subprocess.run([sys.executable, os.path.join(ROOT, skill, "scripts", "generate.py"), "--character",
                        os.path.join(ROOT, skill, "assets", "characters", character + ".json"), "--preset", "pixel",
                        "--clips", clips, "--out", out], check=True, capture_output=True)
        if tamper:
            css = os.path.join(out, "engine", "web", "sprites.css")
            with open(css, encoding="utf-8") as fh:
                text = tamper(fh.read())
            with open(css, "w", encoding="utf-8") as fh:
                fh.write(text)
        p = subprocess.run(["node", os.path.join(ROOT, "dev", "css_playback.js"), out, shots], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        errors, checked = [], 0
        for clip in sorted(os.listdir(shots)):
            src = sorted(glob.glob(os.path.join(out, "frames", clip, "*.png")))
            got = sorted(glob.glob(os.path.join(shots, clip, "*.png")))
            self.assertEqual(len(src), len(got), clip)
            for i, (a, b) in enumerate(zip(src, got)):
                want = np.asarray(Image.open(a).convert("RGBA")).astype(int)
                have = np.asarray(Image.open(b).convert("RGBA")).astype(int)
                # Compare premultiplied colour: the browser composites, so fully transparent
                # pixels lose their colour and soft edges can round by a step or two.
                pw = want[..., :3] * want[..., 3:] // 255
                ph = have[..., :3] * have[..., 3:] // 255
                err = max(np.abs(pw - ph).max(), np.abs(want[..., 3] - have[..., 3]).max())
                if err > 3:
                    errors.append(f"{clip} frame {i}: max channel error {err}")
                checked += 1
        return errors, checked

    def test_sprite_css(self):
        errors, checked = self.play("game-sprite-animator", "hero", "idle,walk,attack_1,death")
        self.assertGreater(checked, 0)
        self.assertEqual(errors, [])

    def test_shooter_css(self):
        errors, checked = self.play("game-shooter-animator", "commando", "rifle_aim_0,roll,hurt,death")
        self.assertGreater(checked, 0)
        self.assertEqual(errors, [])

    def test_detects_wrong_keyframe(self):
        # Fault injection: walk's second keyframe points at the first cell, a classic off-by-one.
        def tamper(css):
            head, tail = css.split("@keyframes sp-walk{", 1)
            first, rest = tail.split("}", 1)
            second, rest = rest.split("}", 1)
            return head + "@keyframes sp-walk{" + first + "}" + second.split("{")[0] + "{background-position:-0px -0px}" + rest
        errors, _ = self.play("game-sprite-animator", "hero", "walk", tamper)
        self.assertTrue(errors and errors[0].startswith("walk frame 1:"), errors)


if __name__ == "__main__":
    unittest.main()
