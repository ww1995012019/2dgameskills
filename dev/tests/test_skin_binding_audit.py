"""Explicit artwork correspondence must survive custom skinning, not only bone lengths."""
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "game-animator/modes/game-sprite-animator/scripts/audit_skin_binding.py"
SPEC = importlib.util.spec_from_file_location("skin_binding_audit_tests", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class SkinBindingAudit(unittest.TestCase):
    def fixture(self, width=100, height=140):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(source)
        draw.rectangle((width * .2, height * .1, width * .8, height * .9), fill="#456a8f")
        # An intentional negative space below the pelvis must remain legal.
        draw.rectangle((width * .48, height * .68, width * .52, height), fill=(0, 0, 0, 0))
        source.save(root / "source.png")
        near, far = [width * .4, height * .45], [width * .6, height * .45]
        doc = dict(schema_version=1, sources={"pose": "source.png"},
                   parts={"near": {"source": "pose"}, "far": {"source": "pose"}},
                   landmarks=[dict(id="near-hip", part="near", joint="hip_n", point=near,
                                   influences=[[0, .25], [1, .75]]),
                              dict(id="far-hip", part="far", joint="hip_f", point=far, influences=[[0, 1]])],
                   seams=[dict(id="pants", parts=["near", "far"], samples=[
                       dict(point=[width * .5, height * y], influences={"near": [[0, 1]], "far": [[0, 1]]})
                       for y in (.4, .45, .5)])], clips={})
        for clip, dy in [("idle", 10), ("crouch", 18)]:
            frame = Image.new("RGBA", (width + 20, height + 30))
            frame.alpha_composite(source, (10, dy))
            frame.save(root / f"{clip}.png")
            matrix = [1, 0, 0, 1, 10, dy]
            doc["clips"][clip] = dict(frames=[dict(image=f"{clip}.png",
                skeleton={"hip_n": [near[0] + 10, near[1] + dy], "hip_f": [far[0] + 10, far[1] + dy]},
                matrices={"near": [matrix[:], matrix[:]], "far": [matrix[:]]})])
        manifest = root / "manifest.json"
        self.save(manifest, doc)
        return root, manifest, doc

    @staticmethod
    def save(path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_two_body_proportions_keep_registered_seams_without_claiming_visual_approval(self):
        for width, height in [(100, 140), (70, 240)]:
            with self.subTest(proportions=(width, height)):
                root, manifest, _ = self.fixture(width, height)
                report = audit.write_audit(manifest)
                self.assertEqual(report["status"], "pass")
                self.assertEqual(report["visual_status"], "pending")
                self.assertEqual(report["scope"], dict(clips=2, frames=2, clip_frames={"idle": 1, "crouch": 1},
                                                      landmarks=2, seam_samples=3))
                self.assertEqual(audit.audit_current(root / "binding_audit.json"), 0)
                for filename in report["review_sheets"]:
                    self.assertTrue((root / filename).is_file())

    def test_shared_painted_point_splits_despite_correct_bone_landmarks(self):
        root, manifest, doc = self.fixture()
        data = doc["clips"]["crouch"]["frames"][0]
        for matrix in data["matrices"]["near"]:
            matrix[4] += 9
        data["skeleton"]["hip_n"][0] += 9
        self.save(manifest, doc)
        report, _ = audit.inspect_manifest(manifest)
        self.assertEqual(report["status"], "fail")
        self.assertEqual({(r["clip"], r["frame"], r["kind"], r["id"]) for r in report["failures"]},
                         {("crouch", 0, "seam", "pants")})
        self.assertTrue(all(abs(r["error_px"] - 9) < 1e-6 for r in report["failures"]))

    def test_bone_length_preservation_does_not_clear_artwork_joint_misalignment(self):
        _, manifest, doc = self.fixture()
        skeleton = doc["clips"]["idle"]["frames"][0]["skeleton"]
        length = math.dist(skeleton["hip_n"], skeleton["hip_f"])
        for point in skeleton.values():
            point[0] += 7
        self.assertEqual(math.dist(skeleton["hip_n"], skeleton["hip_f"]), length)
        self.save(manifest, doc)
        report, _ = audit.inspect_manifest(manifest)
        self.assertEqual({(r["clip"], r["kind"]) for r in report["failures"]}, {("idle", "landmark")})
        self.assertTrue(all(r["error_px"] == 7 for r in report["failures"]))

    def test_missing_evidence_never_becomes_a_numeric_pass(self):
        for field in ["sources", "parts", "landmarks", "seams", "clips"]:
            with self.subTest(field=field):
                _, manifest, doc = self.fixture()
                doc.pop(field)
                self.save(manifest, doc)
                self.assertEqual(audit.write_audit(manifest, sheets=False)["status"], "invalid")
        for field in ["image", "skeleton", "matrices"]:
            with self.subTest(frame_field=field):
                _, manifest, doc = self.fixture()
                doc["clips"]["idle"]["frames"][0].pop(field)
                self.save(manifest, doc)
                self.assertEqual(audit.write_audit(manifest, sheets=False)["status"], "invalid")

    def test_every_declared_part_requires_a_registered_artwork_landmark(self):
        _, manifest, doc = self.fixture()
        doc["landmarks"].pop()
        self.save(manifest, doc)
        with self.assertRaisesRegex(audit.ContractError, "without registered landmarks"):
            audit.inspect_manifest(manifest)

    def test_nonfinite_and_invalid_influence_data_are_rejected(self):
        bads = [dict(point=[float("nan"), 20]), dict(influences=[[0, .9]]),
                dict(influences=[[0, -.1], [1, 1.1]]), dict(influences=[[0, .5], [0, .5]]),
                dict(influences=[[99, 1]]), dict(influences=[[True, 1]])]
        for changes in bads:
            with self.subTest(changes=changes):
                _, manifest, doc = self.fixture()
                doc["landmarks"][0].update(changes)
                self.save(manifest, doc)
                self.assertEqual(audit.write_audit(manifest, sheets=False)["status"], "invalid")

    def test_missing_or_nonfinite_skin_matrices_are_rejected(self):
        for matrices in [{"far": [[1, 0, 0, 1, 10, 10]]},
                         {"near": [[1, 0, 0, 1, float("inf"), 10]], "far": [[1, 0, 0, 1, 10, 10]]},
                         {"near": [[0, 0, 0, 0, 10, 10]], "far": [[1, 0, 0, 1, 10, 10]]}]:
            _, manifest, doc = self.fixture()
            doc["clips"]["idle"]["frames"][0]["matrices"] = matrices
            self.save(manifest, doc)
            self.assertEqual(audit.write_audit(manifest, sheets=False)["status"], "invalid")

    def test_original_transparent_leg_gap_cannot_be_declared_shared_fabric(self):
        _, manifest, doc = self.fixture()
        doc["seams"][0]["samples"][0]["point"] = [50, 120]
        self.save(manifest, doc)
        with self.assertRaisesRegex(audit.ContractError, "transparent"):
            audit.inspect_manifest(manifest)

    def test_two_different_source_images_cannot_be_called_one_shared_painted_edge(self):
        _, manifest, doc = self.fixture()
        doc["sources"]["other"] = "source.png"
        doc["parts"]["far"]["source"] = "other"
        self.save(manifest, doc)
        with self.assertRaisesRegex(audit.ContractError, "same source image"):
            audit.inspect_manifest(manifest)

    def test_opaque_scene_screenshot_is_not_isolated_character_evidence(self):
        for mode, color in [("RGB", "blue"), ("RGBA", "blue")]:
            root, manifest, _ = self.fixture()
            Image.new(mode, (120, 170), color).save(root / "idle.png")
            self.assertEqual(audit.write_audit(manifest, sheets=False)["status"], "invalid")

    def test_changed_source_frame_or_manifest_invalidates_current_report(self):
        for name in ["source.png", "idle.png", "manifest.json"]:
            with self.subTest(asset=name):
                root, manifest, _ = self.fixture()
                report = root / "binding_audit.json"
                audit.write_audit(manifest, sheets=False)
                if name.endswith("png"):
                    with Image.open(root / name) as image:
                        image.putpixel((0, 0), (200, 10, 10, 0))
                        image.save(root / name)
                else:
                    manifest.write_text(manifest.read_text() + "\n")
                self.assertEqual(audit.audit_current(report), 1)

    def test_changed_or_missing_binding_diagram_invalidates_its_recorded_evidence(self):
        for remove in [False, True]:
            root, manifest, _ = self.fixture()
            report = audit.write_audit(manifest)
            self.assertEqual(set(report["review_sheets"]), set(report["review_sheet_assets"]))
            diagram = root / report["review_sheets"][0]
            if remove:
                diagram.unlink()
            else:
                with Image.open(diagram) as image:
                    image.putpixel((0, 0), (255, 0, 0))
                    image.save(diagram)
            self.assertEqual(audit.audit_current(root / "binding_audit.json"), 1)

    def test_audit_and_diagnostics_never_overwrite_input_evidence(self):
        root, manifest, doc = self.fixture()
        before = manifest.read_bytes()
        with self.assertRaisesRegex(audit.ContractError, "overwrite"):
            audit.write_audit(manifest, manifest)
        self.assertEqual(manifest.read_bytes(), before)
        renamed = root / "original.json"
        renamed.write_bytes((root / "source.png").read_bytes())
        doc["sources"]["pose"] = renamed.name
        self.save(manifest, doc)
        before = renamed.read_bytes()
        with self.assertRaisesRegex(audit.ContractError, "overwrite"):
            audit.write_audit(manifest, renamed)
        self.assertEqual(renamed.read_bytes(), before)
        diagnostic = root / "binding_review_sources.png"
        diagnostic.write_bytes(renamed.read_bytes())
        doc["sources"]["pose"] = diagnostic.name
        self.save(manifest, doc)
        before = diagnostic.read_bytes()
        self.assertEqual(audit.write_audit(manifest)["status"], "invalid")
        self.assertEqual(diagnostic.read_bytes(), before)

    def test_forging_a_failed_audit_status_cannot_clear_the_geometry(self):
        root, manifest, doc = self.fixture()
        doc["clips"]["idle"]["frames"][0]["skeleton"]["hip_n"][0] += 10
        self.save(manifest, doc)
        saved = audit.write_audit(manifest, sheets=False)
        self.assertEqual(saved["status"], "fail")
        saved["status"] = "pass"
        saved["failures"] = []
        self.save(root / "binding_audit.json", saved)
        self.assertEqual(audit.audit_current(root / "binding_audit.json"), 1)

    def test_assets_cannot_escape_the_archived_manifest_directory(self):
        _, manifest, doc = self.fixture()
        doc["sources"]["pose"] = "../outside.png"
        self.save(manifest, doc)
        with self.assertRaisesRegex(audit.ContractError, "outside manifest"):
            audit.inspect_manifest(manifest)

    def test_cli_produces_a_report_and_requires_current_evidence(self):
        root, manifest, _ = self.fixture()
        result = subprocess.run([sys.executable, str(SCRIPT), str(manifest)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = root / "binding_audit.json"
        result = subprocess.run([sys.executable, str(SCRIPT), "--check", str(report)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        (root / "source.png").unlink()
        result = subprocess.run([sys.executable, str(SCRIPT), "--check", str(report)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)


if __name__ == "__main__":
    unittest.main()
