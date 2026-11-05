"""Basic production stages on two synthetic builds, plus unsupported/stale/faulted input gates.
These are workflow/numerical fixtures, not AI-art visual acceptance.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'game-sprite-animator/scripts'))
import character_workflow as cw
from sprite_anim.layer_slots import BASIC_SLOTS, HAND_HINTS, basic_prompt, basic_reference_prompt
from test_puppet import figure, keyed, KEY
from sprite_anim.rig import Body
from sprite_anim.motions import build_clips
from sprite_anim.render import Renderer
from sprite_anim import puppet_check as pc


class CharacterWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'input.png'
        Image.new('RGB', (64, 64), 'navy').save(self.source)
        self.job = self.root/'job'

    def prepare(self, weapon='none'):
        cw.prepare(self.source, self.job, name='test hero', weapon=weapon)

    def fixture(self, short=False):
        kw = dict(hip=(480,960),leg=300,chest=(170,240),head=210,stride=70,width=84) if short else {}
        return figure(**kw), kw.get('hip', (470,880))

    def reference(self, layers):
        ref = Image.new('RGBA', (1024,1536), KEY)
        for name in ('arm_far','leg_far','leg_near','hips','torso','head','weapon','arm_near'):
            if name in layers:
                ref.alpha_composite(Image.fromarray(keyed(layers[name])))
        ref.convert('RGB').save(self.job/'reference.png')
        (self.job/'identity_notes.md').write_text('Synthetic workflow fixture; no AI identity/visual acceptance claim.')
        cw.review_reference(self.job)
        review = cw.read_json(self.job/'reference_review.template.json')
        review['reviewer'] = 'synthetic test'
        for item in review['checks'].values():
            item.update(status='pass', evidence='synthetic fixture assertion, not a real visual verdict')
        cw.write_json(self.root/'ref-review.json', review)
        cw.review_reference(self.job, self.root/'ref-review.json')

    def layers(self, layers, hip):
        for name, image in layers.items():
            image.save(self.job/'layers'/f'{name}.png')
        yy, xx = np.indices((1536,1024))
        for name, arm, tip in (('hand_near_hint','arm_near',(hip[0]+250,hip[1]-60)),
                                ('hand_far_hint','arm_far',(hip[0]-230,hip[1]-40))):
            pixels = np.array(layers[arm]).copy()
            pixels[(xx-tip[0])**2+(yy-tip[1])**2 > 29**2] = KEY
            Image.fromarray(pixels).save(self.job/'layers'/f'{name}.png')
        cw.review_layers(self.job)
        review = cw.read_json(self.job/'layer_review.template.json')
        review['reviewer'] = 'synthetic test'
        for row in review['layers'].values():
            for value in row['checks'].values():
                value.update(status='pass', evidence='synthetic fixture assertion')
        cw.write_json(self.root/'layer-review.json', review)
        cw.review_layers(self.job, self.root/'layer-review.json')

    def test_two_builds_reach_binding_and_walk_using_identical_rules(self):
        for short in (False, True):
            with self.subTest(short=short):
                self.job = self.root/('short' if short else 'tall')
                self.prepare()
                layers, hip = self.fixture(short)
                self.reference(layers)
                self.layers(layers, hip)
                identity = dict(s=1.,deg=0.,dx=0.,dy=0.,cx=0.,cy=0.,error=0.)
                # Fixture art is already registered. Exercise real binding, export,
                # proportions and walk QA without re-testing the search optimizer.
                with patch.object(cw.lp, 'registration', return_value=identity):
                    cw.bind_job(self.job)
                state = cw.read_json(self.job/'job.json')
                self.assertEqual(state['phase'], 'bound')
                cw.check_render_input(self.job/'rig/character.json')
                state['phase'] = 'preview_rendering'
                cw.write_json(self.job/'job.json', state)
                cw.check_render_input(self.job/'rig/character.json')
                state['phase'] = 'bound'
                cw.write_json(self.job/'job.json', state)
                spec = cw.read_json(self.job/'rig/character.json')
                self.assertEqual(spec['name'], 'test hero')
                spec['_dir'] = str(self.job/'rig')
                body = Body.from_spec(spec['body'])
                clips = build_clips(spec.get('style'), gait=spec['gait'], body=body)
                renderer = Renderer(spec, 256, clips={'walk': clips['walk']})
                self.assertEqual(pc.check_layers(renderer.art.puppet), [])
                self.assertEqual(pc.check_motion(renderer, clips['walk'], 8, 15), [])
                spec['name'] = 'hand-edited'
                cw.write_json(self.job/'rig/character.json', spec)
                with self.assertRaisesRegex(cw.lp.Rejected, 'exported rig was changed'):
                    cw.check_render_input(self.job/'rig/character.json')
                with self.assertRaisesRegex(cw.lp.Rejected, 'exported rig was changed'):
                    cw.preview_job(self.job)

    def test_direct_binder_cannot_skip_basic_layer_review(self):
        self.prepare()
        layers, _ = self.fixture()
        self.reference(layers)
        for name, image in layers.items():
            image.save(self.job/'layers'/f'{name}.png')
        out = self.root/'diagnostic_bind'
        result = subprocess.run([sys.executable, str(cw.HERE/'layer_parts.py'), 'bind',
            '--image', str(self.job/'reference.png'), '--layers', str(self.job/'layers'),
            '--reference-review', str(self.job/'reference_review.json'), '--out', str(out)],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cannot bypass per-layer review', result.stderr)
        self.assertFalse(out.exists())

    def test_copied_reference_review_and_symlinked_layers_keep_basic_gate(self):
        self.prepare()
        layers, _ = self.fixture()
        self.reference(layers)
        outside = self.root/'outside'
        outside.mkdir()
        shutil.copyfile(self.job/'reference.png', outside/'reference.png')
        shutil.copyfile(self.job/'reference_review.json', outside/'review.json')
        (outside/'layers').mkdir()
        with self.assertRaisesRegex(cw.lp.Rejected, 'cannot bypass'):
            cw.lp.require_generic_binding(outside/'reference.png', outside/'layers', outside/'review.json')
        linked = outside/'linked_layers'
        linked.symlink_to(self.job/'layers', target_is_directory=True)
        with self.assertRaisesRegex(cw.lp.Rejected, 'cannot bypass'):
            cw.lp.require_generic_binding(outside/'reference.png', linked, None)

    def test_direct_generator_rejects_unreviewed_diagnostic_before_writing(self):
        self.prepare()
        rig = self.job/'diagnostic_bind'
        rig.mkdir()
        cw.write_json(rig/'character.json', {'name': 'unreviewed diagnostic'})
        out = self.root/'diagnostic_build'
        result = subprocess.run([sys.executable, str(cw.HERE/'generate.py'),
            '--character', str(rig/'character.json'), '--clips', 'idle,run', '--out', str(out)],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('finish the per-layer reviews', result.stderr)
        self.assertFalse(out.exists())

    def test_basic_rig_cannot_be_relocated_without_owning_job(self):
        rig = self.root/'copied_rig'
        rig.mkdir()
        cw.write_json(rig/'character.json', {'name': 'copied diagnostic'})
        cw.write_json(rig/'bind_report.json', {'reference_review': {'profile': 'basic-side-v1'}})
        with self.assertRaisesRegex(cw.lp.Rejected, 'no owning production job'):
            cw.check_render_input(rig/'character.json')

    def test_render_does_not_trust_bound_phase_without_layer_acceptance(self):
        self.prepare()
        layers, _ = self.fixture()
        self.reference(layers)
        job = cw.read_json(self.job/'job.json')
        job['phase'] = 'bound'
        cw.write_json(self.job/'job.json', job)
        rig = self.job/'rig'
        rig.mkdir()
        cw.write_json(rig/'character.json', {'name': 'unreviewed art'})
        out = self.root/'unapproved_build'
        result = subprocess.run([sys.executable, str(cw.HERE/'generate.py'),
            '--character', str(rig/'character.json'), '--out', str(out)],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('layer_review.json', result.stderr)
        self.assertFalse(out.exists())

    def test_bound_job_cannot_render_an_alternate_diagnostic_rig(self):
        self.prepare()
        job = cw.read_json(self.job/'job.json')
        job['phase'] = 'bound'
        cw.write_json(self.job/'job.json', job)
        rig = self.job/'diagnostic_bind'
        rig.mkdir()
        cw.write_json(rig/'character.json', {'name': 'alternate diagnostic'})
        with self.assertRaisesRegex(cw.lp.Rejected, 'only the reviewed rig'):
            cw.check_render_input(rig/'character.json')

    def test_reference_without_specific_neck_or_hand_review_is_refused(self):
        self.prepare()
        layers, hip = self.fixture()
        self.reference(layers)
        original = cw.read_json(self.job/'reference_review.json')
        for check in ('natural_neck_attachment', 'natural_hand_pose'):
            review = json.loads(json.dumps(original))
            del review['checks'][check]
            cw.write_json(self.job/'reference_review.json', review)
            with self.subTest(check=check), self.assertRaisesRegex(cw.lp.Rejected, check):
                cw.accepted_reference(self.job)

    def test_layer_neck_cut_and_unnatural_hand_cannot_inherit_base_check_passes(self):
        self.prepare()
        layers, hip = self.fixture()
        self.reference(layers); self.layers(layers, hip)
        original = cw.read_json(self.job/'layer_review.json')
        for slot, check in (('head', 'natural_neck_attachment'), ('torso', 'natural_neck_attachment'),
                            ('arm_near', 'natural_hand_pose'), ('hand_far_hint', 'natural_hand_pose')):
            review = json.loads(json.dumps(original))
            del review['layers'][slot]['checks'][check]
            with self.subTest(slot=slot), self.assertRaisesRegex(cw.lp.Rejected, slot + ': ' + check):
                cw.accepted_layers(self.job, cw.read_json(self.job/'job.json'), review)

    def test_simple_sword_uses_one_separate_weapon_and_measured_hand_contact(self):
        self.prepare('sword')
        layers, hip = self.fixture()
        arm = keyed(layers['arm_near'])[...,3] > 128
        yy, xx = np.indices(arm.shape)
        tip = (hip[0]+250, hip[1]-60)
        hint = arm & ((xx-tip[0])**2+(yy-tip[1])**2 <= 29**2)
        joints = cw.lp.read_arm(arm, hint)
        grip = joints['wrist'] + (joints['wrist']-joints['elbow'])*0.14
        axis = np.array([0.55,-0.835])
        sword = Image.new('RGB',(1024,1536),KEY)
        draw = ImageDraw.Draw(sword)
        draw.line([tuple(grip-axis*25),tuple(grip+axis*230)], fill=(200,205,215), width=14)
        layers['weapon'] = sword
        self.reference(layers); self.layers(layers,hip)
        identity = dict(s=1.,deg=0.,dx=0.,dy=0.,cx=0.,cy=0.,error=0.)
        with patch.object(cw.lp,'registration',return_value=identity):
            cw.bind_job(self.job)
        spec = cw.read_json(self.job/'rig/character.json')
        self.assertEqual(spec['weapon'],'sword')
        self.assertIn('weapon',spec['puppet']['layers'])
        measured = np.asarray(spec['puppet']['layers']['weapon']['anchor'])
        weapon = keyed(sword)[...,3] > 128
        self.assertTrue((arm & hint & weapon)[round(measured[1]), round(measured[0])])
        self.assertTrue(spec['puppet']['layers']['arm_near']['tip_lock'])
        self.assertIn('weapon_hand_angle',spec['body'])
        frame = cw.lp.measured_grip_frame(measured, measured+axis*100, joints)
        for key in ('weapon_grip_along','weapon_grip_across'):
            self.assertAlmostEqual(spec['body'][key],frame[key],places=5)

    def test_installable_packages_include_the_same_default_workflow(self):
        import zipfile
        import subprocess
        repository = Path(__file__).resolve().parents[2]
        results = []
        for package, relative in (
            ('game-sprite-animator', 'game-sprite-animator/scripts/character_workflow.py'),
            ('game-animator', 'game-animator/modes/game-sprite-animator/scripts/character_workflow.py')):
            target = self.root/package
            with zipfile.ZipFile(repository/(package+'.skill')) as archive:
                archive.extractall(target)
            output = target/'job'
            result = subprocess.run([sys.executable, str(target/relative), 'prepare', '--image', str(self.source),
                                     '--out', str(output), '--weapon', 'sword'], capture_output=True, text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            results.append((output/'prompts/01_reference.txt').read_text())
            self.assertEqual(cw.read_json(output/'job.json')['profile'],'basic-side-v1')
        self.assertEqual(results[0],results[1])

    def test_proxy_provenance_and_generic_guide_are_explicit(self):
        cw.prepare(self.source,self.job,source_proxy_note='Original visible only in chat; generated proxy is not original bytes')
        job = cw.read_json(self.job/'job.json')
        self.assertEqual(job['source_kind'],'generated_identity_proxy')
        self.assertIn('not original bytes',job['original_source_note'])
        with Image.open(self.job/'pose_guide.png') as guide:
            self.assertEqual(guide.size,(1024,1536))
        self.assertIn('POSE GUIDE',(self.job/'prompts/01_reference.txt').read_text())

    def test_arbitrary_source_gets_complete_presets_before_numeric_reference_gate(self):
        self.prepare()
        text = (self.job/'prompts/01_reference.txt').read_text()
        self.assertIn('Both hands empty', text)
        self.assertIn('1024 x 1536', text)
        self.assertFalse((self.job/'prompts/arm_near.txt').exists())
        with self.assertRaises(cw.lp.Rejected):
            cw.bind_job(self.job)
        with self.assertRaises(cw.lp.Rejected):
            cw.prepare(self.source, self.job)

    def test_weapon_scope_and_layer_prompts(self):
        text = basic_reference_prompt('same hero', 'same style', 'sword')
        self.assertIn('Exactly ONE', text)
        with self.assertRaises(ValueError):
            basic_reference_prompt('hero','style','spear')
        for name in (*BASIC_SLOTS, 'weapon', *HAND_HINTS):
            self.assertIn('KEEP ONLY:', basic_prompt(name))
        with self.assertRaises(ValueError):
            basic_prompt('robe')

    def test_scope_fail_blocks_prompt_release(self):
        self.prepare(); layers, _ = self.fixture()
        self.reference(layers)
        review = cw.read_json(self.root/'ref-review.json')
        review['checks']['short_fitted_clothing']['status'] = 'fail'
        cw.write_json(self.root/'bad.json', review)
        with self.assertRaisesRegex(cw.lp.Rejected, 'short_fitted_clothing'):
            cw.review_reference(self.job, self.root/'bad.json')
        self.assertFalse((self.job/'reference_review.json').exists())
        self.assertFalse((self.job/'prompts/arm_near.txt').exists())
        with self.assertRaises(cw.lp.Rejected):
            cw.bind_job(self.job)

    def test_missing_hints_unsupported_layers_and_changed_canvas_are_rejected(self):
        self.prepare(); layers, hip = self.fixture()
        self.reference(layers)
        for name, image in layers.items(): image.save(self.job/'layers'/f'{name}.png')
        with self.assertRaisesRegex(cw.lp.Rejected, 'hand_far_hint'):
            cw.review_layers(self.job)
        self.layers(layers, hip)
        Image.new('RGB',(1024,1536),KEY).save(self.job/'layers/robe.png')
        with self.assertRaisesRegex(cw.lp.Rejected, 'extra'):
            cw.review_layers(self.job)
        (self.job/'layers/robe.png').unlink()
        Image.new('RGB',(64,64),'red').save(self.job/'layers/arm_near.png')
        with self.assertRaisesRegex(cw.lp.Rejected, 'changed canvas'):
            cw.review_layers(self.job)

    def test_changed_layers_and_unreviewed_completeness_cannot_bind(self):
        self.prepare(); layers, hip = self.fixture()
        self.reference(layers); self.layers(layers, hip)
        review = cw.read_json(self.job/'layer_review.json')
        review['layers']['arm_near']['checks']['complete_shape']['status'] = 'fail'
        cw.write_json(self.root/'bad.json',review)
        with self.assertRaisesRegex(cw.lp.Rejected, 'complete_shape'):
            cw.review_layers(self.job, self.root/'bad.json')
        with Image.open(self.job/'layers/arm_near.png') as im:
            im.putpixel((10,10),(0,0,0)); im.save(self.job/'layers/arm_near.png')
        with self.assertRaisesRegex(cw.lp.Rejected, 'finish|stale'):
            cw.bind_job(self.job)

    def test_retries_preserve_history_invalidate_acceptance_and_stop_at_three(self):
        self.prepare(); layers, hip = self.fixture()
        self.reference(layers); self.layers(layers, hip)
        cw.retry(self.job,'arm_near','incomplete','arm layer: forearm missing')
        self.assertTrue((self.job/'attempts/arm_near-1/arm_near.png').exists())
        self.assertFalse((self.job/'layer_review.json').exists())
        self.assertIn('arm layer: forearm missing',(self.job/'prompts/retry_arm_near.txt').read_text())
        self.assertTrue((self.job/'attempts/arm_near-1/prompt.txt').is_file())
        with self.assertRaisesRegex(cw.lp.Rejected, 'finish'):
            cw.bind_job(self.job)
        cw.retry(self.job,'arm_near','incomplete','same blocker persists')
        with self.assertRaisesRegex(cw.lp.Rejected,'exhausted'):
            cw.retry(self.job,'arm_near','incomplete','still broken')
        self.assertEqual(cw.read_json(self.job/'job.json')['attempts']['arm_near'],3)
        self.assertEqual(cw.read_json(self.job/'job.json')['phase'],'blocked')
        with self.assertRaisesRegex(cw.lp.Rejected,'job is blocked'):
            cw.review_layers(self.job)

    def test_preview_command_never_generates_attacks_or_full_set(self):
        self.prepare()
        root, job = cw.load_job(self.job)
        (root/'rig').mkdir()
        cw.write_json(root/'rig/character.json', {'fixture':True, 'puppet':{
            'connection_skinning':'registered_garment_v3', 'attachment_checks':True}})
        job.update(phase='bound', rig_assets={'character.json':cw.vr.file_hash(root/'rig/character.json')})
        cw.write_json(root/'job.json',job)
        cw.write_json(root/'rig/bind_report.json', {'status':'accepted','layer_review':{'assets':{'fixture':'hash'}}})
        from types import SimpleNamespace
        with patch.object(cw,'accepted_layers'), patch.object(cw,'layer_assets',return_value={'fixture':'hash'}), patch.object(cw.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
            cw.preview_job(self.job)
        args = run.call_args_list[0].args[0]
        self.assertEqual(args[args.index('--clips')+1], 'idle,walk')
        self.assertEqual(cw.read_json(root/'job.json')['phase'], 'awaiting_walk_review')
        (root/'build').mkdir()
        cw.write_json(root/'build/visual_report.json', {'status':'pass'})
        with patch.object(cw,'accepted_layers'), patch.object(cw,'layer_assets',return_value={'fixture':'hash'}), patch.object(cw.subprocess,'run',side_effect=[SimpleNamespace(returncode=n) for n in (0,1,0)]):
            with self.assertRaisesRegex(cw.lp.Rejected,'QA/review build failed'):
                cw.preview_job(self.job)
        self.assertEqual(cw.read_json(root/'job.json')['phase'], 'preview_blocked')
        self.assertFalse((root/'build/visual_report.json').exists())

if __name__ == '__main__':
    unittest.main()
