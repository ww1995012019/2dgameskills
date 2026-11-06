"""real_characters.py locks approved frames and reports any later change, with comparison GIFs."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('real_characters', ROOT / 'dev/real_characters.py')
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)
DEMO = ROOT / 'game-animator/modes/game-sprite-animator/assets/characters/cutout_demo/character.json'
SMALL = ['--extra', '--no-fx']


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = rc.main([str(a) for a in argv])
    return code, buf.getvalue()


class RealCharacters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / 'fixtures'
        cls.out = Path(cls.tmp.name) / 'out'
        code, text = run('--root', cls.root, 'add', 'demo', '--character', DEMO, '--clips', 'idle,run',
                         '--preset', 'pixel48', *SMALL)
        assert code == 0, text

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_1_unapproved_fixture_generates_and_says_so(self):
        code, text = run('--root', self.root, 'check', '--out', self.out)
        self.assertEqual(code, 0, text)
        self.assertIn('nothing is approved yet', text)
        meta = json.loads((self.root / 'demo/fixture.json').read_text())
        self.assertTrue((self.root / 'demo' / meta['character']).is_file())

    def test_2_approved_frames_are_locked_and_changes_are_shown(self):
        build = self.out / 'demo'
        if not (build / 'animations.json').is_file():
            run('--root', self.root, 'check', '--out', self.out)
        code, text = run('--root', self.root, 'approve', 'demo', '--build', build, '--by', 'unit test')
        self.assertEqual(code, 0, text)
        meta = json.loads((self.root / 'demo/fixture.json').read_text())
        self.assertEqual(meta['approved']['by'], 'unit test')
        self.assertTrue(meta['approved']['clips']['run']['frames'])

        code, text = run('--root', self.root, 'check', '--out', self.out)
        self.assertEqual(code, 0, text)
        self.assertIn('OK, all approved frames identical', text)

        # A change to the input art must be caught frame by frame and shown side by side.
        parts = sorted((self.root / 'demo/input').rglob('*.png'))
        self.assertTrue(parts)
        with Image.open(parts[0]) as im:
            im = im.convert('RGBA')
        px = im.load()
        for x in range(im.width):
            for y in range(im.height):
                r, g, b, a = px[x, y]
                if a:
                    px[x, y] = (255 - r, 255 - g, b, a)
        im.save(parts[0])
        code, text = run('--root', self.root, 'check', '--out', self.out, '--compare')
        self.assertEqual(code, 1, text)
        self.assertIn('CHANGED since approval by unit test', text)
        self.assertRegex(text, r'(idle|run): \d+/\d+ frames changed')
        self.assertTrue((self.out / 'demo/compare/run.gif').is_file())

    def test_missing_fixture_folder_is_not_a_failure(self):
        code, text = run('--root', Path(self.tmp.name) / 'none', 'check')
        self.assertEqual(code, 0)
        self.assertIn('no real-character fixtures', text)


if __name__ == '__main__':
    unittest.main()
