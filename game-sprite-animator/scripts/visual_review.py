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
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

CELL = 180
PELVIS_CELL = 256
REVIEW_SCHEMA = 3
PER_SHEET = 6
MAX_POSES = 8
CROP_PAD = 4      # frame pixels kept around the art
JOINT_UNITS = 28  # rig units shown around a joint in its close-up
JOINTS = (("kn_n", "hip_n", "an_n"), ("kn_f", "hip_f", "an_f"), ("el_n", "sh_n", "wr_n"), ("el_f", "sh_f", "wr_f"))
GROUND = (240, 184, 74, 255)
BG = (58, 62, 74, 255)
PELVIS_JOINTS = ("waist", "neck", "hip_n", "hip_f", "kn_n", "kn_f", "an_n", "an_f")
PELVIS_CHECKS = ("rig_alignment", "pelvis_continuity", "source_garment_registration", "limb_shape_preservation",
                 "hidden_garment_edges", "motion_style_match")
NECK_CHECKS = ("neck_continuity", "head_motion_naturalness")
HAND_CHECKS = ("hand_pose_naturalness", "wrist_continuity")
POSE_CHECKS = PELVIS_CHECKS + NECK_CHECKS + HAND_CHECKS
TEMPORAL_CHECKS = ("head_motion_naturalness", "hand_pose_naturalness")
DETAIL_CELL = 256
DETAIL_PER_SHEET = 2


def detail_scope(doc, trace, kind):
    """Use measured humanoid joints; never apply side-view neck rules to other anatomies."""
    required = ('neck', 'waist') if kind == 'neck' else ('el_n', 'wr_n', 'el_f', 'wr_f')
    scope = {}
    for name, clip in doc.get('clips', {}).items():
        if clip_layer(clip) == 'lower':
            continue
        count = len(clip.get('frames', []))
        sk = trace.get('traces', {}).get(name, {}).get('skeleton', {})
        if not any(key in sk for key in required):
            if trace.get('portrait_review_required'):
                raise ValueError(f'{name}: missing required {kind} rendered joint trace')
            continue
        for key in required:
            points = np.asarray(sk.get(key, []), dtype=float)
            if points.shape != (count, 2) or not count or not np.isfinite(points).all():
                raise ValueError(f'{name}: incomplete {kind} rendered joint trace: {key}')
        scope[name] = sk
    return scope


def detail_frames(sk, trace_clip, count, kind):
    reasons = {}
    def add(frame, why):
        reasons.setdefault(int(frame), set()).add(why)
    for i in np.linspace(0, count - 1, min(5, count)).round().astype(int):
        add(i, 'cycle/rest/recovery sample')
    if kind == 'neck':
        motion = trace_clip.get('head_motion', {})
        for key in ('head_world_deg', 'chest_world_deg', 'relative_deg'):
            if key not in motion:
                continue  # Legacy traces still require the full temporal review.
            values = np.asarray(motion[key], dtype=float)
            if values.shape != (count,) or not np.isfinite(values).all():
                raise ValueError(f'head_motion.{key}: invalid rendered angle track')
            add(np.argmin(values), f'minimum {key}'); add(np.argmax(values), f'maximum {key}')
    else:
        for side in 'nf':
            for axis in (0, 1):
                values = np.asarray(sk['wr_' + side])[:, axis]
                add(np.argmin(values), f'{side} wrist minimum axis {axis}')
                add(np.argmax(values), f'{side} wrist maximum axis {axis}')
    return [dict(frame=i, reasons=sorted(why)) for i, why in sorted(reasons.items())]


def detail_rows(doc, trace, kind):
    rows = []
    for name, sk in detail_scope(doc, trace, kind).items():
        poses = detail_frames(sk, trace.get('traces', {}).get(name, {}), len(doc['clips'][name]['frames']), kind)
        for start in range(0, len(poses), MAX_POSES):
            rows.append((name, sk, poses[start:start + MAX_POSES]))
    return rows


def detail_boxes(sk, trace, kind, frame=None):
    """Local still close-ups; fixed whole-clip playback boxes retain bob and wrist travel."""
    if frame is not None:
        sk = {key: values[frame:frame + 1] for key, values in sk.items()}
    unit = float(trace.get('unit_px', 1))
    if kind == 'neck':
        radius = (30 * float(trace.get('head_size', 1)) + 8) * unit
        points = np.asarray(sk['neck'], dtype=float).copy()
        points[:, 1] -= radius * .25
        groups = [(points, radius), (np.asarray(sk['neck'], dtype=float), radius * .35)]
    else:
        groups = []
        for side in 'nf':
            wrist, elbow = np.asarray(sk['wr_' + side], float), np.asarray(sk['el_' + side], float)
            radius = max(6 * unit, float(np.linalg.norm(wrist - elbow, axis=1).max()) * .8)
            groups.append((wrist + (wrist - elbow) * .2, radius))
    return [tuple(np.concatenate((np.floor(points.min(0) - max(radius, 2)),
                                   np.ceil(points.max(0) + max(radius, 2)))).astype(int))
            for points, radius in groups]


