"""Custom clip handovers are checked and identify a broken joint pose."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "game-sprite-animator"


class CustomActionTransitions(unittest.TestCase):
    def test_custom_handover_and_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = json.loads((SKILL / "assets/characters/hero.json").read_text(encoding="utf-8"))
            spec["cloth"] = []
            spec["custom_clips"] = {"salute": {
                "keys": [[0, {}], [0.3, {"arm_n_up": 60}], [0.6, {}]],
                "tags": ["ground"], "prev": "idle", "next": "idle"}}
            character = root / "character.json"
            character.write_text(json.dumps(spec), encoding="utf-8")
            out = root / "out"
            subprocess.run([sys.executable, str(SKILL / "scripts/generate.py"), "--character", str(character),
                            "--preset", "pixel48", "--clips", "idle,salute", "--no-fx", "--out", str(out)],
                           check=True, capture_output=True)
            trace_path = out / "rig_trace.json"
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            self.assertIn(["idle", "salute"], trace["seams"])
            self.assertIn(["salute", "idle"], trace["seams"])
            qa = [sys.executable, str(SKILL / "scripts/qa_motion.py"), str(out)]
            self.assertEqual(subprocess.run(qa, capture_output=True).returncode, 0)
            for points in trace["traces"]["salute"]["joints"].values():
                points[0][0] += 100
            trace_path.write_text(json.dumps(trace), encoding="utf-8")
            self.assertEqual(subprocess.run(qa, capture_output=True).returncode, 1)
            report = json.loads((out / "qa_report.json").read_text(encoding="utf-8"))
            edge = next(x for x in report["transitions"] if (x["a"], x["b"]) == ("idle", "salute"))
            self.assertEqual(edge["status"], "FAIL")
            self.assertEqual(edge["b_frame"], 0)
            self.assertIn("0", report["clips"]["salute"]["flags"])


if __name__ == "__main__":
    unittest.main()
