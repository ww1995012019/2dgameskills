"""Render a creature rig with per-bone PNG parts or simple placeholder strokes.

PNG parts point along +x in their source rest pose. Their pivot is in source pixels and
pixels_per_unit relates the source drawing to rig units. Parts are composited in declared order.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return float(value)


class CreatureRenderer:
    def __init__(self, rig, spec, base_dir, size=256):
        if isinstance(size, bool) or not isinstance(size, int) or not 32 <= size <= 1024:
            raise ValueError("size must be an integer in 32..1024")
        self.rig, self.size = rig, size
        view = spec.get("view", {})
        if not isinstance(view, dict):
            raise ValueError("view must be an object")
        self.unit = size / _positive(view.get("units", 120), "view.units")
        pivot = view.get("pivot", [0.5, 0.5])
        if not isinstance(pivot, (list, tuple)) or len(pivot) != 2 or any(
                isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1
                for x in pivot):
            raise ValueError("view.pivot must contain two finite values in 0..1")
        self.pivot = (size * pivot[0], size * pivot[1])
        parts = spec.get("parts", {})
        if not isinstance(parts, dict) or set(parts) - set(rig.bones):
            raise ValueError("parts must map existing bone names to part descriptions")
        order = spec.get("draw_order", rig.order)
        if (not isinstance(order, list) or any(not isinstance(name, str) for name in order)
                or len(order) != len(rig.bones) or set(order) != set(rig.bones)):
            raise ValueError("draw_order must list every bone exactly once")
        self.order, self.parts = order, {}
        for name in self.order:
            part = parts.get(name, {})
            if not isinstance(part, dict):
                raise ValueError(f"parts.{name} must be an object")
            if "image" in part:
                if not isinstance(part["image"], str) or not part["image"]:
                    raise ValueError(f"parts.{name}.image must be a nonempty path")
                source = Path(base_dir) / part["image"]
                with Image.open(source) as image:
                    bitmap = image.convert("RGBA")
                pivot = part.get("pivot")
                if not isinstance(pivot, (list, tuple)) or len(pivot) != 2 or any(
                        isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in pivot):
                    raise ValueError(f"parts.{name}.pivot must contain two finite numbers")
                self.parts[name] = (bitmap, tuple(pivot), _positive(part.get("pixels_per_unit"), f"parts.{name}.pixels_per_unit"))
            else:
                width = _positive(part.get("width", 3), f"parts.{name}.width")
                self.parts[name] = (part.get("color", "#b5ccd6"), width)

    def render(self, pose):
        canvas = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
        for name in self.order:
            start, end, angle = pose[name]
            origin = (self.pivot[0] + start[0] * self.unit, self.pivot[1] + start[1] * self.unit)
            part = self.parts[name]
            if len(part) == 2:
                color, width = part
                finish = (self.pivot[0] + end[0] * self.unit, self.pivot[1] + end[1] * self.unit)
                draw = ImageDraw.Draw(canvas)
                thickness = max(1, round(width * self.unit))
                draw.line((origin, finish), fill=color, width=thickness)
                radius = thickness / 2
                for x, y in (origin, finish):
                    draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
            else:
                bitmap, pivot, source_unit = part
                scale = self.unit / source_unit
                a = math.radians(angle)
                c, s = math.cos(a), math.sin(a)
                # Inverse affine maps output coordinates to the part image.
                coeff = (c / scale, s / scale, pivot[0] - (c * origin[0] + s * origin[1]) / scale,
                         -s / scale, c / scale, pivot[1] + (s * origin[0] - c * origin[1]) / scale)
                patch = bitmap.transform((self.size, self.size), Image.Transform.AFFINE, coeff,
                                         resample=Image.Resampling.BICUBIC)
                canvas.alpha_composite(patch)
        return canvas
