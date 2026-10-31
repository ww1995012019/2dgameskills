"""Synchronize or check the original mode files in the unified skill snapshot."""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = ("game-sprite-animator", "game-shooter-animator", "game-topdown-animator", "game-quadruped-animator")

# The unified bundle owns one copy of each listed module. Standalone skills keep
# their own copies. Executing in the importing module's namespace preserves
# monkeypatches and module globals as well as relative imports.
SHARED_MODULES = {"scripts/sprite_anim/export.py", "scripts/sprite_anim/integrity.py",
                  "scripts/sprite_anim/mathx.py"}
ADAPTER = '''"""Use a shared sprite module from the unified bundle."""
from pathlib import Path as _Path

_source = (_Path(__file__).resolve().parents[3] / "game-sprite-animator" /
           "scripts" / "sprite_anim" / _Path(__file__).name)
exec(compile(_source.read_bytes(), str(_source), "exec"), globals())
del _source, _Path
'''.encode("utf-8")


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
            relative = source.relative_to(ROOT / mode).as_posix()
            is_adapter = mode != MODES[0] and relative in SHARED_MODULES
            data = ADAPTER if is_adapter else source.read_bytes()
            actual = dest.read_bytes() if dest.exists() else None
            if is_adapter and actual is not None:
                actual = actual.replace(b"\r\n", b"\n")
            if actual != data:
                mismatch.append(str(dest.relative_to(ROOT)))
                if not args.check:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
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
