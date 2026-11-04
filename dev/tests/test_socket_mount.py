"""Explicit socket geometry checks; synthetic approval is not visual approval."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'game-sprite-animator/scripts'))
from socket_mount import validate_socket, place_socket


def fixture(scale=1):
    h = np.zeros((160, 160), bool); t = h.copy()
    h[10:70, 50:110] = True; h[60:91, 72:88] = True
    t[75:140, 60:100] = True
    # neck_core row 76, core center 79.5
    return np.repeat(np.repeat(h, scale, 0), scale, 1), np.repeat(np.repeat(t, scale, 0), scale, 1)


class SocketMount(unittest.TestCase):
    def test_visible_rim_and_nested_stem_at_two_scales(self):
        for scale in (1, 2):
            h, t = fixture(scale)
            from layer_parts import neck_core, Rejected
            row, cols, _ = neck_core(t)
            report = validate_socket(h, t, (cols.mean(), row))
            self.assertEqual(report['stem_coverage'], 1.)
            self.assertTrue((t[row] & ~h[row]).any())

    def test_floating_stem_is_rejected(self):
        h, t = fixture(); t[76:92] = False
        with self.assertRaisesRegex(ValueError, 'socket:'):
            validate_socket(h, t, (79.5, 76))

    def test_side_slip_is_rejected(self):
        h, t = fixture(); h = np.roll(h, 20, axis=1)
        with self.assertRaisesRegex(ValueError, 'offset|support'):
            validate_socket(h, t, (79.5, 76))

    def test_contact_gap_is_rejected(self):
        h, t = fixture(); t[84] = False
        with self.assertRaisesRegex(ValueError, 'support|gap'):
            validate_socket(h, t, (79.5, 76))

    def test_diagonal_only_stem_connection_is_rejected(self):
        h, t = fixture()
        h[76:91] = False
        h[76:84, 72:80] = True
        h[84:91, 80:88] = True
        from sprite_anim.integrity import components
        labels = components(h[76:])
        self.assertEqual(len(np.unique(labels[labels > 0])), 1)
        with self.assertRaisesRegex(ValueError, 'disconnected'):
            validate_socket(h, t, (79.5, 76))

    def test_broad_head_is_not_a_stem(self):
        h, t = fixture(); h[70:91, 50:110] = True
        with self.assertRaisesRegex(ValueError, 'not narrow'):
            validate_socket(h, t, (79.5, 76))

    def test_deep_burial_is_rejected(self):
        h, t = fixture(); h[90:120, 72:88] = True
        with self.assertRaisesRegex(ValueError, 'depth'):
            validate_socket(h, t, (79.5, 76))

    def test_thin_full_gap_cannot_hide_in_total_coverage(self):
        h = np.zeros((4100, 160), bool); t = h.copy()
        h[10:3000, 50:110] = True; h[2900:3600, 72:88] = True
        t[3100:4000, 60:100] = True
        from layer_parts import neck_core, Rejected
        row, cols, _ = neck_core(t)
        t[3400] = False
        self.assertGreater((h[row:] & t[row:]).sum() / h[row:].sum(), .995)
        with self.assertRaisesRegex(ValueError, 'contact gap'):
            validate_socket(h, t, (cols.mean(), row))

    def test_missing_art_and_nonfinite_scale_rejected(self):
        h, t = fixture()
        for head, scale in ((np.zeros_like(h), 1.), (h, float('nan'))):
            with self.assertRaisesRegex(ValueError, 'socket:'):
                place_socket(head, t, scale, 1., (0., 0.), (160, 160))

    def test_manifest_opt_in_rechecks_socket_and_default_stays_strict(self):
        import json
        from unittest.mock import patch
        from PIL import Image
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import template_full_character as full
        import template_puppet as tp
        import test_template_full_character as fixtures
        import bind_known_joints as entry
        from layer_parts import neck_core, Rejected
        import socket_mount
        stage = fixtures.FullTemplate.complete_fixture(self, next(iter(tp.PROFILES)))
        full.inspect(stage)
        report = tp.read(stage / 'assembly_report.json')
        order = [n for n in full.ORDER if n != 'weapon']
        layers = {n: 'assembled_layers/' + n + '.png' for n in order}
        torso = np.asarray(Image.open(stage / layers['torso']))[..., 3] > 128
        row, cols, _ = neck_core(torso)
        cx = int(round(cols.mean()))
        # A simple head with a narrow terminal stem in the existing torso seat.
        head = np.zeros((*torso.shape, 4), np.uint8)
        half = max(25, len(cols))
        head[row - 160:row - 20, cx - half:cx + half] = (90, 110, 130, 255)
        stem_half = max(3, len(cols) // 5)
        head[row - 30:row + 16, cx - stem_half:cx + stem_half] = (90, 110, 130, 255)
        Image.fromarray(head).save(stage / layers['head'])
        joints = report['joints']; joints['head']['head_base'] = [float(cols.mean()), float(row)]
        job = dict(name='Synthetic socket', layers=layers, order=order, joints=joints)
        manifest = stage / 'socket-input.json'
        tp.write(manifest, job)
        with self.assertRaisesRegex(Rejected, 'neck|head'):
            entry.bind(manifest, stage / 'default-rejected')
        self.assertFalse((stage / 'default-rejected').exists())
        job['head_attachment'] = 'not-a-mode'; tp.write(manifest, job)
        with self.assertRaisesRegex(ValueError, 'head_attachment'):
            entry.bind(manifest, stage / 'unknown-rejected')
        job['head_attachment'] = 'socket'; tp.write(manifest, job)
        with patch.object(socket_mount, 'validate_socket', wraps=socket_mount.validate_socket) as checked:
            entry.bind(manifest, stage / 'socket-rig')
            checked.assert_called_once()
        spec = json.loads((stage / 'socket-rig/character.json').read_text())
        self.assertEqual(spec['puppet']['head_attachment'], 'socket')
        head[row + 8, :, 3] = 0
        Image.fromarray(head).save(stage / layers['head'])
        with self.assertRaisesRegex(ValueError, 'socket:'):
            entry.bind(manifest, stage / 'damaged-rejected')
        self.assertFalse((stage / 'damaged-rejected').exists())

    def test_placement_keeps_scale_and_inputs(self):
        h, t = fixture(); h = h[10:91, 50:110]; t = t[75:140, 60:100]
        hb, tb = h.copy(), t.copy()
        anchor, offset, report = place_socket(h, t, 1., 1., (60., 75.), (160, 160))
        self.assertEqual(report['head_scale_unchanged'], 1.)
        np.testing.assert_array_equal(h, hb); np.testing.assert_array_equal(t, tb)


if __name__ == '__main__':
    unittest.main()
