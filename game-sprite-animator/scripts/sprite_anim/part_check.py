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
EDGE_SLACK = 2        # picture pixels: turning a part back softens its edge by about this much
LIMBS = {n for n in PART_BONES if n.startswith(("arm_", "leg_"))}
NUB = 2.5             # rig units a limb's art may run past its joint: cut_parts.py leaves 2, marks add a little
INVENTED_SHARE = 0.03  # of a part's art outside the picture's silhouette: hand-made or a fill gone wrong
SECOND_FACE_SHARE = 0.08  # of the head also inside the torso's image: it shows when the head turns


def disc(shape, centre, radius):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return np.hypot(xx - centre[0], yy - centre[1]) <= radius


def grown(mask, steps):
    out = mask.copy()
    for _ in range(steps):
        wider = out.copy()
        wider[1:] |= out[:-1]
        wider[:-1] |= out[1:]
        wider[:, 1:] |= out[:, :-1]
        wider[:, :-1] |= out[:, 1:]
        out = wider
    return out


def in_picture(alpha, pivot, origin, size):
    """A part's alpha, turned back to where cut_parts.py took it from in the source picture."""
    w, h = size
    margin = math.ceil(math.hypot(w, h))
    centre = (origin["pivot"][0] + margin, origin["pivot"][1] + margin)
    roomy = Image.new("L", (w + 2 * margin, h + 2 * margin))
    roomy.paste(alpha, (round(centre[0] - pivot[0]), round(centre[1] - pivot[1])))
    back = roomy.rotate(-origin["angle"], resample=Image.BILINEAR, center=centre)
    return np.asarray(back.crop((margin, margin, margin + w, margin + h))) > SOLID


def check_source(spec):
    """Do the parts still match the picture they were cut from? Rigs with no record of it are skipped."""
    base = spec.get("_dir", ".")
    path = os.path.join(base, spec.get("source_image") or "")
    parts = {n: p for n, p in (spec.get("parts") or {}).items() if "from" in p}
    if not parts or not spec.get("source_image") or not os.path.isfile(path):
        return []
    with Image.open(path) as im:
        picture = im.convert("RGBA")
    art = grown(np.asarray(picture)[..., 3] > 24, EDGE_SLACK)
    placed, out = {}, []
    for name, part in parts.items():
        image = os.path.join(base, part["image"])
        if not os.path.isfile(image):
            continue     # check_part has already reported it
        with Image.open(image) as im:
            placed[name] = in_picture(im.convert("RGBA").getchannel("A"), part["pivot"], part["from"], picture.size)
        extra = placed[name] & ~art
        if placed[name].any() and extra.sum() > INVENTED_SHARE * placed[name].sum():
            out.append(f"{name}: {extra.sum() / placed[name].sum():.0%} of it is not in the source picture, "
                       "pixels were invented past the silhouette")
    if "head" in placed and "torso" in placed and placed["head"].any():
        shared = (placed["head"] & placed["torso"]).sum() / placed["head"].sum()
        if shared > SECOND_FACE_SHARE:
            out.append(f"torso: {shared:.0%} of the head is also in this image, a second face shows when the head turns")
    return out


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
        if name in LIMBS:
            yy, xx = np.nonzero(solid)
            along = (xx - pivot[0]) * direction[0] + (yy - pivot[1]) * direction[1]
            across = np.abs((xx - pivot[0]) * direction[1] - (yy - pivot[1]) * direction[0])
            past = along[across < STRIP * ppu].max(initial=0) / ppu - span
            if past > NUB:
                out.append(f"{name}: art runs {past:.1f} units past its joint, it sticks out as a nub when the joint bends")
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
    return out + check_source(spec)
