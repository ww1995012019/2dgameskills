"""Foot contacts and authored loop timing stay continuous when motion is retimed."""
import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_motion(mode):
    # Keep the two standalone sprite_anim packages isolated from each other and
    # from modules imported by other test files in unittest discovery.
    name = "_timing_" + mode.replace("-", "_")
    spec = importlib.util.spec_from_file_location(
        name, ROOT / mode / "scripts/sprite_anim/__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return importlib.import_module(name + ".motions")


class MotionTiming(unittest.TestCase):
    def test_gait_horizontal_velocity_matches_at_both_contacts(self):
        for mode in ("game-sprite-animator", "game-shooter-animator"):
            motions = load_motion(mode)
            for clip in motions.build_clips().values():
                if not isinstance(clip, motions.Gait):
                    continue
                with self.subTest(mode=mode, clip=clip.name):
                    eps = 1e-7
                    x = lambda phase: clip.foot(phase)[0]
                    for boundary in (clip.duty, 1.0):
                        center = x(boundary % 1)
                        before = (center - x(boundary - eps)) / (eps * clip.T)
                        after = (x((boundary + eps) % 1) - center) / (eps * clip.T)
                        self.assertAlmostEqual(before, -clip.speed, delta=0.01)
                        self.assertAlmostEqual(after, -clip.speed, delta=0.01)
                    if mode == 'game-sprite-animator' and clip.name == 'walk':
                        render = importlib.import_module(motions.__package__ + '.render')
                        for count in (7, 9, 13, 20, 25):
                            phase = render.walk_hold_phase(clip, count)
                            for p in (phase, phase+.5):
                                frame = __import__('math').floor(p*count+1e-10)
                                self.assertTrue(all(clip.contacts(frame*clip.duration/count).values()))
                        for count in (3, 5):
                            with self.assertRaisesRegex(ValueError, 'double-support'):
                                render.walk_hold_phase(clip, count)

    def test_custom_loop_retimes_period_keys_and_events_together(self):
        motions = load_motion("game-sprite-animator")
        for explicit_period in (False, True):
            for speed in (0.8, 1.0, 1.3):
                with self.subTest(explicit_period=explicit_period, speed=speed):
                    spec = {"loop": True,
                            "keys": [(0, {"root_x": 0}),
                                     (0.5, {"root_x": 10}), (1, {"root_x": 0})],
                            "events": [(0.5, "marker")]}
                    if explicit_period:
                        spec["period"] = 1.0
                    clip = motions.build_clips(style={"speed": speed},
                                               custom={"loop_test": spec})["loop_test"]
                    self.assertAlmostEqual(clip.duration, 1 / speed)
                    self.assertAlmostEqual(clip.sample(0.5 / speed)["root_x"], 10)
                    self.assertEqual(clip.events, [(0.5 / speed, "marker")])
                    self.assertAlmostEqual(clip.sample(clip.duration - 1e-7)["root_x"],
                                           clip.sample(0)["root_x"], delta=1e-6)

    def test_explicit_loop_rest_interval_scales_with_speed(self):
        motions = load_motion("game-sprite-animator")
        for speed in (0.8, 1.3):
            with self.subTest(speed=speed):
                clip = motions.build_clips(style={"speed": speed}, custom={
                    "loop_test": {"loop": True, "period": 2,
                                  "keys": [(0, {"root_x": 0}),
                                           (0.5, {"root_x": 10}),
                                           (1, {"root_x": 0})]}})["loop_test"]
                self.assertAlmostEqual(clip.duration, 2 / speed)
                self.assertAlmostEqual(clip.sample(1.5 / speed)["root_x"], 0)


class ExportPlaybackClock(unittest.TestCase):
    def test_exported_fps_speed_and_qa_share_the_player_clock(self):
        import numpy as np
        skill = ROOT / 'game-sprite-animator'
        spec = json.loads((skill/'assets/characters/hero.json').read_text())
        spec['cloth'] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'character.json'
            source.write_text(json.dumps(spec))
            out = root/'out'
            result = subprocess.run([sys.executable, str(skill/'scripts/generate.py'),
                '--character', str(source), '--preset', 'hd512', '--fps', '24',
                '--fps-override', 'walk=15', '--clips', 'walk,run,roll', '--no-fx', '--out', str(out)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            doc = json.loads((out/'animations.json').read_text())
            trace = json.loads((out/'rig_trace.json').read_text())
            for name, clip in doc['clips'].items():
                with self.subTest(clip=name):
                    fps, n = clip['fps'], len(clip['frames'])
                    self.assertEqual(fps, 15 if name == 'walk' else 24)
                    self.assertAlmostEqual(clip['duration'], n/fps)
                    self.assertAlmostEqual(trace['traces'][name]['frame_dt'], 1/fps)
                    if name == 'roll':
                        continue
                    tr = trace['traces'][name]
                    drift = []
                    for side in 'nf':
                        heel, ball = (tr['feet'][side][k] for k in ('heel', 'ball'))
                        c = tr['contacts'][side]
                        for i in range(n):
                            j = (i+1) % n
                            if not (c[i] and c[j]):
                                continue
                            p = heel if heel[i][1]+heel[j][1] <= ball[i][1]+ball[j][1] else ball
                            drift.append(p[j][0]-p[i][0]+clip['speed_px_s']/fps)
                    self.assertTrue(drift)
                    self.assertLess(float(np.mean(np.abs(drift))), .03)
                    clock = clip['locomotion'] if name == 'walk' else None
                    if clock:
                        self.assertAlmostEqual(clock['period_s'], n/fps)
                        self.assertAlmostEqual(clock['speed_px_s'], clip['speed_px_s'], delta=.0051)
            command = [sys.executable, str(skill/'scripts/qa_motion.py'), str(out)]
            clean = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(clean.returncode, 0, clean.stdout+clean.stderr)
            clean_doc = json.dumps(doc)
            clean_trace = json.dumps(trace)
            report = json.loads((out/'qa_report.json').read_text())
            self.assertEqual(report['locomotion']['status'], 'PASS')
            # Reintroduce the former speed/trace clock mismatch. QA must detect
            # it using the manifest's actual FPS, even if the sidecar claims a
            # different sampling interval. This is the original 512px defect.
            run = doc['clips']['run']
            run['speed_px_s'] *= len(run['frames']) / (run['source_duration']*run['fps'])
            trace['traces']['run']['frame_dt'] = run['source_duration']/len(run['frames'])
            (out/'animations.json').write_text(json.dumps(doc))
            (out/'rig_trace.json').write_text(json.dumps(trace))
            broken = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(broken.returncode, 1, broken.stdout+broken.stderr)
            report = json.loads((out/'qa_report.json').read_text())
            self.assertEqual(report['clips']['run']['slide'], 'FAIL')
            for fault in ('missing_policy', 'wrong_period', 'unplanted_stop'):
                with self.subTest(fault=fault):
                    doc, trace = json.loads(clean_doc), json.loads(clean_trace)
                    if fault == 'missing_policy':
                        del doc['clips']['walk']['locomotion']
                    elif fault == 'wrong_period':
                        doc['clips']['walk']['locomotion']['period_s'] *= .9
                    else:
                        trace['traces']['walk']['contacts']['f'][0] = False
                    (out/'animations.json').write_text(json.dumps(doc))
                    (out/'rig_trace.json').write_text(json.dumps(trace))
                    broken = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(broken.returncode, 1, broken.stdout+broken.stderr)
                    report = json.loads((out/'qa_report.json').read_text())
                    self.assertEqual(report['locomotion']['status'], 'FAIL')
                    self.assertIn('0', report['clips']['walk']['flags'])


if __name__ == "__main__":
    unittest.main()
