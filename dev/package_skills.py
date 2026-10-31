#!/usr/bin/env python3
"""Build the four mode packages and the unified game-animator.skill in the repo root.

    python dev/package_skills.py            # rebuild packages
    python dev/package_skills.py --check    # exit 1 if a package is out of date

A .skill is a zip of the skill folder. It holds exactly the git-tracked files of that folder, read
from the working tree, with a fixed timestamp so the package only changes when its content does.
Refuses to build while shared files or unified mode snapshots are out of sync.
"""
import argparse
import io
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = ("game-sprite-animator", "game-shooter-animator", "game-topdown-animator", "game-quadruped-animator", "game-animator")
STAMP = (2026, 1, 1, 0, 0, 0)


def tracked(skill):
    out = subprocess.run(["git", "ls-files", "-z", skill], cwd=ROOT, check=True, capture_output=True).stdout
    return sorted(p for p in out.decode("utf-8").split("\0") if p and os.path.isfile(os.path.join(ROOT, p)))


def check_frontmatter(skill):
    with open(os.path.join(ROOT, skill, "SKILL.md"), encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        sys.exit(f"{skill}/SKILL.md: no front matter")
    name = re.search(r"^name:\s*(\S+)", m.group(1), re.M)
    if not name or name.group(1) != skill:
        sys.exit(f"{skill}/SKILL.md: name must be {skill}")
    if not re.search(r"^description:", m.group(1), re.M):
        sys.exit(f"{skill}/SKILL.md: missing description")


def build(skill):
    if not tracked(skill):
        sys.exit(f"{skill}: no tracked files; register new source files with git add -N first")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in tracked(skill):
            info = zipfile.ZipInfo(p, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(os.path.join(ROOT, p), "rb") as fh:
                z.writestr(info, fh.read())
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="compare instead of writing")
    a = ap.parse_args()
    if subprocess.run([sys.executable, os.path.join(ROOT, "dev", "sync_shared.py"), "--check"]).returncode:
        sys.exit(1)
    if subprocess.run([sys.executable, os.path.join(ROOT, "dev", "sync_modes.py"), "--check"]).returncode:
        sys.exit("unified modes out of sync; run dev/sync_modes.py and register new paths")
    stale = []
    for skill in SKILLS:
        check_frontmatter(skill)
        data, dst = build(skill), os.path.join(ROOT, f"{skill}.skill")
        old = open(dst, "rb").read() if os.path.exists(dst) else None
        if data == old:
            print(f"[ok] {skill}.skill up to date")
        elif a.check:
            stale.append(skill)
        else:
            with open(dst, "wb") as fh:
                fh.write(data)
            print(f"[pack] {skill}.skill ({len(tracked(skill))} files, {len(data) // 1024} KB)")
    if stale:
        sys.exit("out of date, run dev/package_skills.py: " + ", ".join(f"{s}.skill" for s in stale))


if __name__ == "__main__":
    main()
