"""Configuration-driven 2D bones and flight poses; coordinates use x right, y down.

This module computes positions only. Drawing, export and image-part binding are not implemented
here. A pose maps each bone name to (start, end, absolute angle in degrees).
"""
import math

FLIGHT_ACTIONS = ("flap", "hover", "glide", "dive", "hurt", "fall")
LOOPS = frozenset(("flap", "hover", "glide"))


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _point(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must contain two numbers")
    return tuple(_number(x, name) for x in value)


def _rotate(point, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return point[0] * c - point[1] * s, point[0] * s + point[1] * c


class CreatureRig:
    """A rooted tree of fixed-length bones, with local angles and optional wing drivers."""

    def __init__(self, spec):
        if not isinstance(spec, dict):
            raise ValueError("creature configuration must be an object")
        bones = spec.get("bones")
        if not isinstance(bones, list) or not bones:
            raise ValueError("bones must be a nonempty list")
        self.bones = {}
        for raw in bones:
            if not isinstance(raw, dict):
                raise ValueError("each bone must be an object")
            name = raw.get("name")
            if not isinstance(name, str) or not name or name in self.bones:
                raise ValueError(f"invalid or duplicate bone name: {name!r}")
            length = _number(raw.get("length"), f"{name}.length")
            if length <= 0:
                raise ValueError(f"{name}.length must be positive")
            angle = _number(raw.get("angle", 0), f"{name}.angle")
            limits = _point(raw.get("limits", [-180, 180]), f"{name}.limits")
            if limits[0] > limits[1] or not limits[0] <= angle <= limits[1]:
                raise ValueError(f"{name}.angle must lie inside ordered limits")
            parent = raw.get("parent")
            if parent is not None and not isinstance(parent, str):
                raise ValueError(f"{name}.parent must be a bone name or null")
            anchor = raw.get("anchor", "end")
            if anchor not in ("start", "end"):
                raise ValueError(f"{name}.anchor must be start or end")
            tags = raw.get("tags", [])
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise ValueError(f"{name}.tags must be a list of strings")
            self.bones[name] = dict(name=name, length=length, angle=angle, limits=limits, parent=parent,
                                    anchor=anchor, offset=_point(raw.get("offset", [0, 0]), f"{name}.offset"),
                                    tags=tuple(tags), flap_amplitude=_number(raw.get("flap_amplitude", 0), f"{name}.flap_amplitude"),
                                    flap_phase=_number(raw.get("flap_phase", 0), f"{name}.flap_phase"))
            amplitude = abs(self.bones[name]["flap_amplitude"])
            if angle - amplitude < limits[0] or angle + amplitude > limits[1]:
                raise ValueError(f"{name}.flap_amplitude exceeds joint limits")
        roots = [name for name, bone in self.bones.items() if bone["parent"] is None]
        if len(roots) != 1:
            raise ValueError("bones must have exactly one root")
        self.order = []
        visiting, done = set(), set()

        def visit(name):
            if name in visiting:
                raise ValueError(f"bone parent cycle at {name}")
            if name in done:
                return
            visiting.add(name)
            parent = self.bones[name]["parent"]
            if parent is not None:
                if parent not in self.bones:
                    raise ValueError(f"{name} has unknown parent {parent}")
                visit(parent)
            visiting.remove(name)
            done.add(name)
            self.order.append(name)

        for name in self.bones:
            visit(name)
        pairs = spec.get("wing_pairs", [])
        if not isinstance(pairs, list):
            raise ValueError("wing_pairs must be a list")
        self.wing_pairs = []
        for pair in pairs:
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or pair[0] == pair[1]
                    or any(not isinstance(n, str) or n not in self.bones or "wing" not in self.bones[n]["tags"] for n in pair)):
                raise ValueError("wing_pairs entries must name two different wing-tagged bones")
            self.wing_pairs.append(tuple(pair))
        self.motion = spec.get("motion", {})
        if not isinstance(self.motion, dict):
            raise ValueError("motion must be an object")
        self.period = _number(self.motion.get("period", 1.0), "motion.period")
        self.bob = _number(self.motion.get("bob", 2.0), "motion.bob")
        self.pitch = _number(self.motion.get("pitch", 4.0), "motion.pitch")
        if self.period <= 0:
            raise ValueError("motion.period must be positive")

    def pose(self, time, action="flap"):
        """Evaluate a pose at seconds; finite actions use one period and clamp at their end."""
        time = _number(time, "time")
        if action not in FLIGHT_ACTIONS:
            raise ValueError(f"unknown flight action {action!r}")
        phase = (time / self.period) % 1.0 if action in LOOPS else min(1.0, max(0.0, time / self.period))
        cycle = 2 * math.pi * phase
        if action in ("flap", "hover"):
            strength = 1.0 if action == "flap" else 0.7
            root_y = self.bob * (1 - math.cos(cycle)) * strength
            root_angle = self.pitch * math.sin(cycle) * strength
        elif action == "glide":
            strength = 0.0
            root_y = 0.25 * self.bob * (1 - math.cos(cycle))
            root_angle = 0.25 * self.pitch * math.sin(cycle)
        else:
            strength = 0.0
            root_y = (self.bob * 3 * phase) if action in ("dive", "fall") else 0.0
            root_angle = (35 * phase if action == "dive" else 70 * phase if action == "fall"
                          else -15 * math.sin(math.pi * phase))
        result = {}
        for name in self.order:
            bone = self.bones[name]
            parent = bone["parent"]
            parent_angle = result[parent][2] if parent is not None else root_angle
            anchor = result[parent][0 if bone["anchor"] == "start" else 1] if parent is not None else (0.0, root_y)
            dx, dy = _rotate(bone["offset"], parent_angle)
            start = (anchor[0] + dx, anchor[1] + dy)
            change = (strength * bone["flap_amplitude"] * math.sin(cycle + math.radians(bone["flap_phase"])))
            local = bone["angle"] + change
            angle = parent_angle + local
            ex, ey = _rotate((bone["length"], 0), angle)
            result[name] = (start, (start[0] + ex, start[1] + ey), angle)
        return result
