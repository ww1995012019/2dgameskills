"""Compare all 26 installed unified-bundle outputs against the recorded baseline.

Usage: python dev/regress_unified.py --out ../unified-regression [--jobs 2]
The output directory must not exist. Each generated set is removed only after its
QA and pixel hashes are recorded, limiting disk usage. Logs and the snapshot remain.
"""
import argparse
import concurrent.futures
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import baseline

ROOT = Path(__file__).resolve().parents[1]
SPRITE = {'hero', 'knight', 'mage', 'ninja', 'goblin', 'cutout_demo'}
SHOOTER = {'commando', 'swat', 'ghost', 'mercenary'}
TOPDOWN = {'wanderer', 'warden'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--archive', type=Path, default=ROOT / 'game-animator.skill',
                        help='unified bundle to test (defaults to the current package)')
    parser.add_argument('--jobs', type=int, default=2, choices=(1, 2, 3, 4))
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(args.archive) as archive:
        archive.extractall(out / 'install')
    bundle = out / 'install/game-animator/modes'
    runs = out / 'runs'
    runs.mkdir()
    logs = out / 'logs'
    logs.mkdir()
    with (ROOT / 'dev/baseline.json').open(encoding='utf-8') as f:
        reference = json.load(f)

    def run(name):
        character, preset = name.rsplit('-', 1)
        if character in SPRITE:
            mode = 'game-sprite-animator'
        elif character in SHOOTER:
            mode = 'game-shooter-animator'
        elif character in TOPDOWN:
            mode = 'game-topdown-animator'
        elif character == 'wolf':
            mode = 'game-quadruped-animator'
        else:
            raise ValueError(f'unknown baseline set: {name}')
        skill = bundle / mode
        spec = skill / 'assets/characters' / (character + '.json')
        if not spec.exists():
            spec = skill / 'assets/characters' / character / 'character.json'
        target = runs / name
        if target.resolve().parent != runs.resolve() or target.exists():
            raise ValueError(f'unsafe or existing target: {target}')
        with (logs / (name + '.log')).open('w', encoding='utf-8') as log:
            for command in ([sys.executable, str(skill / 'scripts/generate.py'), '--character', str(spec),
                             '--preset', preset, '--out', str(target)],
                            [sys.executable, str(skill / 'scripts/qa_motion.py'), str(target)]):
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
                if result.returncode:
                    raise RuntimeError(f'{name}: exit {result.returncode}; see {log.name}')
        snapshot = baseline.snapshot_set(str(target))
        # The target is a fresh direct child of runs, constructed above, never a user directory.
        if target.is_symlink() or target.resolve().parent != runs.resolve():
            raise ValueError(f'unsafe cleanup target: {target}')
        shutil.rmtree(target)
        return name, snapshot

    results, failures = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run, name): name for name in reference}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                _, results[name] = future.result()
                print(f'{name}: generated and checked', flush=True)
            except Exception as exc:
                failures.append(str(exc))
                print(f'{name}: ERROR {exc}', flush=True)
    (out / 'snapshot.json').write_text(json.dumps(results, indent=1), encoding='utf-8')
    reg, changed, drift = baseline.compare(reference, results)
    report = {'failures': failures, 'regressions': reg, 'changed': changed, 'drift': drift}
    (out / 'comparison.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(f'{len(results)} sets: {len(failures)} errors, {len(reg)} regressions, '
          f'{len(changed)} changed, {len(drift)} drifted', flush=True)
    return 1 if failures or reg or changed else 0


if __name__ == '__main__':
    sys.exit(main())
