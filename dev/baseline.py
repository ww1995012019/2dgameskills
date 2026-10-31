#!/usr/bin/env python3
"""Compare a full regression run against the recorded baseline, or record a new one.

    bash dev/regress_all.sh                       # writes $TEMP/spr/all/<set>
    python dev/baseline.py                        # compare those results with dev/baseline.json
    python dev/baseline.py --strict               # also fail if any frame's pixels changed
    python dev/baseline.py --update               # record the results as the new baseline

For every set and clip the baseline keeps the frame count, every QA status, the QA numbers and a
hash of the decoded frame pixels. Compared with it:
  regression   a status got worse (PASS -> WARN/FAIL), a clip or set went missing: exit 1
  changed      pixels or frame count differ; expected after an art or motion change, a bug after
               a refactor that should not touch the output (use --strict there)
  drift        a QA number moved; listed for review, never fails on its own
Run --update only after the changes are reviewed, and commit dev/baseline.json with them.
"""
import argparse
import glob
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE = os.path.join(HERE, "baseline.json")
STATUS = ("integrity", "tail", "gait", "structure", "direction", "phase", "hold", "seam", "spike", "slide", "jitter", "grip", "cadence", "limits", "clip", "float", "bones", "bounds")
NUMBERS = ("tail_length_error", "seam_ratio", "joint_seam_ratio", "joint_seam_height", "joint_gait_seam_ratio", "spike_ratio", "slide_px", "hover_px", "foot_wobble_px", "excess_deg",
           "bone_err", "weapon_head", "weapon_ground", "body_ground", "grip_px", "shots")
# n/a ranks below PASS so a check that stops running counts as a regression, not as no change.
RANK = {"PASS": 0, "n/a": 1, "WARN": 1, "FAIL": 2}


def pixels_hash(paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(np.asarray(Image.open(p).convert("RGBA")).tobytes())
    return h.hexdigest()[:16]


def snapshot_set(d):
    with open(os.path.join(d, "qa_report.json"), encoding="utf-8") as fh:
        qa = json.load(fh)
    clips = {}
    for name, r in qa["clips"].items():
        frames = sorted(glob.glob(os.path.join(d, "frames", name, "*.png")))
        c = {"frames": r["frames"], "pixels": pixels_hash(frames)}
        c.update({k: r[k] for k in STATUS if k in r})
        c.update({k: r[k] for k in NUMBERS if k in r})
        clips[name] = c
    trans = {f"{t['a']}->{t['b']}" + (f"[{t['group']}]" if "group" in t else ""): [t["status"], t["ratio"]] for t in qa.get("transitions", [])}
    return {"clips": clips, "transitions": trans}


def snapshot(results):
    sets = sorted(s for s in os.listdir(results) if os.path.exists(os.path.join(results, s, "qa_report.json")))
    return {s: snapshot_set(os.path.join(results, s)) for s in sets}


def compare(old, new, only_sets=None):
    reg, changed, drift = [], [], []
    for s, o in old.items():
        if only_sets is not None and s not in only_sets:
            continue
        if s not in new:
            reg.append(f"{s}: set missing")
            continue
        n = new[s]
        for clip, oc in o["clips"].items():
            nc = n["clips"].get(clip)
            if nc is None:
                reg.append(f"{s}/{clip}: clip missing")
                continue
            for k in STATUS:
                if k in oc and RANK[nc.get(k, "PASS")] > RANK[oc[k]]:
                    reg.append(f"{s}/{clip}: {k} {oc[k]} -> {nc.get(k)}")
            if nc["frames"] != oc["frames"]:
                changed.append(f"{s}/{clip}: frames {oc['frames']} -> {nc['frames']}")
            elif nc["pixels"] != oc["pixels"]:
                changed.append(f"{s}/{clip}: pixels changed")
            for k in NUMBERS:
                a, b = oc.get(k), nc.get(k)
                if a is not None and b is not None and abs(b - a) > max(0.02, 0.05 * abs(a)):
                    drift.append(f"{s}/{clip}: {k} {a} -> {b}")
        for clip in n["clips"].keys() - o["clips"].keys():
            changed.append(f"{s}/{clip}: new clip")
        for key, (st, ratio) in o["transitions"].items():
            got = n["transitions"].get(key)
            if got is None:
                reg.append(f"{s}: transition {key} missing")
            elif RANK[got[0]] > RANK[st]:
                reg.append(f"{s}: transition {key} {st} -> {got[0]}")
    if only_sets is None:
        for s in new.keys() - old.keys():
            changed.append(f"{s}: new set")
    return reg, changed, drift


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="?", default=os.path.join(os.environ.get("TEMP", "/tmp"), "spr", "all"))
    ap.add_argument("--update", action="store_true", help="record these results as the baseline")
    ap.add_argument("--strict", action="store_true", help="fail on any pixel or frame-count change")
    ap.add_argument("--partial", action="store_true", help="compare only the sets present (ONLY= runs)")
    a = ap.parse_args()
    new = snapshot(a.results)
    if not new:
        sys.exit(f"no results in {a.results}: run dev/regress_all.sh first")
    if a.update:
        with open(BASELINE, "w", encoding="utf-8") as fh:
            # One line per clip keeps the diff of a baseline update readable.
            fh.write("{\n" + ",\n".join(
                f' "{s}": {{"transitions": {json.dumps(v["transitions"], sort_keys=True)}, "clips": {{\n'
                + ",\n".join(f'  "{c}": {json.dumps(cv, sort_keys=True)}' for c, cv in v["clips"].items())
                + "}}" for s, v in new.items()) + "\n}\n")
        print(f"baseline recorded: {len(new)} sets, {sum(len(v['clips']) for v in new.values())} clips")
        return
    with open(BASELINE, encoding="utf-8") as fh:
        old = json.load(fh)
    reg, changed, drift = compare(old, new, set(new) if a.partial else None)
    for title, rows in (("regression", reg), ("changed", changed), ("drift", drift)):
        if rows:
            print(f"{title} ({len(rows)}):")
            print("\n".join(f"  {r}" for r in rows[:60]) + (f"\n  ... {len(rows) - 60} more" if len(rows) > 60 else ""))
    print(f"compared {len(new)} sets: {len(reg)} regressions, {len(changed)} changed, {len(drift)} drifted")
    sys.exit(1 if reg or (a.strict and changed) else 0)


if __name__ == "__main__":
    main()
