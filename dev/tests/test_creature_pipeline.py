"""Exercise the experimental flight pipeline and inject detectable motion faults."""
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "game-animator"
SPEC = importlib.util.spec_from_file_location("creature_qa", SKILL / "scripts/qa_creature.py")
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


class CreaturePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "out"
        cls.cmd = [sys.executable, str(SKILL / "scripts/generate_creature.py"), "--config",
                   str(SKILL / "assets/creatures/flight_example.json"), "--out", str(cls.out), "--size", "128", "--fps", "8"]
        subprocess.run(cls.cmd, cwd=cls.tmp.name, check=True, capture_output=True)
        cls.trace = json.loads((cls.out / "rig_trace.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.trace_path = self.out / "rig_trace.json"
        self.trace_path.write_text(json.dumps(self.trace), encoding="utf-8")

    def write_trace(self, trace):
        self.trace_path.write_text(json.dumps(trace), encoding="utf-8")

    def test_export_and_clean_qa(self):
        report = qa.inspect(self.out)
        self.assertEqual(set(report["clips"]), {"flap", "hover", "glide", "dive", "hurt", "fall"})
        self.assertTrue(all(c["status"] == "PASS" for c in report["clips"].values()), report)
        doc = json.loads((self.out / "animations.json").read_text(encoding="utf-8"))
        for name, clip in doc["clips"].items():
            region = doc["regions"][clip["frames"][0]]
            with Image.open(self.out / doc["pages"][region["page"]]["file"]) as atlas:
                crop = np.asarray(atlas.convert("RGBA"))[region["y"]:region["y"]+region["h"], region["x"]:region["x"]+region["w"]]
            with Image.open(self.out / "frames" / name / f"{name}_000.png") as frame:
                src = np.asarray(frame.convert("RGBA"))[region["oy"]:region["oy"]+region["h"], region["ox"]:region["ox"]+region["w"]]
            self.assertTrue(np.array_equal(crop[:, :, 3], src[:, :, 3]), name)
            self.assertTrue(np.array_equal(crop[:, :, :3][src[:, :, 3] > 0], src[:, :, :3][src[:, :, 3] > 0]), name)

    def test_faults_identify_clip_and_frame(self):
        trace = copy.deepcopy(self.trace)
        trace["clips"]["flap"]["poses"][3]["wing_near"][1][0] += 12
        self.write_trace(trace)
        flags = qa.inspect(self.out)["clips"]["flap"]["flags"]
        self.assertTrue(any("bone length changed" in msg for msg in flags["3"]))
        self.assertTrue(any("joint detached" in msg for msg in flags["3"]))

        trace = copy.deepcopy(self.trace)
        trace["clips"]["flap"]["poses"][4]["wing_near"][2] += 20
        self.write_trace(trace)
        flags = qa.inspect(self.out)["clips"]["flap"]["flags"]
        self.assertTrue(any("wing pair out of phase" in msg for msg in flags["4"]))

        trace = copy.deepcopy(self.trace)
        trace["clips"]["hover"]["loop_reference"]["body"][1][0] += 3
        self.write_trace(trace)
        flags = qa.inspect(self.out)["clips"]["hover"]["flags"]
        self.assertTrue(any("loop endpoint" in msg for messages in flags.values() for msg in messages))

        trace = copy.deepcopy(self.trace)
        for point in trace["clips"]["flap"]["poses"][5].values():
            point[0][0] += 100
            point[1][0] += 100
        self.write_trace(trace)
        flags = qa.inspect(self.out)["clips"]["flap"]["flags"]
        self.assertTrue(any("abrupt endpoint movement" in msg for msg in flags["5"]))

        trace = copy.deepcopy(self.trace)
        trace["clips"]["flap"]["poses"][6]["body"][2] = float("inf")
        self.write_trace(trace)
        flags = qa.inspect(self.out)["clips"]["flap"]["flags"]
        self.assertTrue(any("non-finite" in msg for msg in flags["6"]))

        trace = copy.deepcopy(self.trace)
        trace["clips"]["flap"]["times"][3] = trace["clips"]["flap"]["times"][2]
        self.write_trace(trace)
        flags = qa.inspect(self.out)["clips"]["flap"]["flags"]
        self.assertIn("invalid frame times", flags["0"])

    def test_clipped_frame_and_existing_output(self):
        frame = self.out / "frames/flap/flap_002.png"
        original = frame.read_bytes()
        try:
            with Image.open(frame) as src:
                image = src.convert("RGBA")
            image.putpixel((0, 0), (255, 0, 0, 255))
            image.save(frame)
            flags = qa.inspect(self.out)["clips"]["flap"]["flags"]
            self.assertIn("art touches frame edge", flags["2"])
        finally:
            frame.write_bytes(original)
        before = (self.out / "animations.json").read_bytes()
        self.assertNotEqual(subprocess.run(self.cmd, capture_output=True).returncode, 0)
        self.assertEqual(before, (self.out / "animations.json").read_bytes())

    def test_swapped_frame_is_reported(self):
        frame = self.out / "frames/flap/flap_002.png"
        original = frame.read_bytes()
        try:
            frame.write_bytes((self.out / "frames/flap/flap_005.png").read_bytes())
            flags = qa.inspect(self.out)["clips"]["flap"]["flags"]
            self.assertIn("frame pixels differ from recorded frame hash", flags["2"])
        finally:
            frame.write_bytes(original)

    def test_swapped_atlas_reference_is_reported(self):
        path = self.out / "animations.json"
        original = path.read_bytes()
        try:
            doc = json.loads(original)
            doc["clips"]["flap"]["frames"][2] = doc["clips"]["flap"]["frames"][5]
            path.write_text(json.dumps(doc), encoding="utf-8")
            flags = qa.inspect(self.out)["clips"]["flap"]["flags"]
            self.assertIn("atlas frame differs from source pixels", flags["2"])
        finally:
            path.write_bytes(original)

    def test_config_relative_png_is_used_in_generated_frames(self):
        root = Path(self.tmp.name)
        spec = json.loads((SKILL / "assets/creatures/flight_example.json").read_text(encoding="utf-8"))
        image = Image.new("RGBA", (20, 8), (255, 0, 255, 255))
        image.save(root / "wing.png")
        spec["parts"]["wing_near"] = {"image": "wing.png", "pivot": [0, 4], "pixels_per_unit": 1}
        path = root / "part-config.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        out = root / "with-png"
        subprocess.run([sys.executable, str(SKILL / "scripts/generate_creature.py"), "--config", str(path),
                        "--out", str(out), "--clips", "flap", "--size", "128", "--fps", "8"],
                       check=True, capture_output=True)
        with Image.open(out / "frames/flap/flap_000.png") as frame:
            pixels = np.asarray(frame.convert("RGBA"))
        self.assertTrue(np.any((pixels[:, :, 0] > 200) & (pixels[:, :, 2] > 200) & (pixels[:, :, 1] < 50)))

    def test_three_different_skeleton_configs_use_same_pipeline(self):
        for name in ("bird", "bat", "dragon"):
            with self.subTest(name=name):
                config = SKILL / "assets/creatures" / f"flight_{name}_skeleton.json"
                out = Path(self.tmp.name) / f"{name}-output"
                subprocess.run([sys.executable, str(SKILL / "scripts/generate_creature.py"), "--config", str(config),
                                "--out", str(out), "--size", "128", "--fps", "8"], check=True, capture_output=True)
                report = qa.inspect(out)
                self.assertTrue(all(c["status"] == "PASS" for c in report["clips"].values()), report)

    def test_excessive_frame_memory_is_rejected_before_writing(self):
        out = Path(self.tmp.name) / "too-large"
        result = subprocess.run([sys.executable, str(SKILL / "scripts/generate_creature.py"), "--config",
                                 str(SKILL / "assets/creatures/flight_example.json"), "--out", str(out),
                                 "--size", "1024", "--fps", "60"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"raw frames would exceed", result.stderr)
        self.assertFalse(out.exists())

    def test_name_cannot_break_out_of_preview_script(self):
        root = Path(self.tmp.name)
        spec = json.loads((SKILL / "assets/creatures/flight_example.json").read_text(encoding="utf-8"))
        spec["name"] = "example </script><script>alert(1)</script>"
        path = root / "unsafe-name.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        out = root / "unsafe-name-output"
        subprocess.run([sys.executable, str(SKILL / "scripts/generate_creature.py"), "--config", str(path),
                        "--out", str(out), "--clips", "flap", "--size", "96", "--fps", "8"], check=True, capture_output=True)
        preview = (out / "preview.html").read_text(encoding="utf-8")
        self.assertEqual(preview.count("</script>"), 1)
        self.assertIn(r"\u003c/script\u003e", preview)

    @unittest.skipUnless(shutil.which("node"), "requires Node.js")
    def test_generated_preview_switches_and_plays(self):
        subprocess.run([shutil.which("node"), str(ROOT / "dev/test_creature_preview.js"),
                        str(self.out / "preview.html")], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
