#!/usr/bin/env python3
"""Fixed, staged basic-side-v1 image-to-puppet workflow. See references/basic-character-workflow.md."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

import layer_parts as lp
import visual_review as vr
from sprite_anim.layer_slots import (BASIC_PROFILE, BASIC_SCOPE_CHECKS, BASIC_SLOTS, HAND_HINTS,
                                    IDENTITY_PROMPT, REPAIR_RULES, REFERENCE_HAND_REPAIR, basic_prompt, basic_reference_prompt)

LAYER_CHECKS = ('complete_shape', 'exclusive_contents', 'sharp_art', 'unchanged_pose', 'valid_attachment')


def layer_checks(name):
    extra = (('natural_neck_attachment',) if name in ('head', 'torso') else
             ('natural_hand_pose',) if name in ('arm_near', 'arm_far', *HAND_HINTS) else ())
    return LAYER_CHECKS + extra


MAX_ATTEMPTS = 3
HERE = Path(__file__).resolve().parent


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def read_json(path):
    with open(path, encoding='utf-8') as source:
        return json.load(source)


def load_job(folder, allow_blocked=False):
    root = Path(folder).resolve()
    job = read_json(root/'job.json')
    if job.get('profile') != BASIC_PROFILE or job.get('weapon') not in ('none', 'sword'):
        raise lp.Rejected('unsupported job profile or weapon; do not switch a production job to an experimental rig')
    if vr.file_hash(root/'source.png') != job['source_hash']:
        raise lp.Rejected('source image changed; prepare a new job and inspect identity again')
    if job.get('phase') == 'blocked' and not allow_blocked:
        raise lp.Rejected('job is blocked after its attempt budget; inspect the recorded blocker, do not reset or bypass it')
    return root, job


def slots(job):
    return (*BASIC_SLOTS, *(('weapon',) if job['weapon'] == 'sword' else ()))


def write_pose_guide(path, weapon="none"):
    """One fixed skeleton for the whole basic profile, never traced on a character."""
    image = Image.new('RGB', (1024, 1536), (255, 0, 255))
    draw = ImageDraw.Draw(image)
    # Constant template geometry, not inferred or hand-tuned image landmarks.
    neck, hip = (500, 320), (500, 790)
    shoulder = (500, 370)
    far = [shoulder, (350, 520), (285, 680)]
    near = [shoulder, (650, 520), (800, 430)]
    legs = [[hip, (405, 1080), (350, 1360)], [hip, (585, 1080), (665, 1360)]]
    draw.polygon([(450, 320), (540, 320), (550, 790), (450, 790)], fill=(80, 90, 110))
    draw.ellipse((425, 110, 565, 310), fill=(160, 170, 180))
    draw.polygon([(553, 175), (585, 210), (550, 222)], fill=(160, 170, 180))
    draw.line([neck, hip], fill='white', width=7)
    for points, colour in ((far, (255, 190, 55)), (near, (40, 225, 255)),
                           (legs[0], (255, 190, 55)), (legs[1], (40, 225, 255))):
        draw.line(points, fill=colour, width=22)
        for x, y in points:
            draw.ellipse((x-15, y-15, x+15, y+15), fill=colour)
    for x in (350, 665):
        draw.rectangle((x-35, 1360, x+90, 1405), fill=(160, 170, 180))
        draw.line([(x-35, 1405), (x+90, 1405)], fill='white', width=4)
    if weapon == 'sword':
        draw.line([(775, 475), (935, 195)], fill=(205, 205, 215), width=10)
    image.save(path)


def prepare(image, folder, name='character', weapon='none', who=None, style=None, source_proxy_note=None):
    root = Path(folder).resolve()
    if root.exists() and any(root.iterdir()):
        raise lp.Rejected('prepare needs a new or empty output directory; existing jobs must not lose their history')
    with Image.open(image) as source:
        source = source.convert('RGBA')
        if not source.getbbox():
            raise lp.Rejected('source image is empty')
        root.mkdir(parents=True, exist_ok=True)
        source.save(root/'source.png')
    (root/'prompts').mkdir()
    (root/'layers').mkdir()
    write_pose_guide(root/'pose_guide.png', weapon)
    (root/'prompts/00_identity.txt').write_text(IDENTITY_PROMPT, encoding='utf-8')
    (root/'prompts/01_reference.txt').write_text(basic_reference_prompt(
        who or 'the same character as the supplied identity picture',
        style or 'preserve the supplied picture\'s linework, palette and shading', weapon), encoding='utf-8')
    job = dict(profile=BASIC_PROFILE, name=name, weapon=weapon, source_hash=vr.file_hash(root/'source.png'),
               phase='awaiting_standard_reference', attempts={'reference': 1}, retries=[],
               source_kind='generated_identity_proxy' if source_proxy_note else 'original_file',
               original_source_note=source_proxy_note)
    write_json(root/'job.json', job)
    print(f'Prepared {BASIC_PROFILE}: inspect source identity, then use prompts/01_reference.txt -> reference.png')


def current_reference(root):
    image = root/'reference.png'
    array = lp.reference(image)
    if (array.shape[1], array.shape[0]) != (1024, 1536):
        raise lp.Rejected('standard reference must use the fixed 1024 x 1536 portrait canvas; regenerate it')
    return image, array


def reference_template(root):
    image, _ = current_reference(root)
    review = lp.reference_review_template(image)
    job = read_json(root/'job.json')
    review.update(profile=BASIC_PROFILE, expected_weapon=job['weapon'], source_hash=job['source_hash'])
    review['checks'].update({k: dict(status='pending', evidence='') for k in BASIC_SCOPE_CHECKS})
    return review


def accepted_reference(root):
    image, _ = current_reference(root)
    review = lp.check_reference_review(image, root/'reference_review.json')
    job = read_json(root/'job.json')
    if (review.get('profile') != BASIC_PROFILE or review.get('expected_weapon') != job['weapon']
            or review.get('source_hash') != job['source_hash']):
        raise lp.Rejected('reference review must explicitly cover this profile, source and expected weapon')
    for name in BASIC_SCOPE_CHECKS:
        item = review.get('checks', {}).get(name, {})
        if item.get('status') != 'pass' or not isinstance(item.get('evidence'), str) or not item['evidence'].strip():
            raise lp.Rejected(f'unsupported reference or incomplete review: {name}; regenerate within basic scope or stop')
    notes = root/'identity_notes.md'
    if not notes.is_file() or not notes.read_text(encoding='utf-8').strip():
        raise lp.Rejected('inspect the source identity and record preserved traits/adaptations in identity_notes.md first')
    return review


def review_reference(folder, review=None):
    root, job = load_job(folder)
    if review is None:
        target = root/'reference_review.template.json'
        write_json(target, reference_template(root))
        print(f'Numeric preflight only. Inspect reference.png and complete {target.name}; no layers released yet.')
        return
    try:
        value = read_json(Path(review).resolve())
    finally:
        for name in ('reference_review.json', 'layer_review.json'):
            (root/name).unlink(missing_ok=True)
        for name in (*slots(job), *HAND_HINTS):
            (root/'prompts'/f'{name}.txt').unlink(missing_ok=True)
        job['phase'] = 'awaiting_standard_reference'
        write_json(root/'job.json', job)
    if value.get('image_sha256') != lp.reference_review_template(root/'reference.png')['image_sha256']:
        raise lp.Rejected('reference review is stale; inspect the current image again')
    if not isinstance(value.get('reviewer'), str) or not value['reviewer'].strip():
        raise lp.Rejected('reference review needs a reviewer')
    template = reference_template(root)
    for key in template['checks']:
        item = value.get('checks', {}).get(key, {})
        if item.get('status') != 'pass' or not isinstance(item.get('evidence'), str) or not item['evidence'].strip():
            raise lp.Rejected(f'reference: {key} has not passed visual inspection')
    if (value.get('profile') != BASIC_PROFILE or value.get('expected_weapon') != job['weapon']
            or value.get('source_hash') != job['source_hash']):
        raise lp.Rejected('reference: wrong profile, source or expected weapon')
    notes = root/'identity_notes.md'
    if not notes.is_file() or not notes.read_text(encoding='utf-8').strip():
        raise lp.Rejected('identity_notes.md must record identity preservation and any adaptations')
    write_json(root/'reference_review.json', value)
    for slot in (*slots(job), *HAND_HINTS):
        (root/'prompts'/f'{slot}.txt').write_text(basic_prompt(slot), encoding='utf-8')
        job['attempts'].setdefault(slot, 1)
    job['phase'] = 'awaiting_layers'
    write_json(root/'job.json', job)
    print('Reference reviewed. Generate only the released layer prompts; then generate BOTH hand hints from the finished arm layers.')


def layer_assets(root, job):
    accepted_reference(root)
    names = (*slots(job), *HAND_HINTS)
    actual = {p.stem for p in (root/'layers').glob('*.png')}
    if actual != set(names):
        raise lp.Rejected(f'layers do not match the basic contract: missing {sorted(set(names)-actual)}, extra {sorted(actual-set(names))}')
    assets = {'source.png': vr.file_hash(root/'source.png'), 'reference.png': vr.file_hash(root/'reference.png'),
              'reference_review.json': vr.file_hash(root/'reference_review.json'),
              'identity_notes.md': vr.file_hash(root/'identity_notes.md')}
    for name in names:
        path = root/'layers'/f'{name}.png'
        with Image.open(path) as image:
            if image.size != (1024, 1536):
                raise lp.Rejected(f'{name}: changed canvas; regenerate at the reference canvas size')
        if not (lp.key_out(path)[..., 3] > 128).any():
            raise lp.Rejected(f'{name}: empty layer; regenerate it')
        assets[f'layers/{name}.png'] = vr.file_hash(path)
    return assets


def layer_template(root, job):
    return dict(profile=BASIC_PROFILE, reviewer='', assets=layer_assets(root, job), layers={
        name: dict(checks={k: dict(status='pending', evidence='') for k in layer_checks(name)})
        for name in (*slots(job), *HAND_HINTS)})


def accepted_layers(root, job, path):
    review = path if isinstance(path, dict) else read_json(path)
    if review.get('profile') != BASIC_PROFILE or review.get('assets') != layer_assets(root, job):
        raise lp.Rejected('layer review is stale or for another profile; inspect current layers again')
    if not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip():
        raise lp.Rejected('layer review needs a reviewer')
    if set(review.get('layers', {})) != set((*slots(job), *HAND_HINTS)):
        raise lp.Rejected('layer review must cover exactly every production layer and both hand hints')
    for name, row in review['layers'].items():
        for check in layer_checks(name):
            value = row.get('checks', {}).get(check, {})
            if value.get('status') != 'pass' or not isinstance(value.get('evidence'), str) or not value['evidence'].strip():
                raise lp.Rejected(f'{name}: {check} not approved; use the fixed repair prompt or stop')
    return review


def review_layers(folder, review=None):
    root, job = load_job(folder)
    if review is None:
        template = layer_template(root, job)
        write_json(root/'layer_review.template.json', template)
        names = (*slots(job), *HAND_HINTS)
        sheet = Image.new('RGB', (320*4, 500*((len(names)+3)//4)), (58, 62, 74))
        draw = ImageDraw.Draw(sheet)
        for i, name in enumerate(names):
            art = Image.fromarray(lp.key_out(root/'layers'/f'{name}.png'), 'RGBA')
            art.thumbnail((310, 465))
            x, y = i % 4 * 320, i // 4 * 500
            sheet.paste(art, (x+(320-art.width)//2, y+25), art)
            draw.text((x+8, y+6), name, fill='white')
        sheet.save(root/'layer_review.png')
        print('Inspect layer_review.png AND each original layer at full size; complete layer_review.template.json.')
        return
    try:
        candidate = read_json(review)
    finally:
        (root/'layer_review.json').unlink(missing_ok=True)
        job['phase'] = 'awaiting_layers'
        write_json(root/'job.json', job)
    value = accepted_layers(root, job, candidate)
    write_json(root/'layer_review.json', value)
    job['phase'] = 'ready_to_bind'
    write_json(root/'job.json', job)
    print('Layer inspection recorded. Numerical binding is the next gate, not a delivery verdict.')


def bind_job(folder):
    root, job = load_job(folder)
    if job['phase'] not in ('ready_to_bind', 'bound', 'awaiting_walk_review', 'preview_blocked'):
        raise lp.Rejected('finish the reference and per-layer reviews before binding')
    semantic = accepted_reference(root)
    layer_review = accepted_layers(root, job, root/'layer_review.json')
    _, ref = current_reference(root)
    layers = {name: lp.key_out(root/'layers'/f'{name}.png') for name in (*slots(job), *HAND_HINTS)}
    state = {}
    try:
        out, spec, report = lp.bind(ref, layers, str(root/'fit_cache'), state, registered_connections=True)
    except lp.Rejected:
        lp.save_diagnostics(root/'rig', ref, state)
        raise
    state.update(profile=BASIC_PROFILE, reference_review=semantic, layer_review=layer_review,
                 semantic_verification='reviewer_attested')
    lp.write_binding(str(root/'rig'), job['name'], ref, out, spec, report, state)
    job['rig_assets'] = {str(p.relative_to(root/'rig')): vr.file_hash(p)
                         for pattern in ('*.json', '*.png', 'layers/*.png') for p in (root/'rig').glob(pattern)}
    job['phase'] = 'bound'
    write_json(root/'job.json', job)


def check_bound_rig(root, job):
    """Shared by the staged preview and direct generation; neither may skip review."""
    accepted_layers(root, job, root/'layer_review.json')
    if not job.get('rig_assets'):
        raise lp.Rejected('missing exported rig provenance; bind through this workflow first')
    for relative, digest in job['rig_assets'].items():
        path = root/'rig'/relative
        if not path.is_file() or vr.file_hash(path) != digest:
            raise lp.Rejected('exported rig was changed; fix the general rule and bind again, do not tune one character')
    # Refuse a stale rig after a reviewed layer was replaced and re-reviewed.
    bound = read_json(root/'rig/bind_report.json')
    if bound.get('layer_review', {}).get('assets') != layer_assets(root, job) or bound.get('status') != 'accepted':
        raise lp.Rejected('rig is stale; bind the current reviewed layers again')
    spec = read_json(root/'rig/character.json')
    if (spec.get('puppet', {}).get('connection_skinning') != 'registered_pelvis_v1'
            or spec['puppet'].get('attachment_checks') is not True):
        raise lp.Rejected('basic-side-v1 requires current registered pelvis and full attachment checks; rebind')


def check_render_input(character):
    """Reject basic-job diagnostics or stale rigs before the renderer writes any output."""
    path = Path(character).resolve()
    owner = lp.find_basic_job(path)
    if owner is None:
        report = path.parent/'bind_report.json'
        if report.is_file():
            value = read_json(report)
            if not isinstance(value, dict) or not isinstance(value.get('reference_review', {}), dict):
                raise lp.Rejected('invalid binding review provenance')
            if (value.get('profile') == BASIC_PROFILE
                    or value.get('reference_review', {}).get('profile') == BASIC_PROFILE):
                raise lp.Rejected('basic-side-v1 rig has no owning production job; '
                                  'render from the original reviewed job')
        return
    root, job = load_job(owner)
    if job['phase'] not in ('bound', 'preview_rendering', 'awaiting_walk_review', 'preview_blocked'):
        raise lp.Rejected('basic-side-v1: finish the per-layer reviews and bind before rendering')
    if path != root/'rig/character.json':
        raise lp.Rejected('basic-side-v1: only the reviewed rig/character.json may be rendered; '
                          'diagnostic bindings are not approved production input')
    check_bound_rig(root, job)


def preview_job(folder):
    root, job = load_job(folder)
    if job['phase'] not in ('bound', 'awaiting_walk_review', 'preview_blocked'):
        raise lp.Rejected('bind the reviewed layers before preview')
    check_bound_rig(root, job)
    scripts = [
        ['generate.py', '--character', str(root/'rig/character.json'), '--preset', 'hd512',
         '--clips', 'idle,walk', '--no-fx', '--out', str(root/'build')],
        ['qa_motion.py', str(root/'build')],
        ['visual_review.py', str(root/'build')],
    ]
    (root/'build/visual_report.json').unlink(missing_ok=True)
    job['phase'] = 'preview_rendering'
    write_json(root/'job.json', job)
    codes = []
    for args in scripts:
        result = subprocess.run([sys.executable, str(HERE/args[0]), *args[1:]], check=False)
        codes.append(result.returncode)
        if args[0] == 'generate.py' and result.returncode:
            job.update(phase='preview_blocked', preview_exit_codes=codes)
            write_json(root/'job.json', job)
            raise lp.Rejected('preview generation failed; do not deliver or advance')
    job.update(phase='preview_blocked' if any(codes) else 'awaiting_walk_review', preview_exit_codes=codes)
    write_json(root/'job.json', job)
    if any(codes):
        raise lp.Rejected('preview QA/review build failed; inspect the flagged art and repair before proceeding')
    print('Review every sheet, record/check the visual verdict, show the running preview, and wait for the user\'s walk approval. No full-set or attack generation is enabled here.')


def repair_prompt(baseline, fault, reason):
    """Fixed repair structure, with the actual observed failure as data, never rig offsets."""
    return (baseline + '\nOBSERVED FAILURE (inspection data; correct this defect, do not draw it):\n'
            + json.dumps(reason, ensure_ascii=False) + '\nFIXED REPAIR INSTRUCTION:\n' + REPAIR_RULES[fault])


def retry(folder, stage, fault, reason):
    root, job = load_job(folder)
    if stage not in ('reference', *slots(job), *HAND_HINTS):
        raise lp.Rejected('unsupported retry stage')
    attempt = job['attempts'].get(stage, 1)
    if attempt >= MAX_ATTEMPTS:
        job.update(phase='blocked', blocker=dict(stage=stage, fault=fault, evidence=reason, resolved=False))
        write_json(root/'job.json', job)
        raise lp.Rejected(f'{stage}: {MAX_ATTEMPTS} attempts exhausted; stop and report the remaining blocker')
    if not reason.strip():
        raise lp.Rejected('retry needs a concrete observed fault and frame/layer evidence')
    archive = root/'attempts'/f'{stage}-{attempt}'
    archive.mkdir(parents=True, exist_ok=True)
    current = root/'reference.png' if stage == 'reference' else root/'layers'/f'{stage}.png'
    if current.exists():
        shutil.copyfile(current, archive/current.name)
    for record in ('reference_review.json', 'layer_review.json'):
        if (root/record).exists():
            shutil.copyfile(root/record, archive/record)
    used_prompt = root/'prompts'/('01_reference.txt' if stage == 'reference' and attempt == 1 else f'{stage}.txt' if attempt == 1 else f'retry_{stage}.txt')
    if used_prompt.is_file():
        shutil.copyfile(used_prompt, archive/'prompt.txt')
    if stage == 'reference':
        for name in (*slots(job), *HAND_HINTS):
            (root/'prompts'/f'{name}.txt').unlink(missing_ok=True)
    baseline = (root/'prompts/01_reference.txt').read_text(encoding='utf-8') if stage == 'reference' else basic_prompt(stage)
    if stage == 'reference' and fault == 'hand_pose':
        baseline = REFERENCE_HAND_REPAIR
    (root/'prompts'/f'retry_{stage}.txt').write_text(repair_prompt(baseline, fault, reason), encoding='utf-8')
    job['attempts'][stage] = attempt+1
    job['retries'].append(dict(stage=stage, attempt=attempt+1, fault=fault, evidence=reason))
    job['phase'] = 'awaiting_standard_reference' if stage == 'reference' else 'awaiting_layers'
    # A retry invalidates acceptance even if the next image happens to be identical.
    for record in ('layer_review.json', *(['reference_review.json'] if stage == 'reference' else [])):
        (root/record).unlink(missing_ok=True)
    write_json(root/'job.json', job)
    print(f'{stage}: attempt {attempt+1}/{MAX_ATTEMPTS}; use prompts/retry_{stage}.txt, then repeat the relevant reviews.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--image', required=True); p.add_argument('--out', required=True)
    p.add_argument('--name', default='character'); p.add_argument('--weapon', choices=('none', 'sword'), default='none')
    p.add_argument('--who'); p.add_argument('--style')
    p.add_argument('--source-proxy-note', help='explicit provenance when a generated proxy is used because the original chat image has no readable local file; never claim it is the original')
    for command in ('reference', 'layers', 'bind', 'preview', 'status', 'retry'):
        p = sub.add_parser(command); p.add_argument('--job', required=True)
        if command in ('reference', 'layers'):
            p.add_argument('--review')
        if command == 'retry':
            p.add_argument('--stage', required=True); p.add_argument('--fault', choices=tuple(REPAIR_RULES), required=True)
            p.add_argument('--reason', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args.image, args.out, args.name, args.weapon, args.who, args.style, args.source_proxy_note)
        elif args.command == 'reference':
            review_reference(args.job, args.review)
        elif args.command == 'layers':
            review_layers(args.job, args.review)
        elif args.command == 'bind':
            bind_job(args.job)
        elif args.command == 'preview':
            preview_job(args.job)
        elif args.command == 'retry':
            retry(args.job, args.stage, args.fault, args.reason)
        else:
            root, job = load_job(args.job, allow_blocked=True)
            print(json.dumps(job, ensure_ascii=False, indent=2))
    except (lp.Rejected, OSError, ValueError) as exc:
        sys.exit(f'[blocked] {exc}')


if __name__ == '__main__':
    main()
