import json, os, sys, collections
for name in sys.argv[1:]:
    d = json.load(open(os.path.join(os.environ['TEMP'], 'spr', name, 'qa_report.json'), encoding='utf-8'))
    print('==', name)
    for clip, r in d['clips'].items():
        fl = r.get('flags', {})
        if not fl:
            continue
        kinds = collections.Counter()
        sample = {}
        for f, msgs in fl.items():
            for m in msgs:
                k = ' '.join(w for w in m.split() if not any(c.isdigit() for c in w))
                kinds[k] += 1
                sample.setdefault(k, m)
        print(f"{clip:<20} {r.get('limits')}/{r.get('clip')}/{r.get('bounds')}", '; '.join(f"{sample[k]} x{n}" for k, n in kinds.items())[:150])
