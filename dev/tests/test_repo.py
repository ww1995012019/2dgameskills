"""Repo hygiene: generated standalone folders match game-animator, packages match tracked files."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "dev", script), *args], capture_output=True, text=True)


class TestRepo(unittest.TestCase):
    def test_standalone_folders_generated_from_unified(self):
        p = run("build_standalone.py", "--check")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_packages_up_to_date(self):
        p = run("package_skills.py", "--check")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
