"""Small shared building blocks for review sheets; no approval decisions."""
from collections import OrderedDict
import os

from sprite_anim.export import gif_durations


def playback_media(meta, clip, filename, parts=1):
    count = len(meta['frames'])
    durations = gif_durations(count, meta['fps'], parts)
    return dict(clip=clip, file=filename, frame_count=count, fps=meta['fps'],
                loop=bool(meta['loop']), duration_ms=sum(durations)), durations


def sheet_groups(rows, prefix, per_sheet):
    for start in range(0, len(rows), per_sheet):
        yield f'{prefix}_{start//per_sheet:02d}.png', rows[start:start+per_sheet]


def pose_coverage(rows):
    return [dict(clip=clip, **pose) for clip, _, poses in rows for pose in poses]


class ReviewFrames:
    """Bounded image reads for one build, not used by record/--check hashing."""
    def __init__(self, root, doc, loader, max_bytes=32*1024*1024):
        if max_bytes < 0:
            raise ValueError('negative review image cache capacity')
        self.root, self.doc, self.loader = os.path.realpath(root), doc, loader
        self.max_bytes, self.cached_bytes = max_bytes, 0
        self.frames = OrderedDict()

    def read(self, root, doc, name, index):
        if os.path.realpath(root) != self.root or doc is not self.doc:
            raise ValueError('review image cache belongs to another build')
        key = name, index
        if key not in self.frames:
            image = self.loader(root, doc, name, index)
            cost = image.width*image.height*len(image.getbands())
            if cost > self.max_bytes:
                return image
            while self.frames and self.cached_bytes+cost > self.max_bytes:
                _, (old, old_cost) = self.frames.popitem(last=False)
                old.close()
                self.cached_bytes -= old_cost
            self.frames[key] = image, cost
            self.cached_bytes += cost
        self.frames.move_to_end(key)
        # Consumers can crop/paint without changing another sheet's input.
        return self.frames[key][0].copy()

    def close(self):
        for image, _ in self.frames.values():
            image.close()
        self.frames.clear()
        self.cached_bytes = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