def detail_sheets(root, doc, trace, out, kind):
    rows, files, media = detail_rows(doc, trace, kind), [], {}
    scopes = detail_scope(doc, trace, kind)
    boxes = {name: detail_boxes(sk, trace, kind) for name, sk in scopes.items()}
    for number, name in enumerate(scopes):
        clip = doc['clips'][name]
        frames = []
        for frame in range(len(clip['frames'])):
            original = composite(root, doc, name, frame)
            cell = Image.new('RGB', (DETAIL_CELL * len(boxes[name]), DETAIL_CELL), BG[:3])
            for col, box in enumerate(boxes[name]):
                art = original.crop(box).resize((DETAIL_CELL, DETAIL_CELL), Image.Resampling.NEAREST)
                cell.paste(art, (col * DETAIL_CELL, 0), art)
            # Keep every frame, including identical holds; duration is the exported FPS.
            frames.append(cell)
        filename = f'{kind}_motion_{number:03d}.gif'
        # Integer-centisecond GIF timing uses cumulative rounding rather than speeding up 30fps.
        durations = [max(10, (round((i + 1) * 100 / clip['fps']) - round(i * 100 / clip['fps'])) * 10)
                     for i in range(len(frames))]
        frames[0].save(os.path.join(out, filename), save_all=True, append_images=frames[1:],
                       duration=durations, loop=0, disposal=2, optimize=False)
        media[name] = dict(clip=name, file=filename, frame_count=len(frames), fps=clip['fps'],
                           loop=bool(clip['loop']), duration_ms=sum(durations))
    for start in range(0, len(rows), DETAIL_PER_SHEET):
        group = rows[start:start + DETAIL_PER_SHEET]
        sheet = Image.new('RGBA', (DETAIL_CELL * MAX_POSES, (28 + 2 * DETAIL_CELL) * len(group)), BG)
        draw = ImageDraw.Draw(sheet)
        poses = []
        for row, (name, sk, picks) in enumerate(group):
            top = row * (28 + 2 * DETAIL_CELL)
            labels = 'head context / enlarged neck root + driving bones' if kind == 'neck' else 'near hand / far hand'
            draw.text((4, top + 3), f'{name}: {labels}; PLAY {media[name]["file"]}', fill='white')
            for col, pose in enumerate(picks):
                frame, x = pose['frame'], col * DETAIL_CELL
                original = composite(root, doc, name, frame)
                closeups = detail_boxes(sk, trace, kind, frame)
                for band in range(2):
                    box = closeups[band]
                    art = original.crop(box).resize((DETAIL_CELL, DETAIL_CELL), Image.Resampling.NEAREST)
                    sheet.alpha_composite(art, (x, top + 28 + band * DETAIL_CELL))
                    if kind == 'neck' and band:
                        overlay = Image.new('RGBA', (DETAIL_CELL, DETAIL_CELL))
                        bones = ImageDraw.Draw(overlay)
                        def point(key):
                            xx, yy = sk[key][frame]
                            return ((xx - box[0]) * DETAIL_CELL / (box[2] - box[0]),
                                    (yy - box[1]) * DETAIL_CELL / (box[3] - box[1]))
                        bones.line((point('waist'), point('neck')), fill=(40, 235, 225), width=2)
                        sheet.alpha_composite(overlay, (x, top + 28 + DETAIL_CELL))
                    draw.text((x + 4, top + 31 + band * DETAIL_CELL), f'#{frame}', fill='white')
                poses.append(dict(clip=name, **pose))
        filename = f'{kind}_{len(files):02d}.png'
        sheet.convert('RGB').save(os.path.join(out, filename))
        clips = sorted({name for name, _, _ in group})
        files.append(dict(sheet=filename, kind=kind, clips=clips, poses=poses,
                          playback=[media[name] for name in clips]))
    return files


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


def clip_layer(clip):
    layer = clip.get("layer")
    if layer is None or layer == "":
        return None
    if layer not in ("upper", "lower"):
        raise ValueError(f"unknown animation layer {layer!r}: only upper/lower are layered clips")
    return layer


def humanoid_scope(doc, trace):
    """Review full-body humanoid clips only when the rendered joint trace exists.

    Upper/lower composited shooter clips retain their existing scoped review.
    Absence of measured hips must never silently turn a body review into a pass.
    """
    scope = {}
    for name, clip in doc.get("clips", {}).items():
        if clip_layer(clip):
            continue
        count = len(clip.get("frames", []))
        sk = trace.get("traces", {}).get(name, {}).get("skeleton", {})
        missing = [key for key in PELVIS_JOINTS if len(sk.get(key, [])) != count or not count]
        if missing:
            raise ValueError(f"{name}: full-body review requires complete rendered pelvis/leg trace: {', '.join(missing)}")
        for key in PELVIS_JOINTS:
            points = np.asarray(sk[key], dtype=float)
            if points.shape != (count, 2) or not np.isfinite(points).all():
                raise ValueError(f"{name}: invalid rendered joint trace: {key}")
        scope[name] = sk
    return scope


