"""Packages should not change with the checkout's line endings."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from package_skills import package_content


class PackageLineEndings(unittest.TestCase):
    def test_text_normalizes_crlf_but_binary_is_untouched(self):
        for suffix in ('.py', '.md', '.json', '.html', '.js', '.cs'):
            with self.subTest(suffix=suffix):
                self.assertEqual(package_content('file' + suffix, b'a\r\nb\r\n'), b'a\nb\n')
        self.assertEqual(package_content('image.png', b'\x89PNG\r\n'), b'\x89PNG\r\n')


if __name__ == '__main__':
    unittest.main()
