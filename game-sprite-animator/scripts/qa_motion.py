#!/usr/bin/env python3
"""Motion QA: measures the things that read as stutter.

    python qa_motion.py out/hero                # generated set (uses animations.json + rig_trace.json)
    python qa_motion.py path/to/frames_dir --loop               # any PNG sequence

Checks
  hold      consecutive identical frames (a repeated frame every loop is the classic hitch)
  seam      last->first frame change vs the clip's typical step, loops must close
  spike     one frame step far larger than both neighbours: a skipped in-between
  jitter    feet that should be planted wobbling in the frame (pivot/trim drift)
  slide     stance foot speed vs the ground speed the engine will use
  transition  pose jump where one clip hands over to the next
  limits    joints past their range, bones changing length, knees flipping direction
  clip      weapon through the head, weapon or body through the ground
  float     art floating free of the body
  bones     a bone with nothing drawn along it
  parts     a cut-out part missing, broken along its bone, in loose pieces, not matching its picture
  bind      the cut's own warnings (WARN) and joints it saw open (FAIL), from bind_report.json
  bounds    art cut off by the frame edge
Exit code 1 when anything FAILs.
"""
import argparse
import glob
import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sprite_anim.constraints import summarize  # noqa: E402
from sprite_anim.integrity import frame_problems, connection_report_faults, source_carry_required  # noqa: E402

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
RANK = {PASS: 0, WARN: 1, FAIL: 2}


def load_seq(paths):
    return [np.asarray(Image.open(p).convert("RGBA"), dtype=np.float32) / 255 for p in paths]


def diff(a, b):
    """Mean premultiplied RGBA change over the union silhouette."""
    pa = np.dstack([a[..., :3] * a[..., 3:], a[..., 3]])
    pb = np.dstack([b[..., :3] * b[..., 3:], b[..., 3]])
    m = (a[..., 3] > 0) | (b[..., 3] > 0)
    return float(np.abs(pa - pb)[m].mean()) if m.any() else 0.0


def worst(*st):
    return max(st, key=lambda s: RANK[s])


def analyse(frames, loop, attack=False):
    n = len(frames)
    d = [diff(frames[i], frames[i + 1]) for i in range(n - 1)]
    typical = float(np.median(d)) if d else 0.0
    res = {"frames": n, "typical_step": round(typical, 5)}
    cut = [i for i, f in enumerate(frames) if (f[0, :, 3].max() > 0 or f[-1, :, 3].max() > 0 or f[:, 0, 3].max() > 0 or f[:, -1, 3].max() > 0)]
    res["bounds"] = PASS if not cut else FAIL
    res["cut_frames"] = cut

    holds = sum(1 for x in d if x < 1e-5)
    run, longest = 0, 0
    for x in d:
        run = run + 1 if x < 1e-5 else 0
        longest = max(longest, run)
    res["hold_frames"], res["hold_run"] = holds, longest
    limit = 1 if loop else 3            # one-shots may legitimately settle on a final pose
    res["hold"] = PASS if longest < limit else (FAIL if loop else WARN)

    if loop and n > 2:
        seam = diff(frames[-1], frames[0])
        ratio = seam / max(typical, 1e-6)
        res["seam_ratio"] = round(ratio, 2)
        res["seam"] = FAIL if seam < 1e-5 else PASS if ratio <= 1.7 else WARN if ratio <= 2.6 else FAIL
    else:
        res["seam"] = PASS

    seq = d + ([diff(frames[-1], frames[0])] if loop else [])
    m = len(seq)
    peak = 0.0
    for i in range(1, m - 1) if not loop else range(m):
        nb = max(seq[(i - 1) % m], seq[(i + 1) % m])
        floor = max(nb, typical * 0.5, 0.004)
        peak = max(peak, seq[i] / floor)
    res["spike_ratio"] = round(peak, 2)
    # Attacks are meant to accelerate hard into the strike; smears carry that frame.
    hi, fail = (4.5, 8.0) if attack else (2.6, 4.0)
    res["spike"] = PASS if peak <= hi else WARN if peak <= fail else FAIL
    return res


