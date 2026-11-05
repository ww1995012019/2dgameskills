"""Bounded, command-local preparation shared by one clip's numerical checks.

Only poses, cloth positions and final native meshes are cached, never verdicts or
rendered alpha buffers. Rendering and independent delivery checks do not use this
cache. Construct a new context after changing a rig, clip or renderer.
"""
from collections import OrderedDict

from .rig import full_pose, solve


class FrameContext:
    def __init__(self, renderer, clip, count, fps, max_bytes=32*1024*1024, max_frames=128):
        if count < 1 or fps <= 0 or max_bytes < 0 or max_frames < 1:
            raise ValueError('invalid frame-check cache scope or capacity')
        self.renderer, self.clip, self.count, self.fps = renderer, clip, count, fps
        self.max_bytes, self.max_frames = max_bytes, max_frames
        self._samples, self._cloth, self._meshes = OrderedDict(), OrderedDict(), OrderedDict()
        self.cached_bytes = 0

    def require(self, renderer, clip, count, fps):
        if renderer is not self.renderer or clip is not self.clip or count != self.count or fps != self.fps:
            raise ValueError('frame-check context belongs to another renderer, clip or sampling clock')

    def sample(self, index):
        if not 0 <= index < self.count:
            raise IndexError('frame is outside the check scope')
        if index not in self._samples:
            from .render import frame_time
            t = frame_time(self.clip, index, self.count, self.fps)
            pose = full_pose(self.clip.sample(t))
            self._samples[index] = t, pose, solve(pose, self.renderer.art.body)
            if len(self._samples) > self.max_frames:
                self._samples.popitem(last=False)
        self._samples.move_to_end(index)
        return self._samples[index]

    def cloth(self, index):
        if index not in self._cloth:
            self._cloth[index] = self.renderer.cloth_at(self.clip, self.sample(index)[0])
            if len(self._cloth) > self.max_frames:
                self._cloth.popitem(last=False)
        self._cloth.move_to_end(index)
        return self._cloth[index]

    def meshes(self, index, canvas):
        # Native and reduced canvases, squash and origin must never alias. Raw
        # unrelaxed framing meshes are deliberately outside this interface.
        geometry = tuple(getattr(canvas, name) for name in
                         ('w', 'h', 's', 'ox', 'oy', 'sx', 'sy', 'squash_x0'))
        key = index, geometry
        if key in self._meshes:
            self._meshes.move_to_end(key)
            return self._meshes[key][0]
        _, _, skeleton = self.sample(index)
        meshes = list(self.renderer.art.puppet.meshes(
            canvas, skeleton, self.cloth(index), 'ground' in self.clip.tags))
        cost = sum(vertices.nbytes for _, vertices in meshes)
        if cost <= self.max_bytes:
            while self._meshes and (self.cached_bytes+cost > self.max_bytes
                                    or len(self._meshes) >= self.max_frames):
                _, (_, old_cost) = self._meshes.popitem(last=False)
                self.cached_bytes -= old_cost
            for _, vertices in meshes:
                vertices.setflags(write=False)
            self._meshes[key] = meshes, cost
            self.cached_bytes += cost
        return meshes

    def clear(self):
        self._samples.clear()
        self._cloth.clear()
        self._meshes.clear()
        self.cached_bytes = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.clear()


def sample_frame(renderer, clip, index, count, fps, context=None):
    if context is not None:
        context.require(renderer, clip, count, fps)
        return context.sample(index)
    from .render import frame_time
    t = frame_time(clip, index, count, fps)
    pose = full_pose(clip.sample(t))
    return t, pose, solve(pose, renderer.art.body)


def frame_meshes(renderer, clip, index, count, fps, canvas, skeleton, context=None, cloth=None):
    if context is not None:
        context.require(renderer, clip, count, fps)
        return context.meshes(index, canvas)
    if cloth is None:
        from .render import frame_time
        cloth = renderer.cloth_at(clip, frame_time(clip, index, count, fps))
    return list(renderer.art.puppet.meshes(canvas, skeleton, cloth, 'ground' in clip.tags))
