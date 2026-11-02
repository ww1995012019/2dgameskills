# Shared by both skills. Edit the copy in the repo's shared/ folder, then run dev/sync_shared.py.
"""Joint limits and clipping checks, shared by the rig (enforcement) and QA (measurement).

Limits are soft: a pose inside the range is untouched, one past it eases into the limit along a
smooth curve. A hard clamp would stop a joint dead on one frame, a velocity jump the eye reads
as a hitch, which is the same problem the rest of the pipeline exists to avoid.
"""
import math

from .mathx import rot

# Degrees, relative to the parent bone. Lean forward and elbow bend are positive.
LIMITS = dict(
    spine=(-40.0, 52.0),    # chest relative to pelvis
    head=(-58.0, 58.0),     # head relative to chest
    elbow=(0.0, 168.0),     # forearm relative to upper arm; never bends backward
)
ANKLE_RANGE = (34.0, 178.0)  # angle between shin and foot
ANKLE_SOFT = 44.0            # closer than this and the heel starts to lift
KNEE_MAX = 165.0             # flexion, measured only: IK makes this geometric

BAND = 8.0                   # how far inside the limit the easing begins


def soft_limit(v, lo, hi, band=BAND):
    """Identity in the middle, tanh roll-off near the ends. C1 at the join, never passes the limit."""
    top, bot = hi - band, lo + band
    if v > top:
        return top + band * math.tanh((v - top) / band)
    if v < bot:
        return bot + band * math.tanh((v - bot) / band)
    return v


def limited(name, v, excess):
    """Apply a named limit, recording how far the authored pose asked to go past it."""
    lo, hi = LIMITS[name]
    out = soft_limit(v, lo, hi)
    excess.append(max(0.0, v - hi, lo - v))
    return out


def ankle_angle(knee, ankle, foot_rot):
    """Angle between the shin and the foot, 90 when standing."""
    toe = rot((1.0, 0.0), foot_rot)
    shin = (knee[0] - ankle[0], knee[1] - ankle[1])
    ln = math.hypot(*shin) or 1e-6
    return math.degrees(math.acos(max(-1.0, min(1.0, (shin[0] * toe[0] + shin[1] * toe[1]) / ln))))


def ground_clamp(angle, wrist_y, front, back, margin=2.8, reference=None):
    """Rotate a held weapon about the wrist so neither end enters the ground. angle: 0 points down,
    90 forward, -90 back. The allowed cone narrows toward level as the hand nears the floor, so
    a blade rests on the ground instead of sinking into it. Eased like the joint limits."""
    room = max(wrist_y - margin, 0.0)
    if reference is not None:
        # Project onto the connected legal arc nearest the previous orientation.
        # Choosing by the desired angle's sign would teleport across the floor.
        angle = reference + (angle - reference + 180) % 360 - 180
        lo = math.degrees(math.acos(room / front)) if front > room else 0.0
        hi = 180.0 - math.degrees(math.acos(room / back)) if back > room else 180.0
        if lo == 0 and hi == 180:
            return angle
        arcs = [(lo, hi), (-hi, -lo)]
        if lo == 0:
            arcs = [(-hi, hi)]
        elif hi == 180:
            arcs = [(lo, 360 - lo)]
        turn = math.floor(reference / 360)
        arcs = [(a + 360 * k, b + 360 * k)
                for a, b in arcs for k in range(turn - 2, turn + 3)]
        a, b = min(arcs, key=lambda ab: abs(reference - max(ab[0], min(ab[1], reference))))
        return max(a, min(b, angle))
    a = (angle + 180.0) % 360.0 - 180.0
    side = -1.0 if a < 0 else 1.0
    b = abs(a)
    if front > room:
        b = _lower(b, math.degrees(math.acos(room / front)))
    if back > room:
        b = _upper(b, 180.0 - math.degrees(math.acos(room / back)))
    return side * b


