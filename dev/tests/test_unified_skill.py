"""The unified package preserves the original modes and their exports."""
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
            manifest = bundle / 'assets/shared_character_example.json'
            resolved = []
            for view in ('side', 'topdown'):
                output = root / ('shared-' + view)
                subprocess.run([sys.executable, str(bundle / 'scripts/generate_character.py'),
                                '--manifest', str(manifest), '--view', view, '--out', str(output),
                                '--preset', 'pixel48', '--size', '32', '--fps', '8', '--clips', 'idle'],
                               cwd=root, check=True, capture_output=True)
                self.assertTrue((output / 'atlas.png').is_file())
                resolved.append(json.loads((output / 'character-resolved.json').read_text(encoding='utf-8')))
            self.assertEqual(resolved[0]['name'], resolved[1]['name'])
            self.assertEqual(resolved[0]['colors']['tunic'], resolved[1]['colors']['coat'])
            for mode in MODES[1:]:
                for module in ('export.py', 'integrity.py'):
                    adapter = bundle / 'modes' / mode / 'scripts/sprite_anim' / module
                    self.assertIn('game-sprite-animator', adapter.read_text(encoding='utf-8'))
                # The functions must use the importing module's globals, as they do
                # in standalone modes (for example when a caller changes MAX_PAGE).
                subprocess.run([sys.executable, "-c",
                                "import sys; sys.path.insert(0,sys.argv[1]); "
                                "from sprite_anim import export; export.MAX_PAGE=77; "
                                "assert export.write_sheet.__globals__['MAX_PAGE']==77",
                                str(bundle / 'modes' / mode / 'scripts')],
                               cwd=root, check=True, capture_output=True)
            for mode in ('game-shooter-animator', 'game-quadruped-animator'):
                adapter = bundle / 'modes' / mode / 'scripts/sprite_anim/mathx.py'
                self.assertIn('game-sprite-animator', adapter.read_text(encoding='utf-8'))
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
                    args = ["--preset", "pixel48", "--size", "32", "--fps", "8", "--clips", "idle,walk,run"]
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
                        # Small 32px fixtures can trigger warnings or failures. The
                        # important property here is identical QA in both bundles.
                        subprocess.run([sys.executable, str(path / 'scripts/qa_motion.py'), str(out)],
                                       cwd=root, capture_output=True)
                        frames = sorted((out / "frames").rglob("*.png"))
                        self.assertTrue(frames)
                        outputs.append([(p.relative_to(out / "frames"), hashlib.sha256(p.read_bytes()).hexdigest()) for p in frames])
                    self.assertEqual(outputs[0], outputs[1], "unified mode changed output")
                    for name in ("animations.json", "atlas.json", "atlas.png", "qa_report.json"):
                        self.assertEqual((root / (mode + "-source") / name).read_bytes(),
                                         (root / (mode + "-install") / name).read_bytes(),
                                         f"unified mode changed {name}")
                    engine_paths = []
                    for label in ('source', 'install'):
                        engine = root / (mode + '-' + label) / 'engine'
                        files = []
                        for p in sorted(engine.rglob('*')):
                            if not p.is_file():
                                continue
                            data = p.read_bytes()
                            if p.suffix.lower() in ('.cs', '.js'):
                                data = data.replace(b'\r\n', b'\n')
                            files.append((p.relative_to(engine), hashlib.sha256(data).hexdigest()))
                        engine_paths.append(files)
                    self.assertEqual(engine_paths[0], engine_paths[1], 'unified engine exports changed')


if __name__ == "__main__":
    unittest.main()
