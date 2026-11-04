"""Clip -> frames. Handles frame sampling, HD/pixel output and temporal smoothing."""
import math
import numpy as np

from .art import Canvas, CharacterArt, chain_defs
from .cloth import bake_all
from .constraints import bake_weapon_contacts
from .mathx import catmull_open, rot
from .rig import full_pose, solve

PRESETS = {
    "hd": dict(size=256, fps=30, pixel=False),
    "hd60": dict(size=256, fps=60, pixel=False),
    "hd512": dict(size=512, fps=30, pixel=False),
    "pixel": dict(size=64, fps=15, pixel=True),
    "pixel48": dict(size=48, fps=12, pixel=True),
    "pixel96": dict(size=96, fps=20, pixel=True),
}

GROUND_FRAC = 0.86      # y of the feet inside the frame
UNIT_PX = 1 / 190.0     # px per rig unit, as a fraction of frame size


def frame_count(clip, fps):
    """Loops sample [0, T) with no endpoint: repeating t=0 at the end would hold one pose
    for two frames every cycle, a visible hitch. One-shots include the end pose."""
    if clip.loop:
        return max(2, int(round(clip.duration * fps)))
    return max(2, int(round(clip.duration * fps)) + 1)


def frame_time(clip, i, n, fps):
    if clip.loop:
        return i * clip.duration / n
    return i * clip.duration / (n - 1)


def playback_speed(clip, fps, n=None):
    """World speed of the baked samples played at the requested frame rate.

    Rounding the frame count retimes the authored motion. Keep the pixels and
    requested FPS, and apply the same retiming to the world's movement speed.
    """
    n = frame_count(clip, fps) if n is None else n
    intervals = n if clip.loop else n - 1
    return clip.speed * clip.duration * fps / intervals


def walk_hold_phase(clip, n):
    """A pair of half-cycle-separated holds whose displayed frames support both feet.

    At sparse odd frame counts the ideal support centre can round down to a
    swing frame. Move the shared phase forward to the first sampled second-half
    support, retaining the normal centre whenever it already works.
    """
    phase = max((clip.duty - .5) / 2, math.ceil(n / 2) / n - .5)
    if not 0 <= phase < clip.duty - .5:
        raise ValueError('walk FPS misses double-support stop frames; increase export FPS')
    for hold in (phase, phase + .5):
        frame = math.floor(hold * n + 1e-10)
        if not all(clip.contacts(frame_time(clip, frame, n, 1)).values()):
            raise ValueError('walk FPS misses double-support stop frames; increase export FPS')
    return phase


