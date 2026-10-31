"""Are a cut-out character's part images whole? Checked on the images, before any animation.

A rendered frame can't answer this: an upper arm with its middle gone lies over the torso in most
poses, and the torso fills the hole. Each part is checked alone, in the rest orientation the rig
turns it from. Returns plain messages; any message fails QA.
"""
import math
import os

import numpy as np
from PIL import Image

from .art import CUTOUT_BONES
from .integrity import PART_GAP_SHARE, SOLID, islands, strip_gap

# Bone inside each part: the body length it spans, and +1 when it hangs down from the pivot or -1
# when it points up. Hands, feet and head have no one bone to walk; a weapon's length comes from
# its own entry, which cut_parts.py writes.
PART_BONES = {"arm_f_up": ("up_arm", 1), "arm_f_lo": ("lo_arm", 1), "leg_f_up": ("thigh", 1), "leg_f_lo": ("shin", 1),
              "arm_n_up": ("up_arm", 1), "arm_n_lo": ("lo_arm", 1), "leg_n_up": ("thigh", 1), "leg_n_lo": ("shin", 1),
              "pelvis": ("pelvis_len", -1), "torso": ("chest_len", -1)}
STRIP = 1.2           # rig units either side of the bone that may hold the art
PIVOT_REACH = 1.5     # rig units: a pivot further than this from any art turns the part about air
MIN_AREA = 2.0        # square rig units: less than this is not a body part
GRIP_REACH = 6.0      # rig units around the grip the fist hides, so a blade may be split there


def disc(shape, centre, radius):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return np.hypot(xx - centre[0], yy - centre[1]) <= radius


def check_part(name, solid, pivot, rest_angle, ppu, body, weapon_length=None):
    if solid.sum() < MIN_AREA * ppu * ppu:
        return [f"{name}: image is empty or nearly empty ({int(solid.sum())} px)"]
    out = []
    if not (solid & disc(solid.shape, pivot, PIVOT_REACH * ppu)).any():
        out.append(f"{name}: no art at its pivot, it would turn about empty space")
    field, sign = PART_BONES.get(name, (None, -1))
    span = getattr(body, field) if field else weapon_length if name == "weapon" else None
    if span:
        a = math.radians(rest_angle)
        direction = (-math.sin(a) * sign, math.cos(a) * sign)
        gap = strip_gap(solid, pivot, direction, span * ppu, STRIP * ppu)
        if gap > PART_GAP_SHARE:
            out.append(f"{name}: {gap:.0%} of the bone has no art in its own image, the limb is broken")
    bridge = disc(solid.shape, pivot, GRIP_REACH * ppu) if name == "weapon" else None
    loose = islands(solid, bridge)
    if loose:
        out.append(f"{name}: {len(loose)} piece(s) cut off from the part ({loose[0]:.0%} of it), it will float as the part moves")
    return out


def check_parts(spec, body):
    """Every problem with spec["parts"], or [] if all are whole."""
    parts = spec.get("parts") or {}
    wanted = [n for n in CUTOUT_BONES if n != "weapon" or spec.get("weapon", "sword") != "none"]
    out = [f"{n}: part is missing, the rig will draw nothing on that bone" for n in wanted if n not in parts]
    ppu = float(spec.get("px_per_unit", 4.0))
    for name, part in parts.items():
        path = os.path.join(spec.get("_dir", "."), part["image"])
        if not os.path.isfile(path):
            out.append(f"{name}: image {part['image']} not found")
            continue
        with Image.open(path) as im:
            solid = np.asarray(im.convert("RGBA"))[..., 3] > SOLID
        out += check_part(name, solid, tuple(part["pivot"]), float(part.get("rest_angle", 0)),
                          ppu / float(part.get("scale", 1.0)), body, part.get("length"))
    return out
