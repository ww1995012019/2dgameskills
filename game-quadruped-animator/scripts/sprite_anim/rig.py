"""A canine rig: three spine segments, neck/head, four digitigrade legs and a tail anchor.

Coordinates are x-forward, y-up, floor y=0. Each leg has three fixed-length segments.
Paws are independent ground targets. Stance travels at exactly -clip.speed; body sway
is solved around those targets, never added to a planted paw.
"""

import math
from dataclasses import dataclass

import numpy as np

from .mathx import hermite

LEGS = ("hind_near", "hind_far", "front_near", "front_far")
GAITS = {
    "idle": dict(duration=1.6, stride=0.0, duty=1.0, phases=dict.fromkeys(LEGS, 0.0), lift=0.0),
    "walk": dict(
        duration=1.04,
        stride=8.0,
        duty=0.72,
        phases=dict(zip(LEGS, (0.0, 0.5, 0.25, 0.75))),
        lift=5.0,
    ),
    "trot": dict(
        duration=0.68, stride=9.0, duty=0.5, phases=dict(zip(LEGS, (0.5, 0.0, 0.0, 0.5))), lift=7.0
    ),
    "run": dict(
        duration=0.48,
        stride=10.0,
        duty=0.28,
        phases=dict(zip(LEGS, (0.0, 0.1, 0.56, 0.46))),
        lift=10.0,
    ),
}
ACTIONS = dict(attack=0.8, hurt=0.48, death=1.2)

LENGTHS = {
    "spine_0->spine_1": 14.0,
    "spine_1->spine_2": 15.0,
    "spine_2->spine_3": 14.0,
    "spine_3->neck": 12.0,
    "neck->head": 11.0,
}
for leg in LEGS:
    LENGTHS.update(
        {
            leg + "_root->" + leg + "_bend": 18.0,
            leg + "_bend->" + leg + "_ankle": 20.0,
            leg
            + "_ankle->"
            + leg
            + "_paw": math.hypot(3, 7) if leg.startswith("hind") else math.hypot(4, 4),
        }
    )


def polar(length, degrees):
    a = math.radians(degrees)
    return np.array([length * math.cos(a), length * math.sin(a)])


def two_bone(root, target, bend):
    delta = target - root
    distance = float(np.linalg.norm(delta))
    if not 2.000001 < distance < 37.999999:
        raise ValueError(f"unreachable canine foot target: {distance:.5f}")
    axis = delta / distance
    along = (18**2 - 20**2 + distance**2) / (2 * distance)
    height = math.sqrt(max(0.0, 18**2 - along**2))
    normal = np.array([-axis[1], axis[0]]) * bend
    return root + axis * along + normal * height


@dataclass
class Clip:
    name: str
    fps: int

    def __post_init__(self):
        if self.name in ACTIONS:
            self.gait = GAITS["idle"]
            self.count = max(8, round(ACTIONS[self.name] * self.fps)) + 1
            self.duration = (self.count - 1) / self.fps
            self.loop = False
            self.speed = 0.0
            return
        self.gait = GAITS[self.name]
        self.count = max(8, round(self.gait["duration"] * self.fps / 4) * 4)
        self.duration = self.count / self.fps
        self.loop = True
        self.speed = (
            0.0
            if self.name == "idle"
            else 2 * self.gait["stride"] / (self.gait["duty"] * self.duration)
        )

    def vel(self, t):
        return self.speed, 0.0


def foot_path(phase, gait):
    duty = gait["duty"]
    stride = gait["stride"]
    if phase < duty:
        return stride * (1 - 2 * phase / duty), 0.0, True
    u = (phase - duty) / (1 - duty)
    tangent = -2 * stride * (1 - duty) / duty
    return (
        float(hermite(-stride, tangent, stride, tangent, u)),
        gait["lift"] * math.sin(math.pi * u) ** 2,
        False,
    )