class Renderer:
    def __init__(self, spec, size, pixel=False, motion_blur=1, clips=None, fit_clips=None):
        self.art = CharacterArt(spec)
        self.size, self.pixel = size, pixel
        self.motion_blur = motion_blur
        self.defs = chain_defs(self.art.spec)
        # Finite banks retain source cloth, even when rendered on their own.
        # Do not mutate the caller's clip registry or silently replace a source.
        sources = [c.cloth_source[0] for c in clips.values() if hasattr(c, 'cloth_source')]
        if sources:
            clips = dict(clips)
            for source in sources:
                if source.name in clips and clips[source.name] is not source:
                    raise ValueError('conflicting cloth source clip: ' + source.name)
                clips[source.name] = source
        self.clips = clips
        self.fit_clips = clips if fit_clips is None else fit_clips
        bake_weapon_contacts(clips, self.art.body, solve, full_pose)
        contact_chains = ({layer.chain for layer in self.art.puppet.layers if layer.kind == 'cloth'}
                          if self.art.puppet else ())
        self.bakes = bake_all(clips, self.art.body, self.defs, grounded_chains=contact_chains)
        self.fit = self.fit_scale()
        self.unit = size * UNIT_PX * self.fit
        self.pal = np.array(self.art.palette(), dtype=np.float32) if pixel else None
        self.ss = 2 if self.art.puppet else 4 if size >= 128 else 5     # a puppet is resampled art, not drawn edges
        if pixel:
            self.stroke = 0.62
        else:
            self.stroke = max(1.0, size / 256 * 1.5)

    def fit_scale(self):
        """Shrink the character just enough that its widest action fits the frame, measured
        from every pose. Cropped art is a bug at any size, and raising --size can't fix it
        because the character scales with the frame."""
        half, up, down = 0.0, 0.0, 0.0
        mesh_canvas = Canvas(2, 1, 1.0, 0.0, 1.0, False, self.art.ink) if self.art.puppet else None
        for clip in self.fit_clips.values():
            # 120 Hz: a fast swing crosses its widest point between 30 Hz samples, and
            # hd60 frames or the smear land right on it.
            n = max(8, int(clip.duration * 120))
            for i in range(n + 1):
                t = clip.duration * i / n
                pose = full_pose(clip.sample(t))
                sk = solve(pose, self.art.body)
                wide = 1.0 / pose["squash"] ** 0.6     # squash widens the body as it flattens
                for p in self.art.extent_points(sk, pose):
                    half, up = max(half, abs(p[0]) * wide), max(up, p[1] * pose["squash"])
                if mesh_canvas is not None:
                    mesh_canvas.set_squash(pose['squash'], 0.0)
                    # Source cells, not skeleton joints, bound a painted robe
                    # or hair fan. Raw mesh bounds are conservative: subsequent
                    # relaxation averages neighbouring vertices inside them.
                    for _, points in self.art.puppet.meshes(
                            mesh_canvas, sk, self.cloth_at(clip, t), 'ground' in clip.tags,
                            relax=False, used_only=True):
                        half = max(half, float(np.abs(points[:, 0] - mesh_canvas.ox).max()))
                        up = max(up, float((-points[:, 1]).max()))
                        down = max(down, float(points[:, 1].max()))
                # The smear's spline overshoots the blade positions it passes through. Measure
                # it at the shortest window and at 10 fps, the longest any preset uses.
                for dt in (0.0, 0.1):
                    hist = self.smear_history(clip, t, pose, dt)
                    for p in catmull_open(hist[0], 5) if hist else ():
                        half, up = max(half, abs(p[0]) * wide), max(up, p[1] * pose["squash"])
        for name, by_chain in self.bakes.items():
            if name not in self.fit_clips:
                continue
            for bake in by_chain.values():
                half = max(half, float(np.abs(bake.pos[..., 0]).max()) + 8.0)
                up = max(up, float(bake.pos[..., 1].max()) + 8.0)
        # 4 units of pad cover the outline and the blade's own width; the points are exact.
        frame_half, frame_up = 0.5 / UNIT_PX, GROUND_FRAC / UNIT_PX
        fit = min((frame_half - 3) / max(half + 4, 1), (frame_up - 3) / max(up + 4, 1))
        if self.art.puppet:
            frame_down = (1 - GROUND_FRAC) / UNIT_PX
            fit = min(fit, (frame_down - 3) / max(down + 4, 1))
        # A puppet's art is far finer than the frame, so it fills the frame instead of the rig's 100 units.
        return fit if self.art.puppet else min(1.0, fit)

    def cloth_at(self, clip, t):
        source = getattr(clip, 'cloth_source', None)
        if source is None:
            return {d.name: self.bakes[clip.name][d.name].at(t) for d in self.defs}
        # A reversible settle bank must inherit the displayed walk's secondary
        # pose, not initialize a fresh cloth simulation. Carry that sampled shape
        # with its attachment frame as the pelvis lowers. This is deliberately
        # kinematic cloth during settling, not a simulated cloth relaxation.
        source_clip, source_time = source
        before = solve(full_pose(source_clip.sample(source_time)), self.art.body)
        after = solve(full_pose(clip.sample(t)), self.art.body)
        result = {}
        for d in self.defs:
            joint, angle, offset = d.attach
            a = np.add(before[joint], rot(offset, before[angle]))
            b = np.add(after[joint], rot(offset, after[angle]))
            points = self.bakes[source_clip.name][d.name].at(source_time)
            delta = after[angle] - before[angle]
            result[d.name] = np.array([b + rot(tuple(p - a), delta) for p in points])
        return result

    def smear_history(self, clip, t, pose, dt):
        if pose["smear"] <= 0.02 or self.art.spec["weapon"] == "none":
            return None
        tips, hilts = [], []
        window = max(0.054, dt)     # must span the frame gap or low fps leaves the arc broken
        for k in range(6, -1, -1):
            tt = max(0.0, t - k * window / 6)
            past = full_pose(clip.sample(tt))
            h, tip = self.art.blade_points(solve(past, self.art.body))
            # The canvas squashes with this frame's pose; undo that and apply the squash the
            # blade was drawn with, so the arc traces where it really was on screen.
            sx = (pose["squash"] / past["squash"]) ** 0.6
            sy = past["squash"] / pose["squash"]
            tips.append((tip[0] * sx, tip[1] * sy))
            hilts.append((h[0] * sx, h[1] * sy))
        return np.array(tips), np.array(hilts)

    def _render_once(self, clip, t, dt=0.0):
        pose = full_pose(clip.sample(t))
        sk = solve(pose, self.art.body)
        cv = Canvas(self.size, self.ss, self.unit, GROUND_FRAC, self.stroke,
                    self.pixel, self.art.ink)
        self.art.draw(cv, sk, pose, self.cloth_at(clip, t), self.smear_history(clip, t, pose, dt),
                      ground_contact='ground' in clip.tags)
        return cv.resolve()

    def render(self, clip, t, dt=0.0):
        """Returns float RGBA in [0,1], straight alpha."""
        if self.motion_blur > 1 and not self.pixel and dt > 0:
            acc = np.zeros((self.size, self.size, 4), dtype=np.float32)
            for k in range(self.motion_blur):
                st = t + dt * 0.5 * (k / self.motion_blur)
                if not clip.loop:
                    st = min(st, clip.duration)
                f = self._render_once(clip, st, dt)
                f[..., :3] *= f[..., 3:]
                acc += f
            acc /= self.motion_blur
            a = acc[..., 3:]
            with np.errstate(divide="ignore", invalid="ignore"):
                acc[..., :3] = np.where(a > 1e-4, acc[..., :3] / a, 0)
            return self.finish(acc)
        return self.finish(self._render_once(clip, t, dt))

    def finish(self, f):
        if not self.pixel:
            return f
        # Hard alpha + nearest palette colour: no anti-aliased in-betweens, which would
        # shimmer on low-res frames as edges cross pixel boundaries.
        a = f[..., 3] > 0.5
        rgb = f[..., :3][a] * 255
        d = ((rgb[:, None, :] - self.pal[None, :, :]) ** 2).sum(axis=2)
        idx = d.argmin(axis=1)
        out = np.zeros_like(f)
        out[..., :3][a] = self.pal[idx] / 255
        out[..., 3][a] = 1.0
        return out

    def render_clip(self, clip, fps):
        n = frame_count(clip, fps)
        dt = clip.duration / n
        frames = []
        for i in range(n):
            t = frame_time(clip, i, n, fps)
            frames.append(self.render(clip, t, dt))
        return frames


def to_u8(f):
    return (np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8)

