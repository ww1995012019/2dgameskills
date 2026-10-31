"""The unified package contains standalone, unchanged animation modes."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODES = ("game-sprite-animator", "game-shooter-animator", "game-topdown-animator", "game-quadruped-animator")


class UnifiedSkill(unittest.TestCase):
    def test_archive_modes_generate_identical_frames_in_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with zipfile.ZipFile(ROOT / "game-animator.skill") as archive:
                self.assertIsNone(archive.testzip())
                archive.extractall(root / "install")
            bundle = root / "install/game-animator"
            self.assertTrue((bundle / "SKILL.md").is_file())
            rig_script = bundle / "scripts/creature_rig.py"
            self.assertTrue(rig_script.is_file())
            subprocess.run([sys.executable, "-c",
                            "import runpy,sys; m=runpy.run_path(sys.argv[1]); "
                            "r=m['CreatureRig']({'bones':[{'name':'body','parent':None,'length':3}]}); "
                            "assert 'body' in r.pose(0)", str(rig_script)], cwd=root, check=True, capture_output=True)
            creature_out = root / "creature"
            subprocess.run([sys.executable, str(bundle / "scripts/generate_creature.py"), "--config",
                            str(bundle / "assets/creatures/flight_example.json"), "--out", str(creature_out),
                            "--clips", "flap", "--size", "96", "--fps", "8"], cwd=root, check=True, capture_output=True)
            subprocess.run([sys.executable, str(bundle / "scripts/qa_creature.py"), str(creature_out)],
                           cwd=root, check=True, capture_output=True)
            for mode in MODES:
                with self.subTest(mode=mode):
                    original = ROOT / mode
                    installed = bundle / "modes" / mode
                    self.assertTrue((installed / "SKILL.md").is_file())
                    args = ["--preset", "pixel48", "--size", "32", "--fps", "8", "--clips", "idle"]
                    if mode in MODES[:2]:
                        args += ["--no-fx"]
                        spec = json.loads((original / "assets/characters" / ("hero.json" if mode == MODES[0] else "commando.json")).read_text(encoding="utf-8"))
                        spec["cloth"] = []
                        character = root / (mode + ".json")
                        character.write_text(json.dumps(spec), encoding="utf-8")
                        args += ["--character", str(character)]
                    outputs = []
                    for label, path in (("source", original), ("install", installed)):
                        out = root / (mode + "-" + label)
                        subprocess.run([sys.executable, str(path / "scripts/generate.py"), *args, "--out", str(out)],
                                       cwd=root, check=True, capture_output=True)
                        frames = sorted((out / "frames").rglob("*.png"))
                        self.assertTrue(frames)
                        outputs.append([(p.relative_to(out / "frames"), hashlib.sha256(p.read_bytes()).hexdigest()) for p in frames])
                    self.assertEqual(outputs[0], outputs[1], "unified mode changed output")


if __name__ == "__main__":
    unittest.main()
