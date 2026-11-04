"""Custom action faults fail at the input boundary, without changing valid curves."""
import copy
import importlib
import importlib.util
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = '_custom_validation_sprite'
spec = importlib.util.spec_from_file_location(
    PACKAGE, ROOT / 'game-sprite-animator/scripts/sprite_anim/__init__.py')
module = importlib.util.module_from_spec(spec)
sys.modules[PACKAGE] = module
spec.loader.exec_module(module)
motions = importlib.import_module(PACKAGE + '.motions')


class CustomClipValidation(unittest.TestCase):
    def build(self, action):
        return motions.build_clips(custom={'gesture': action})['gesture']

    def test_invalid_keys_identify_action(self):
        faults = [None, [], [[0]], [[0, []]], [[0, {}], [0, {}]],
                  [[0, {}], [-1, {}]], [[1, {}], [2, {}]],
                  [[False, {}], [1, {}]], [[0, {}], [float('inf'), {}]],
                  [[0, {}], [1, {'arm_n_upp': 20}]],
                  [[0, {}], [1, {'root_y': float('nan')}]],
                  [[0, {}], [1, {'root_y': True}]],
                  [[0, {}], [1, {'squash': 0}]],
                  [[0, {}], [1, {'ik_body': 2}]], [[0, {}]]]
        for keys in faults:
            with self.subTest(keys=keys), self.assertRaisesRegex(ValueError, 'custom_clips.gesture'):
                self.build({'keys': keys})

    def test_invalid_metadata_identifies_action(self):
        faults = [{'loop': 'false'}, {'next': 'missing'}, {'prev': []},
                  {'next_at': float('nan')}, {'next_at': True}, {'next_at': 1.1},
                  {'next_at': 1, 'next': None}, {'period': 2},
                  {'events': [[-1, 'sound']]}, {'events': [[2, 'sound']]},
                  {'events': [[0.5, '']]}, {'events': [[True, 'sound']]},
                  {'events': 'sound'}, {'tags': 'ground'}, {'tags': [1]}]
        for fields in faults:
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'custom_clips.gesture'):
                self.build(dict(keys=[[0, {}], [1, {}]], **fields))

    def test_invalid_container_fails_clearly(self):
        for custom in ([], {'gesture': None}, {'': {'keys': [[0, {}], [1, {}]]}}):
            with self.subTest(custom=custom), self.assertRaisesRegex(ValueError, 'custom_clips'):
                motions.build_clips(custom=custom)

    def test_loop_faults_rejected(self):
        for period in (0, -1, True, float('inf'), 0.5, 1):
            with self.subTest(period=period), self.assertRaisesRegex(ValueError, 'custom_clips.gesture'):
                self.build({'loop': True, 'period': period,
                            'keys': [[0, {'root_x': 0}], [1, {'root_x': 20}]]})
        with self.assertRaisesRegex(ValueError, 'next_at'):
            self.build({'loop': True, 'period': 2, 'next_at': 1,
                        'keys': [[0, {}], [1, {}]]})

    def test_open_closed_and_constant_loops_remain_supported(self):
        actions = [
            {'loop': True, 'keys': [[0, {}], [0.5, {'root_x': 10}], [1, {}]]},
            {'loop': True, 'period': 2, 'keys': [[0, {}], [1, {'root_x': 10}]]},
            {'loop': True, 'period': 2, 'keys': [[0, {}]]},
        ]
        for action in actions:
            with self.subTest(action=action):
                clip = self.build(action)
                self.assertAlmostEqual(clip.sample(clip.duration - 1e-8)['root_x'],
                                       clip.sample(0)['root_x'], delta=1e-5)

    def test_forward_references_and_terminal_actions(self):
        clips = motions.build_clips(custom={
            'first': {'keys': [[0, {}], [1, {}]], 'next': 'second'},
            'second': {'keys': [[0, {}], [1, {}]], 'prev': 'first', 'next': None}})
        self.assertEqual(clips['first'].next, 'second')
        self.assertIsNone(clips['second'].next)

    def test_next_at_is_forwarded_without_retiming(self):
        for speed in (0.8, 1, 1.3):
            clip = motions.build_clips(style={'speed': speed}, custom={
                'gesture': {'keys': [[0, {}], [1, {}]], 'next': 'block', 'next_at': 1}})['gesture']
            self.assertEqual(clip.next_at, 1)
            self.assertEqual(clip.next, 'block')
            self.assertAlmostEqual(clip.duration, 1 / speed)

    def test_next_at_reaches_exported_hold_frame(self):
        skill = ROOT / 'game-sprite-animator'
        character = json.loads((skill / 'assets/characters/hero.json').read_text())
        character['cloth'] = []
        character['custom_clips'] = {'gesture': {
            'keys': [[0, {}], [0.3, {}]], 'next': 'block', 'next_at': 1}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'character.json'
            source.write_text(json.dumps(character))
            out = root / 'out'
            subprocess.run([sys.executable, str(skill / 'scripts/generate.py'),
                            '--character', str(source), '--preset', 'pixel48',
                            '--clips', 'gesture,block', '--no-fx', '--out', str(out)],
                           check=True, capture_output=True)
            clips = json.loads((out / 'animations.json').read_text())['clips']
            self.assertEqual(clips['gesture']['next'], 'block')
            self.assertEqual(clips['gesture']['next_frame'], len(clips['block']['frames']) - 1)

    def test_existing_goblin_samples_match_prevalidation_construction(self):
        character = json.loads((ROOT / 'game-sprite-animator/assets/characters/goblin.json').read_text())
        action = character['custom_clips']['taunt']
        original = copy.deepcopy(action)
        for speed in (0.8, 1, 1.3):
            clips = motions.build_clips(style={'speed': speed}, custom={'taunt': action})
            idle = clips['idle'].sample(0)
            expected = motions.Keyed('taunt', [(t * (1.0 / speed), motions.P(idle, **pose))
                                               for t, pose in action['keys']],
                                     prev=action.get('prev', 'idle'), next=action.get('next', 'idle'),
                                     events=[(t * (1.0 / speed), n) for t, n in action.get('events', [])],
                                     tags=tuple(action.get('tags', ())))
            actual = clips['taunt']
            self.assertEqual(actual.events, expected.events)
            for step in range(21):
                t = step * actual.duration / 20
                for channel in motions.CH:
                    self.assertAlmostEqual(actual.sample(t)[channel], expected.sample(t)[channel], places=12)
        self.assertEqual(action, original)


if __name__ == '__main__':
    unittest.main()
