"""Repo hygiene: shared files match their copies, packages match the tracked files."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "dev", script), *args], capture_output=True, text=True)


class TestRepo(unittest.TestCase):
    def test_shared_files_in_sync(self):
        p = run("sync_shared.py", "--check")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_packages_up_to_date(self):
        p = run("package_skills.py", "--check")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
