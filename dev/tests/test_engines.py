"""Engine smoke tests: Godot 4.3 headless, Phaser 3 and PixiJS 8 in Chromium.

Setup, once:
    bash dev/engines/get_godot.sh                 # or set GODOT to a Godot 4.3 binary
    npm install --prefix dev/engines              # Phaser and PixiJS, pinned in package.json
Each engine is skipped when it is not installed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "dev"))

import godot_smoke  # noqa: E402


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def write(p, text):
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)

GODOT = godot_smoke.find_godot()
WEB = os.path.isdir(os.path.join(ROOT, "dev", "engines", "node_modules", "phaser")) and shutil.which("node")
TMP = None
SETS = {}


def generate(skill, character, preset, clips):
    out = os.path.join(TMP, f"{character}-{preset}")
    subprocess.run([sys.executable, os.path.join(ROOT, skill, "scripts", "generate.py"), "--character",
                    os.path.join(ROOT, skill, "assets", "characters", character + ".json"), "--preset", preset,
                    "--clips", clips, "--out", out], check=True, capture_output=True)
    return out


def setUpModule():
    global TMP
    if not (GODOT or WEB):
        return
    TMP = tempfile.mkdtemp(prefix="engines_")
    SETS["hero"] = generate("game-sprite-animator", "hero", "pixel", "idle,walk,attack_1,death")
    SETS["hero_hd"] = generate("game-sprite-animator", "hero", "hd", "idle,attack_1")
    SETS["quadruped"] = generate("game-quadruped-animator", "wolf", "pixel", "idle,walk,trot,run")
    SETS["topdown"] = generate("game-topdown-animator", "wanderer", "pixel", "idle,walk,attack,death")
    SETS["commando"] = generate("game-shooter-animator", "commando", "pixel", "run,rifle_aim_0,rifle_fire_0,death")


def tearDownModule():
    if TMP:
        shutil.rmtree(TMP, ignore_errors=True)


def tampered(src, fn):
    d = tempfile.mkdtemp(prefix="tampered_", dir=TMP)
    shutil.rmtree(d)
    shutil.copytree(src, d)
    fn(d)
    return d


@unittest.skipUnless(GODOT, "needs Godot 4: bash dev/engines/get_godot.sh or set GODOT")
class TestGodot(unittest.TestCase):
    def test_sets_import_and_play(self):
        for name in ("hero", "hero_hd", "commando", "topdown", "quadruped"):
            ok, log = godot_smoke.run(SETS[name], GODOT, all_clips=name == "quadruped")
            self.assertTrue(ok, f"{name}:\n{log}")
            if name == "quadruped":
                for clip in ("idle", "walk", "trot", "run"):
                    self.assertIn(f"played {clip} @60Hz", log)
                    self.assertIn(f"played {clip} @144Hz", log)

    def test_default_import_settings_fringe_hd(self):
        # Without the exported .import file, Godot's fix_alpha_border recolours soft HD edges.
        ok, log = godot_smoke.run(SETS["hero_hd"], GODOT, rates=(60,), import_settings=False)
        self.assertFalse(ok)
        self.assertIn("pixels differ", log)

    def test_detects_wrong_margin(self):
        def shift(d):
            p = os.path.join(d, "engine", "godot", "sprite_frames.tres")
            text = read(p)
            head, rest = text.split('[sub_resource type="AtlasTexture" id="a3"]', 1)
            block, tail = rest.split("\n\n", 1)
            block = block.replace("margin = Rect2(", "margin = Rect2(1", 1)
            write(p, head + '[sub_resource type="AtlasTexture" id="a3"]' + block + "\n\n" + tail)
        ok, log = godot_smoke.run(tampered(SETS["hero"], shift), GODOT, rates=(60,))
        self.assertFalse(ok)
        self.assertIn("idle#3", log)

    def test_detects_wrong_speed(self):
        def slow(d):
            p = os.path.join(d, "engine", "godot", "sprite_frames.tres")
            write(p, read(p).replace('"name": &"walk", "speed": 15.0', '"name": &"walk", "speed": 12.0'))
        ok, log = godot_smoke.run(tampered(SETS["hero"], slow), GODOT, rates=(60,))
        self.assertFalse(ok)
        self.assertIn("walk: speed 12", log)


@unittest.skipUnless(WEB, "needs node and npm install --prefix dev/engines")
class TestWeb(unittest.TestCase):
    def web(self, set_dir):
        return subprocess.run(["node", os.path.join(ROOT, "dev", "web_engines.js"), set_dir] + (["--all-clips"] if os.path.basename(set_dir).startswith("wolf-") else []), capture_output=True, text=True, timeout=900)

    def test_sets_load_and_play(self):
        for name in ("hero", "hero_hd", "commando", "topdown", "quadruped"):
            p = self.web(SETS[name])
            self.assertEqual(p.returncode, 0, f"{name}:\n{p.stdout}{p.stderr}")
            self.assertIn("RESULT phaser ok", p.stdout)
            self.assertIn("RESULT pixi ok", p.stdout)
            if name == "quadruped":
                for clip in ("idle", "walk", "trot", "run"):
                    for hz in (60, 144):
                        self.assertIn(f"{clip}@{hz}", p.stdout)

    def test_detects_bad_trim_offset_and_missing_frame(self):
        def break_atlas(d):
            p = os.path.join(d, "atlas.json")
            doc = json.loads(read(p))
            doc["frames"]["walk_003"]["spriteSourceSize"]["x"] += 2
            del doc["frames"]["death_005"]
            write(p, json.dumps(doc))
        p = self.web(tampered(SETS["hero"], break_atlas))
        self.assertNotEqual(p.returncode, 0)
        for eng in ("phaser", "pixi"):
            self.assertIn(f"FAIL {eng} walk#3: pixels differ", p.stdout)
            self.assertIn(f"FAIL {eng} death#5: frame missing", p.stdout)


if __name__ == "__main__":
    unittest.main()
