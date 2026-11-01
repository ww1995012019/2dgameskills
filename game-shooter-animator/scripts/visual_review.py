#!/usr/bin/env python3
# Shared by both skills. Edit the copy in the repo's shared/ folder, then run dev/sync_shared.py.
"""AI visual QA: build review sheets, then record the reviewer's verdict.

Numbers catch what can be measured. Whether a pose looks right can't be, so the agent running this
skill looks at the sheets itself, against references/visual-review.md.

    python visual_review.py out/hero                       # writes out/hero/review/*.png + index.json
    python visual_review.py out/hero --record verdict.json # validates the verdict, exit 1 if unresolved

Each sheet shows key poses plus every frame QA flagged (red border). The bottom row of each clip is
the same poses as black silhouettes: a pose that doesn't read in silhouette doesn't read in game.
joints_00.png enlarges every knee and elbow at its sharpest bends, and the head beside the raised
arms. shoulders_*.png shows shoulder attachment and occlusion at rest, arm extremes and recovery,
with art and bone overlays. A verdict has to cover all of them.
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
CROP_PAD = 4      # frame pixels kept around the art
JOINT_UNITS = 28  # rig units shown around a joint in its close-up
JOINTS = (("kn_n", "hip_n", "an_n"), ("kn_f", "hip_f", "an_f"), ("el_n", "sh_n", "wr_n"), ("el_f", "sh_f", "wr_f"))
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


def crop_box(images, size, ground_y):
    """Square around the art of a clip's poses, ground included: a character small in its frame
    otherwise reaches the reviewer too small to judge a face or a joint."""
    boxes = [b for b in (im.getbbox() for im in images) if b]
    if not boxes:
        return (0, 0, size, size)
    x0, y0 = min(b[0] for b in boxes), min(min(b[1] for b in boxes), ground_y)
    x1, y1 = max(b[2] for b in boxes), max(max(b[3] for b in boxes), ground_y + 1)
    side = min(size, max(x1 - x0, y1 - y0) + 2 * CROP_PAD)
    left = min(max((x0 + x1 - side) // 2, 0), size - side)
    top = min(max((y0 + y1 - side) // 2, 0), size - side)
    return (left, top, left + side, top + side)


def draw_clip(sheet, d, root, doc, name, flagged, y, zoom):
    c = doc["clips"][name]
    n = len(c["frames"])
    picks = pick_frames(n, flagged)
    size = doc["frame_size"]
    images = [composite(root, doc, name, i) for i in picks]
    box = crop_box(images, size, int(doc["pivot"][1]))
    side = box[2] - box[0]
    d.text((4, y + 2), f"{name}  ({n}f @ {c['fps']}fps, {'loop' if c['loop'] else 'once'}, shown x{CELL / side:.1f})", fill=(255, 255, 255, 255))
    gy = int((doc["pivot"][1] - box[1]) * CELL / side)
    for k, i in enumerate(picks):
        im = images[k].crop(box).resize((CELL, CELL), Image.NEAREST if size < 128 else Image.LANCZOS)
        x, top = k * CELL, y + 16
        d.line((x, top + gy, x + CELL - 1, top + gy), fill=GROUND)
        sheet.alpha_composite(im, (x, top))
        sheet.alpha_composite(silhouette(im), (x, top + CELL))
        d.text((x + 4, top + 3), f"#{i}", fill=(255, 255, 255, 255))
        if i in flagged:
            d.rectangle((x, top, x + CELL - 1, top + CELL - 1), outline=(240, 70, 70, 255), width=3)
    return y + 16 + CELL * 2


def bend(a, b, c):
    """Inside angle at b in degrees: 180 is straight, small is sharply folded."""
    u, v = np.subtract(a, b), np.subtract(c, b)
    size = np.hypot(*u) * np.hypot(*v)
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v) / size, -1, 1)))) if size else 180.0


def sharpest(traces, doc, joint, a, b):
    """Each clip's most folded frame at a joint, most folded clip first."""
    out = []
    for name, tr in traces.items():
        sk = tr.get("skeleton", {})
        if doc["clips"].get(name, {}).get("layer") or not all(k in sk for k in (joint, a, b)):
            continue
        angle, frame = min((bend(sk[a][i], sk[joint][i], sk[b][i]), i) for i in range(len(sk[joint])))
        out.append((angle, name, frame))
    return sorted(out)


