"""Articulated 2.5D humanoid, projected into eight screen directions.

The camera is fixed. Limbs move in a ground plane and have height; front, back and
profile art have different facial details and occlusion. No side-view bitmap is rotated.
Ground velocities are expressed in screen space, so diagonal travel is normalized.
"""

import math

import numpy as np

DEPTH = 0.55
DIRECTIONS = dict(
    zip(
        ("right", "down_right", "down", "down_left", "left", "up_left", "up", "up_right"),
        [(math.cos(i * math.pi / 4), math.sin(i * math.pi / 4)) for i in range(8)],
    )
)
DIRECTIONS = {k: tuple(0.0 if abs(x) < 1e-9 else x for x in v) for k, v in DIRECTIONS.items()}
MIRRORS = {"left": "right", "down_left": "down_right", "up_left": "up_right"}
DURATIONS = dict(idle=1.6, walk=0.8, run=0.6, attack=0.7, hurt=0.4, death=1.0)
LOOPS = ("idle", "walk", "run")
BONES = [
    ("hip_r", "knee_r"),
    ("knee_r", "foot_r"),
    ("hip_l", "knee_l"),
    ("knee_l", "foot_l"),
    ("shoulder_r", "elbow_r"),
    ("elbow_r", "hand_r"),
    ("shoulder_l", "elbow_l"),
    ("elbow_l", "hand_l"),
]


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def keyed(t, keys):
    for (a, x), (b, y) in zip(keys, keys[1:]):
        if t <= b:
            return x + (y - x) * smooth((t - a) / (b - a))
    return keys[-1][1]


def project(p):
    return np.array([p[0], DEPTH * p[1] - p[2]])


def basis(direction):
    dx, dy = DIRECTIONS[direction]
    ground = np.array([dx, dy / DEPTH, 0.0])
    forward = ground / np.linalg.norm(ground)
    side = np.array([forward[1], -forward[0], 0.0])
    return forward, side, ground


def gait(phase, stride, duty):
    """Foot's ground displacement, height and contact. Stance has exact constant speed."""
    if phase < duty:
        return stride * (1 - 2 * phase / duty), 0.0, True
    u = (phase - duty) / (1 - duty)
    # Hermite endpoint derivatives equal stance speed, including the loop wrap.
    m = -2 * stride * (1 - duty) / duty
    x = (
        (2 * u**3 - 3 * u**2 + 1) * -stride
        + (u**3 - 2 * u**2 + u) * m
        + (-2 * u**3 + 3 * u**2) * stride
        + (u**3 - u**2) * m
    )
    return x, 5 * math.sin(math.pi * u) ** 2, False


def knee(hip, foot, forward):
    """Two equal 18-unit bones. Bend forward in the leg's sagittal plane."""
    v = foot - hip
    d = float(np.linalg.norm(v))
    if d > 36.00001:
        raise ValueError(f"foot outside leg reach: {d}")
    axis = v / max(d, 1e-9)
    bend = forward - axis * np.dot(forward, axis)
    bend /= max(float(np.linalg.norm(bend)), 1e-9)
    return (hip + foot) / 2 + bend * math.sqrt(max(0.0, 18**2 - (d / 2) ** 2))


def sample(action, direction, phase):
    f, side, ground = basis(direction)
    z = np.array([0.0, 0.0, 1.0])
    moving = action in ("walk", "run")
    stride = 10.0 if action == "run" else 8.0
    duty = 0.55 if action == "run" else 0.6
    collapse = smooth((phase - 0.12) / 0.75) if action == "death" else 0.0
    recoil = math.sin(math.pi * phase) ** 2 if action == "hurt" else 0.0
    bob = (1 - math.cos(4 * math.pi * phase)) * 0.5 if moving else 0.0
    breath = math.sin(2 * math.pi * phase) * 0.45 if action == "idle" else 0.0
    hip_h = (28 if action == "run" else 31) - bob + breath - recoil * 3
    hip_h = hip_h * (1 - collapse) + 13 * collapse
    root = z * hip_h - f * recoil * 3
    lean = collapse * math.pi / 2 - recoil * 0.16 + (0.10 if action == "run" else 0.0)
    spine = z * math.cos(lean) + f * math.sin(lean)
    neck = root + spine * 25
    head = neck + spine * 13
    points = {"root": root, "neck": neck, "head": head}
    contacts = {}
    for label, sign, offset in (("r", 1, 0.0), ("l", -1, 0.5)):
        step, lift, contact = (
            gait((phase + offset) % 1, stride, duty) if moving else (0.0, 0.0, True)
        )
        foot = side * sign * 7 + ground * step + z * (2 + lift)
        hip = root + side * sign * 6
        points["hip_" + label] = hip
        points["knee_" + label] = knee(hip, foot, f)
        points["foot_" + label] = foot
        shoulder = root + spine * 20 + side * sign * 11
        swing = -step * 0.55 if moving else 0.0
        hand = root + side * sign * 15 + f * swing + z * 5
        if collapse:
            hand = hand * (1 - collapse) + (side * sign * 15 + f * 19 + z * 5) * collapse
        points["shoulder_" + label] = shoulder
        points["hand_" + label] = hand
        contacts[label] = contact
    # A right-handed slash, with anticipation, a clear strike, and recovery to idle.
    reach = (
        keyed(phase, [(0, 0), (0.22, -6), (0.42, 18), (0.65, 8), (1, 0)])
        if action == "attack"
        else 0.0
    )
    sweep = (
        keyed(phase, [(0, 0), (0.22, -1.1), (0.42, 1.2), (0.65, 0.4), (1, 0)])
        if action == "attack"
        else 0.0
    )
    points["hand_r"] += f * reach + side * (math.sin(sweep) * 5)
    for label in ("r", "l"):
        a, b = points["shoulder_" + label], points["hand_" + label]
        v = b - a
        distance = float(np.linalg.norm(v))
        if distance > 28:
            raise ValueError(f"hand outside arm reach: {distance}")
        axis = v / max(distance, 1e-9)
        bend = side * (1 if label == "r" else -1)
        bend -= axis * np.dot(bend, axis)
        bend /= max(float(np.linalg.norm(bend)), 1e-9)
        points["elbow_" + label] = (a + b) / 2 + bend * math.sqrt(
            max(0, 14**2 - (distance / 2) ** 2)
        )
    blade_axis = (f * math.cos(sweep) + side * math.sin(sweep)) * 0.72 + z * 0.69
    blade_axis = blade_axis * (1 - collapse) + f * collapse
    blade_axis /= np.linalg.norm(blade_axis)
    points["blade_tip"] = points["hand_r"] + blade_axis * 23
    return dict(points=points, contacts=contacts, forward=f, side=side, collapse=collapse)


def frame_count(action, fps):
    return max(4, round(DURATIONS[action] * fps)) + (0 if action in LOOPS else 1)


def phase_at(action, i, count):
    return i / (count if action in LOOPS else count - 1)


def events(action, count):
    if action in ("walk", "run"):
        return [dict(frame=0, name="footstep"), dict(frame=count // 2, name="footstep")]
    if action == "attack":
        return [
            dict(frame=round((count - 1) * 0.32), name="hit_on"),
            dict(frame=round((count - 1) * 0.56), name="hit_off"),
        ]
    if action == "death":
        return [dict(frame=round((count - 1) * 0.87), name="body_thud")]
    return []