def pelvic_frames(sk, clip, trace_clip):
    """Every clip contributes its own seam-risk poses, with no global top-eight cap."""
    count = len(sk["waist"])
    reasons = {}
    def add(frame, reason):
        reasons.setdefault(int(frame), set()).add(reason)
    add(0, "first/rest"); add(count - 1, "last/recovery")
    legs = np.stack([sk[key] for key in ("hip_n", "hip_f", "kn_n", "kn_f", "an_n", "an_f")])
    add(np.argmax(np.ptp(legs[:, :, 0], axis=0)), "maximum leg separation")
    add(np.argmax(np.mean([sk["hip_n"], sk["hip_f"]], axis=0)[:, 1]), "lowest pelvis/deepest crouch")
    for side in "nf":
        add(min(range(count), key=lambda i: bend(sk["hip_" + side][i], sk["kn_" + side][i], sk["an_" + side][i])), f"sharpest {side} knee")
        add(min(range(count), key=lambda i: bend(sk["neck"][i], sk["hip_" + side][i], sk["kn_" + side][i])), f"sharpest {side} hip")
    for meta in (clip, trace_clip):
        for key in ("source_frames", "attachment_frames"):
            sources = meta.get(key)
            if sources is None:
                continue
            if not isinstance(sources, list) or len(sources) != count:
                raise ValueError(f"{key}: source-switch metadata must match the rendered frame count")
            for i in range(1, count):
                if sources[i] != sources[i - 1]:
                    for adjacent in (i - 1, i, min(count - 1, i + 1)):
                        add(adjacent, f"{key} switch at {i}")
    return [dict(frame=frame, reasons=sorted(why)) for frame, why in sorted(reasons.items())]


def pelvic_rows(doc, trace):
    rows = []
    for name, sk in humanoid_scope(doc, trace).items():
        poses = pelvic_frames(sk, doc["clips"][name], trace.get("traces", {}).get(name, {}))
        if trace.get('connection_review_required'):
            poses = [dict(frame=i, reasons=['complete garment connection review']) for i in range(len(sk['waist']))]
        for start in range(0, len(poses), MAX_POSES):
            rows.append((name, sk, poses[start:start + MAX_POSES]))
    return rows