def analyse_rig(clip, tr, speed, tags):
    res = {"slide": PASS, "jitter": PASS}
    n = len(tr["feet"]["n"]["heel"])
    if speed > 0 and any(tr["contacts"]["n"]):
        expect = -speed * tr["frame_dt"]    # px per frame the engine moves the ground under us
        errs, gaps = [], []
        for s in "nf":
            heel, ball, c = tr["feet"][s]["heel"], tr["feet"][s]["ball"], tr["contacts"][s]
            for i in range(n):
                j = (i + 1) % n
                if not (c[i] and c[j]):
                    continue
                # Follow one physical point across the step: whichever is lower over both
                # frames. Switching heel->ball mid-step would read as a fake 15 px jump.
                pts = heel if heel[i][1] + heel[j][1] <= ball[i][1] + ball[j][1] else ball
                errs.append(pts[j][0] - pts[i][0] - expect)
                gaps.append(min(heel[i][1], ball[i][1]))
        res["slide_px"] = round(float(np.abs(errs).mean()), 3)
        res["hover_px"] = round(float(np.max(np.abs(gaps))), 3)
        ok = res["slide_px"] <= 0.25 and res["hover_px"] <= 1.0
        bad = res["slide_px"] > 0.75 or res["hover_px"] > 2.5
        res["slide"] = PASS if ok else FAIL if bad else WARN
    if "hold_feet" in tags:
        wob = 0.0
        for s in "nf":
            # A foot is planted if either end stays put: lifting the heel is not sliding.
            ends = [np.array(tr["feet"][s][key]) for key in ("heel", "ball")]
            wob = max(wob, min(max(float(np.ptp(f[:, 0])), float(np.ptp(f[:, 1]))) for f in ends))
        res["foot_wobble_px"] = round(wob, 3)
        res["jitter"] = PASS if wob <= 0.25 else WARN if wob <= 0.75 else FAIL
    return res


def joint_positions(tr):
    """Frames x joints x xy, in the same output-pixel space as the trace."""
    return np.stack([tr["joints"][j] for j in sorted(tr["joints"])], axis=1)


def pose_distance(a, b):
    """RMS joint displacement; retains root motion as well as limb changes."""
    return float(np.sqrt(np.mean(np.sum((a - b) ** 2, axis=-1))))


def joint_seam(tr, height):
    pts = joint_positions(tr)
    step = float(np.mean([pose_distance(a, b) for a, b in zip(pts, pts[1:])]))
    distance = pose_distance(pts[-1], pts[0])
    # Ignore sub-perceptual movement below 0.2% of standing height, including trace rounding.
    ratio = distance / max(step, height * 0.002)
    status = PASS if ratio <= 1.7 else WARN if ratio <= 2.6 else FAIL
    values = dict(joint_seam_ratio=round(ratio, 3), joint_seam_height=round(distance / height, 5))
    return values, status


def skeleton_flags(r, seq, tr, unit_px, bones, flags):
    """Art floating free of the body and bones with nothing on them, per frame. A smear can leave
    the blade behind on purpose, so its frames skip the floating check. Traces from before these
    fields existed report n/a rather than a pass."""
    if "skeleton" not in tr:
        r["float"] = r["bones"] = "n/a"
        return
    skip = {i for i, on in enumerate(tr["smear"]) if on}
    floating, empty = frame_problems(seq, unit_px, tr["skeleton"], bones, skip)
    r["float"], r["bones"] = FAIL if floating else PASS, FAIL if empty else PASS
    for found in (floating, empty):
        for i, messages in found.items():
            flags.setdefault(i, []).extend(messages)


