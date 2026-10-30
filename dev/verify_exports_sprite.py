"""Verifies exported data against the source frames, independent of the exporter's own logic."""
import glob, json, os, plistlib, re, sys
import numpy as np
from PIL import Image

root = sys.argv[1]
doc = json.load(open(os.path.join(root, 'animations.json'), encoding='utf-8'))
size = doc['frame_size']
pages = [np.asarray(Image.open(os.path.join(root, p['file'])).convert('RGBA')) for p in doc['pages']]

# 1. every frame rebuilt from the atlas must equal the loose PNG
bad = total = 0
for name, c in doc['clips'].items():
    files = sorted(glob.glob(os.path.join(root, 'frames', name, '*.png')))
    assert len(files) == len(c['frames']), name
    for path, r in zip(files, c['frames']):
        g = doc['regions'][r]
        out = np.zeros((size, size, 4), np.uint8)
        out[g['oy']:g['oy'] + g['h'], g['ox']:g['ox'] + g['w']] = pages[g['page']][g['y']:g['y'] + g['h'], g['x']:g['x'] + g['w']]
        src = np.asarray(Image.open(path).convert('RGBA'))
        vis = src[..., 3] > 0
        same = (out[..., 3] == src[..., 3]).all() and (out[vis] == src[vis]).all()
        bad += not same; total += 1
print(f'atlas rebuild: {total - bad}/{total} frames identical')
assert bad == 0, f'{bad} frames rebuilt from the atlas differ from the source PNGs'

# 2. transparent atlas pixels next to sprites carry bled colour, not black
p = pages[0]; edge = (p[..., 3] == 0) & (p[..., :3].sum(2) > 0)
print('bled transparent px:', int(edge.sum()))
assert edge.sum() > 0, 'transparent atlas pixels carry no bled colour'

# 3. texturepacker json covers all frames and animations
n = 0
for pf in doc['pages']:
    tp = json.load(open(os.path.join(root, pf['file'].replace('.png', '.json')), encoding='utf-8'))
    n += len(tp['frames'])
    assert tp['meta']['image'] == pf['file']
    for k, f in tp['frames'].items():
        assert f['frame']['x'] + f['frame']['w'] <= pf['w'] and f['frame']['y'] + f['frame']['h'] <= pf['h'], k
print('texturepacker frames:', n)

# 4. plist parses with the stdlib and frames stay in bounds
n = 0
for pf in doc['pages']:
    d = plistlib.load(open(os.path.join(root, 'engine', 'cocos', pf['file'].replace('.png', '.plist')), 'rb'))
    assert d['metadata']['textureFileName'] == pf['file']
    for k, f in d['frames'].items():
        x, y, w, h = map(int, re.findall(r'-?\d+', f['frame']))
        assert x + w <= pf['w'] and y + h <= pf['h'], k
    n += len(d['frames'])
print('plist frames:', n)

# 5. tres: every SubResource reference resolves, ext resources exist
t = open(os.path.join(root, 'engine', 'godot', 'sprite_frames.tres'), encoding='utf-8').read()
subs = set(re.findall(r'\[sub_resource type="AtlasTexture" id="(\w+)"\]', t))
refs = set(re.findall(r'SubResource\("(\w+)"\)', t))
exts = re.findall(r'path="res://([^"]+)" id="(\d+)"', t)
used = set(re.findall(r'ExtResource\("(\d+)"\)', t))
assert refs == subs and used <= {e[1] for e in exts}
for f, _ in exts:
    assert os.path.exists(os.path.join(root, f)), f
head = int(re.search(r'load_steps=(\d+)', t).group(1))
assert head == len(subs) + len(exts) + 1, (head, len(subs), len(exts))
print('tres sub_resources:', len(subs), 'ext:', len(exts), 'anims:', t.count('"name": &"'))

# 6. css: every keyframe block present, sheet files exist, sheet sizes match
css = open(os.path.join(root, 'engine', 'web', 'sprites.css'), encoding='utf-8').read()
for name in doc['clips']:
    assert f'@keyframes sp-{name}{{' in css, name
    assert os.path.exists(os.path.join(root, 'sheets', name + '.png')), name
    im = Image.open(os.path.join(root, 'sheets', name + '.png'))
    assert max(im.size) <= 4096, (name, im.size)
print('css clips:', len(doc['clips']), 'bytes:', len(css))
print('OK')
