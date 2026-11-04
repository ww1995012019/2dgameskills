"""Rejected skeletal-blend diagnostic. NOT shipped in the animation skills.

Smooth seams alone do not make grounded locomotion: this experiment slides.
Use only for regression comparison against GroundedGaitRamp.
"""
import math
from sprite_anim.motions import Clip, NaturalWalk, Proc, CH
from sprite_anim.mathx import lerp
from sprite_anim.rig import REST


def bind_idle(idle, body):
    """Explicitly register this diagnostic's built-in idle fixture and body."""
    if not isinstance(idle, Proc) or idle.name != 'idle':
        raise ValueError('diagnostic requires built-in idle')
    idle._transition_body = body
    return idle


class PhaseTransition(Clip):
    """Natural-walk/idle pose blend with independently advancing clip clocks.

    Times are seconds, not normalized phases. Sample at elapsed transition time;
    after ``duration`` the target keeps advancing without a restart. Quintic
    weights preserve pose velocity and acceleration at both boundaries. This is
    a pose sampler, not a baked-sprite transition or a planted-foot planner.
    """

    def __init__(self, source, target, body, source_time, target_time=0., duration=.25):
        for key, value in (("source_time", source_time), ("target_time", target_time),
                           ("duration", duration)):
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or key == "duration" and value <= 0):
                raise ValueError(f"transition.{key}: expected a finite number"
                                 + (" greater than zero" if key == "duration" else ""))
        for clip in (source, target):
            compatible = (isinstance(clip, (NaturalWalk, PhaseTransition))
                          and clip.body == body or
                          isinstance(clip, Proc) and clip.name == 'idle'
                          and getattr(clip, '_transition_body', None) == body)
            if not compatible:
                raise ValueError("transition requires natural_walk_v1 and its matching idle/body")
        super().__init__(source.name + "_to_" + target.name, duration, False,
                         tags=source.tags & target.tags)
        self.contact_validation = 'not_applicable_pose_blend'
        self.source, self.target, self.body = source, target, body
        self.source_time, self.target_time = source_time, target_time

    def _weight(self, t):
        u = min(1., max(0., t / self.duration))
        return u*u*u*(10. + u*(-15. + 6.*u))

    def sample(self, t):
        if t <= 0.:
            return self.source.sample(self.source_time + t)
        if t >= self.duration:
            return self.target.sample(self.target_time + t)
        a = self.source.sample(self.source_time + t)
        b = self.target.sample(self.target_time + t)
        w = self._weight(t)
        p = {c: lerp(a.get(c, REST[c]), b.get(c, REST[c]), w) for c in CH}
        # This solver parameter must blend too: abruptly enabling the natural
        # walk's tighter soft-IK zone can move an ankle despite continuous pose
        # channels. Nested transitions retain the interpolated value.
        p['_leg_soft'] = lerp(a.get('_leg_soft', self.body.leg_soft),
                              b.get('_leg_soft', self.body.leg_soft), w)
        return p

    def vel(self, t):
        a = self.source.vel(self.source_time + t)
        b = self.target.vel(self.target_time + t)
        w = self._weight(t)
        return tuple(lerp(x, y, w) for x, y in zip(a, b))

    def contacts(self, t):
        # Crossfading foot targets is not a contact constraint. Do not label a
        # transitioning foot planted or incorrectly claim zero world sliding.
        if t <= 0.:
            return self.source.contacts(self.source_time + t)
        if t >= self.duration:
            return self.target.contacts(self.target_time + t)
        return {}


def transition_from(walk, source, source_time, target_time=0., duration=None):
    return PhaseTransition(source, walk, walk.body, source_time, target_time,
                           .3 * walk.duration if duration is None else duration)


def transition_to(walk, target, source_time, target_time=0., duration=None):
    return PhaseTransition(walk, target, walk.body, source_time, target_time,
                           .3 * walk.duration if duration is None else duration)