def bake_weapon_contacts(clips, body, solve, full_pose, hz=240):
    """Bake only clips whose old stateless clamp jumps across the forbidden cone.

    Fixed-rate baking keeps random-access rendering, motion blur and QA identical.
    The grip never moves: a blocked weapon stops, then resumes when there is room.
    Unaffected clips and gun IK retain their original sampling exactly.
    """
    from .mathx import Curve

    if not (body.weapon_front or body.weapon_back):
        return
    prepared = []
    for clip in clips.values():
        sample = getattr(clip, "_weapon_source", clip.sample)
        n = max(2, math.ceil(clip.duration * hz))
        dt = clip.duration / n
        times = [i * dt for i in range(n + 1)]
        rows = []
        for t in times:
            pose = full_pose(sample(t))
            if pose.get("gun_ik", 0) > 0:
                rows = []
                break
            sk = solve(pose, body)
            rows.append((sk["weapon_input"], sk["weapon_pivot_y"], sk["wep_a"]))
        def delta(a, b):
            return (a - b + 180) % 360 - 180
        if not any(a[2] * b[2] < 0 and
                   abs(delta(b[2], a[2])) > max(1e-5, 2 * abs(delta(b[0], a[0])))
                   for a, b in zip(rows, rows[1:])):
            continue
        previous = rows[0][2]
        for cycle in range(8 if clip.loop else 1):
            angles = [previous]
            for i, (desired, height, _) in enumerate(rows[1:], 1):
                # Follow authored angular speed; use a bounded catch-up speed
                # after contact releases instead of snapping to the authored pose.
                step = max(abs(delta(desired, rows[i - 1][0])), 720 * dt)
                goal = delta(desired, previous)
                candidate = previous + max(-step, min(step, goal))
                previous = ground_clamp(candidate, height, body.weapon_front,
                                        body.weapon_back, body.weapon_margin,
                                        reference=previous)
                angles.append(previous)
            if not clip.loop or abs(delta(angles[-1], angles[0])) < 1e-5:
                break
        if clip.loop:
            if abs(delta(angles[-1], angles[0])) >= 1e-5:
                raise ValueError(f"{clip.name}: weapon contact cannot close the loop; lift the grip before crossing the floor")
            # Keep winding for full rotations, but close numerical endpoint noise.
            angles[-1] = angles[0] + 360 * round((angles[-1] - angles[0]) / 360)
        prepared.append((clip, sample, times, angles))
    # Do not wrap a clip while another clip is still being sampled (combos and
    # reversed clips may delegate to it).
    for clip, sample, times, angles in prepared:
        curve = Curve(times, [[a] for a in angles])
        def corrected(t, source=sample, curve=curve, clip=clip):
            p = dict(source(t))
            at = t % clip.duration if clip.loop else t
            p["_weapon_angle"] = float(curve(at)[0])
            return p
        clip._weapon_source = sample
        clip.sample = corrected


def _lower(v, lo, band=5.0):
    return v if v >= lo + band else lo + band + band * math.tanh((v - lo - band) / band)


def _upper(v, hi, band=5.0):
    return v if v <= hi - band else hi - band + band * math.tanh((v - hi + band) / band)


def _flex(a, b, c):
    """Bend at joint b: 0 straight, positive folded. Also returns the bend direction."""
    u = (a[0] - b[0], a[1] - b[1])
    w = (c[0] - b[0], c[1] - b[1])
    lu, lw = math.hypot(*u) or 1e-6, math.hypot(*w) or 1e-6
    dot = max(-1.0, min(1.0, (u[0] * w[0] + u[1] * w[1]) / (lu * lw)))
    cross = u[0] * w[1] - u[1] * w[0]
    return 180.0 - math.degrees(math.acos(dot)), 1 if cross >= 0 else -1


def _seg_point(a, b, p):
    ab = (b[0] - a[0], b[1] - a[1])
    ln = ab[0] * ab[0] + ab[1] * ab[1] or 1e-6
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / ln))
    return math.hypot(a[0] + ab[0] * t - p[0], a[1] + ab[1] * t - p[1]), t


def _head_point(sk, body, x, y):
    c = rot((x * body.head_size, y * body.head_size), sk["head_rot"])
    return (sk["head_base"][0] + c[0], sk["head_base"][1] + c[1])


def face_circle(sk, body):
    """The eyes-to-mouth area. Chibi arms are too short to lift anything clear of the skull, so
    overhead weapons always cross the hair; only covering the face hurts the read."""
    return _head_point(sk, body, 8.5, 12.0), 7.5 * body.head_size


def foot_low(sk, side):
    """Lowest of heel and ball. The toes hinge at the ball, so they stay flat when the heel lifts
    and aren't part of the rigid foot."""
    a, r = sk["an_" + side], sk["fr_" + side]
    points=(sk.get('foot_'+side+'_heel',(-4.5, -5.0)),sk.get('foot_'+side+'_ball',(6.5, -5.0)))
    return min(a[1] + rot(p, r)[1] for p in points)


def low_points(sk, body):
    """Height of the lowest point of each body part, in rig units."""
    skull = _head_point(sk, body, 1.5, 15.0)
    return {"knee": min(sk["kn_n"][1], sk["kn_f"][1]) - 4.0, "hand": min(sk["wr_n"][1], sk["wr_f"][1]) - 3.0,
            "head": skull[1] - 13.5 * body.head_size, "hip": sk["hip"][1] - 6.0,
            "foot": min(foot_low(sk, "n"), foot_low(sk, "f"))}


