#!/usr/bin/env python3
"""Real-character fixtures: lock the frames a user approved and catch any later change to them.

    python dev/real_characters.py add soldier --job /path/to/job --clips idle,run --preset hd512
    python dev/real_characters.py add demo --character path/to/character.json --clips idle,walk
    python dev/real_characters.py approve soldier --build out/soldier --by "user, 2026-11-06 chat"
    python dev/real_characters.py check                    # every fixture; exit 1 on any change
    python dev/real_characters.py check soldier --out /tmp/rc --compare

The 26 template sets prove the programmatic characters; this proves the real AI-art characters
that the user has already looked at. `add` copies the reviewed job (layers, reviews, rig) or a
character folder into dev/fixtures/characters/<name>/input/ and records how its clips are
generated. `approve` is run only after the user approved the moving result: it stores that
build's atlas and per-frame RGBA hashes. `check` regenerates each fixture through the normal
generate.py gates, runs qa_motion.py and compares every approved frame.

A changed frame is not automatically wrong, but the user approved the old pixels, not the new
ones. With --compare the check writes compare_clips.py GIFs (approved left, new right) to show
the user; only after they approve again, run `approve` with the new build.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODE = ROOT / 'game-animator/modes/game-sprite-animator'
FIXTURES = ROOT / 'dev/fixtures/characters'
# Generated or bulky outputs that are not inputs of a reviewed job.
SKIP_DIRS = {'build', 'out', 'review', 'preview', 'compare', '__pycache__', 'art-history', 'website'}
SKIP_SUFFIXES = {'.gif', '.zip', '.mp4', '.webm', '.html'}

_spec = importlib.util.spec_from_file_location('compare_clips', MODE / 'scripts/compare_clips.py')
compare = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def frame_hashes(build, clips):
    """sha256 of each frame's raw RGBA, independent of PNG encoding or atlas packing."""
    b = compare.Build(build)
    out = {}
    for clip in clips:
        frames = b.frames(clip)
        out[clip] = {'fps': b.fps(clip), 'size': b.size, 'pivot': list(b.pivot),
                     'frames': [hashlib.sha256(f.tobytes()).hexdigest() for f in frames]}
    return out


def copy_inputs(source, dest):
    for item in sorted(source.rglob('*')):
        rel = item.relative_to(source)
        if not item.is_file() or item.suffix.lower() in SKIP_SUFFIXES:
            continue
        if any(part in SKIP_DIRS or part.startswith('build') for part in rel.parts[:-1]):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def cmd_add(args):
    folder = args.root / args.name
    if folder.exists():
        raise SystemExit(f'{folder} exists; remove it first to replace the fixture')
    if bool(args.job) == bool(args.character):
        raise SystemExit('give exactly one of --job or --character')
    if args.job:
        job = args.job.resolve()
        if not (job / 'job.json').is_file() or not (job / 'rig/character.json').is_file():
            raise SystemExit(f'{job}: expected a bound job with job.json and rig/character.json')
        copy_inputs(job, folder / 'input')
        character = 'input/rig/character.json'
    else:
        spec = args.character.resolve()
        copy_inputs(spec.parent, folder / 'input')
        character = 'input/' + spec.name
    meta = {'name': args.name, 'character': character,
            'clips': [c.strip() for c in args.clips.split(',') if c.strip()],
            'generate_args': ['--preset', args.preset] + (args.extra or []),
            'source': str(args.job or args.character), 'added': datetime.date.today().isoformat(),
            'approved': None}
    write(folder / 'fixture.json', meta)
    print(f'[add] {folder} ({sum(1 for _ in (folder / "input").rglob("*") if _.is_file())} input files)')
    print('Run check, show the result to the user, and approve only after they accept it.')


