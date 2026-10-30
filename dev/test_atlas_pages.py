# Run from a skill's scripts directory.
"""Forces the atlas onto several pages with synthetic frames and validates every export."""
import json, os, re, plistlib, sys, tempfile
sys.path.insert(0, '.')
import numpy as np
from PIL import Image
from sprite_anim import export

root = tempfile.mkdtemp(prefix='pg')
for d in ('engine/godot', 'engine/cocos', 'engine/web'):
    os.makedirs(os.path.join(root, d))
size = 512
rng = np.random.default_rng(1)
clips = {}
for c in range(3):
    fr = []
    for i in range(120):
        a = np.zeros((size, size, 4), np.uint8)
        a[40:470, 40:470] = (*rng.integers(1, 255, 3), 255)
        a[41, 41, 0] = i; a[42, 41, 1] = c
        fr.append(a)
    clips[f'c{c}'] = dict(frames=fr)
sp, refs, files = export.build_atlas(root, clips, size)
print('pages', files)
assert len(files) > 1
pivot = (256, 440)
export.texturepacker_json(root, sp, refs, files, size, pivot)
meta = {k: dict(fps=30, loop=True, duration=4, events=[], tags=[], next=None) for k in clips}
doc = export.manifest(sp, refs, files, meta, size, pivot, 'x')
export.godot_tres(root, doc); export.cocos_plist(root, doc)
assert sum(len(json.load(open(os.path.join(root, f['file'].replace('.png', '.json'))))['frames']) for f in files) == 360
imgs = [np.asarray(Image.open(os.path.join(root, f['file']))) for f in files]
assert all(max(i.shape[:2]) <= 4096 for i in imgs)
for name, c in clips.items():
    for f, r in zip(c['frames'], refs[name]):
        g = doc['regions'][r]
        got = imgs[g['page']][g['y']:g['y'] + g['h'], g['x']:g['x'] + g['w']]
        assert (got[..., :4] == f[g['oy']:g['oy'] + g['h'], g['ox']:g['ox'] + g['w']]).all()
n = sum(len(plistlib.load(open(os.path.join(root, 'engine/cocos', f['file'].replace('.png', '.plist')), 'rb'))['frames']) for f in files)
assert n == 360, n
t = open(os.path.join(root, 'engine/godot/sprite_frames.tres'), encoding='utf-8').read()
assert len(re.findall('ext_resource', t)) == len(files)
assert set(re.findall(r'ExtResource\("(\d+)"\)', t)) == {str(i + 1) for i in range(len(files))}
print('multi-page OK')