def joint_sheet(root, doc, trace, out):
    """Every joint at its worst, enlarged. Trouble at a joint only shows at its sharpest bend and is
    a few pixels across, so a full-body cell can't show it."""
    traces, unit = trace.get("traces", {}), trace.get("unit_px", 1.0)
    rows = [(j, sharpest(traces, doc, j, a, b)[:MAX_POSES], JOINT_UNITS) for j, a, b in JOINTS]
    # The head at the arms' sharpest frames, when a hand or weapon is most likely to reach the face.
    head = 2 * (30 * trace.get("head_size", 1.0) + 6)
    rows.append(("neck", rows[2][1], head))
    rows = [r for r in rows if r[1]]
    if not rows:
        return None
    sheet = Image.new("RGBA", (CELL * MAX_POSES, (16 + CELL) * len(rows)), BG)
    d = ImageDraw.Draw(sheet)
    size = doc["frame_size"]
    for row, (joint, picks, units) in enumerate(rows):
        y = row * (16 + CELL)
        d.text((4, y + 2), f"{joint}: sharpest bends, {CELL / (units * unit):.1f}x", fill=(255, 255, 255, 255))
        for k, (angle, name, frame) in enumerate(picks):
            x0, y0 = traces[name]["skeleton"][joint][frame]
            half = units * unit / 2
            box = (int(x0 - half), int(y0 - half), int(x0 + half), int(y0 + half))
            im = composite(root, doc, name, frame).crop(box).resize((CELL, CELL), Image.NEAREST)
            cell = Image.new("RGBA", (CELL, CELL), BG)
            cell.alpha_composite(im)
            sheet.alpha_composite(cell, (k * CELL, y + 16))
            d.text((k * CELL + 4, y + 19), f"{name} #{frame} {angle:.0f} deg", fill=(255, 255, 255, 255))
    fn = "joints_00.png"
    sheet.convert("RGB").save(os.path.join(out, fn))
    return fn


def shoulder_frames(sk):
    """Rest/recovery plus each upper arm's forward/back extremes."""
    n = len(sk["neck"])
    picks = {0, n - 1}
    for side in "nf":
        delta = np.asarray(sk["el_" + side]) - np.asarray(sk["sh_" + side])
        angles = np.unwrap(np.arctan2(delta[:, 1], delta[:, 0]))
        picks.update((int(angles.argmin()), int(angles.argmax())))
    return sorted(picks)


def shoulder_sheets(root, doc, trace, out):
    """Shoulder connections need torso context, with both art and joint seats visible."""
    required = ("neck", "waist", "sh_n", "el_n", "sh_f", "el_f")
    rows = []
    for name, tr in trace.get("traces", {}).items():
        sk = tr.get("skeleton", {})
        if doc["clips"].get(name, {}).get("layer") or not all(sk.get(k) for k in required):
            continue
        rows.append((name, sk, shoulder_frames(sk)))
    files = []
    for start in range(0, len(rows), PER_SHEET):
        group = rows[start:start + PER_SHEET]
        sheet = Image.new("RGBA", (CELL * MAX_POSES, (20 + 2 * CELL) * len(group)), BG)
        d = ImageDraw.Draw(sheet)
        for row, (name, sk, picks) in enumerate(group):
            y = row * (20 + 2 * CELL)
            d.text((4, y + 2), f"{name}: shoulders, art / bones; near cyan, far orange", fill="white")
            for col, frame in enumerate(picks):
                pts = np.array([sk[k][frame] for k in required])
                pad = max(4, trace.get("unit_px", 1) * 5)
                span = np.ptp(pts, axis=0)
                side = max(span) + 2 * pad
                center = (pts.min(0) + pts.max(0)) / 2
                left, top = center - side / 2
                box = (int(left), int(top), int(left + side + 1), int(top + side + 1))
                im = composite(root, doc, name, frame).crop(box).resize((CELL, CELL), Image.NEAREST)
                cell = Image.new("RGBA", im.size, BG)
                cell.alpha_composite(im)
                sheet.alpha_composite(cell, (col * CELL, y + 20))
                overlay = cell.copy()
                draw = ImageDraw.Draw(overlay)
                def point(key):
                    x, yy = sk[key][frame]
                    return ((x - box[0]) * CELL / (box[2] - box[0]),
                            (yy - box[1]) * CELL / (box[3] - box[1]))
                draw.line((*point("waist"), *point("neck")), fill=(220, 220, 220), width=1)
                for arm, color in (("n", (40, 235, 225)), ("f", (255, 145, 55))):
                    a, b = point("sh_" + arm), point("el_" + arm)
                    draw.line((*a, *b), fill=color, width=2)
                    radius = 4 if arm == "n" else 2
                    draw.ellipse((a[0] - radius, a[1] - radius, a[0] + radius, a[1] + radius), outline=color, width=2)
                sheet.alpha_composite(overlay, (col * CELL, y + 20 + CELL))
                d.text((col * CELL + 4, y + 23), f"#{frame}", fill="white")
        fn = f"shoulders_{len(files):02d}.png"
        sheet.convert("RGB").save(os.path.join(out, fn))
        files.append(dict(sheet=fn, clips=[name for name, _, _ in group]))
    return files


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
    tp = os.path.join(root, "rig_trace.json")
    if os.path.exists(tp):
        with open(tp, encoding="utf-8") as fh:
            trace = json.load(fh)
        fn = joint_sheet(root, doc, trace, out)
        if fn:     # listed like any sheet, so --record refuses a verdict that skips it
            index.append(dict(sheet=fn, clips=["joints"]))
        index.extend(shoulder_sheets(root, doc, trace, out))
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
