"""Read-only input snapshot for one workflow command, never a saved QA verdict.

Each command constructs a fresh snapshot. Images and hashes are reused only while
validating/binding those same inputs; independent CLI entry points read them again.
Pixel hashes and reference-review byte hashes deliberately remain different.
"""
import hashlib
from pathlib import Path

from PIL import Image

import layer_parts
import visual_review


class JobAssets:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self._keyed = {}
        self._hashes = {}
        self._reference = None
        self._reference_digest = None

    def require_root(self, root):
        if Path(root).resolve() != self.root:
            raise ValueError('workflow assets belong to another job')
        return self

    def reference(self):
        if self._reference is None:
            self._reference = layer_parts.reference(self.root/'reference.png')
            self._reference.setflags(write=False)
        return self._reference

    def reference_digest(self):
        if self._reference_digest is None:
            self._reference_digest = hashlib.sha256((self.root/'reference.png').read_bytes()).hexdigest()
        return self._reference_digest

    def keyed(self, name):
        if name not in self._keyed:
            self._keyed[name] = layer_parts.key_out(self.root/name)
            self._keyed[name].setflags(write=False)
        return self._keyed[name]

    def image_size(self, name):
        if name in self._keyed:
            return self._keyed[name].shape[1], self._keyed[name].shape[0]
        with Image.open(self.root/name) as image:
            return image.size

    def file_hash(self, name):
        if name not in self._hashes:
            self._hashes[name] = visual_review.file_hash(self.root/name)
        return self._hashes[name]
