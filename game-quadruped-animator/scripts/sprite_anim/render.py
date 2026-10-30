"""Render a loop with deterministic, rig-independent simulated tail chains."""

from .art import QuadrupedArt
from .rig import sample, Clip
from .cloth import ChainDef, simulate, blend_to

TAIL = dict(
    n=6,
    seg=6,
    gravity=120,
    drag=4,
    stiff=0.018,
    rest=(-1, -0.35),
    flutter=8,
    width=(7, 1.2),
    follow=0.6,
    max_bend=45,
    max_curl=110,
)


class Renderer:
    def __init__(self, spec, size, pixel):
        self.art = QuadrupedArt(spec, size, pixel)

    def bake(self, clip):
        def state(t):
            pose = sample(clip, t)
            return pose["joints"]["tail_base"], pose["spine_rot"]

        definition = ChainDef("tail", ("tail_base", "spine_rot", (0, 0)), **TAIL)
        result = simulate(definition, clip, None, state_at=state)
        if clip.name in ("attack", "hurt"):
            target = self.bake(Clip("idle", clip.fps))
            blend_to(result, target.first(), TAIL["seg"])
        return result

    def frame(self, clip, tail, i):
        t = i / clip.fps
        pose = sample(clip, t)
        chain = tail.at(t)
        # Fractional SIM_HZ samples interpolate the root; attach it to the exact frame pose.
        chain = chain + (pose["joints"]["tail_base"] - chain[0])
        for k, p in enumerate(chain):
            pose["joints"]["tail_" + str(k)] = p
        return self.art.render(pose, chain), pose
