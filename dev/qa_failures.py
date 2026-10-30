import glob, json, os
import numpy as np
from PIL import Image
base = os.path.join(os.environ['TEMP'], 'spr', 'all')
for s in sorted(os.listdir(base)):
    q = os.path.join(base, s, 'qa_report.json')
    if not os.path.exists(q):
        print(s, 'no report')
        continue
    d = json.load(open(q, encoding='utf-8'))
    fails = []
    for n, r in d['clips'].items():
        for k in ('hold', 'seam', 'spike', 'slide', 'jitter', 'grip', 'cadence', 'limits', 'clip', 'bounds'):
            if r.get(k) == 'FAIL':
                fails.append(f'{n}:{k}')
    line = f"{s}: {fails or 'clean'}"
    for n, r in d['clips'].items():
        for i in r.get('cut_frames', []):
            f = np.asarray(Image.open(os.path.join(base, s, 'frames', n, f'{n}_{i:03d}.png')).convert('RGBA'))[..., 3]
            edges = [e for e, v in (('top', f[0].max()), ('bottom', f[-1].max()), ('left', f[:, 0].max()), ('right', f[:, -1].max())) if v > 0]
            line += f' [{n}#{i} {edges} a={int(max(f[0].max(), f[-1].max(), f[:, 0].max(), f[:, -1].max()))}]'
    print(line)
