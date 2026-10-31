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
  bounds    art cut off by the frame edge
  grip      hands drifting off the gun
  cadence   shots not evenly spaced in frames, or a shot frame with no muzzle flash
Exit code 1 when anything FAILs.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sprite_anim.constraints import summarize  # noqa: E402
from sprite_anim.integrity import frame_problems  # noqa: E402

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


def analyse(frames, loop, tags=()):
    attack = "attack" in tags or "action" in tags
    fire = "fire" in tags
    subtle = "subtle" in tags       # slow enough that pixel rounding decides which frame changes
    drift = "drift" in tags         # closed-form periodic: only rounding can open the seam
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
    if subtle or fire:  # slow breathing and post-shot cooldown legitimately hold a frame
        res["hold"] = PASS

    if loop and n > 2:
        seam = diff(frames[-1], frames[0])
        ratio = seam / max(typical, 1e-6)
        res["seam_ratio"] = round(ratio, 2)
        res["seam"] = FAIL if seam < 1e-5 else PASS if ratio <= 1.7 else WARN if ratio <= 2.6 else FAIL
        if subtle or fire or drift:     # for fire, recoil snapping back at the wrap is the shot
            res["seam"] = PASS
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
    res["spike"] = PASS if fire or subtle or peak <= hi else WARN if peak <= fail else FAIL
    return res


def analyse_rig(clip, tr, speed, tags):
    res = {"slide": PASS, "jitter": PASS, "grip": PASS, "cadence": PASS}
    gaps = [g for row in tr.get("gaps", []) for g in row]
    if gaps:
        res["grip_px"] = round(max(gaps), 2)
        res["grip"] = PASS if res["grip_px"] <= 0.6 else WARN if res["grip_px"] <= 1.5 else FAIL
    shots = tr.get("shots") or []
    if shots:
        spacing = {b - a for a, b in zip(shots, shots[1:])}
        lit = all(tr["flash"][f] > 0.9 for f in shots)
        res["shots"] = len(shots)
        res["cadence"] = PASS if lit and len(spacing) <= 1 else FAIL
    n = len(tr["feet"]["n"]["heel"])
    if speed != 0 and any(tr["contacts"]["n"]):
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


def joint_seam(tr, height, layer="full"):
    pts = joint_positions(tr)
    step = float(np.mean([pose_distance(a, b) for a, b in zip(pts, pts[1:])]))
    distance = pose_distance(pts[-1], pts[0])
    # Ignore sub-perceptual movement below 0.2% of standing height, including trace rounding.
    ratio = distance / max(step, height * 0.002)
    status = PASS if ratio <= 1.7 else WARN if ratio <= 2.6 else FAIL
    values = dict(joint_seam_ratio=round(ratio, 3), joint_seam_height=round(distance / height, 5))
    if 0 in tr.get("shots", []):
        # A shot at the wrap intentionally resets recoil. Bound the whole pose impulse by
        # standing height, using the same limits as a transition, rather than recovery speed.
        status = PASS if distance / height <= 0.1 else WARN if distance / height <= 0.2 else FAIL
        values["joint_seam_mode"] = "shot_impulse"
        if layer != "upper":
            # Running while firing still needs a continuous gait; recoil is upper-body only.
            lower = {j: p for j, p in tr["joints"].items() if j in ("an_n", "an_f", "kn_n", "kn_f", "hip")}
            gait, gait_status = joint_seam({"joints": lower}, height)
            values["joint_gait_seam_ratio"] = gait["joint_seam_ratio"]
            status = worst(status, gait_status)
    return values, status


def skeleton_flags(r, seq, tr, unit_px, bones, flags, layer, tags):
    """Art floating free of the body and bones with nothing on them, per frame. Layered clips draw
    half a body, so only that half's bones are held to it. Fire and action clips throw things clear
    of the body on purpose (casings, a dropped magazine) and report float n/a, as do smear frames in
    the rest. Traces from before these fields existed report n/a rather than a pass."""
    if "skeleton" not in tr:
        r["float"] = r["bones"] = "n/a"
        return
    if layer != "full":
        bones = [b for b in bones if (b[0][:2] in ("sh", "el", "wa")) == (layer == "upper")]
    props = "fire" in tags or "action" in tags
    skip = set(range(len(seq))) if props else {i for i, on in enumerate(tr["smear"]) if on}
    floating, empty = frame_problems(seq, unit_px, tr["skeleton"], bones, skip)
    r["float"], r["bones"] = "n/a" if props else FAIL if floating else PASS, FAIL if empty else PASS
    for found in (floating, empty):
        for i, messages in found.items():
            flags.setdefault(i, []).extend(messages)


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
        r = analyse(seqs[name], c["loop"], c["tags"])
        if trace:
            r.update(analyse_rig(name, trace["traces"][name], trace["speeds"][name], c["tags"]))
            geo, flags = summarize(trace["traces"][name]["metrics"], c["tags"], trace["traces"][name]["frame_dt"])
            r.update(geo)
            tr = trace["traces"][name]
            if tr.get("joints") and c["loop"] and r["frames"] > 2:
                values, status = joint_seam(tr, 100 * trace["unit_px"], c.get("layer", "full"))
                r.update(values)
                r["seam"] = worst(r["seam"], status)
                if status != PASS:
                    for i in (0, r["frames"] - 1):
                        flags.setdefault(i, []).append("joint loop seam: last -> first pose")
            for i in r["cut_frames"]:
                flags.setdefault(i, []).append("cut off by the frame edge")
            skeleton_flags(r, seqs[name], tr, trace["unit_px"], trace.get("bones", []), flags, c.get("layer", "full"), c["tags"])
            r["flags"] = {str(k): v for k, v in sorted(flags.items())}
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
    out = dict(clips=report, transitions=trans)
    cols = ["hold", "seam", "spike", "slide", "jitter", "grip", "cadence", "limits", "clip", "float", "bones", "bounds"]
    print(f"{'clip':<22}{'frm':>4}  " + "".join(f"{c:<7}" for c in cols) + "detail")
    failed = 0
    for name, r in report.items():
        st = [r.get(c, PASS) for c in cols]
        failed += sum(1 for s in st if s == FAIL)
        detail = " ".join(f"{k}={r[k]}" for k in ("seam_ratio", "joint_seam_ratio", "spike_ratio", "slide_px", "hover_px", "foot_wobble_px", "grip_px", "shots", "excess_deg", "weapon_head", "weapon_ground", "body_ground") if k in r)
        print(f"{name:<22}{r['frames']:>4}  " + "".join(f"{s:<7}" for s in st) + detail)
    if trans:
        print("\ntransitions")
        for t in trans:
            failed += t["status"] == FAIL
            print(f"  {t['a']:>13} -> {t['b']:<13} {t['status']:<5} ratio={t['ratio']} joints/height={t.get('joint_distance_height', 'unavailable')}")
    with open(os.path.join(root, "qa_report.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    warns = sum(1 for r in report.values() for c in cols if r.get(c) == WARN) + sum(t["status"] == WARN for t in trans)
    print(f"\nresult: {failed} FAIL, {warns} WARN")
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
