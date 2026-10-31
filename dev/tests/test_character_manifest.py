"""The shared manifest resolves consistently and drives both existing modes."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'game-animator/scripts/generate_character.py'
MODULE_SPEC = importlib.util.spec_from_file_location('shared_character_manifest', SCRIPT)
manifest_tool = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(manifest_tool)


class CharacterManifest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'character.json'
        self.data = {
            'name': 'shared hero',
            'palette': {'coat': '#112233', 'hair': '#445566', 'trim': '#aabbcc'},
            'body': {'head_size': 0.9},
            'views': {
                'side': {'base': str(ROOT / 'game-animator/modes/game-sprite-animator/assets/characters/hero.json')},
                'topdown': {'base': str(ROOT / 'game-animator/modes/game-topdown-animator/assets/characters/wanderer.json')},
            },
        }
        self.write_manifest()
        self.addCleanup(self.temp.cleanup)

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.data), encoding='utf-8')

    def test_view_mapping_and_overrides(self):
        self.data['views']['side']['overrides'] = {'colors': {'tunic': '#abcdef'}}
        self.write_manifest()
        side = manifest_tool.resolve_character(self.manifest, 'side')
        top = manifest_tool.resolve_character(self.manifest, 'topdown')
        self.assertEqual(side['name'], top['name'])
        self.assertEqual(side['colors']['tunic'], '#abcdef')
        self.assertEqual(top['colors']['coat'], '#112233')
        self.assertEqual(side['colors']['hair'], top['colors']['hair'])
        self.assertEqual(side['body']['head_size'], 0.9)
        self.assertNotIn('body', top)

    def test_relative_art_paths_remain_relative_to_base(self):
        base = self.root / 'assets/base.json'
        base.parent.mkdir()
        base.write_text(json.dumps({'parts': {'head': {'image': 'parts/head.png'}}}), encoding='utf-8')
        self.data['views']['side']['base'] = 'assets/base.json'
        self.write_manifest()
        result = manifest_tool.resolve_character(self.manifest, 'side')
        self.assertEqual(Path(result['parts']['head']['image']), base.parent / 'parts/head.png')

    def test_rejects_invalid_palette(self):
        for palette in ({'coat': 'red'}, {'unknown': '#123456'}):
            self.data['palette'] = palette
            self.write_manifest()
            with self.subTest(palette=palette), self.assertRaises(ValueError):
                manifest_tool.resolve_character(self.manifest, 'side')

    def test_generate_both_views_and_refuse_overwrite(self):
        for view in ('side', 'topdown'):
            out = self.root / view
            command = [sys.executable, str(SCRIPT), '--manifest', str(self.manifest), '--view', view,
                       '--out', str(out), '--preset', 'pixel48', '--size', '32', '--fps', '8', '--clips', 'idle']
            subprocess.run(command, check=True, capture_output=True)
            self.assertTrue((out / 'preview.html').exists())
            self.assertTrue((out / 'atlas.png').exists())
            self.assertTrue(any((out / 'frames').rglob('*.png')))
            resolved = json.loads((out / 'character-resolved.json').read_text(encoding='utf-8'))
            self.assertEqual(resolved['name'], 'shared hero')
            before = (out / 'atlas.png').read_bytes()
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(before, (out / 'atlas.png').read_bytes())

    def test_cutout_base_loads_its_relative_pngs(self):
        base = ROOT / 'game-animator/modes/game-sprite-animator/assets/characters/cutout_demo/character.json'
        self.data['views']['side']['base'] = str(base)
        self.write_manifest()
        out = self.root / 'cutout'
        subprocess.run([sys.executable, str(SCRIPT), '--manifest', str(self.manifest), '--view', 'side',
                        '--out', str(out), '--preset', 'pixel48', '--size', '48', '--fps', '8', '--clips', 'idle'],
                       check=True, capture_output=True)
        resolved = json.loads((out / 'character-resolved.json').read_text(encoding='utf-8'))
        self.assertTrue(Path(resolved['parts']['head']['image']).is_file())
        self.assertTrue((out / 'frames/idle/idle_000.png').is_file())


if __name__ == '__main__':
    unittest.main()