def sample(clip, t):
    if not clip.loop:
        return combat_sample(clip, t)
    phase = (t / clip.duration) % 1
    g = clip.gait
    if clip.name == "idle":
        bob = 0.45 * math.sin(math.tau * phase)
        flex = 0.6 * math.sin(math.tau * phase)
    elif clip.name == "walk":
        bob = 0.6 * math.cos(2 * math.tau * phase)
        flex = 1.5 * math.sin(math.tau * phase)
    elif clip.name == "trot":
        bob = -1.2 * math.cos(2 * math.tau * phase)
        flex = 2.0 * math.sin(math.tau * phase)
    else:
        bob = 3.0 * math.cos(2 * math.tau * (phase - 0.42))
        flex = 10.0 * math.sin(math.tau * (phase - 0.1))
    joints = {"spine_0": np.array([-23.0, 34.0 + bob])}
    for i, (length, angle) in enumerate(((14, 5 + flex), (15, 6 - flex * 0.5), (14, -1 - flex))):
        joints["spine_" + str(i + 1)] = joints["spine_" + str(i)] + polar(length, angle)
    shoulder = joints["spine_3"]
    head_bob = (1.5 if clip.name == "run" else 0.7) * math.sin(math.tau * phase)
    joints["neck"] = shoulder + polar(12, 40 + head_bob)
    joints["head"] = joints["neck"] + polar(11, 15 - head_bob)
    joints["muzzle"] = joints["head"] + polar(12, -10)
    contacts = {}
    for leg in LEGS:
        hind = leg.startswith("hind")
        near = leg.endswith("near")
        root = joints["spine_0" if hind else "spine_3"] + np.array(
            [1.5 if near else -1.5, -1.0 if near else 0.3]
        )
        step, lift, contact = foot_path((phase - g["phases"][leg]) % 1, g)
        base = (-22.0 if hind else 22.0) + (1.5 if near else -1.5)
        paw = np.array([base + step, 2.0 + lift])
        ankle = paw + np.array([-3, 7] if hind else [-4, 4])
        joints[leg + "_root"] = root
        joints[leg + "_bend"] = two_bone(root, ankle, 1 if hind else -1)
        joints[leg + "_ankle"] = ankle
        joints[leg + "_paw"] = paw
        contacts[leg] = contact
    joints["tail_base"] = joints["spine_0"] + np.array([-2.0, 1.0])
    spine_rot = math.degrees(math.atan2(*(joints["spine_1"] - joints["spine_0"])[::-1]))
    return dict(
        joints=joints,
        contacts=contacts,
        phase=phase,
        spine_rot=spine_rot,
        mouth=(0.8 if clip.name == "run" else 0.25 if clip.name == "trot" else 0.0),
    )


def combat_sample(clip, t):
    u = min(1.0, max(0.0, t / clip.duration))
    base = sample(Clip("idle", clip.fps), 0.0)

    def ease(v):
        v = min(1.0, max(0.0, v))
        return v * v * (3 - 2 * v)

    collapse = ease((u - 0.12) / 0.78) if clip.name == "death" else 0.0
    pulse = math.sin(math.pi * u) ** 2
    thrust = (ease(u / 0.38) * (1 - ease((u - 0.48) / 0.52))) if clip.name == "attack" else 0.0
    shift = 3 * thrust if clip.name == "attack" else -3 * pulse if clip.name == "hurt" else 0.0
    j = base["joints"]
    for k in ("spine_0", "spine_1", "spine_2", "spine_3"):
        j[k] = j[k] + np.array(
            [
                shift,
                -15 * collapse - 2 * pulse if clip.name == "hurt" else -15 * collapse - 2 * thrust,
            ]
        )
    shoulder = j["spine_3"]
    neck_angle = 40 - 80 * collapse - 32 * thrust + 10 * pulse * (clip.name == "hurt")
    head_angle = 15 - 45 * collapse - 15 * thrust
    j["neck"] = shoulder + polar(12, neck_angle)
    j["head"] = j["neck"] + polar(11, head_angle)
    j["muzzle"] = j["head"] + polar(12, -10)
    for leg in LEGS:
        hind = leg.startswith("hind")
        near = leg.endswith("near")
        root = j["spine_0" if hind else "spine_3"] + np.array(
            [1.5 if near else -1.5, -1 if near else 0.3]
        )
        j[leg + "_root"] = root
        j[leg + "_bend"] = two_bone(root, j[leg + "_ankle"], 1 if hind else -1)
    j["tail_base"] = j["spine_0"] + np.array([-2.0, 1.0])
    base.update(phase=u, collapse=collapse, mouth=1.7 * thrust if clip.name == "attack" else 0.0)
    return base
