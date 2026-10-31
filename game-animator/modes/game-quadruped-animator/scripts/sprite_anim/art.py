"""Side-view wolf art. A long muzzle, pointed ears, chest ruff, hocks and bushy tail."""

import math

import numpy as np
from PIL import Image, ImageDraw

from .mathx import catmull_closed


DEFAULTS = dict(
    fur="#89969d",
    back="#596775",
    belly="#c3c6ba",
    far="#57616d",
    eye="#e5b55b",
    nose="#232a32",
    ink="#26313b",
)


def capsule(a, b, ra, rb):
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    out = []
    for center, r, start in ((a, ra, angle + math.pi / 2), (b, rb, angle - math.pi / 2)):
        for i in range(11):
            t = start + i * math.pi / 10
            out.append(center + np.array([math.cos(t), math.sin(t)]) * r)
    return out


class QuadrupedArt:
    def __init__(self, spec, size, pixel):
        self.size, self.pixel = size, pixel
        self.unit = size / 142
        self.pivot = (size // 2, round(size * 0.82))
        self.ss = 1 if pixel else 3
        self.colors = {
            k: tuple(bytes.fromhex(v.lstrip("#")))
            for k, v in dict(DEFAULTS, **spec.get("colors", {})).items()
        }

    def render(self, pose, tail):
        s = self.unit * self.ss
        px, py = self.pivot
        im = Image.new("RGBA", (self.size * self.ss, self.size * self.ss))
        d = ImageDraw.Draw(im)
        c = self.colors
        ink = c["ink"]
        sw = max(1, round(s * 0.55))
        j = pose["joints"]

        def xy(p):
            return ((px + p[0] * self.unit) * self.ss, (py - p[1] * self.unit) * self.ss)

        def polygon(points, color, outline=True, smooth=False):
            if smooth:
                points = catmull_closed(points, 5)
            pts = [xy(p) for p in points]
            d.polygon(pts, fill=(*color, 255))
            if outline:
                d.line(pts + [pts[0]], fill=(*ink, 255), width=sw, joint="curve")

        def oval(center, rx, ry, color, outline=True):
            x, y = xy(center)
            d.ellipse(
                (x - rx * s, y - ry * s, x + rx * s, y + ry * s),
                fill=(*color, 255),
                outline=(*ink, 255) if outline else None,
                width=sw,
            )

        def line(a, b, color, width=1):
            d.line([xy(a), xy(b)], fill=(*color, 255), width=max(1, round(width * s)))

        def leg(name, far):
            root, bend, ankle, paw = (j[name + "_" + k] for k in ("root", "bend", "ankle", "paw"))
            hind = name.startswith("hind")
            color = c["far"] if far else c["fur"]
            polygon(capsule(root, bend, 5.1 if hind else 3.3, 3.0 if hind else 2.6), color)
            polygon(capsule(bend, ankle, 2.7 if hind else 2.3, 1.8), color)
            polygon(capsule(ankle, paw, 1.9, 2.1), color)
            oval(paw + np.array([1.6, 0]), 3.6, 2, color)
            line(paw + np.array([1.0, -1.0]), paw + np.array([1.0, 0.5]), c["back"], 0.45)

        leg("hind_far", True)
        leg("front_far", True)
        # Tail silhouette uses the actual simulated chain and its tapered width.
        tang = np.gradient(tail, axis=0)
        normal = np.stack([-tang[:, 1], tang[:, 0]], axis=1)
        normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-8)
        widths = np.linspace(7.0, 1.2, len(tail))[:, None] / 2
        polygon(list(tail + normal * widths) + list((tail - normal * widths)[::-1]), c["fur"])
        polygon(
            list((tail + normal * widths)[-3:]) + list((tail - normal * widths)[-3:][::-1]),
            c["back"],
            False,
        )
        hip, shoulder = j["spine_0"], j["spine_3"]
        mid = j["spine_2"]
        # The torso follows the articulated spine, with a tucked waist and deep chest.
        body = [
            hip + [-6, 1],
            hip + [-3, 7],
            j["spine_1"] + [0, 8],
            mid + [0, 8],
            shoulder + [2, 5],
            shoulder + [8, -3],
            shoulder + [7, -13],
            shoulder + [-1, -17],
            mid + [-3, -10],
            j["spine_1"] + [-1, -6],
            hip + [-6, -6],
        ]
        polygon(body, c["fur"], smooth=True)
        polygon(
            [
                hip + [-4, 5],
                j["spine_1"] + [0, 8],
                mid + [0, 8],
                shoulder + [3, 4],
                shoulder + [-3, 1],
                mid + [-5, 3],
                j["spine_1"] + [-1, 3],
            ],
            c["back"],
            False,
            smooth=True,
        )
        polygon(
            [
                j["spine_1"] + [-1, -5],
                mid + [-3, -10],
                shoulder + [-1, -17],
                shoulder + [5, -11],
                shoulder + [1, -7],
                mid + [-3, -6],
            ],
            c["belly"],
            False,
            smooth=True,
        )
        leg("hind_near", False)
        leg("front_near", False)
        # Cover upper limb roots with continuous fur masses rather than detached joint discs.
        oval(hip + [-1, -2], 6, 7, c["fur"], False)
        neck, head, muzzle = j["neck"], j["head"], j["muzzle"]
        polygon(
            [
                shoulder + [-5, 5],
                neck + [-3, 8],
                head + [-5, 5],
                head + [5, -2],
                neck + [4, -9],
                shoulder + [6, -13],
                shoulder + [1, -10],
                shoulder + [1, -14],
                shoulder + [-3, -9],
                shoulder + [-5, -11],
            ],
            c["fur"],
        )
        polygon(
            [neck + [-3, 6], head + [-5, 5], head + [-1, 1], neck + [-4, -2], shoulder + [-3, 2]],
            c["back"],
            False,
        )
        # Far ear, skull and then near ear. The snout is distinctly longer than a cat's.
        polygon([head + [-5, 6], head + [-7, 17], head + [0, 10]], c["far"])
        polygon(
            [
                head + [-6, 4],
                head + [-4, 10],
                head + [5, 8],
                head + [9, 3],
                muzzle + [2, 1],
                muzzle + [2, -3],
                head + [7, -6],
                head + [-2, -7],
                head + [-7, -1],
            ],
            c["fur"],
            smooth=True,
        )
        polygon([head + [-4, 6], head + [-2, 18], head + [5, 8]], c["fur"])
        polygon([head + [-2, 9], head + [-1, 15], head + [2, 9]], c["back"], False)
        polygon(
            [head + [1, -3], muzzle + [2, -2], muzzle + [1, -4 - pose["mouth"]], head + [2, -7]],
            c["belly"],
        )
        oval(muzzle + [1, 0], 2.2, 1.7, c["nose"])
        eye = head + [4, 2.5]
        oval(eye, 1.8, 1.15, c["eye"], False)
        oval(eye + [0.45, 0], 0.65, 0.9, c["nose"], False)
        if pose.get("collapse", 0) > 0.7:
            oval(eye, 2.0, 1.4, c["fur"], False)
            line(eye + [-1.7, 0], eye + [1.7, 0], c["nose"], 0.7)
        line(eye + [-2, 2], eye + [2, 0.7], c["back"], 0.8)
        line(head + [4, -3], muzzle + [0, -2], c["nose"], 0.55)
        if pose["mouth"] > 0.5:
            oval(muzzle + [-2, -4], 2.0, 1.0, (173, 103, 104), False)
        if self.ss > 1:
            im = im.resize((self.size, self.size), Image.Resampling.LANCZOS)
        array = np.asarray(im).copy()
        if self.pixel:
            array[..., 3] = (array[..., 3] > 127).astype(np.uint8) * 255
        return array
