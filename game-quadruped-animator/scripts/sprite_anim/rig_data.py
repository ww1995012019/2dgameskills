"""A small common boundary for 2D rigs: named joint samples in output pixels.

Humanoid and quadruped solvers keep their own anatomy and contact rules. This
recorder accepts either rig's joint mapping and preserves the original humanoid
rounding/order exactly. Chain physics separately accepts state_at(t) callbacks.
"""


class JointRecorder:
    def __init__(self, names, unit_px, precision=3):
        self.joints = {name: [] for name in names}
        self.unit_px = unit_px
        self.precision = precision

    def append(self, joints):
        for name, track in self.joints.items():
            point = joints[name]
            track.append(
                [
                    round(point[0] * self.unit_px, self.precision),
                    round(point[1] * self.unit_px, self.precision),
                ]
            )