def occlusion_status(root, trace, clips):
    """Surface semantic-review candidates without calling them broken geometry."""
    path = os.path.join(root, 'occlusion_review.json')
    if not os.path.isfile(path) and not (trace and 'occlusion_review' in trace):
        return None
    from sprite_anim.occlusion_review import check_current
    pending = bool(check_current(root))
    candidates, error = [], None
    try:
        with open(path, encoding='utf-8') as source:
            candidates = json.load(source)['candidates']
        if not isinstance(candidates, list):
            raise ValueError('candidate list missing')
        if pending:
            for row in candidates:
                name, frame = row['clip'], row['frame']
                if name in clips and type(frame) is int and 0 <= frame < clips[name]['frames']:
                    clips[name].setdefault('flags', {}).setdefault(str(frame), []).append(
                        f"occlusion review needed: {row['arm']} hand/forearm readability; not a physical tear verdict")
    except (OSError, ValueError, KeyError, TypeError) as issue:
        error, pending = str(issue), True
        if not isinstance(candidates, list):
            candidates = []
    return dict(status=WARN if pending else PASS, review_required=pending, candidates=len(candidates),
                report='occlusion_review.json', error=error)


def locomotion_status(doc, trace, clips):
    """Check the baked clock and both displayed support frames used for stopping.

    The separate authored idle is not an endpoint of this runtime policy.
    These measurements do not certify start/stop appearance on new artwork.
    """
    required = set((trace or {}).get('locomotion_required', []))
    required.update(n for n, c in doc['clips'].items() if 'locomotion' in c)
    if not required:
        return None
    results = {}
    for name in sorted(required):
        problems, frames = [], []
        c = doc['clips'].get(name, {})
        m = c.get('locomotion', {})
        try:
            n, fps = len(c['frames']), c['fps']
            period, duty, speed = m['period_s'], m['duty'], m['speed_px_s']
            hold = m.get('hold_phase', (duty-.5)/2)
            if (not c['loop'] or m['profile'] not in ('natural_walk_v1', 'phase_walk_v1') or
                    any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                        for v in (fps, period, duty, speed, hold)) or fps <= 0 or period <= 0 or
                    not .5 < duty < 1 or speed <= 0 or not 0 <= hold < duty-.5):
                raise ValueError('invalid phase-walk contract')
            if abs(period - n/fps) > 1e-9 or abs(speed - c['speed_px_s']) > .0051:
                problems.append('movement and sprite playback clocks differ')
            if clips[name]['frames'] != n:
                problems.append('frame count differs from the exported clip')
            contacts = trace['traces'][name]['contacts']
            for side in range(2):
                frame = math.floor((hold + side*.5) * n + 1e-10)
                frames.append(frame)
                if not all(contacts[s][frame] for s in 'nf'):
                    problems.append(f'frame {frame} is not double support')
        except (KeyError, TypeError, ValueError, IndexError) as error:
            problems.append(str(error))
        if problems and name in clips:
            for frame in frames or [0]:
                clips[name].setdefault('flags', {}).setdefault(str(frame), []).extend(
                    'locomotion handover: ' + p for p in problems)
        results[name] = dict(status=FAIL if problems else PASS, hold_frames=frames, problems=problems)
    return dict(status=FAIL if any(r['problems'] for r in results.values()) else PASS,
                policy='retain_walk_phase_and_brake_to_double_support', clips=results)


