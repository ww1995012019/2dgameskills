"""Direction-aware 3/4 character art: depth-sorted limbs, front/back clothing and heads."""

import math

import numpy as np
from PIL import Image, ImageDraw

from .topdown import project

DEFAULTS = dict(
    skin="#edbd97",
    hair="#54362c",
    coat="#397eb3",
    trim="#d8b966",
    pants="#344055",
    boots="#554036",
    scarf="#c94e49",
    steel="#c8dae2",
    ink="#20212d",
)


def rgb(value):
    return tuple(bytes.fromhex(value.lstrip("#")))


def tint(c, amount):
    return tuple(int(max(0, min(255, v * amount))) for v in c)


class TopDownArt:
    def __init__(self, spec, size, pixel):
        self.size, self.pixel = size, pixel
        self.ss = 1 if pixel else 3
        self.unit = size / 120
        self.pivot = (size // 2, round(size * 0.78))
        self.colors = {k: rgb(v) for k, v in dict(DEFAULTS, **spec.get("colors", {})).items()}
        self.hood = spec.get("head", "hair") == "hood"
        self.palette = np.array(
            list(self.colors.values())
            + [tint(c, t) for c in self.colors.values() for t in (0.72, 1.18)],
            dtype=np.int16,
        )

    def render(self, pose):
        ss, unit = self.ss, self.unit
        im = Image.new("RGBA", (self.size * ss, self.size * ss))
        d = ImageDraw.Draw(im)
        p = pose["points"]
        f, side = pose["forward"], pose["side"]
        c = self.colors
        ink = (*c["ink"], 255)
        stroke = max(1, round(unit * 0.8 * ss))

        def xy(v):
            q = project(v) * unit
            return ((self.pivot[0] + q[0]) * ss, (self.pivot[1] + q[1]) * ss)

        def poly(points, fill, outline=True):
            pts = [xy(v) for v in points]
            d.polygon(pts, fill=(*fill, 255))
            if outline:
                d.line(pts + [pts[0]], fill=ink, width=stroke, joint="curve")

        def oval(center, rx, ry, fill, outline=True):
            x, y = xy(center)
            box = (x - rx * unit * ss, y - ry * unit * ss, x + rx * unit * ss, y + ry * unit * ss)
            d.ellipse(box, fill=(*fill, 255), outline=ink if outline else None, width=stroke)

        def segment(a, b, radius, fill):
            a2, b2 = np.array(xy(a)), np.array(xy(b))
            v = b2 - a2
            length = float(np.linalg.norm(v))
            if length < 1e-6:
                oval(a, radius, radius, fill)
                return
            normal = np.array([-v[1], v[0]]) / length * radius * unit * ss
            pts = [
                tuple(a2 + normal),
                tuple(b2 + normal * 0.8),
                tuple(b2 - normal * 0.8),
                tuple(a2 - normal),
            ]
            d.polygon(pts, fill=(*fill, 255))
            d.line(pts + [pts[0]], fill=ink, width=stroke, joint="curve")
            for point, r in ((a2, radius), (b2, radius * 0.8)):
                rad = r * unit * ss
                d.ellipse(
                    (point[0] - rad, point[1] - rad, point[0] + rad, point[1] + rad),
                    fill=(*fill, 255),
                    outline=ink,
                    width=stroke,
                )

        # Separate foot shadows show contact in a ground plane, not a side-view ground line.
        for label in ("r", "l"):
            foot = p["foot_" + label].copy()
            foot[2] = 0
            x, y = xy(foot)
            r = unit * ss * 5
            d.ellipse((x - r, y - r * 0.4, x + r, y + r * 0.4), fill=(22, 30, 40, 65))

        parts = []

        def part(depth, order, fn):
            parts.append((float(depth), order, fn))

        for label in ("r", "l"):
            hip, knee, foot = [p[k + "_" + label] for k in ("hip", "knee", "foot")]
            shade = 0.78 if foot[1] < 0 else 1.0

            def leg(hip=hip, knee=knee, foot=foot, shade=shade):
                segment(hip, knee, 4.3, tint(c["pants"], shade))
                segment(knee, foot, 3.5, tint(c["pants"], shade))
                oval(foot + f * 2, 4.8, 2.8, tint(c["boots"], shade))
                # Toe extends with facing, rather than using a front-facing oval for every view.
                segment(foot, foot + f * 4, 2.5, tint(c["boots"], shade))

            part((foot[1] + hip[1]) / 2, -3, leg)

        def torso():
            root = p["root"]
            neck = p["neck"]
            front = f * 4
            back = -f * 4
            # Back and front panels have different trim; side panels show depth at oblique views.
            panels = []
            for offset, color in ((front, c["coat"]), (back, tint(c["coat"], 0.72))):
                pts = [
                    root - side * 8 + offset,
                    root + side * 8 + offset,
                    neck + side * 11 + offset,
                    neck - side * 11 + offset,
                ]
                panels.append((float(offset[1]), pts, color))
            panels.append(
                (
                    float(side[1] * 10),
                    [
                        root + side * 8 - front,
                        root + side * 8 + front,
                        neck + side * 11 + front,
                        neck + side * 11 - front,
                    ],
                    tint(c["coat"], 0.82),
                )
            )
            panels.append(
                (
                    float(-side[1] * 10),
                    [
                        root - side * 8 - front,
                        root - side * 8 + front,
                        neck - side * 11 + front,
                        neck - side * 11 - front,
                    ],
                    tint(c["coat"], 0.9),
                )
            )
            for _, pts, col in sorted(panels, key=lambda v: v[0]):
                poly(pts, col)
            belt = root + np.array([0, 0, 4.0])
            segment(belt - side * 9, belt + side * 9, 1.8, c["boots"])
            if f[1] >= 0:
                oval(belt + front, 1.8, 1.6, c["trim"])
                # Buttons are only on the chest; no face/chest details on a back view.
                for h in (10, 15):
                    oval(root + np.array([0, 0, h]) + front, 0.7, 0.8, c["trim"], False)
            else:
                # Back seam and a small satchel make the rear view unambiguous.
                segment(root + np.array([0, 0, 8]) + back, neck + back, 0.7, tint(c["coat"], 0.6))
                bag = root + np.array([0, 0, 9]) + back
                oval(bag, 5, 5, c["boots"])
            # Scarf knot and two tails, with phase-derived motion already in the skeleton.
            knot = neck + back
            segment(neck - side * 10, neck + side * 10, 2.2, c["scarf"])
            tail = knot + back * 1.7 - np.array([0, 0, 11.0])
            poly([knot - side * 2, knot + side * 2, tail + side * 3, tail - side * 2], c["scarf"])

        part(0, 0, torso)

        for label in ("r", "l"):
            shoulder, elbow, hand = [p[k + "_" + label] for k in ("shoulder", "elbow", "hand")]
            shade = 0.78 if hand[1] < 0 else 1.0

            def arm(shoulder=shoulder, elbow=elbow, hand=hand, shade=shade):
                segment(shoulder, elbow, 3.4, tint(c["coat"], shade))
                segment(elbow, hand, 2.8, tint(c["coat"], shade))
                oval(hand, 2.8, 2.7, c["skin"])

            part((shoulder[1] + hand[1]) / 2, 1, arm)

        def weapon():
            hand = p["hand_r"]
            tip = p["blade_tip"]
            axis = tip - hand
            base = hand + axis * 0.18
            normal = side * 2.3
            poly([base - normal, base + normal, tip], c["steel"])
            segment(hand - normal * 1.6, hand + normal * 1.6, 0.9, c["trim"])
            segment(hand - axis * 0.13, hand, 1.1, c["boots"])

        part((p["hand_r"][1] + p["blade_tip"][1]) / 2, 2, weapon)

        def head():
            center = p["head"]
            frontness = float(f[1])
            profile = abs(float(f[0]))
            hair = c["coat"] if self.hood else c["hair"]
            width = 12 - profile * 2
            oval(center, width, 13, hair)
            if frontness > -0.25:
                face = center + np.array([f[0] * 4, 0, -2.0])
                oval(face, width - 2, 9.8, c["skin"])
                # Hairline follows front/side facing; back and back-diagonal show only hair.
                x, y = xy(center + np.array([0, 0, 6.0]))
                w = width * unit * ss
                d.polygon(
                    [
                        (x - w, y),
                        (x + w, y),
                        (x + w * 0.7, y + 3 * unit * ss),
                        (x - w * 0.8, y + unit * ss),
                    ],
                    fill=(*hair, 255),
                )
                eyes = (-4, 4) if frontness > 0.45 else (4 if f[0] > 0 else -4,)
                for offset in eyes:
                    eye = face + np.array([offset * (1 - profile * 0.35), 0, 1.0])
                    if pose["collapse"] > 0.65:
                        a, b = xy(eye + np.array([-1.4, 0, 0.0])), xy(eye + np.array([1.4, 0, 0.0]))
                        d.line([a, b], fill=ink, width=stroke)
                    else:
                        oval(eye, 0.9, 1.5, c["ink"], False)
                        oval(eye + np.array([-0.25, 0, 0.5]), 0.25, 0.4, c["steel"], False)
                oval(face + np.array([f[0] * 3, 0, -4.0]), 1.4, 0.6, tint(c["skin"], 0.75), False)
            elif self.hood:
                # Stitch on the back of the hood.
                segment(
                    center + np.array([0, 0, -5.0]),
                    center + np.array([0, 0, 7.0]),
                    0.7,
                    tint(hair, 0.7),
                )
            else:
                for dx in (-5, 1, 6):
                    segment(
                        center + np.array([dx, 0, 3.0]),
                        center + np.array([dx - 2, 0, -7.0]),
                        0.7,
                        tint(hair, 0.8),
                    )

        part(float(p["head"][1]), 3, head)
        for _, _, draw in sorted(parts, key=lambda a: (a[0], a[1])):
            draw()
        if ss > 1:
            im = im.resize((self.size, self.size), Image.Resampling.LANCZOS)
        out = np.asarray(im).copy()
        if self.pixel:
            mask = out[..., 3] > 127
            colors = out[..., :3][mask].astype(np.int16)
            idx = np.argmin(
                ((colors[:, None, :].astype(np.int32) - self.palette[None, :, :]) ** 2).sum(2),
                axis=1,
            )
            out[..., :3][mask] = self.palette[idx].astype(np.uint8)
            out[..., 3] = mask.astype(np.uint8) * 255
        return out
