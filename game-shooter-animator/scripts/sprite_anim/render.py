"""Clip -> frames. Handles frame sampling, HD/pixel output and temporal smoothing."""
import numpy as np

from .art import Canvas, chain_defs
from .cloth import bake_all
from .mathx import catmull_open, rot
from .rig import full_pose, solve
from .soldier import SoldierArt

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


class Renderer:
    def __init__(self, spec, size, pixel=False, motion_blur=1, clips=None):
        self.art = SoldierArt(spec)
        self.size, self.pixel = size, pixel
        self.motion_blur = motion_blur
        self.defs = chain_defs(self.art.spec)
        self.clips = clips
        self.bakes = bake_all({k: c for k, c in clips.items() if not c.cloth_ref}, self.art.body, self.defs)
        self.fit = self.fit_scale()
        self.unit = size * UNIT_PX * self.fit
        self.pal = np.array(self.art.palette(), dtype=np.float32) if pixel else None
        self.ss = 4 if size >= 128 else 5
        if pixel:
            self.stroke = 0.62
        else:
            self.stroke = max(1.0, size / 256 * 1.5)

    def fit_scale(self):
        """Shrink the character just enough that its widest action fits the frame, measured
        from every pose. Cropped art is a bug at any size, and raising --size can't fix it
        because the character scales with the frame."""
        half, up = 0.0, 0.0
        for clip in self.clips.values():
            # 120 Hz: a fast swing crosses its widest point between 30 Hz samples, and
            # hd60 frames or the smear land right on it.
            n = max(8, int(clip.duration * 120))
            for i in range(n + 1):
                t = clip.duration * i / n
                pose = full_pose(clip.sample(t))
                sk = solve(pose, self.art.body)
                self.art.active = clip.weapon or self.art.primary
                wide = 1.0 / pose["squash"] ** 0.6     # squash widens the body as it flattens
                for p in self.art.extent_points(sk, pose):
                    half, up = max(half, abs(p[0]) * wide), max(up, p[1] * pose["squash"])
                # The smear's spline overshoots the blade positions it passes through. Measure
                # it at the shortest window and at 10 fps, the longest any preset uses.
                for dt in (0.0, 0.1):
                    hist = self.smear_history(clip, t, pose, dt)
                    for p in catmull_open(hist[0], 5) if hist else ():
                        half, up = max(half, abs(p[0]) * wide), max(up, p[1] * pose["squash"])
        for by_chain in self.bakes.values():
            for bake in by_chain.values():
                half = max(half, float(np.abs(bake.pos[..., 0]).max()) + 8.0)
                up = max(up, float(bake.pos[..., 1].max()) + 8.0)
        frame_half, frame_up = 0.5 / UNIT_PX, GROUND_FRAC / UNIT_PX
        return min(1.0, (frame_half - 3) / max(half + 6, 1), (frame_up - 3) / max(up + 6, 1))

    def cloth_at(self, clip, t, sk):
        """Hold and fire clips share one bake, rigidly carried by the head they hang from."""
        src = clip.cloth_ref or clip.name
        out = {}
        for d in self.defs:
            pts = self.bakes[src][d.name].at(t)
            if clip.cloth_ref:
                joint, ang, off = d.attach
                pts = pts + (np.add(sk[joint], rot(off, sk[ang])) - pts[0])
            out[d.name] = pts
        return out

    def smear_history(self, clip, t, pose, dt):
        if pose["smear"] <= 0.02:
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
        self.art.active = clip.weapon or self.art.spec["weapons"][0]
        self.art.draw(cv, sk, pose, self.cloth_at(clip, t, sk), self.smear_history(clip, t, pose, dt),
                      layer=clip.layer if clip.layer != "full" else None, weapon=clip.weapon)
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