def frame_metrics(sk, body, span=None):
    """One frame of geometry checks, in rig units so thresholds hold at any output size.

    span: weapon as (start, end, radius), or None for an unarmed character.
    """
    m = {"excess": round(max(sk.get("excess", [0.0])), 2)}
    bones = []
    for s in "nf":
        bones.append(abs(math.dist(sk["hip_" + s], sk["kn_" + s]) - body.thigh))
        bones.append(abs(math.dist(sk["kn_" + s], sk["an_" + s]) - body.shin))
        bones.append(abs(math.dist(sk["sh_" + s], sk["el_" + s]) - body.up_arm))
        bones.append(abs(math.dist(sk["el_" + s], sk["wr_" + s]) - body.lo_arm))
    m["bone_err"] = round(max(bones), 3)

    knees = [_flex(sk["hip_" + s], sk["kn_" + s], sk["an_" + s]) for s in "nf"]
    m["knee"] = [round(k[0], 1) for k in knees]
    m["knee_dir"] = [k[1] for k in knees]
    m["ankle"] = [round(ankle_angle(sk["kn_" + s], sk["an_" + s], sk["fr_" + s]), 1) for s in "nf"]

    lows = low_points(sk, body)
    part = min(lows, key=lows.get)
    m["body_ground"] = round(max(0.0, -lows[part]), 2)
    m["body_part"] = part
    m["weapon_head"] = 0.0
    m["weapon_ground"] = 0.0
    if span:
        a, b, r = span
        centre, radius = face_circle(sk, body)
        d, _ = _seg_point(a, b, centre)
        m["weapon_head"] = round(max(0.0, radius + r - d), 2)
        m["weapon_ground"] = round(max(0.0, -min(a[1] - r, b[1] - r)), 2)
    return m


def _longest(rows, test):
    run = best = 0
    for r in rows:
        run = run + 1 if test(r) else 0
        best = max(best, run)
    return best


def summarize(rows, tags=(), dt=1 / 30):
    """Aggregate a clip's frame metrics into statuses. Returns (result dict, flagged frames)."""
    PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
    tags = set(tags)
    flags = {}

    def flag(i, why):
        flags.setdefault(i, []).append(why)

    excess = max(r["excess"] for r in rows)
    bone = max(r["bone_err"] for r in rows)
    res = {"excess_deg": excess, "bone_err": bone}
    for i, r in enumerate(rows):
        if r["excess"] > 12:
            flag(i, f"joint past limit by {r['excess']} deg")
        if r["bone_err"] > 0.25:
            flag(i, f"bone length off by {r['bone_err']}")
        if max(r["knee"]) > KNEE_MAX:
            flag(i, f"knee folded {max(r['knee'])} deg")
        if (min(r["ankle"]) < ANKLE_RANGE[0] or max(r["ankle"]) > ANKLE_RANGE[1]) and "tumble" not in tags:
            flag(i, f"ankle {r['ankle']}")
    flips = 0
    for a, b in zip(rows, rows[1:]):
        # A knee that passes straight can legitimately read as a flip when nearly extended.
        for s in (0, 1):
            if a["knee_dir"][s] != b["knee_dir"][s] and min(a["knee"][s], b["knee"][s]) > 8:
                flips += 1
                flag(rows.index(b), "knee flipped direction")
    res["knee_flips"] = flips
    bad_limit = bone > 0.25 or flips > 0 or excess > 25
    res["limits"] = FAIL if bad_limit else WARN if excess > 12 or len(flags) else PASS

    wh = max(r["weapon_head"] for r in rows)
    wg = max(r["weapon_ground"] for r in rows)
    bg = max(r["body_ground"] for r in rows)
    res.update(weapon_head=wh, weapon_ground=wg, body_ground=bg)
    status = PASS
    # In side view the weapon is on the camera side of the head, so a swing crossing the face is
    # fine. Parking it there is not: the face vanishes for as long as the pose holds.
    allowed = 0.22 if tags & {"attack", "action"} else 0.1      # a wind-up may pause there briefly
    parked = _longest(rows, lambda r: r["weapon_head"] > 1.5) * dt > allowed and "tumble" not in tags
    res["weapon_parked"] = parked
    for i, r in enumerate(rows):
        if r["weapon_head"] > 1.5 and parked:
            flag(i, f"weapon held over face {r['weapon_head']}")
        if "ground" in tags:
            if r["weapon_ground"] > 1.0:
                flag(i, f"weapon through ground {r['weapon_ground']}")
            if r["body_ground"] > 1.0:
                flag(i, f"{r['body_part']} through ground {r['body_ground']}")
    worst = max(wh if parked else 0.0, (wg if "ground" in tags else 0.0), (bg if "ground" in tags else 0.0))
    if worst > 3.0:
        status = FAIL
    elif worst > 1.0:
        status = WARN
    res["clip"] = status
    return res, flags
