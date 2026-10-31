"""Synchronize or check the original mode files in the unified skill snapshot."""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = ("game-sprite-animator", "game-shooter-animator", "game-topdown-animator", "game-quadruped-animator")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    mismatch = []
    for mode in MODES:
        result = subprocess.run(["git", "ls-files", "-z", "--", mode], cwd=ROOT, check=True, capture_output=True)
        expected = set()
        for rel in filter(None, result.stdout.decode("utf-8").split("\0")):
            source = ROOT / rel
            if not source.is_file():
                continue
            dest = ROOT / "game-animator" / "modes" / mode / source.relative_to(ROOT / mode)
            expected.add(dest)
            if not dest.exists() or source.read_bytes() != dest.read_bytes():
                mismatch.append(str(dest.relative_to(ROOT)))
                if not args.check:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(source.read_bytes())
        folder = ROOT / "game-animator" / "modes" / mode
        if folder.exists():
            for extra in folder.rglob("*"):
                if extra.is_file() and "__pycache__" not in extra.parts and extra not in expected:
                    mismatch.append(str(extra.relative_to(ROOT)) + " (extra; remove manually)")
    if mismatch:
        print("\n".join(mismatch))
        if args.check or any(" (extra; remove manually)" in x for x in mismatch):
            return 1
    print("unified modes in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
