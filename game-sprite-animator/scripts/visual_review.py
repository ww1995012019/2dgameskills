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
arms. shoulders_*.png shows shoulder attachment and occlusion; arms_*.png follows both complete
arm paths, including their closest-spacing frames. A verdict has to cover all of them.
"""
import argparse
import glob
import hashlib
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


def shoulder_sheets(root, doc, trace, out, full_arms=False):
    """Shoulder connections need torso context, with both art and joint seats visible."""
    required = ("neck", "waist", "sh_n", "el_n", "sh_f", "el_f")
    if full_arms:
        required += ("wr_n", "wr_f")
    rows = []
    for name, tr in trace.get("traces", {}).items():
        sk = tr.get("skeleton", {})
        if doc["clips"].get(name, {}).get("layer") or not all(sk.get(k) for k in required):
            continue
        picks = set(shoulder_frames(sk))
        if full_arms:
            # Also inspect where hands/upper arms come closest, not only the
            # poses with the largest motion. Fused arms can be worst at rest.
            hands = np.asarray(sk["wr_n"]) - np.asarray(sk["wr_f"])
            upper = ((np.asarray(sk["sh_n"]) - np.asarray(sk["sh_f"])) * 0.25
                     + (np.asarray(sk["el_n"]) - np.asarray(sk["el_f"])) * 0.75)
            picks.update((int(np.linalg.norm(hands, axis=1).argmin()),
                          int(np.linalg.norm(upper, axis=1).argmin())))
        rows.append((name, sk, sorted(picks)))
    files = []
    for start in range(0, len(rows), PER_SHEET):
        group = rows[start:start + PER_SHEET]
        sheet = Image.new("RGBA", (CELL * MAX_POSES, (20 + 2 * CELL) * len(group)), BG)
        d = ImageDraw.Draw(sheet)
        for row, (name, sk, picks) in enumerate(group):
            y = row * (20 + 2 * CELL)
            title = "full arm paths / closest spacing" if full_arms else "shoulders"
            d.text((4, y + 2), f"{name}: {title}, art / bones; near cyan, far orange", fill="white")
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
                    if full_arms:
                        wrist = point("wr_" + arm)
                        draw.line((*b, *wrist), fill=color, width=2)
                        draw.ellipse((wrist[0] - 3, wrist[1] - 3, wrist[0] + 3, wrist[1] + 3), outline=color, width=2)
                        draw.text((wrist[0] + 3, wrist[1]), arm.upper(), fill=color)
                    radius = 4 if arm == "n" else 2
                    draw.ellipse((a[0] - radius, a[1] - radius, a[0] + radius, a[1] + radius), outline=color, width=2)
                sheet.alpha_composite(overlay, (col * CELL, y + 20 + CELL))
                d.text((col * CELL + 4, y + 23), f"#{frame}", fill="white")
        prefix = "arms" if full_arms else "shoulders"
        fn = f"{prefix}_{len(files):02d}.png"
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
    report_path = os.path.join(root, "visual_report.json")
    if os.path.exists(report_path):
        os.remove(report_path)
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
        index.extend(shoulder_sheets(root, doc, trace, out, full_arms=True))
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(review_id=review_id(review_assets(root)), sheets=index, skipped=sorted(set(doc["clips"]) - set(names)),
                       qa_flags={n: qa[n]["flags"] for n in names if qa.get(n, {}).get("flags")}), fh, ensure_ascii=False, indent=1)
    template = dict(reviewer="", review_id=review_id(review_assets(root)), sheets={
        e["sheet"]: dict(verdict="fail", checks={name: dict(status="pending", evidence="") for name in CHECKS}, issues=[])
        for e in index})
    with open(os.path.join(out, "verdict_template.json"), "w", encoding="utf-8") as target:
        json.dump(template, target, ensure_ascii=False, indent=1)
    print(f"{len(index)} review sheets in {out}")
    for e in index:
        print(f"  {e['sheet']}: {', '.join(e['clips'])}")
    print("Read each sheet, judge it against references/visual-review.md, then record with --record.")


CHECKS = ("complete_limbs", "continuous_garments", "no_ghosting", "expected_weapons", "anatomy", "readable_motion")
CATEGORIES = {"missing_limb", "broken_garment", "ghosting", "extra_weapon", "anatomy", "unreadable_motion", "cosmetic"}


def file_hash(path):
    if str(path).lower().endswith(".png"):
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            return hashlib.sha256(str(rgba.size).encode() + rgba.tobytes()).hexdigest()
    with open(path, "rb") as source:
        return hashlib.sha256(source.read()).hexdigest()


def review_assets(root):
    """Bind a verdict to the exact frames, sheets and QA it actually reviewed."""
    paths = []
    for pattern in ("frames/*/*.png", "review/*.png", "animations.json", "rig_trace.json", "qa_report.json",
                    "occlusion_review.json", "occlusion_decisions.json"):
        paths.extend(glob.glob(os.path.join(root, pattern)))
    return {os.path.relpath(p, root).replace(os.sep, "/"): file_hash(p) for p in sorted(paths)}


def review_id(assets):
    return hashlib.sha256(json.dumps(assets, sort_keys=True).encode()).hexdigest()


def occlusion_gate(root):
    """Optional humanoid visibility review cannot be cleared by a generic sheet pass.

    Other modes have no such report and keep their existing review contract.
    Missing machinery for an explicitly requested review fails closed.
    """
    required = os.path.isfile(os.path.join(root, "occlusion_review.json"))
    trace_path = os.path.join(root, "rig_trace.json")
    try:
        if os.path.isfile(trace_path):
            with open(trace_path, encoding="utf-8") as source:
                required = required or "occlusion_review" in json.load(source)
        if not required:
            return 0
        from sprite_anim.occlusion_review import check_current as check_occlusion
        return check_occlusion(root)
    except (ImportError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"occlusion review: missing or invalid gate: {error}")
        return 1


def record(root, path):
    """Accept only explicit, current reviews; resolution requires changed-frame evidence."""
    current_report = os.path.join(root, "visual_report.json")
    if os.path.exists(current_report):
        os.remove(current_report)
    with open(os.path.join(root, "review", "index.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    with open(path, encoding="utf-8") as fh:
        v = json.load(fh)
    want = {e["sheet"] for e in index["sheets"]}
    if want != set(v.get("sheets", {})):
        sys.exit(f"not reviewed yet or unexpected sheets: {sorted(want ^ set(v.get('sheets', {})))}")
    assets = review_assets(root)
    current = review_id(assets)
    if not assets or index.get("review_id") != current or v.get("review_id") != current:
        sys.exit("stale or unversioned review: rebuild sheets and review the current review_id")
    if not isinstance(v.get("reviewer"), str) or not v["reviewer"].strip():
        sys.exit("reviewer is required")
    registry_path = os.path.join(root, "review", "issue_registry.json")
    registry = {}
    if os.path.isfile(registry_path):
        with open(registry_path, encoding="utf-8") as source:
            registry = json.load(source)
    open_issues, failed_sheets, ids = [], [], set()
    for sheet, r in v["sheets"].items():
        if r.get("verdict") not in ("pass", "fail"):
            sys.exit(f"{sheet}: verdict must be pass or fail")
        checklist = r.get("checks", {})
        for name in CHECKS:
            check = checklist.get(name, {})
            if check.get("status") not in ("pass", "fail", "not_applicable") or not isinstance(check.get("evidence"), str) or not check["evidence"].strip():
                sys.exit(f"{sheet}: {name} needs status and visual evidence")
            if check["status"] == "not_applicable" and name not in ("continuous_garments", "expected_weapons"):
                sys.exit(f"{sheet}: {name} cannot be skipped")
            if check["status"] == "fail" and r["verdict"] != "fail":
                sys.exit(f"{sheet}: failed {name} cannot have a pass verdict")
        if r["verdict"] == "fail":
            failed_sheets.append(sheet)
            if not r.get("issues"):
                sys.exit(f"{sheet}: a fail needs at least one issue")
        for issue in r.get("issues", []):
            ident = issue.get("id")
            if not isinstance(ident, str) or not ident.strip() or ident in ids:
                sys.exit(f"{sheet}: issue needs a unique id")
            ids.add(ident)
            if issue.get("severity") not in ("blocker", "polish") or issue.get("category") not in CATEGORIES:
                sys.exit(f"{sheet}: issue needs a valid severity and category")
            if issue["category"] != "cosmetic" and issue["severity"] != "blocker":
                sys.exit(f"{sheet}: structural or motion defects must be blocker")
            if type(issue.get("resolved")) is not bool:
                sys.exit(f"{sheet}: resolved must be a boolean")
            if not issue.get("clip") or not issue.get("what"):
                sys.exit(f"{sheet}: an issue needs clip and what")
            if issue["resolved"]:
                resolution = issue.get("resolution", {})
                prior_id = resolution.get("previous_review_id", "")
                if len(prior_id) != 64 or any(c not in "0123456789abcdef" for c in prior_id):
                    sys.exit(f"{sheet}: resolution needs a previous_review_id")
                prior_path = os.path.join(root, "review", "history", prior_id + ".json")
                if not os.path.isfile(prior_path):
                    sys.exit(f"{sheet}: previous unresolved review not found")
                with open(prior_path, encoding="utf-8") as source:
                    prior = json.load(source)
                matches = [i for row in prior.get("sheets", {}).values() for i in row.get("issues", [])
                           if i.get("id") == ident and i.get("resolved") is False
                           and i.get("clip") == issue["clip"] and i.get("category") == issue["category"]]
                if not matches or not isinstance(resolution.get("change"), str) or not resolution["change"].strip() or not resolution.get("frames"):
                    sys.exit(f"{sheet}: resolution needs a recorded open issue, change and changed frames")
                for frame in resolution["frames"]:
                    clip, number = frame.get("clip"), frame.get("frame")
                    if clip != issue["clip"] or type(number) is not int or number < 0:
                        sys.exit(f"{sheet}: invalid resolution frame")
                    key = f"frames/{clip}/{clip}_{number:03d}.png"
                    before, after = prior.get("assets", {}).get(key), assets.get(key)
                    if not before or not after or before == after:
                        sys.exit(f"{sheet}: resolved issue has no changed frame evidence")
            else:
                open_issues.append(issue)
                if r["verdict"] == "pass":
                    sys.exit(f"{sheet}: unresolved issue cannot have a pass verdict")
    dropped = {key for key, value in registry.items() if not value["resolved"]} - ids
    if dropped:
        sys.exit(f"previous unresolved issues omitted: {sorted(dropped)}")
    for row in v["sheets"].values():
        for issue in row.get("issues", []):
            registry[issue["id"]] = dict(resolved=issue["resolved"])
    with open(registry_path, "w", encoding="utf-8") as target:
        json.dump(registry, target, indent=1)
    occlusion_pending = bool(occlusion_gate(root))
    report = dict(v, assets=assets, open_blockers=sum(i["severity"] == "blocker" for i in open_issues),
                  open_issues=len(open_issues), occlusion_review_required=occlusion_pending,
                  status="fail" if failed_sheets or open_issues else "review_required" if occlusion_pending else "pass")
    history = os.path.join(root, "review", "history")
    os.makedirs(history, exist_ok=True)
    for output in (os.path.join(root, "visual_report.json"), os.path.join(history, current + ".json")):
        with open(output, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
    print(f"visual review: {len(want)} sheets, {report['status']}, {len(open_issues)} open issue(s)")
    return 0 if report["status"] == "pass" else 1


def check_current(root):
    """Delivery gate: a saved pass is valid only for the assets currently on disk."""
    path = os.path.join(root, "visual_report.json")
    if not os.path.isfile(path):
        print("visual review: no current report")
        return 1
    with open(path, encoding="utf-8") as source:
        report = json.load(source)
    current = review_id(review_assets(root))
    ok = report.get("status") == "pass" and report.get("review_id") == current and occlusion_gate(root) == 0
    print("visual review: current pass" if ok else "visual review: failed or stale report; rebuild and review")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--record", help="verdict JSON to validate and store")
    mode.add_argument("--check", action="store_true", help="verify a passing report still matches current assets")
    a = ap.parse_args()
    if a.check:
        sys.exit(check_current(a.path))
    if a.record:
        sys.exit(record(a.path, a.record))
    build(a.path)


if __name__ == "__main__":
    main()
