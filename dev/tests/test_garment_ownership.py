"""Explicit ownership is source-space preparation, not semantic or motion approval."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import garment_ownership as go


class GarmentOwnership(unittest.TestCase):
    def fixture(self, root, scale=1, collar=True, armed=True, torso_first=True):
        source = root / 'source'
        (source / 'layers').mkdir(parents=True)
        cluster = ['torso', 'head'] + (['torso_front'] if collar else [])
        legs = ['leg_far', 'leg_near']
        middle = cluster + ['hips'] + legs if torso_first else legs + ['hips'] + cluster
        names = ['cape', 'arm_far'] + middle + ['pelvis_front']
        names += (['weapon'] if armed else []) + ['arm_near', 'sparkle']
        torso_geometry = dict(kind='tube', bones=['skirt', 'hip', 'waist', 'head_base'],
                              rest=[[30.25 * scale, 50 * scale], [30 * scale, 40 * scale],
                                    [30 * scale, 30 * scale], [30 * scale, 20 * scale]],
                              radius=12.5 * scale, source_frame=True, offset=[20 * scale, 20 * scale])
        layers = {}
        for i, name in enumerate(names):
            row = dict(kind='rigid', follow=['hip', 'body_rot'], anchor=[30.25 * scale, 40 * scale],
                       custom={'name': name}, offset=[10 * scale, 10 * scale])
            size = (5 * scale, 7 * scale)
            if name in ('torso', 'torso_front'):
                row = copy.deepcopy(torso_geometry)
                size = (20 * scale, 30 * scale)
            if name in legs:
                row.update(kind='tube', bones=['hip', 'knee', 'ankle'],
                           rest=[[22 * scale, 48 * scale], [23 * scale, 60 * scale], [23 * scale, 75 * scale]],
                           offset=[(14 if name == 'leg_far' else 24) * scale, 48 * scale], source_frame=True)
                size = (10 * scale, 30 * scale)
            row['image'] = f'layers/{name}.png'
            rgba = np.zeros((size[1], size[0], 4), dtype=np.uint8)
            rgba[..., :3] = (11, 22, 33)  # Preserve hidden RGB without claiming it is occupied.
            rgba[scale:-scale, scale:-scale] = (20 + i, 70 + i, 110 + i, 255)
            rgba[scale, scale:-scale, 3] = 1  # Even alpha=1 pixels must remain byte-identical.
            Image.fromarray(rgba).save(source / row['image'])
            layers[name] = row
        spec = dict(puppet=dict(source='source.png', layers=layers, joints={'hip': [30.25 * scale, 40 * scale]},
                                px_per_unit=1.25, chains={}, rest_angles={'body_rot': 1.5}),
                    body={'thigh': 21.5}, gait={'walk': {'stride': 3.75}}, name='synthetic', custom={'keep': [1, 2]})
        (source / 'character.json').write_text(json.dumps(spec))
        (source / 'provenance.json').write_text(json.dumps(dict(final_visual_pass=True, user_motion_approval='approved',
                                                               derived_pelvic_overlay={'source_rgb_unchanged': True})))
        Image.new('RGBA', (80 * scale, 100 * scale), (1, 2, 3, 255)).save(source / 'source.png')
        (source / 'bind_report.json').write_text('{"status":"accepted","semantic_verification":"reviewer_attested"}')
        (source / 'visual_report.json').write_text('{"final_visual_pass":true}')
        (source / 'collar_overlay.json').write_text('{"visual_approval":"approved"}')
        (source / 'pelvic_overlay.json').write_text('{"source_rgb_unchanged":true}')
        (source / 'input_manifest.json').write_text('{"old":true}')
        (source / 'custom_report.json').write_text('{"old":true}')
        (source / 'notes.txt').write_text('Preserve unrelated source documents in history.')
        (source / 'review').mkdir()
        (source / 'review/approval.json').write_text('{"pass":true}')
        Image.new('RGB', (5, 5), (255, 0, 0)).save(source / 'bind_joints.png')
        garment = root / 'garment.png'
        with Image.open(source / layers['torso']['image']) as image:
            new = np.array(image)
        new[15 * scale:, :, :3] = (180, 100, 30)
        Image.fromarray(new).save(garment)
        return source, garment, spec

    @staticmethod
    def snapshot(root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    @staticmethod
    def read_spec(source):
        return json.loads((source / 'character.json').read_text())

    def save_spec(self, source, spec):
        (source / 'character.json').write_text(json.dumps(spec))

    def install(self, source, destination, garment, **kwargs):
        return go.install_garment_ownership(source, destination, garment,
                                            ownership=kwargs.pop('ownership', 'continuous_garment'), **kwargs)

    def assert_atomic_failure(self, root, source, garment, **kwargs):
        before = self.snapshot(root)
        destination = root / 'missing-parent' / 'new-rig'
        with self.assertRaises((ValueError, OSError)):
            self.install(source, destination, garment, **kwargs)
        self.assertEqual(self.snapshot(root), before)
        self.assertFalse(destination.parent.exists())

    def test_two_sizes_preserve_geometry_source_history_and_recompose_reference(self):
        for scale in (1, 3):
            for collar, armed, torso_first in ((False, False, False), (True, True, True), (True, False, False)):
                with self.subTest(scale=scale, collar=collar, armed=armed, torso_first=torso_first), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    source, garment, original = self.fixture(root, scale, collar, armed, torso_first)
                    before = self.snapshot(source)
                    destination = root / 'derived'
                    self.assertEqual(self.install(source, destination, garment), destination / 'character.json')
                    self.assertEqual(before, self.snapshot(source))
                    self.assertEqual(before, self.snapshot(destination / go.HISTORY))
                    result = self.read_spec(destination)
                    expected = copy.deepcopy(original)
                    expected_layers = expected['puppet']['layers']
                    for name in ('hips', 'pelvis_front'):
                        del expected_layers[name]
                    for name in ('torso', 'torso_front'):
                        if name in expected_layers:
                            expected_layers[name]['image'] = go.GARMENT
                    self.assertEqual(expected, result)
                    layers = result['puppet']['layers']
                    cluster = ['torso', 'head'] + (['torso_front'] if collar else [])
                    order = ['cape', 'arm_far', 'leg_far', 'leg_near'] + cluster
                    order += (['weapon'] if armed else []) + ['arm_near', 'sparkle']
                    self.assertEqual(list(layers), order)
                    for name, row in original['puppet']['layers'].items():
                        self.assertEqual((destination / row['image']).read_bytes(), before[row['image']])
                    recomposed = Image.new('RGBA', (80 * scale, 100 * scale))
                    for row in layers.values():
                        with Image.open(destination / row['image']) as image:
                            recomposed.alpha_composite(image, tuple(row['offset']))
                    np.testing.assert_array_equal(np.array(Image.open(destination / 'source.png')), np.array(recomposed))
                    report = json.loads((destination / 'garment_ownership.json').read_text())
                    self.assertEqual(report['removed_active_layers'], ['hips', 'pelvis_front'])
                    self.assertFalse(report['garment_source_identity_claimed'])
                    self.assertFalse(report['source_rgb_unchanged_claimed'])
                    measured = report['registered_garment']
                    self.assertGreater(measured['source_nontransparent_rgba_pixels_preserved'], 0)
                    self.assertGreater(measured['source_nontransparent_rgba_pixels_changed_or_missing'], 0)
                    self.assertEqual(measured['input_sha256'], hashlib.sha256(garment.read_bytes()).hexdigest())
                    provenance = json.loads((destination / 'provenance.json').read_text())
                    for key in ('bind_approval', 'semantic_verification', 'registration_visual_approval',
                                'motion_contact_approval', 'user_motion_approval'):
                        self.assertEqual(provenance[key], 'pending')
                    self.assertFalse(provenance['final_visual_pass'])
                    self.assertNotIn('derived_pelvic_overlay', provenance)
                    for path in ('bind_report.json', 'visual_report.json', 'collar_overlay.json', 'pelvic_overlay.json',
                                 'input_manifest.json', 'custom_report.json', 'bind_joints.png', 'review/approval.json'):
                        self.assertFalse((destination / path).exists(), path)
                    for path, digest in provenance['runtime_assets'].items():
                        self.assertEqual(hashlib.sha256((destination / path).read_bytes()).hexdigest(), digest)
                        self.assertFalse(path.startswith('history/'))

    def test_explicit_padded_garment_offset_preserves_mesh_and_measures_source_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, garment, original = self.fixture(root)
            old = Image.open(source / 'layers/torso.png')
            expanded = Image.new('RGBA', (24, 36))
            expanded.paste(old, (2, 4))
            expanded.putpixel((0, 30), (200, 100, 40, 255))
            expanded.save(garment)
            self.assert_atomic_failure(root, source, garment)
            destination = root / 'derived'
            self.install(source, destination, garment, garment_offset=[18, 16])
            layers = self.read_spec(destination)['puppet']['layers']
            for name in ('torso', 'torso_front'):
                expected = dict(original['puppet']['layers'][name], image=go.GARMENT, offset=[18, 16])
                self.assertEqual(layers[name], expected)
            report = json.loads((destination / 'garment_ownership.json').read_text())['registered_garment']
            self.assertEqual(report['source_nontransparent_rgba_pixels_changed_or_missing'], 0)
            self.assertEqual(report['source_nontransparent_pixels'], report['source_nontransparent_rgba_pixels_preserved'])

    def test_optional_front_partition_and_backing_share_registration_and_geometry(self):
        for scale in (1, 3):
            with self.subTest(scale=scale), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, garment, original = self.fixture(root, scale)
                front, backing = root / 'front.png', root / 'backing.png'
                Image.new('RGBA', (20 * scale, 30 * scale), (0, 0, 0, 1)).save(front)
                Image.new('RGBA', (20 * scale, 30 * scale), (45, 45, 50, 255)).save(backing)
                self.install(source, root / 'derived', garment, garment_front_image=front, aperture_backing_image=backing)
                layers = self.read_spec(root / 'derived')['puppet']['layers']
                order = list(layers)
                self.assertEqual(order[order.index('garment_backing') + 1], 'leg_far')
                self.assertLess(order.index('arm_far'), order.index('garment_backing'))
                expected = dict(original['puppet']['layers']['torso'], image=go.GARMENT_BACKING)
                self.assertEqual(layers['garment_backing'], expected)
                self.assertEqual(layers['torso_front']['image'], go.GARMENT_FRONT)
                for name, path in (('torso_front', front), ('garment_backing', backing)):
                    np.testing.assert_array_equal(np.array(Image.open(root / 'derived' / layers[name]['image'])),
                                                  np.array(Image.open(path)))
                for name in ('leg_far', 'leg_near'):
                    self.assertEqual(layers[name], original['puppet']['layers'][name])
                report = json.loads((root / 'derived/garment_ownership.json').read_text())
                self.assertEqual(report['torso_front_policy'], 'supplied_registered_partition')
                self.assertEqual(report['added_active_layers'], ['garment_backing'])
                self.assertEqual(report['additional_registered_artwork']['garment_backing']['semantic_visual_approval'], 'pending')

    def completion(self, root, source, original, name='leg_near', expansion=True):
        row = original['puppet']['layers'][name]
        with Image.open(source / row['image']) as image:
            old = image.copy()
        dx, dy = (2, 4) if expansion else (0, 0)
        expanded = Image.new('RGBA', (old.width + dx * 2, old.height + dy))
        expanded.paste(old, (dx, dy))
        expanded.putpixel((0, 0), (40, 50, 60, 255))
        path = root / (name + '_completed.png')
        expanded.save(path)
        return {'image': path, 'offset': [row['offset'][0] - dx, row['offset'][1] - dy]}

    def test_completed_legs_preserve_all_original_nontransparent_rgba_and_allow_padding(self):
        for expansion in (False, True):
            with self.subTest(expansion=expansion), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, garment, original = self.fixture(root)
                inputs = {name: self.completion(root, source, original, name, expansion) for name in ('leg_far', 'leg_near')}
                before = self.snapshot(source)
                self.install(source, root / 'derived', garment, completed_legs=inputs)
                self.assertEqual(before, self.snapshot(source))
                layers = self.read_spec(root / 'derived')['puppet']['layers']
                report = json.loads((root / 'derived/garment_ownership.json').read_text())
                for name in inputs:
                    expected = dict(original['puppet']['layers'][name], image=f'layers/completed_{name}.png', offset=inputs[name]['offset'])
                    self.assertEqual(layers[name], expected)
                    np.testing.assert_array_equal(np.array(Image.open(root / 'derived' / layers[name]['image'])),
                                                  np.array(Image.open(inputs[name]['image'])))
                    self.assertEqual(report['completed_legs'][name]['source_nontransparent_rgba_pixels_changed_or_missing'], 0)
                    self.assertEqual(report['completed_legs'][name]['new_nontransparent_pixels'], 1)
                    self.assertTrue(report['completed_legs'][name]['original_nontransparent_rgba_preserved'])

    def test_completed_leg_changes_clipping_shift_and_wrong_descriptors_are_rejected(self):
        for fault in ('rgb', 'alpha', 'alpha_one', 'shift', 'crop_transparent', 'nonrgba', 'bad_offset', 'missing_offset', 'unknown', 'extra_key'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, garment, original = self.fixture(root)
                descriptor = self.completion(root, source, original, expansion=False)
                inputs = {'leg_near': descriptor}
                with Image.open(descriptor['image']) as image:
                    rgba = np.array(image)
                if fault == 'rgb': rgba[2, 2, 0] += 1
                if fault == 'alpha': rgba[2, 2, 3] = 254
                if fault == 'alpha_one': rgba[1, 2, 3] = 0
                Image.fromarray(rgba).save(descriptor['image'])
                if fault == 'shift': descriptor['offset'][0] -= 1
                if fault == 'crop_transparent': Image.fromarray(rgba[:-1]).save(descriptor['image'])
                if fault == 'nonrgba': Image.fromarray(rgba[..., :3]).save(descriptor['image'])
                if fault == 'bad_offset': descriptor['offset'] = [float('nan'), 48]
                if fault == 'missing_offset': del descriptor['offset']
                if fault == 'unknown': inputs = {'head': descriptor}
                if fault == 'extra_key': descriptor['trust_me'] = True
                self.assert_atomic_failure(root, source, garment, completed_legs=inputs)

    def test_malformed_and_nonfinite_offsets_are_rejected_before_writes(self):
        bad = (None, [], [1], [1, 2, 3], '1,2', [True, 2], [1.0, 2], [0.5, 2], [float('nan'), 2], [float('inf'), 2], ['1', 2])
        for value in bad:
            for target in ('layer', 'garment', 'completion'):
                if target == 'garment' and value is None:
                    continue  # None is the documented exact-size default.
                with self.subTest(value=value, target=target), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    source, garment, original = self.fixture(root)
                    kwargs = {}
                    if target == 'layer':
                        original['puppet']['layers']['head']['offset'] = value
                        self.save_spec(source, original)
                    elif target == 'garment':
                        kwargs['garment_offset'] = value
                    else:
                        descriptor = self.completion(root, source, original)
                        descriptor['offset'] = value
                        kwargs['completed_legs'] = {'leg_near': descriptor}
                    self.assert_atomic_failure(root, source, garment, **kwargs)

    def test_rgba_size_ownership_empty_and_registration_errors_are_atomic(self):
        for fault in ('size', 'garment_rgb', 'garment_empty', 'source_rgb', 'layer_rgb', 'ownership', 'negative',
                      'clip', 'layer_clip', 'front_geometry', 'front_size', 'front_offset', 'wrong_source', 'missing_image'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, garment, original = self.fixture(root)
                kwargs = {}
                if fault == 'size': Image.new('RGBA', (19, 30), (1, 2, 3, 255)).save(garment)
                if fault == 'garment_rgb': Image.new('RGB', (20, 30)).save(garment)
                if fault == 'garment_empty': Image.new('RGBA', (20, 30)).save(garment)
                if fault == 'source_rgb': Image.new('RGB', (80, 100)).save(source / 'source.png')
                if fault == 'layer_rgb': Image.new('RGB', (5, 7)).save(source / 'layers/cape.png')
                if fault == 'ownership': kwargs['ownership'] = 'automatic'
                if fault == 'negative': kwargs['garment_offset'] = [-1, 20]
                if fault == 'clip': kwargs['garment_offset'] = [70, 90]
                if fault == 'layer_clip': original['puppet']['layers']['cape']['offset'] = [79, 99]
                if fault == 'front_geometry': original['puppet']['layers']['torso_front']['radius'] = 123
                if fault == 'front_size': Image.new('RGBA', (10, 20)).save(source / 'layers/torso_front.png')
                if fault == 'front_offset': original['puppet']['layers']['torso_front']['offset'][0] += 1
                if fault == 'wrong_source': original['puppet']['source'] = 'reference.png'
                if fault == 'missing_image': original['puppet']['layers']['head']['image'] = 'missing.png'
                self.save_spec(source, original)
                self.assert_atomic_failure(root, source, garment, **kwargs)

    def test_optional_art_rejects_wrong_dimensions_mode_empty_or_missing_front_owner(self):
        for kind in ('front', 'backing'):
            for fault in ('size', 'mode', 'empty', 'missing_owner'):
                if kind == 'backing' and fault == 'missing_owner':
                    continue
                with self.subTest(kind=kind, fault=fault), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    source, garment, _ = self.fixture(root, collar=fault != 'missing_owner')
                    path = root / 'extra.png'
                    Image.new('RGB' if fault == 'mode' else 'RGBA', (10, 30) if fault == 'size' else (20, 30),
                              (0, 0, 0) if fault == 'mode' else (5, 10, 15, 0 if fault == 'empty' else 255)).save(path)
                    kwargs = {'garment_front_image' if kind == 'front' else 'aperture_backing_image': path}
                    self.assert_atomic_failure(root, source, garment, **kwargs)

    def test_bad_order_unknown_interleaving_and_missing_layers_are_rejected(self):
        for fault in ('head_before_torso', 'late_arm_far', 'split_legs', 'late_front', 'missing_head',
                      'unknown_cluster', 'unknown_legs', 'unknown_front', 'reserved_backing'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, garment, original = self.fixture(root)
                layers = original['puppet']['layers']
                names = list(layers)
                if fault == 'head_before_torso':
                    a, b = names.index('head'), names.index('torso')
                    names[a], names[b] = names[b], names[a]
                if fault == 'late_arm_far': names.remove('arm_far'); names.append('arm_far')
                if fault == 'split_legs': names.remove('leg_near'); names.insert(names.index('torso'), 'leg_near')
                if fault == 'late_front': names.remove('torso_front'); names.append('torso_front')
                if fault == 'missing_head': names.remove('head')
                if fault.startswith('unknown_'):
                    names.remove('sparkle')
                    target = {'unknown_cluster': 'head', 'unknown_legs': 'leg_near', 'unknown_front': 'arm_near'}[fault]
                    names.insert(names.index(target), 'sparkle')
                if fault == 'reserved_backing':
                    layers['garment_backing'] = copy.deepcopy(layers['torso'])
                    names.append('garment_backing')
                original['puppet']['layers'] = {name: layers[name] for name in names}
                self.save_spec(source, original)
                self.assert_atomic_failure(root, source, garment)

    def test_unsafe_asset_paths_symlinks_and_reserved_collisions_are_rejected(self):
        for fault in ('absolute', 'parent', 'nested_parent', 'backslash', 'empty', 'reserved_source',
                      'reserved_history', 'file_link', 'directory_link', 'derived_collision', 'history_collision'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, garment, original = self.fixture(root)
                path = {'absolute': str(garment), 'parent': '../garment.png', 'nested_parent': 'layers/../layers/head.png',
                        'backslash': 'layers\\head.png', 'empty': '', 'reserved_source': 'source.png',
                        'reserved_history': 'history/head.png'}.get(fault)
                if path is not None: original['puppet']['layers']['head']['image'] = path
                if fault == 'reserved_history':
                    (source / 'history').mkdir()
                    (source / 'history/head.png').write_bytes(garment.read_bytes())
                if fault == 'file_link': (source / 'link.png').symlink_to(garment)
                if fault == 'directory_link': (source / 'linked').symlink_to(root, target_is_directory=True)
                if fault == 'derived_collision': (source / go.GARMENT).write_bytes(garment.read_bytes())
                if fault == 'history_collision':
                    (source / go.HISTORY).mkdir(parents=True)
                    (source / go.HISTORY / 'old.txt').write_text('retain')
                self.save_spec(source, original)
                # Snapshot helper deliberately does not follow a directory loop.
                self.assert_atomic_failure(root, source, garment)

    def test_existing_and_overlapping_destinations_are_never_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, garment, _ = self.fixture(root)
            existing = root / 'existing'
            existing.mkdir()
            (existing / 'sentinel').write_text('retain')
            broken = root / 'broken'
            broken.symlink_to(root / 'missing')
            before = self.snapshot(root)
            for destination in (source, source / 'nested', root, existing, broken):
                with self.subTest(destination=destination), self.assertRaises(ValueError):
                    self.install(source, destination, garment)
            self.assertEqual(before, self.snapshot(root))
            self.assertTrue(broken.is_symlink())

    def test_duplicate_keys_are_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, garment, _ = self.fixture(root)
            text = (source / 'character.json').read_text()
            (source / 'character.json').write_text(text.replace('"name": "synthetic"', '"name": "synthetic", "name": "other"'))
            self.assert_atomic_failure(root, source, garment)

    def test_failed_writes_leave_no_partial_destination_or_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, garment, _ = self.fixture(root)
            before = self.snapshot(root)
            write = Path.write_bytes
            count = 0
            def fail(path, data):
                nonlocal count
                count += 1
                if count == 4:
                    raise OSError('injected disk failure')
                return write(path, data)
            with mock.patch.object(Path, 'write_bytes', fail), self.assertRaisesRegex(OSError, 'disk failure'):
                self.install(source, root / 'derived', garment)
            self.assertEqual(before, self.snapshot(root))
            self.assertFalse((root / 'derived').exists())
            self.assertFalse(list(root.glob('.garment-ownership-*')))

    def test_atomic_publication_refuses_destination_created_during_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, garment, _ = self.fixture(root)
            before = self.snapshot(source)
            publish = go._atomic_publisher()
            def race(staging, destination):
                destination.mkdir()  # POSIX rename alone would replace this empty directory.
                publish(staging, destination)
            with mock.patch.object(go, '_atomic_publisher', return_value=race), self.assertRaises(FileExistsError):
                self.install(source, root / 'derived', garment)
            self.assertTrue((root / 'derived').is_dir())
            self.assertEqual(list((root / 'derived').iterdir()), [])
            self.assertEqual(before, self.snapshot(source))
            self.assertFalse(list(root.glob('.garment-ownership-*')))


if __name__ == '__main__':
    unittest.main()