def run_set(root):
    with open(os.path.join(root, "animations.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    tp = os.path.join(root, "rig_trace.json")
    trace = None
    if os.path.exists(tp):
        with open(tp, encoding="utf-8") as fh:
            trace = json.load(fh)
    report, seqs = {}, {}
    for name, c in doc["clips"].items():
        paths = sorted(glob.glob(os.path.join(root, "frames", name, "*.png")))
        if not paths:
            sys.exit(f"no frames for {name}: run generate.py without --no-frames")
        seqs[name] = load_seq(paths)
        r = analyse(seqs[name], c["loop"], "attack" in c["tags"])
        if trace:
            # Check the exported player's clock, including older exports whose
            # sidecar stored the authored interval rather than 1 / output FPS.
            runtime_trace = dict(trace["traces"][name], frame_dt=1.0 / c["fps"])
            r.update(analyse_rig(name, runtime_trace, c["speed_px_s"], c["tags"]))
            geo, flags = summarize(runtime_trace["metrics"], c["tags"], runtime_trace["frame_dt"])
            r.update(geo)
            tr = trace["traces"][name]
            if tr.get("joints") and c["loop"] and r["frames"] > 2:
                values, status = joint_seam(tr, 100 * trace["unit_px"])
                r.update(values)
                r["seam"] = worst(r["seam"], status)
                if status != PASS:
                    for i in (0, r["frames"] - 1):
                        flags.setdefault(i, []).append("joint loop seam: last -> first pose")
            for i in r["cut_frames"]:
                flags.setdefault(i, []).append("cut off by the frame edge")
            skeleton_flags(r, seqs[name], tr, trace["unit_px"], trace.get("bones", []), flags)
            r["flags"] = {str(k): v for k, v in sorted(flags.items())}
            if {'ground','tumble'}<=set(c['tags']) and (trace.get('portrait_review_required')
                    or trace.get('binding_profile') in ('basic-side-v1','side-rifle-carry-v1')
                    or source_carry_required(trace)):
                from sprite_anim.painted_ground import painted_floor
                ground_y = doc.get('pivot',[0,doc.get('frame_size',512)*.86])[1]
                floor = painted_floor(seqs[name],ground_y,trace['unit_px'])
                r['painted_floor'] = floor['status']
                r['painted_floor_evidence'] = floor
                for index in floor['bad_frames']:
                    r.setdefault('flags',{}).setdefault(str(index),[]).append('painted art below ground')
        report[name] = r
    trans = []
    if trace:
        for a, b in trace["seams"]:
            b_frame = doc["clips"][a].get("next_frame", 0) if doc["clips"][a].get("next") == b else 0
            if not isinstance(b_frame, int) or not 0 <= b_frame < len(seqs[b]):
                raise ValueError(f"invalid next_frame for {a} -> {b}: {b_frame}")
            d = diff(seqs[a][-1], seqs[b][b_frame])
            base = max(report[a]["typical_step"], report[b]["typical_step"], 0.004)
            ratio = d / base
            st = PASS if ratio <= 2.5 else WARN if ratio <= 4.0 else FAIL
            transition = dict(a=a, b=b, ratio=round(ratio, 2), status=st)
            ta, tb = trace["traces"][a], trace["traces"][b]
            if ta.get("joints") and tb.get("joints"):
                distance = pose_distance(joint_positions(ta)[-1], joint_positions(tb)[b_frame])
                normalized = distance / (100 * trace["unit_px"])
                # A tenth of standing height is visible; a fifth is a clear pose discontinuity.
                joint_status = PASS if normalized <= 0.1 else WARN if normalized <= 0.2 else FAIL
                transition.update(joint_distance_height=round(normalized, 5),
                                  status=worst(st, joint_status), a_frame=report[a]["frames"] - 1, b_frame=b_frame)
                if joint_status != PASS:
                    for clip, frame in ((a, transition["a_frame"]), (b, b_frame)):
                        report[clip]["flags"].setdefault(str(frame), []).append(f"joint transition: {a} -> {b}")
            trans.append(transition)
    cols = ["hold", "seam", "spike", "slide", "jitter", "limits", "clip", "float", "bones", "bounds", "painted_floor"]
    print(f"{'clip':<14}{'frm':>4}  " + "".join(f"{c:<7}" for c in cols) + "detail")
    failed = 0
    for name, r in report.items():
        for column in cols:
            r.setdefault(column, 'n/a')
        st = [r.get(c, 'n/a') for c in cols]
        failed += sum(1 for s in st if s == FAIL)
        detail = " ".join(f"{k}={r[k]}" for k in ("seam_ratio", "joint_seam_ratio", "spike_ratio", "slide_px", "hover_px", "foot_wobble_px", "excess_deg", "weapon_head", "weapon_ground", "body_ground") if k in r)
        print(f"{name:<14}{r['frames']:>4}  " + "".join(f"{s:<7}" for s in st) + detail)
    if trans:
        print("\ntransitions")
        for t in trans:
            failed += t["status"] == FAIL
            print(f"  {t['a']:>13} -> {t['b']:<13} {t['status']:<5} ratio={t['ratio']} joints/height={t.get('joint_distance_height', 'unavailable')}")
    parts_checked = bool(trace) and isinstance(trace.get('part_problems'), list)
    bind_checked = bool(trace) and isinstance(trace.get('bind_warnings'), list) and isinstance(trace.get('bind_gaps'), dict)
    missing = []
    if not trace:
        missing.append('rig_trace.json')
    else:
        for key, kind in (('part_problems', list), ('bind_warnings', list), ('bind_gaps', dict)):
            if not isinstance(trace.get(key), kind):
                missing.append(key)
    problems = trace['part_problems'] if parts_checked else []
    if problems:
        print("\nbroken parts (every clip is affected)")
        for p in problems:
            print("  " + p)
    bind_warnings = trace['bind_warnings'] if trace and isinstance(trace.get('bind_warnings'), list) else []
    bind_gaps = trace['bind_gaps'] if trace and isinstance(trace.get('bind_gaps'), dict) else {}
    if bind_warnings or bind_gaps:
        print("\nfrom the cut (bind_report.json)")
        for w in bind_warnings:
            print("  warning: " + w)
        for clip, joints in bind_gaps.items():
            print(f"  gap: {clip}: {joints}")
    visibility = occlusion_status(root, trace, report)
    locomotion = locomotion_status(doc, trace, report)
    out = dict(clips=report, transitions=trans,
               parts=dict(status=(FAIL if problems else PASS) if parts_checked else 'n/a', problems=problems),
               bind=dict(status=FAIL if bind_gaps else WARN if bind_warnings else PASS if bind_checked else 'n/a',
                         warnings=bind_warnings, gaps=bind_gaps),
               evidence=dict(status=WARN if missing else PASS, missing=missing,
                             scope='rig trace and part/binding evidence availability; not visual approval'))
    failed += len(problems) + len(bind_gaps)
    if trace and (trace.get('connection_review_required') or trace.get('binding_profile') == 'basic-side-v1'
                  or source_carry_required(trace)):
        faults = connection_report_faults(root, doc, trace)
        out['connections'] = dict(status=FAIL if faults else PASS, problems=faults,
                                  scope='all exported frames; full registered garment attachment')
        failed += len(faults)
        for fault in faults:
            report[fault['clip']].setdefault('flags', {}).setdefault(str(fault['frame']), []).append(
                'connection: '+fault['part']+': '+fault['what'])
        print(f"connections: {out['connections']['status']}, {len(faults)} faults")
    if locomotion is not None:
        out['locomotion'] = locomotion
        failed += sum(r['status'] == FAIL for r in locomotion['clips'].values())
        print(f"locomotion: {locomotion['status']}; phase clock and displayed stop supports")
    warns = sum(1 for r in report.values() for c in cols if r.get(c) == WARN) + sum(t["status"] == WARN for t in trans)
    warns += len(bind_warnings)
    if missing:
        warns += 1
        print('evidence: WARN; unavailable checks are n/a, not PASS; missing '+', '.join(missing))
    if visibility is not None:
        out['occlusion'] = visibility
        warns += int(visibility['review_required'])
        print(f"occlusion: {visibility['status']}, {visibility['candidates']} visual-review candidates; "
              f"review_required={visibility['review_required']}")
    total = trace.get("clips_total", len(report)) if trace else len(report)
    out["scope"] = dict(clips_checked=len(report), clips_total=total, rig_trace_available=bool(trace))
    with open(os.path.join(root, "qa_report.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"\nresult: {failed} FAIL, {warns} WARN")
    print(f"scope: {len(report)} of {total} clips, measurements only. This does not show the art looks right: review the sheets by eye.")
    return failed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--loop", action="store_true", help="for a raw frame folder")
    a = ap.parse_args()
    if os.path.exists(os.path.join(a.path, "animations.json")):
        sys.exit(1 if run_set(a.path) else 0)
    paths = sorted(glob.glob(os.path.join(a.path, "*.png")))
    if not paths:
        sys.exit("no PNG frames found")
    r = analyse(load_seq(paths), a.loop)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(1 if FAIL in r.values() else 0)


if __name__ == "__main__":
    main()
