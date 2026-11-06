#!/usr/bin/env python3
"""Generate the deprecated standalone skill folders from the unified game-animator bundle.

    python dev/build_standalone.py           # rewrite the four standalone folders and shared copies
    python dev/build_standalone.py --check   # exit 1 if anything generated is stale

`game-animator/` is the only place to edit source. In particular:

* `game-animator/modes/<mode>/` holds each mode. Files shared by several modes are edited once,
  in `game-animator/modes/game-sprite-animator/`; the other modes receive a byte copy, or for the
  Python modules in ADAPTED an exec adapter that loads the sprite-mode file.
* `game-sprite-animator/`, `game-shooter-animator/`, `game-topdown-animator/` and
  `game-quadruped-animator/` are generated, deprecated standalone copies. Adapters are replaced by
  the real file so each folder still installs on its own, and SKILL.md gets a deprecation notice.

This replaces the former shared/ folder, dev/sync_shared.py and dev/sync_modes.py.
New files must be registered with `git add -N` before they are generated or packaged.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIFIED = ROOT / "game-animator" / "modes"
PRIMARY = "game-sprite-animator"
MODES = (PRIMARY, "game-shooter-animator", "game-topdown-animator", "game-quadruped-animator")

# Files maintained once in the primary mode and distributed to the other modes that need them.
SHARED = {
    "assets/engine/unity/SpriteSetImporter.cs": MODES[1:],
    "references/skeleton-qa.md": MODES[1:],
    "references/skin-binding-audit.md": ("game-shooter-animator",),
    "references/visual-review.md": ("game-shooter-animator",),
    "scripts/audit_skin_binding.py": ("game-shooter-animator",),
    "scripts/visual_review.py": ("game-shooter-animator",),
    "scripts/sprite_anim/cloth.py": ("game-shooter-animator", "game-quadruped-animator"),
    "scripts/sprite_anim/constraints.py": ("game-shooter-animator",),
    "scripts/sprite_anim/export.py": MODES[1:],
    "scripts/sprite_anim/integrity.py": MODES[1:],
    "scripts/sprite_anim/mathx.py": ("game-shooter-animator", "game-quadruped-animator"),
    "scripts/sprite_anim/rig_data.py": ("game-shooter-animator", "game-quadruped-animator"),
}
# Inside the unified bundle these are stored once and loaded through an adapter.
ADAPTED = {"scripts/sprite_anim/export.py", "scripts/sprite_anim/integrity.py",
           "scripts/sprite_anim/mathx.py"}
ADAPTER = '''"""Use a shared sprite module from the unified bundle."""
from pathlib import Path as _Path

_source = (_Path(__file__).resolve().parents[3] / "game-sprite-animator" /
           "scripts" / "sprite_anim" / _Path(__file__).name)
exec(compile(_source.read_bytes(), str(_source), "exec"), globals())
del _source, _Path
'''.encode("utf-8")
NOTICE = ("> **Deprecated standalone package.** Install `game-animator` instead; it contains this mode\n"
          "> unchanged. This folder is generated from `game-animator/modes/{mode}/` and is kept only for\n"
          "> existing installs.\n\n")
DESCRIPTION_PREFIX = "(Deprecated: use game-animator.) "


def tracked(prefix):
    out = subprocess.run(["git", "ls-files", "-z", "--", prefix], cwd=ROOT, check=True,
                         capture_output=True).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p and (ROOT / p).is_file()]


def normalise(data):
    return data.replace(b"\r\n", b"\n")


def deprecate_skill_md(data, mode):
    text = data.decode("utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"{mode}/SKILL.md: missing front matter")
    end = text.index("\n---\n", 4) + len("\n---\n")
    head, body = text[:end], text[end:]
    if "description: >\n  " in head:
        head = head.replace("description: >\n  ", "description: >\n  " + DESCRIPTION_PREFIX, 1)
    else:
        head = head.replace("description: ", "description: " + DESCRIPTION_PREFIX, 1)
    if DESCRIPTION_PREFIX not in head:
        raise SystemExit(f"{mode}/SKILL.md: no description line")
    body = body.lstrip("\n")
    return (head + "\n" + NOTICE.format(mode=mode) + body).encode("utf-8")


def expected_files():
    """Map every generated path to the bytes it must hold."""
    want = {}
    primary = UNIFIED / PRIMARY
    for rel, modes in SHARED.items():
        source = primary / rel
        if not source.is_file():
            raise SystemExit(f"shared source missing: {source.relative_to(ROOT)}")
        for mode in modes:
            want[UNIFIED / mode / rel] = ADAPTER if rel in ADAPTED else source.read_bytes()
    for mode in MODES:
        base = UNIFIED / mode
        for rel_path in tracked(str(base.relative_to(ROOT))):
            rel = (ROOT / rel_path).relative_to(base).as_posix()
            unified_file = base / rel
            data = want.get(unified_file, unified_file.read_bytes())
            if mode != PRIMARY and rel in ADAPTED:
                data = (primary / rel).read_bytes()
            if rel == "SKILL.md":
                data = deprecate_skill_md(data, mode)
            want[ROOT / mode / rel] = data
    return want


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report stale files instead of writing")
    args = parser.parse_args()
    want = expected_files()
    stale = []
    for path, data in sorted(want.items()):
        actual = path.read_bytes() if path.exists() else None
        if actual is not None and path.suffix != ".png" and normalise(actual) == normalise(data):
            continue
        if actual == data:
            continue
        stale.append(str(path.relative_to(ROOT)))
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    extras = []
    for mode in MODES:
        for rel_path in tracked(mode):
            if ROOT / rel_path not in want:
                extras.append(rel_path)
    if extras:
        print("tracked in a generated folder but absent from game-animator (move it into "
              "game-animator/modes/ or git rm it):")
        print("\n".join("  " + p for p in extras))
    if stale:
        print(("stale (edit game-animator/, then run dev/build_standalone.py):" if args.check
               else "regenerated:"))
        print("\n".join("  " + p for p in stale))
    if extras or (stale and args.check):
        return 1
    print("standalone folders match game-animator")
    return 0


if __name__ == "__main__":
    sys.exit(main())