def pelvic_sheets(root, doc, trace, out):
    """Enlarged waist/hip/inner-thigh art followed by the exact rendered bones."""
    files, rows = [], pelvic_rows(doc, trace)
    unit = float(trace.get("unit_px", 1))
    per_sheet = 2 if trace.get('connection_review_required') else PER_SHEET
    for start in range(0, len(rows), per_sheet):
        group = rows[start:start + per_sheet]
        sheet = Image.new("RGBA", (PELVIS_CELL * MAX_POSES, (28 + 2 * PELVIS_CELL) * len(group)), BG)
        draw = ImageDraw.Draw(sheet)
        evidence = []
        for row, (name, sk, poses) in enumerate(group):
            top = row * (28 + 2 * PELVIS_CELL)
            draw.text((4, top + 2), f"{name}: pelvis / crotch seam; art then rendered bones", fill="white")
            for col, pose in enumerate(poses):
                frame, x = pose["frame"], col * PELVIS_CELL
                # Include complete thighs and knees: the old half-thigh crop
                # concealed the very shape regressions a seam fix can create.
                points = np.array([sk[key][frame] for key in ("waist", "hip_n", "hip_f", "kn_n", "kn_f")])
                low, high = points.min(0), points.max(0)
                pad = max(8, unit * 10)
                side = max(float(max(high - low)) + 2 * pad, unit * 38, 24)
                center = (low + high) / 2
                box = (int(center[0] - side / 2), int(center[1] - side / 2), int(center[0] + side / 2 + 1), int(center[1] + side / 2 + 1))
                im = composite(root, doc, name, frame).crop(box).resize((PELVIS_CELL, PELVIS_CELL), Image.NEAREST)
                cell = Image.new("RGBA", im.size, BG)
                checker = ImageDraw.Draw(cell)
                for yy in range(0, PELVIS_CELL, 16):
                    for xx in range(0, PELVIS_CELL, 16):
                        if (xx // 16 + yy // 16) % 2:
                            checker.rectangle((xx, yy, xx + 15, yy + 15), fill=(91, 95, 107, 255))
                cell.alpha_composite(im)
                sheet.alpha_composite(cell, (x, top + 28))
                overlay = cell.copy(); lines = ImageDraw.Draw(overlay)
                def point(key):
                    px, py = sk[key][frame]
                    return ((px - box[0]) * PELVIS_CELL / (box[2] - box[0]), (py - box[1]) * PELVIS_CELL / (box[3] - box[1]))
                lines.line((*point("waist"), *point("neck")), fill="white", width=2)
                for limb, color in (("n", (40, 235, 225)), ("f", (255, 145, 55))):
                    keys = ["waist", "hip_" + limb, "kn_" + limb, "an_" + limb]
                    lines.line([point(key) for key in keys], fill=color, width=2)
                    for key in keys[1:]:
                        px, py = point(key); lines.ellipse((px - 3, py - 3, px + 3, py + 3), outline=color, width=2)
                sheet.alpha_composite(overlay, (x, top + 28 + PELVIS_CELL))
                draw.text((x + 4, top + 16), f"#{frame}  {pose['reasons'][0]}", fill="white")
                evidence.append(dict(clip=name, frame=frame, reasons=pose["reasons"], crop=list(box)))
        filename = f"hips_{len(files):02d}.png"
        sheet.convert("RGB").save(os.path.join(out, filename))
        files.append(dict(sheet=filename, kind="pelvis", clips=sorted({name for name, _, _ in group}), poses=evidence))
    return files


def garment_rows(doc, trace):
    """Separate waist macros so full-thigh crops cannot hide small cut edges."""
    if trace.get('connections',{}).get('method') != 'registered_garment_surfaces_v3':
        return []
    rows = []
    for name,sk in humanoid_scope(doc,trace).items():
        count = len(sk['waist'])
        poses = {p['frame']:p for p in pelvic_frames(sk,doc['clips'][name],trace['traces'][name])}
        for frame in (0,count-1,*(min(count-1,round(count*k/4)) for k in range(4))):
            poses.setdefault(frame,dict(frame=frame,reasons=['waist edge / motion phase']))
        ordered = [poses[i] for i in sorted(poses)]
        for start in range(0,len(ordered),MAX_POSES):
            rows.append((name,sk,ordered[start:start+MAX_POSES]))
    return rows


def garment_sheets(root, doc, trace, out):
    files,rows = [],garment_rows(doc,trace)
    unit = float(trace.get('unit_px',1))
    for start in range(0,len(rows),2):
        group = rows[start:start+2]
        sheet = Image.new('RGBA',(PELVIS_CELL*MAX_POSES,(PELVIS_CELL+28)*len(group)),BG)
        draw = ImageDraw.Draw(sheet);evidence = []
        for row,(name,sk,poses) in enumerate(group):
            top = row*(PELVIS_CELL+28)
            draw.text((4,top+2),f'{name}: enlarged waistband / original hidden cut edges',fill='white')
            for col,pose in enumerate(poses):
                frame = pose['frame']
                points = np.asarray([sk[k][frame] for k in ('waist','hip_n','hip_f')])
                low,high = points.min(0),points.max(0)
                side = max(float(max(high-low))+8*unit,20*unit,24)
                center = (low+high)/2
                box = [int(center[0]-side/2),int(center[1]-side/2),
                       int(center[0]+side/2+1),int(center[1]+side/2+1)]
                art = composite(root,doc,name,frame).crop(box).resize((PELVIS_CELL,PELVIS_CELL),Image.NEAREST)
                cell = Image.new('RGBA',art.size,(142,180,212,255));cell.alpha_composite(art)
                sheet.alpha_composite(cell,(col*PELVIS_CELL,top+28))
                draw.text((col*PELVIS_CELL+4,top+16),f'#{frame}',fill='white')
                evidence.append(dict(clip=name,frame=frame,reasons=pose['reasons'],crop=box))
        filename = f'garment_edges_{len(files):02d}.png'
        sheet.convert('RGB').save(os.path.join(out,filename))
        files.append(dict(sheet=filename,kind='pelvis',clips=sorted({n for n,_,_ in group}),poses=evidence))
    return files


def selected_clips(doc, qa):
    def key(name):
        return (0 if qa.get(name, {}).get("flags") else 1, name)
    names = []
    for name in sorted(doc["clips"], key=key):
        clip = doc["clips"][name]
        tag = name.rsplit("_", 1)[-1]
        sparse = clip.get("layer") == "upper" and ("_aim_" in name or "_fire_" in name) and tag not in ("0", "p90", "m90", "p45", "m45")
        if not sparse or qa.get(name, {}).get("flags"):
            names.append(name)
    return names


def binding_sheets(root):
    path = os.path.join(root, "binding_audit.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as source:
        report = json.load(source)
    names = report.get("review_sheets", [])
    if not isinstance(names, list) or len(names) != len(set(names)) or (report.get("status") == "pass" and not names):
        raise ValueError("binding audit requires its source/registration visual review sheets")
    for name in names:
        if not isinstance(name, str) or os.path.basename(name) != name or not name.startswith("binding_review_") or not name.endswith(".png"):
            raise ValueError("binding audit has an invalid visual review sheet path")
        if not os.path.isfile(os.path.join(root, name)):
            raise ValueError(f"missing binding review sheet: {name}")
    return [dict(sheet=name, kind="binding_registration", clips=[]) for name in names]


def sheet_file(root, name):
    return os.path.join(root, name) if name.startswith("binding_review_") else os.path.join(root, "review", name)


def expected_sheets(doc, trace, qa, root=None):
    names = selected_clips(doc, qa)
    expected = {f"sheet_{i:02d}.png" for i in range((len(names) + PER_SHEET - 1) // PER_SHEET)}
    traces = trace.get("traces", {})
    if any(sharpest(traces, doc, joint, a, b) for joint, a, b in JOINTS):
        expected.add("joints_00.png")
    for full_arms, prefix in ((False, "shoulders"), (True, "arms")):
        keys = ("neck", "waist", "sh_n", "el_n", "sh_f", "el_f") + (("wr_n", "wr_f") if full_arms else ())
        count = sum(not doc["clips"].get(name, {}).get("layer") and all(sk.get(key) for key in keys)
                    for name, tr in traces.items() for sk in [tr.get("skeleton", {})])
        expected.update(f"{prefix}_{i:02d}.png" for i in range((count + PER_SHEET - 1) // PER_SHEET))
    rows = pelvic_rows(doc, trace)
    pelvis_per_sheet = 2 if trace.get('connection_review_required') else PER_SHEET
    expected.update(f"hips_{i:02d}.png" for i in range((len(rows) + pelvis_per_sheet - 1) // pelvis_per_sheet))
    expected.update(f'garment_edges_{i:02d}.png' for i in range((len(garment_rows(doc,trace))+1)//2))
    for kind in ('neck', 'hands'):
        count = len(detail_rows(doc, trace, kind))
        expected.update(f'{kind}_{i:02d}.png' for i in range((count + DETAIL_PER_SHEET - 1) // DETAIL_PER_SHEET))
    if root is not None:
        expected.update(entry["sheet"] for entry in binding_sheets(root))
    return expected


def build(root):
    report_path = os.path.join(root, "visual_report.json")
    if os.path.exists(report_path):
        os.remove(report_path)
    with open(os.path.join(root, "animations.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    qa = {}
    qp = os.path.join(root, "qa_report.json")
    if os.path.exists(qp):
        with open(qp, encoding="utf-8") as fh:
            qa = json.load(fh).get("clips", {})
    tp = os.path.join(root, "rig_trace.json")
    trace = {}
    if os.path.exists(tp):
        with open(tp, encoding="utf-8") as fh:
            trace = json.load(fh)
    humanoid_scope(doc, trace)
    out = os.path.join(root, "review")
    os.makedirs(out, exist_ok=True)
    for old in (*glob.glob(os.path.join(out, "*.png")), *glob.glob(os.path.join(out, "*_motion_*.gif"))):
        os.remove(old)

    names = selected_clips(doc, qa)

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
    if trace:
        fn = joint_sheet(root, doc, trace, out)
        if fn:     # listed like any sheet, so --record refuses a verdict that skips it
            index.append(dict(sheet=fn, clips=["joints"]))
        index.extend(shoulder_sheets(root, doc, trace, out))
        index.extend(shoulder_sheets(root, doc, trace, out, full_arms=True))
        index.extend(pelvic_sheets(root, doc, trace, out))
        index.extend(garment_sheets(root,doc,trace,out))
        for kind in ('neck', 'hands'):
            index.extend(detail_sheets(root, doc, trace, out, kind))
    index.extend(binding_sheets(root))
    value = dict(schema_version=REVIEW_SCHEMA, sheets=index, required_sheets=sorted(expected_sheets(doc, trace, qa, root)),
                 skipped=sorted(set(doc["clips"]) - set(names)),
                 qa_flags={n: qa[n]["flags"] for n in names if qa.get(n, {}).get("flags")})
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=1)
    value["review_id"] = review_id(review_assets(root))
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=1)
    template = dict(reviewer="", review_id=review_id(review_assets(root)), sheets={
        e["sheet"]: dict(verdict="fail", checks={name: dict(status="pending", evidence="", **(
            {"observations": [dict(clip=p["clip"], frame=p["frame"], evidence="") for p in e.get("poses", [])]}
            if name in POSE_CHECKS else {}), **(
            {"playback": [dict(clip=p['clip'], file=p['file'], evidence='') for p in e.get('playback', [])]}
            if name in TEMPORAL_CHECKS else {})) for name in checks_for_sheet(e["sheet"])}, issues=[])
        for e in index})
    with open(os.path.join(out, "verdict_template.json"), "w", encoding="utf-8") as target:
        json.dump(template, target, ensure_ascii=False, indent=1)
    print(f"{len(index)} review sheets in {out}")
    for e in index:
        print(f"  {e['sheet']}: {', '.join(e['clips'])}")
    print("Read each sheet, judge it against references/visual-review.md, then record with --record.")


CHECKS = ("complete_limbs", "continuous_garments", "no_ghosting", "expected_weapons", "anatomy", "readable_motion")
CATEGORIES = {"missing_limb", "broken_garment", "ghosting", "extra_weapon", "anatomy", "unreadable_motion", "cosmetic"}
CATEGORIES.update(("pelvis_gap", "rig_misalignment"))
CATEGORIES.update(("neck_seam", "stiff_head", "unnatural_hand", "broken_wrist"))


def checks_for_sheet(name):
    if name.startswith("binding_review_"):
        return ("binding_registration",)
    if name.startswith('neck_'):
        return CHECKS + NECK_CHECKS
    if name.startswith('hands_'):
        return CHECKS + HAND_CHECKS
    return CHECKS + PELVIS_CHECKS if name.startswith(("hips_","garment_edges_")) else CHECKS


def file_hash(path):
    if os.path.basename(str(path)) == "index.json" and os.path.basename(os.path.dirname(str(path))) == "review":
        with open(path, encoding="utf-8") as source:
            data = json.load(source)
        data.pop("review_id", None)  # avoid self-referential hashing; all coverage data remains bound
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if str(path).lower().endswith(".png"):
        return pixel_hash(path)
    with open(path, "rb") as source:
        return hashlib.sha256(source.read()).hexdigest()


def pixel_hash(path):
    """Match actual reviewed pixels, independent of lossless image encoding."""
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return hashlib.sha256(str(rgba.size).encode() + rgba.tobytes()).hexdigest()


def review_assets(root):
    """Bind a verdict to the exact frames, sheets and QA it actually reviewed."""
    paths = []
    for pattern in ("frames/*/*.png", "review/*.png", "review/*_motion_*.gif", "review/index.json", "animations.json", "rig_trace.json", "qa_report.json",
                    "atlas*.png", "atlas*.json", "sheets/*.png", "preview.html", "fx*.png", "fx*.json", "engine/**/*",
                    "binding_audit.json", "binding_reference.png", "binding_review_*.png", "occlusion_review.json", "occlusion_decisions.json"):
        paths.extend(glob.glob(os.path.join(root, pattern), recursive=True))
    # Follow declared page names too, including nested/custom atlas filenames.
    # A missing required page must fail closed, even when it was absent before
    # a reviewer tried recording a pass. Never hash paths outside this export.
    base = os.path.realpath(root)
    for manifest in ("animations.json", "fx.json"):
        path = os.path.join(root, manifest)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as source:
            pages = json.load(source).get("pages", [])
        if not isinstance(pages, list):
            raise ValueError(f"{manifest}: pages must be a list")
        for page in pages:
            name = page.get("file") if isinstance(page, dict) else None
            if not isinstance(name, str) or not name or os.path.isabs(name):
                raise ValueError(f"{manifest}: invalid atlas page")
            image = os.path.realpath(os.path.join(base, name))
            if os.path.commonpath((base, image)) != base:
                raise ValueError(f"{manifest}: atlas page is outside the export")
            if not os.path.isfile(image):
                raise ValueError(f"{manifest}: missing required atlas page: {name}")
            paths.append(image)
    return {os.path.relpath(p, root).replace(os.sep, "/"): file_hash(p) for p in sorted(set(paths)) if os.path.isfile(p)}


def review_id(assets):
    return hashlib.sha256(json.dumps(assets, sort_keys=True).encode()).hexdigest()


def validate_index(root, index):
    if index.get("schema_version") != REVIEW_SCHEMA:
        raise ValueError("stale or unversioned review: rebuild current anatomy review sheets")
    with open(os.path.join(root, "animations.json"), encoding="utf-8") as source:
        doc = json.load(source)
    trace_path = os.path.join(root, "rig_trace.json")
    trace = {}
    if os.path.isfile(trace_path):
        with open(trace_path, encoding="utf-8") as source:
            trace = json.load(source)
    qa_path = os.path.join(root, "qa_report.json")
    qa = {}
    if os.path.isfile(qa_path):
        with open(qa_path, encoding="utf-8") as source:
            qa = json.load(source).get("clips", {})
    expected = expected_sheets(doc, trace, qa, root)
    entries = index.get("sheets", [])
    actual = [entry["sheet"] for entry in entries]
    if len(actual) != len(set(actual)) or set(actual) != expected or index.get("required_sheets") != sorted(expected):
        raise ValueError("missing or unexpected required review sheets; rebuild the complete review")
    for name in expected:
        if not os.path.isfile(sheet_file(root, name)):
            raise ValueError(f"missing required review sheet: {name}")
    rows = pelvic_rows(doc, trace)
    per_sheet = 2 if trace.get('connection_review_required') else PER_SHEET
    for start in range(0, len(rows), per_sheet):
        name = f"hips_{start // per_sheet:02d}.png"
        entry = next(row for row in entries if row["sheet"] == name)
        want = [(clip, pose["frame"], pose["reasons"]) for clip, _, poses in rows[start:start + per_sheet] for pose in poses]
        got = [(pose["clip"], pose["frame"], pose["reasons"]) for pose in entry.get("poses", [])]
        if got != want:
            raise ValueError(f"{name}: missing or altered required pelvis pose coverage")
    rows = garment_rows(doc,trace)
    for start in range(0,len(rows),2):
        name = f'garment_edges_{start//2:02d}.png'
        entry = next(row for row in entries if row['sheet']==name)
        want = [(clip,p['frame'],p['reasons']) for clip,_,poses in rows[start:start+2] for p in poses]
        got = [(p['clip'],p['frame'],p['reasons']) for p in entry.get('poses',[])]
        if got != want:
            raise ValueError(f'{name}: missing or altered required garment-edge pose coverage')
    for kind in ('neck', 'hands'):
        rows = detail_rows(doc, trace, kind)
        scope = list(detail_scope(doc, trace, kind))
        for start in range(0, len(rows), DETAIL_PER_SHEET):
            name = f'{kind}_{start // DETAIL_PER_SHEET:02d}.png'
            entry = next(row for row in entries if row['sheet'] == name)
            group = rows[start:start + DETAIL_PER_SHEET]
            want = [dict(clip=clip, **pose) for clip, _, poses in group for pose in poses]
            if entry.get('poses') != want:
                raise ValueError(f'{name}: missing or altered required {kind} pose coverage')
            expected_media = []
            for clip in sorted({clip for clip, _, _ in group}):
                meta = doc['clips'][clip]
                count = len(meta['frames'])
                filename = f'{kind}_motion_{scope.index(clip):03d}.gif'
                expected_media.append(dict(clip=clip, file=filename, frame_count=count, fps=meta['fps'],
                                           loop=bool(meta['loop']), duration_ms=sum(
                    max(10, (round((i + 1) * 100 / meta['fps']) - round(i * 100 / meta['fps'])) * 10) for i in range(count))))
                if not os.path.isfile(os.path.join(root, 'review', filename)):
                    raise ValueError(f'{name}: missing required playback: {filename}')
            if entry.get('playback') != expected_media:
                raise ValueError(f'{name}: missing or altered required playback coverage')
    return {entry["sheet"]: entry for entry in entries}


def validate_checklist(sheet, row, entry):
    if row.get("verdict") not in ("pass", "fail"):
        raise ValueError(f"{sheet}: verdict must be pass or fail")
    for name in checks_for_sheet(sheet):
        check = row.get("checks", {}).get(name, {})
        if check.get("status") not in ("pass", "fail", "not_applicable") or not isinstance(check.get("evidence"), str) or not check["evidence"].strip():
            raise ValueError(f"{sheet}: {name} needs status and visual evidence")
        if check["status"] == "not_applicable" and name not in ("continuous_garments", "expected_weapons"):
            raise ValueError(f"{sheet}: {name} cannot be skipped")
        if check["status"] == "fail" and row["verdict"] != "fail":
            raise ValueError(f"{sheet}: failed {name} cannot have a pass verdict")
        if name in POSE_CHECKS:
            observations = check.get("observations", [])
            expected = {(pose["clip"], pose["frame"]) for pose in entry["poses"]}
            cited = []
            for pose in observations:
                if type(pose.get("frame")) is not int or not isinstance(pose.get("evidence"), str) or not pose["evidence"].strip():
                    raise ValueError(f"{sheet}: {name} needs concrete evidence for each required clip/frame")
                cited.append((pose.get("clip"), pose["frame"]))
            if len(cited) != len(set(cited)) or set(cited) != expected:
                raise ValueError(f"{sheet}: {name} must cover every required pose exactly once")
        if name in TEMPORAL_CHECKS:
            want = {(p['clip'], p['file']) for p in entry.get('playback', [])}
            observations = check.get('playback', [])
            if any(not isinstance(p.get('evidence'), str) or not p['evidence'].strip() for p in observations):
                raise ValueError(f'{sheet}: {name} needs playback evidence for every clip')
            got = [(p.get('clip'), p.get('file')) for p in observations]
            if len(got) != len(set(got)) or set(got) != want or not want:
                raise ValueError(f'{sheet}: {name} must review every required playback exactly once')


def binding_gate(root):
    path = os.path.join(root, "binding_audit.json")
    try:
        trace_path = os.path.join(root, "rig_trace.json")
        trace = {}
        if os.path.isfile(trace_path):
            with open(trace_path, encoding="utf-8") as source:
                trace = json.load(source)
        if trace.get('connection_review_required') or trace.get('binding_profile') == 'basic-side-v1':
            from sprite_anim.integrity import connection_report_faults
            with open(os.path.join(root, 'animations.json'), encoding='utf-8') as source:
                connections = connection_report_faults(root, json.load(source), trace)
            if connections:
                print('connection audit: missing, stale or failed registered garment attachments')
                return 1
        if not os.path.isfile(path):
            if trace.get("binding_audit_required") is True:
                print("binding audit: missing required report for this external skin binding")
                return 1
            return 0
        with open(path, encoding="utf-8") as source:
            report = json.load(source)
        if report.get("status") != "pass":
            print("binding audit: current measurements are not passing")
            return 1
        with open(os.path.join(root, "animations.json"), encoding="utf-8") as source:
            doc = json.load(source)
        checked = report.get("scope", {}).get("clip_frames", {})
        required = {name: len(clip.get("frames", [])) for name, clip in doc.get("clips", {}).items() if not clip_layer(clip)}
        if any(checked.get(name) != count for name, count in required.items()):
            print("binding audit: scoped measurements do not clear all full-body clips and frames")
            return 1
        from audit_skin_binding import audit_current
        if audit_current(path):
            return 1
        manifest = (Path(path).parent / report["manifest"]).resolve()
        with manifest.open(encoding="utf-8") as source:
            registered = json.load(source)
        for clip, count in required.items():
            frames = registered.get("clips", {}).get(clip, {}).get("frames", [])
            if len(frames) != count:
                print("binding audit: actual registered frames do not match the review scope")
                return 1
            for number, frame in enumerate(frames):
                audited = (manifest.parent / frame["image"]).resolve()
                reviewed = Path(root) / "frames" / clip / f"{clip}_{number:03d}.png"
                if pixel_hash(audited) != pixel_hash(reviewed):
                    print(f"binding audit: {clip} frame {number} measures different RGBA pixels from the reviewed frame")
                    return 1
        return 0
    except (ImportError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"binding audit: missing or invalid gate: {error}")
        return 1


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


def validate_resolution(root, issue, assets):
    resolution = issue.get("resolution", {})
    prior_id = resolution.get("previous_review_id", "")
    if len(prior_id) != 64 or any(c not in "0123456789abcdef" for c in prior_id):
        raise ValueError("resolution needs a previous_review_id")
    prior_path = os.path.join(root, "review", "history", prior_id + ".json")
    if not os.path.isfile(prior_path):
        raise ValueError("previous unresolved review not found")
    with open(prior_path, encoding="utf-8") as source:
        prior = json.load(source)
    matches = [i for row in prior.get("sheets", {}).values() for i in row.get("issues", [])
               if i.get("id") == issue["id"] and i.get("resolved") is False
               and i.get("clip") == issue["clip"] and i.get("category") == issue["category"]]
    if not matches or not isinstance(resolution.get("change"), str) or not resolution["change"].strip() or not resolution.get("frames"):
        raise ValueError("resolution needs a recorded open issue, change and changed frames")
    for frame in resolution["frames"]:
        clip, number = frame.get("clip"), frame.get("frame")
        if clip != issue["clip"] or type(number) is not int or number < 0:
            raise ValueError("invalid resolution frame")
        key = f"frames/{clip}/{clip}_{number:03d}.png"
        before, after = prior.get("assets", {}).get(key), assets.get(key)
        if not before or not after or before == after:
            raise ValueError("resolved issue has no changed frame evidence")


def validate_issue_history(root, report, assets):
    """A hand-edited current status cannot erase a recorded unresolved defect."""
    registry_path = os.path.join(root, "review", "issue_registry.json")
    with open(registry_path, encoding="utf-8") as source:
        registry = json.load(source)
    if not isinstance(registry, dict) or any(not isinstance(row, dict) or type(row.get("resolved")) is not bool for row in registry.values()):
        raise ValueError("invalid issue registry")
    open_ids = {ident for ident, row in registry.items() if row["resolved"] is False}
    if open_ids:
        raise ValueError(f"issue registry still contains unresolved issues: {sorted(open_ids)}")
    history_path = os.path.join(root, "review", "history", report["review_id"] + ".json")
    with open(history_path, encoding="utf-8") as source:
        archived = json.load(source)
    if archived != report:
        raise ValueError("current report differs from its recorded review history")
    seen = set()
    for row in report["sheets"].values():
        for issue in row.get("issues", []):
            ident = issue.get("id")
            if not ident or ident in seen or ident not in registry or registry[ident]["resolved"] is not True:
                raise ValueError("current issue does not match the recorded issue registry")
            seen.add(ident)
            validate_resolution(root, issue, assets)


def record(root, path):
    """Accept only explicit, current reviews; resolution requires changed-frame evidence."""
    current_report = os.path.join(root, "visual_report.json")
    if os.path.exists(current_report):
        os.remove(current_report)
    with open(os.path.join(root, "review", "index.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    with open(path, encoding="utf-8") as fh:
        v = json.load(fh)
    try:
        entries = validate_index(root, index)
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(str(error))
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
        try:
            validate_checklist(sheet, r, entries[sheet])
        except (ValueError, KeyError, TypeError) as error:
            sys.exit(str(error))
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
                try:
                    validate_resolution(root, issue, assets)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    sys.exit(f"{sheet}: {error}")
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
    binding_pending = bool(binding_gate(root))
    report = dict(v, schema_version=REVIEW_SCHEMA, assets=assets, open_blockers=sum(i["severity"] == "blocker" for i in open_issues),
                  open_issues=len(open_issues), occlusion_review_required=occlusion_pending,
                  binding_review_required=binding_pending,
                  status="fail" if failed_sheets or open_issues else "review_required" if occlusion_pending or binding_pending else "pass")
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
    try:
        with open(path, encoding="utf-8") as source:
            report = json.load(source)
        if not isinstance(report.get("reviewer"), str) or not report["reviewer"].strip():
            raise ValueError("current review has no reviewer")
        with open(os.path.join(root, "review", "index.json"), encoding="utf-8") as source:
            index = json.load(source)
        entries = validate_index(root, index)
        if set(report.get("sheets", {})) != set(entries):
            raise ValueError("current report does not cover required sheets")
        for name, row in report["sheets"].items():
            validate_checklist(name, row, entries[name])
            if row["verdict"] != "pass" or any(issue.get("resolved") is not True for issue in row.get("issues", [])):
                raise ValueError("current report contains a failed sheet or unresolved issue")
        assets = review_assets(root)
        validate_issue_history(root, report, assets)
        current = review_id(assets)
        ok = report.get("schema_version") == REVIEW_SCHEMA and report.get("status") == "pass" and report.get("assets") == assets and report.get("review_id") == current == index.get("review_id") and occlusion_gate(root) == 0 and binding_gate(root) == 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"visual review: invalid or incomplete review: {error}")
        ok = False
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
    try:
        build(a.path)
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(f"visual review: cannot build current review: {error}")


if __name__ == "__main__":
    main()