def generate(folder, meta, out):
    cmd = [sys.executable, str(MODE / 'scripts/generate.py'), '--character', str(folder / meta['character']),
           '--clips', ','.join(meta['clips']), *meta['generate_args'], '--out', str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        return f'generate.py exit {result.returncode}: ' + (result.stderr or result.stdout).strip()[-600:]
    qa = subprocess.run([sys.executable, str(MODE / 'scripts/qa_motion.py'), str(out)],
                        capture_output=True, text=True)
    summary = [line for line in qa.stdout.splitlines() if line.startswith('result:')]
    if qa.returncode:
        return f'qa_motion.py exit {qa.returncode}: ' + (summary[-1] if summary else (qa.stdout + qa.stderr).strip()[-600:])
    return None


def cmd_approve(args):
    folder = args.root / args.name
    meta = read(folder / 'fixture.json')
    hashes = frame_hashes(args.build, meta['clips'])
    approved = folder / 'approved'
    if approved.exists():
        shutil.rmtree(approved)
    approved.mkdir()
    doc = read(args.build / 'animations.json')
    shutil.copy2(args.build / 'animations.json', approved / 'animations.json')
    for page in doc['pages']:
        shutil.copy2(args.build / page['file'], approved / page['file'])
    meta['approved'] = {'by': args.by, 'date': datetime.date.today().isoformat(),
                        'note': args.note or '', 'clips': hashes}
    write(folder / 'fixture.json', meta)
    total = sum(len(c['frames']) for c in hashes.values())
    print(f'[approve] {args.name}: {total} frames in {", ".join(hashes)} locked as approved by {args.by}')


def cmd_check(args):
    names = args.names or sorted(p.name for p in args.root.iterdir() if (p / 'fixture.json').is_file()) \
        if args.root.is_dir() else []
    if not names:
        print('no real-character fixtures yet (dev/fixtures/characters/); see `add`')
        return 0
    out_root = args.out or Path(tempfile.mkdtemp(prefix='real-characters-'))
    failed = 0
    for name in names:
        folder = args.root / name
        meta = read(folder / 'fixture.json')
        out = out_root / name
        if out.exists():
            shutil.rmtree(out)
        error = generate(folder, meta, out)
        if error:
            failed += 1
            print(f'{name}: FAIL {error}')
            continue
        if not meta.get('approved'):
            print(f'{name}: generated and QA passed, but nothing is approved yet ({out})')
            continue
        current = frame_hashes(out, meta['clips'])
        changes = []
        for clip, ref in meta['approved']['clips'].items():
            now = current.get(clip)
            if now is None:
                changes.append(f'{clip}: missing')
                continue
            if (now['fps'], now['size'], now['pivot']) != (ref['fps'], ref['size'], ref['pivot']):
                changes.append(f'{clip}: fps/size/pivot changed')
            if len(now['frames']) != len(ref['frames']):
                changes.append(f'{clip}: {len(ref["frames"])} -> {len(now["frames"])} frames')
                continue
            diff = [i for i, (a, b) in enumerate(zip(ref['frames'], now['frames'])) if a != b]
            if diff:
                shown = ', '.join(map(str, diff[:8])) + (' ...' if len(diff) > 8 else '')
                changes.append(f'{clip}: {len(diff)}/{len(ref["frames"])} frames changed ({shown})')
        if not changes:
            print(f'{name}: OK, all approved frames identical')
            continue
        failed += 1
        print(f'{name}: CHANGED since approval by {meta["approved"]["by"]} on {meta["approved"]["date"]}')
        for line in changes:
            print('  ' + line)
        if args.compare:
            target = out / 'compare'
            compare.main([str(out), '--before', str(folder / 'approved'), '--clips',
                          ','.join(c for c in meta['clips'] if c in current), '--out', str(target)])
            print(f'  show the user {target}/*.gif; re-approve only after they accept it')
    print(f'outputs: {out_root}')
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=FIXTURES, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('add')
    p.add_argument('name')
    p.add_argument('--job', type=Path, help='reviewed basic/rifle job folder (job.json, layers, rig/)')
    p.add_argument('--character', type=Path, help='character.json; its folder is copied')
    p.add_argument('--clips', required=True)
    p.add_argument('--preset', default='hd512')
    p.add_argument('--extra', nargs=argparse.REMAINDER, help='further generate.py arguments, last')
    p = sub.add_parser('approve')
    p.add_argument('name')
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--by', required=True, help='who approved and where, e.g. "user, chat 2026-11-06"')
    p.add_argument('--note')
    p = sub.add_parser('check')
    p.add_argument('names', nargs='*')
    p.add_argument('--out', type=Path)
    p.add_argument('--compare', action='store_true', help='write approved-vs-new GIFs for changed fixtures')
    args = parser.parse_args(argv)
    return {'add': cmd_add, 'approve': cmd_approve, 'check': cmd_check}[args.command](args) or 0


if __name__ == '__main__':
    sys.exit(main())
