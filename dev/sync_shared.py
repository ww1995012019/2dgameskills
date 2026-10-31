#!/usr/bin/env python3
"""Copy shared/ into both skills, or check that the copies still match.

    python dev/sync_shared.py           # copy shared/<path> to <skill>/<path> for both skills
    python dev/sync_shared.py --check   # exit 1 if any copy differs from shared/

Each skill has to install on its own, so the files they share are committed in both. shared/ is
the one place to edit them; the copies are overwritten by this script.
"""
import argparse
import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(ROOT, "shared")
SKILLS = ("game-sprite-animator", "game-shooter-animator", "game-topdown-animator", "game-quadruped-animator")
QUADRUPED_FILES = {"scripts/sprite_anim/export.py", "scripts/sprite_anim/mathx.py", "scripts/sprite_anim/cloth.py", "scripts/sprite_anim/rig_data.py", "scripts/sprite_anim/integrity.py", "references/skeleton-qa.md", "assets/engine/unity/SpriteSetImporter.cs"}
TOPDOWN_FILES = {"scripts/sprite_anim/export.py", "scripts/sprite_anim/integrity.py", "references/skeleton-qa.md", "assets/engine/unity/SpriteSetImporter.cs"}


def shared_files():
    for d, _, files in os.walk(SHARED):
        for f in files:
            if f.endswith(".pyc"):
                continue
            yield os.path.relpath(os.path.join(d, f), SHARED)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report drift instead of copying")
    a = ap.parse_args()
    stale = []
    for rel in sorted(shared_files()):
        src = os.path.join(SHARED, rel)
        for skill in SKILLS:
            if skill == "game-topdown-animator" and rel.replace(os.sep, "/") not in TOPDOWN_FILES:
                continue
            if skill == "game-quadruped-animator" and rel.replace(os.sep, "/") not in QUADRUPED_FILES:
                continue
            dst = os.path.join(ROOT, skill, rel)
            if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
                continue
            if a.check:
                stale.append(f"{skill}/{rel}")
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
                print(f"[sync] {skill}/{rel}")
    if stale:
        print("out of sync with shared/ (edit shared/, then run dev/sync_shared.py):")
        print("\n".join(f"  {s}" for s in stale))
        sys.exit(1)
    if a.check:
        print("shared files in sync")


if __name__ == "__main__":
    main()
