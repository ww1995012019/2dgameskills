"""Equivalent numerical decisions with bounded, fresh command-local preparation."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'game-sprite-animator/scripts'))
import character_workflow as workflow
import layer_parts as layers
from workflow_assets import JobAssets
from sprite_anim.frame_checks import FrameContext
from sprite_anim import puppet_check, occlusion_review
from sprite_anim.art import Canvas
from sprite_anim.render import GROUND_FRAC
from review_support import ReviewFrames, playback_media
import test_registered_connections as connections
import test_character_workflow as workflow_fixtures


def reference_score(layer, ref, params, cx, cy):
    """Pre-refactor scorer, kept independent of the precomputed implementation."""
    warped = layers.warp(layer, *params, cx, cy, (ref.shape[1], ref.shape[0]), Image.NEAREST)
    on = warped[..., 3] > 128
    count = int(on.sum())
    if not count:
        return 1.0
    error = np.abs(warped[..., :3].astype(np.float32)-ref[..., :3]).mean(2)/255
    costs = np.where(ref[..., 3] > 128, np.minimum(error, .16), .24)
    lost = max(0, int((layer[..., 3] > 128).sum()*params[0]**2)-count)
    return (float(costs[on].sum())+lost*.24)/(count+lost)


class RegistrationPreparation(unittest.TestCase):
    def test_precomputed_scores_are_bitwise_equal_for_edges_hidden_art_and_scales(self):
        rng = np.random.default_rng(9821)
        for height, width in ((48, 80), (96, 64)):
            art = rng.integers(0, 256, (height, width, 4), dtype=np.uint8)
            ref = rng.integers(0, 256, art.shape, dtype=np.uint8)
            evaluate = layers.RegistrationScore(art, ref, width/2, height/2)
            for scale in (.76, 1., 1.24):
                for angle, x, y in ((-12., -19., 4.), (0., 0., 0.), (12., 17., -8.), (0., 500., 0.)):
                    params = scale, angle, x, y
                    self.assertEqual(evaluate(params), reference_score(art, ref, params, width/2, height/2))


class WorkflowPreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = workflow_fixtures.CharacterWorkflow('runTest')
        cls.fixture.setUp()
        case = cls.fixture
        case.prepare()
        images, hip = case.fixture()
        case.reference(images)
        case.layers(images, hip)
        with patch.object(layers, 'registration', return_value=dict(
                s=1., deg=0., dx=0., dy=0., cx=0., cy=0., error=0.)):
            workflow.bind_job(case.job)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.doCleanups()

    def test_bound_check_keys_each_input_only_once(self):
        case = self.fixture
        with patch.object(layers, 'key_out', wraps=layers.key_out) as key:
            workflow.check_bound_rig(case.job, workflow.read_json(case.job/'job.json'))
        inputs = [Path(call.args[0]) for call in key.call_args_list]
        self.assertEqual(len(inputs), 10)  # reference + seven art layers + two hand hints
        self.assertEqual(len(inputs), len(set(inputs)))

    def test_a_new_command_detects_a_changed_layer_after_a_successful_check(self):
        case = self.fixture
        job = workflow.read_json(case.job/'job.json')
        workflow.check_bound_rig(case.job, job)
        path = case.job/'layers/arm_near.png'
        original = path.read_bytes()
        try:
            with Image.open(path) as image:
                image.putpixel((10, 10), (0, 0, 0))
                image.save(path)
            with self.assertRaisesRegex(layers.Rejected, 'stale'):
                workflow.check_bound_rig(case.job, job)
        finally:
            path.write_bytes(original)

    def test_snapshot_is_read_only_and_bound_to_one_job(self):
        assets = JobAssets(self.fixture.job)
        with self.assertRaises(ValueError):
            assets.keyed('layers/arm_near.png')[0, 0] = 0
        with self.assertRaisesRegex(ValueError, 'another job'):
            assets.require_root(self.fixture.root/'other')


class FramePreparation(unittest.TestCase):
    def fixture(self, wide=False):
        case = connections.RegisteredConnections('runTest')
        renderer, clip = case.renderer(wide)
        self.addCleanup(case.doCleanups)
        return renderer, clip

    def checks(self, renderer, clip, context=None):
        faults = puppet_check.check_motion(renderer, clip, 5, 12, context=context)
        faults += puppet_check.check_neck(renderer, clip, 5, 12, context=context)
        faults += puppet_check.check_connections(renderer, clip, 5, 12, context=context)
        faults += puppet_check.check_attachments(renderer, clip, 5, 12, context=context)
        candidates = occlusion_review.clip_candidates(renderer, clip, 5, 12, context=context)
        return faults, candidates, copy.deepcopy(renderer.connection_checks)

    def test_shared_checks_match_independent_checks_and_solve_mesh_once_per_frame(self):
        for wide in (False, True):
            renderer, clip = self.fixture(wide)
            expected = self.checks(renderer, clip)
            with patch.object(renderer.art.puppet, 'meshes', wraps=renderer.art.puppet.meshes) as meshes:
                with FrameContext(renderer, clip, 5, 12) as context:
                    actual = self.checks(renderer, clip, context)
                    self.assertEqual(meshes.call_count, 5)
                self.assertEqual(context.cached_bytes, 0)
            self.assertEqual(actual, expected)

    def test_cached_mesh_damage_still_names_the_exact_connection_frame(self):
        renderer, clip = self.fixture()
        real = renderer.art.puppet.meshes
        current = -1
        def cloth(*_):
            nonlocal current
            current += 1
            return {}
        renderer.cloth_at = cloth
        def damaged(*args, **kwargs):
            for layer, vertices in real(*args, **kwargs):
                if layer.name == 'leg_far' and current == 2:
                    vertices = vertices.copy()+[5., 0.]
                yield layer, vertices
        with patch.object(renderer.art.puppet, 'meshes', damaged):
            with FrameContext(renderer, clip, 5, 12) as context:
                puppet_check.check_motion(renderer, clip, 5, 12, context=context)
                faults = puppet_check.check_connections(renderer, clip, 5, 12, context=context)
        self.assertTrue(any('leg_far: stride frame 2:' in fault for fault in faults), faults)
        self.assertFalse(any('frame 0:' in fault for fault in faults), faults)

    def test_small_capacity_recomputes_without_changing_decisions(self):
        renderer, clip = self.fixture()
        expected = self.checks(renderer, clip)
        with FrameContext(renderer, clip, 5, 12, max_bytes=1, max_frames=2) as context:
            self.assertEqual(self.checks(renderer, clip, context), expected)
            self.assertLessEqual(context.cached_bytes, 1)
            self.assertLessEqual(len(context._samples), 2)
            self.assertLessEqual(len(context._cloth), 2)

    def test_canvas_scales_and_sampling_clocks_cannot_share_the_wrong_mesh(self):
        renderer, clip = self.fixture()
        with FrameContext(renderer, clip, 5, 12) as context:
            for ss in (1, 2):
                cv = Canvas(renderer.size, ss, renderer.unit, GROUND_FRAC, 1, False, (0, 0, 0))
                _, pose, sk = context.sample(0)
                cv.set_squash(pose['squash'], 0.)
                expected = list(renderer.art.puppet.meshes(cv, sk, renderer.cloth_at(clip, 0)))
                actual = context.meshes(0, cv)
                for (_, a), (_, b) in zip(actual, expected):
                    np.testing.assert_array_equal(a, b)
            with self.assertRaisesRegex(ValueError, 'sampling clock'):
                context.require(renderer, clip, 5, 24)


class ReviewPreparation(unittest.TestCase):
    def test_image_cache_is_bounded_isolated_and_fresh_between_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'frame.png'
            doc = {}
            Image.new('RGBA', (4, 4), 'red').save(path)
            def load(*_):
                with Image.open(path) as image:
                    return image.convert('RGBA')
            with patch.object(Image, 'open', wraps=Image.open) as opened:
                with ReviewFrames(directory, doc, load, max_bytes=64) as frames:
                    first = frames.read(directory, doc, 'idle', 0)
                    first.putpixel((0, 0), (0, 0, 0, 0))
                    self.assertEqual(frames.read(directory, doc, 'idle', 0).getpixel((0, 0)), (255, 0, 0, 255))
                    self.assertEqual(opened.call_count, 1)
                    frames.read(directory, doc, 'idle', 1)
                    self.assertLessEqual(frames.cached_bytes, 64)
                self.assertEqual(frames.cached_bytes, 0)
            Image.new('RGBA', (4, 4), 'blue').save(path)
            with ReviewFrames(directory, doc, load) as frames:
                self.assertEqual(frames.read(directory, doc, 'idle', 0).getpixel((0, 0)), (0, 0, 255, 255))

    def test_media_keeps_original_rounding_and_complete_paired_steps(self):
        meta = dict(frames=list(range(22)), fps=30, loop=True)
        media, durations = playback_media(meta, 'run', 'run.gif', parts=2)
        self.assertEqual(durations[:11], durations[11:])
        self.assertEqual(media['duration_ms'], 740)
        self.assertEqual(media['frame_count'], 22)


if __name__ == '__main__':
    unittest.main()
