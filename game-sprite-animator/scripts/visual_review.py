#!/usr/bin/env python3
"""AI visual QA: build review sheets, then record the reviewer's verdict.

Numbers catch what can be measured. Whether a pose looks right can't be, so the agent running this
skill looks at the sheets itself, against references/visual-review.md.

    python visual_review.py out/hero                       # writes out/hero/review/*.png + index.json
    python visual_review.py out/hero --record verdict.json # validates the verdict, exit 1 if unresolved

Each sheet shows key poses plus every frame QA flagged (red border). The bottom row of each clip is
the same poses as black silhouettes: a pose that doesn't read in silhouette doesn't read in game.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

CELL = 180
PER_SHEET = 6
MAX_POSES = 8
GROUND = (240, 184, 74, 255)
BG = (58, 62, 74, 255)


def pick_frames(n, flagged):
    """Evenly spaced poses, with QA-flagged frames forced in."""
    even = {round(i * (n - 1) / max(1, MAX_POSES - 1)) for i in range(MAX_POSES)} if n > MAX_POSES else set(range(n))
    picked = sorted(even | {f for f in flagged if f < n})
    while len(picked) > MAX_POSES:
        for i in picked:
            if i not in flagged:
                picked.remove(i)
                break
        else:
            picked = picked[:MAX_POSES]
    return picked


def silhouette(im):
    a = np.asarray(im)
    out = np.zeros_like(a)
    out[..., 3] = a[..., 3]
    return Image.fromarray(out, "RGBA")


def composite(root, doc, name, i):
    """Upper-body clips are half a character; review them on the idle legs so the pose reads."""
    path = os.path.join(root, "frames", name, f"{name}_{i:03d}.png")
    im = Image.open(path).convert("RGBA")
    c = doc["clips"][name]
    if c.get("layer") == "upper" and "idle" in doc["clips"]:
        legs = Image.open(os.path.join(root, "frames", "idle", "idle_000.png")).convert("RGBA")
        ax, ay = doc["clips"]["idle"]["anchors"][0]
        base = Image.new("RGBA", im.size, (0, 0, 0, 0))
        base.alpha_composite(legs)
        base.alpha_composite(im, (int(round(ax)), int(round(ay))) if ax >= 0 and ay >= 0 else (0, 0))
        return base
    if c.get("layer") == "lower" and "anchors" in c:
        return im
    return im


def draw_clip(sheet, d, root, doc, name, flagged, y, zoom):
    c = doc["clips"][name]
    n = len(c["frames"])
    picks = pick_frames(n, flagged)
    size = doc["frame_size"]
    d.text((4, y + 2), f"{name}  ({n}f @ {c['fps']}fps, {'loop' if c['loop'] else 'once'})", fill=(255, 255, 255, 255))
    gy = int(doc["pivot"][1] * CELL / size)
    for k, i in enumerate(picks):
        im = composite(root, doc, name, i).resize((CELL, CELL), Image.NEAREST if size < 128 else Image.LANCZOS)
        x, top = k * CELL, y + 16
        d.line((x, top + gy, x + CELL - 1, top + gy), fill=GROUND)
        sheet.alpha_composite(im, (x, top))
        sheet.alpha_composite(silhouette(im), (x, top + CELL))
        d.text((x + 4, top + 3), f"#{i}", fill=(255, 255, 255, 255))
        if i in flagged:
            d.rectangle((x, top, x + CELL - 1, top + CELL - 1), outline=(240, 70, 70, 255), width=3)
    return y + 16 + CELL * 2


def build(root):
    with open(os.path.join(root, "animations.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    qa = {}
    qp = os.path.join(root, "qa_report.json")
    if os.path.exists(qp):
        with open(qp, encoding="utf-8") as fh:
            qa = json.load(fh).get("clips", {})
    out = os.path.join(root, "review")
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "*.png")):
        os.remove(old)

    def key(name):
        """Clips QA is unsure about first, then the rest. Near-identical aim variants review as one."""
        return (0 if qa.get(name, {}).get("flags") else 1, name)

    names = []
    for n in sorted(doc["clips"], key=key):
        c = doc["clips"][n]
        tag = n.rsplit("_", 1)[-1]
        sparse = c.get("layer") == "upper" and ("_aim_" in n or "_fire_" in n) and tag not in ("0", "p90", "m90", "p45", "m45")
        if sparse and not qa.get(n, {}).get("flags"):
            continue
        names.append(n)

    index = []
    for s in range(0, len(names), PER_SHEET):
        group = names[s:s + PER_SHEET]
        sheet = Image.new("RGBA", (CELL * MAX_POSES, (16 + CELL * 2) * len(group)), BG)
        d = ImageDraw.Draw(sheet)
        y = 0
        for n in group:
            flagged = {int(k) for k in qa.get(n, {}).get("flags", {})}
            y = draw_clip(sheet, d, root, doc, n, flagged, y, 1)
        fn = f"sheet_{len(index):02d}.png"
        sheet.convert("RGB").save(os.path.join(out, fn))
        index.append(dict(sheet=fn, clips=group))
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(sheets=index, skipped=sorted(set(doc["clips"]) - set(names)),
                       qa_flags={n: qa[n]["flags"] for n in names if qa.get(n, {}).get("flags")}), fh, ensure_ascii=False, indent=1)
    print(f"{len(index)} review sheets in {out}")
    for e in index:
        print(f"  {e['sheet']}: {', '.join(e['clips'])}")
    print("Read each sheet, judge it against references/visual-review.md, then record with --record.")


def record(root, path):
    """Verdict format: {"reviewer": str, "sheets": {"sheet_00.png": {"verdict": "pass"|"fail", "issues": [...]}}}"""
    with open(os.path.join(root, "review", "index.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    with open(path, encoding="utf-8") as fh:
        v = json.load(fh)
    want = {e["sheet"] for e in index["sheets"]}
    got = set(v.get("sheets", {}))
    if want - got:
        sys.exit(f"not reviewed yet: {sorted(want - got)}")
    open_issues = []
    for sheet, r in v["sheets"].items():
        if r.get("verdict") not in ("pass", "fail"):
            sys.exit(f"{sheet}: verdict must be pass or fail")
        if r["verdict"] == "fail" and not r.get("issues"):
            sys.exit(f"{sheet}: a fail needs at least one issue")
        for issue in r.get("issues", []):
            if issue.get("severity") not in ("blocker", "polish"):
                sys.exit(f"{sheet}: issue severity must be blocker or polish: {issue}")
            if not issue.get("clip") or not issue.get("what"):
                sys.exit(f"{sheet}: an issue needs clip and what: {issue}")
            if issue["severity"] == "blocker" and not issue.get("resolved"):
                open_issues.append(issue)
    out = os.path.join(root, "visual_report.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(dict(v, open_blockers=len(open_issues)), fh, ensure_ascii=False, indent=1)
    print(f"visual review: {len(want)} sheets, {len(open_issues)} open blocker(s)")
    for i in open_issues:
        print(f"  {i['clip']}: {i['what']}")
    return 1 if open_issues else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--record", help="verdict JSON to validate and store")
    a = ap.parse_args()
    if a.record:
        sys.exit(record(a.path, a.record))
    build(a.path)


if __name__ == "__main__":
    main()
