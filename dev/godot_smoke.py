#!/usr/bin/env python3
"""Import a generated set into Godot 4 and run dev/godot/smoke_test.gd on it.

    bash dev/engines/get_godot.sh                            # once, Linux: official 4.3 build
    python dev/godot_smoke.py out/hero                       # Godot from $GODOT, dev/engines or PATH
    python dev/godot_smoke.py out/hero --godot ./Godot_v4.3-stable_linux.x86_64 --hz 60,144

Builds a throwaway project the way engine-integration.md tells users to: atlas pages, their
.import settings and engine/godot/sprite_frames.tres at the project root. Then lets the editor import it headless and
runs the smoke test once per tick rate. Exit 1 if any run fails.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def find_godot(explicit=None):
    local = os.path.join(HERE, "engines", "godot", "Godot_v4.3-stable_linux.x86_64")
    return (explicit or os.environ.get("GODOT") or (local if os.path.exists(local) else None)
            or shutil.which("godot") or shutil.which("godot4"))


def run(set_dir, godot, rates=(60, 144), keep=None, import_settings=True, all_clips=False):
    set_dir = os.path.abspath(set_dir)
    with open(os.path.join(set_dir, "animations.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    proj = keep or tempfile.mkdtemp(prefix="godot_smoke_")
    try:
        with open(os.path.join(proj, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write('config_version=5\n\n[application]\n\nconfig/name="sprite smoke test"\n')
        for p in doc["pages"]:
            shutil.copy(os.path.join(set_dir, p["file"]), proj)
            imp = os.path.join(set_dir, "engine", "godot", p["file"] + ".import")
            if import_settings and os.path.exists(imp):
                shutil.copy(imp, proj)
        shutil.copy(os.path.join(set_dir, "engine", "godot", "sprite_frames.tres"), proj)
        shutil.copy(os.path.join(HERE, "godot", "smoke_test.gd"), proj)
        imp = subprocess.run([godot, "--headless", "--path", proj, "--import"], capture_output=True, text=True, timeout=600)
        if not all(os.path.exists(os.path.join(proj, p["file"] + ".import")) for p in doc["pages"]):
            return False, "import failed:\n" + imp.stdout[-2000:] + imp.stderr[-2000:]
        log, ok = [], True
        for hz in rates:
            p = subprocess.run([godot, "--headless", "--path", proj, "--script", "res://smoke_test.gd",
                                "--fixed-fps", str(hz), "--", set_dir, str(hz), "all" if all_clips else "representative"], capture_output=True, text=True, timeout=600)
            out = "\n".join(l for l in p.stdout.splitlines() if l.startswith(("FAIL", "RESULT", "played", "frames checked")))
            errs = "\n".join(l for l in p.stderr.splitlines() if "ERROR" in l or "SCRIPT" in l)
            ok &= p.returncode == 0 and "RESULT ok" in out and not errs
            log.append(f"[{hz} Hz] exit {p.returncode}\n{out}" + (f"\n{errs}" if errs else ""))
        return ok, "\n".join(log)
    finally:
        if not keep:
            shutil.rmtree(proj, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("set_dir")
    ap.add_argument("--godot", help="Godot 4 binary; default $GODOT, dev/engines/godot, or godot on PATH")
    ap.add_argument("--hz", default="60,144", help="tick rates to play at")
    ap.add_argument("--keep", help="build the project in this folder and keep it")
    ap.add_argument("--default-import", action="store_true", help="leave out the exported .import files")
    ap.add_argument("--all-clips", action="store_true", help="play every clip at each tick rate")
    a = ap.parse_args()
    godot = find_godot(a.godot)
    if not godot:
        sys.exit("no Godot binary: pass --godot or set GODOT")
    if a.keep:
        os.makedirs(a.keep, exist_ok=True)
    ok, log = run(a.set_dir, godot, [int(x) for x in a.hz.split(",")], a.keep, not a.default_import, a.all_clips)
    print(log)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
