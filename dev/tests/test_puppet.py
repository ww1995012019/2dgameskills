"""Layered puppets: the contract's gates and the checks for what cut-up art gets wrong. Every check is
shown catching a planted fault, and two figures of different build go through the same code."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "game-sprite-animator/scripts"))

import layer_parts as lp  # noqa: E402
from sprite_anim import puppet, puppet_check as pc  # noqa: E402
from sprite_anim.cloth import ChainDef, simulate, turn_to  # noqa: E402
from sprite_anim.art import Canvas  # noqa: E402
from sprite_anim.motions import CH, STANCE_REACH, build_clips, face_gap, stance_reach  # noqa: E402
from sprite_anim.render import GROUND_FRAC, Renderer, frame_time, to_u8  # noqa: E402
from sprite_anim.rig import Body, full_pose, solve  # noqa: E402

KEY = lp.KEY_COLOR
SIZE = (1024, 1536)


def canvas():
    return Image.new("RGB", SIZE, KEY)


def inked(d, shape, xy, fill):
    getattr(d, shape)(xy, fill=fill, outline=(15, 15, 20), width=6)


def limb(d, a, b, width, fill):
    d.line([a, b], fill=(15, 15, 20), width=width + 12)
    d.line([a, b], fill=fill, width=width)
    for t in np.linspace(0.1, 0.9, 7):        # drawn detail, so the art isn't flat
        x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        d.line([(x - width / 3, y), (x + width / 3, y)], fill=(90, 70, 50), width=3)


def figure(hip=(470, 880), leg=420, chest=(120, 300), stride=90, head=120, width=64):
    """Layers for a plain side-view figure. Build changes with the arguments."""
    layers = {n: canvas() for n in ("arm_far", "leg_far", "leg_near", "hips", "torso", "head", "arm_near")}
    hx, hy = hip
    for name, sign in (("leg_near", 1), ("leg_far", -1)):
        d = ImageDraw.Draw(layers[name])
        foot = (hx + sign * stride, hy + leg + 60)
        knee = (hx + sign * stride // 2 + 12, hy + leg // 2)
        limb(d, (hx + sign * 8, hy), knee, width, (60, 60, 90))
        limb(d, knee, (foot[0], foot[1] - 60), width - 8, (70, 50, 40))
        inked(d, "rectangle", (foot[0] - 44, foot[1] - 64, foot[0] + 92, foot[1]), (90, 60, 40))
    neck = (hx, hy - chest[1])
    inked(ImageDraw.Draw(layers["hips"]), "rectangle", (hx - chest[0] // 2 + 6, hy - chest[1] // 2, hx + chest[0] // 2 - 6, hy + 28), (60, 60, 90))
    d = ImageDraw.Draw(layers["torso"])
    inked(d, "polygon", [(hx - chest[0] // 2, hy + 30), (hx + chest[0] // 2, hy + 30), (neck[0] + chest[0] // 2, neck[1]), (neck[0] - chest[0] // 2, neck[1])], (170, 40, 40))
    for y in range(neck[1] + 30, hy, 45):
        d.line([(hx - 40, y), (hx + 40, y)], fill=(230, 190, 60), width=6)
    d = ImageDraw.Draw(layers["head"])
    inked(d, "ellipse", (hx - head, neck[1] - 2 * head, hx + head, neck[1]), (235, 190, 150))
    inked(d, "ellipse", (hx + head // 3, neck[1] - head - 20, hx + head // 3 + 30, neck[1] - head + 10), (20, 20, 30))
    for name, tip, shoulder in (("arm_near", (hx + 250, hy - 60), hx + 20), ("arm_far", (hx - 230, hy - 40), hx - 20)):
        d = ImageDraw.Draw(layers[name])
        sh = (shoulder, neck[1] + 40)
        el = ((sh[0] + tip[0]) // 2, (sh[1] + tip[1]) // 2 + 14)
        limb(d, sh, el, width - 16, (225, 225, 215))
        limb(d, el, tip, width - 22, (50, 40, 40))
        inked(d, "ellipse", (tip[0] - 34, tip[1] - 34, tip[0] + 34, tip[1] + 34), (235, 190, 150))
        for k in range(-20, 30, 13):        # fingers, the drawing a blurred hand loses
            d.line([(tip[0] + k, tip[1] - 26), (tip[0] + k, tip[1] + 26)], fill=(120, 70, 50), width=4)
    return layers


def keyed(im):
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "l.png")
        im.save(p)
        return lp.key_out(p)


def reference_of(layers):
    """The layers drawn together, as the picture they were cut from."""
    out = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    for n in ("arm_far", "leg_far", "leg_near", "hips", "torso", "head", "arm_near"):
        out.alpha_composite(Image.fromarray(keyed(layers[n]), "RGBA"))
    return np.asarray(out).copy()


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layers = figure()
        cls.ref = reference_of(cls.layers)
        cls.keyed = {k: keyed(v) for k, v in cls.layers.items()}

    def test_missing_layer_is_refused_by_name(self):
        partial = {k: v for k, v in self.keyed.items() if k != "arm_far"}
        with self.assertRaisesRegex(lp.Rejected, "arm_far"):
            lp.bind(self.ref, partial)

    def test_one_limb_in_both_layers_is_refused(self):
        same = dict(self.keyed, arm_near=self.keyed["arm_far"])
        with self.assertRaisesRegex(lp.Rejected, "same limb"):
            lp.bind(self.ref, same)

    def test_art_in_no_layer_is_refused(self):
        ref = self.ref.copy()
        ref[300:900, 60:300] = (10, 200, 10, 255)     # a big cape no layer holds
        with self.assertRaisesRegex(lp.Rejected, "cover only"):
            lp.bind(ref, self.keyed)

    def test_a_changed_layer_is_refused(self):
        repainted = self.keyed["torso"].copy()
        on = repainted[..., 3] > 128
        repainted[on, :3] = (30, 200, 255)
        with self.assertRaisesRegex(lp.Rejected, "torso"):
            lp.bind(self.ref, dict(self.keyed, torso=repainted))

    def test_a_see_through_waist_is_refused(self):
        split = self.keyed["torso"].copy()
        split[640:920, 440:500, 3] = 0             # a robe open at the front, as a model draws one
        hips = self.keyed["hips"].copy()
        hips[..., 3] = 0                           # and nothing behind it
        hips[880:910, 400:540, 3] = 255
        open_ref = self.ref.copy()
        open_ref[640:920, 440:500, 3] = 0          # the reference shows the same gap, so no art is missing
        with self.assertRaisesRegex(lp.Rejected, "hips: .* see-through"):
            lp.bind(open_ref, dict(self.keyed, torso=split, hips=hips))

    def test_an_oversized_hidden_layer_is_cut_to_the_body(self):
        big = np.zeros((*self.ref.shape[:2], 4), np.uint8)
        big[500:1200, 200:800] = (60, 60, 90, 255)           # far wider and longer than any body
        waist, hip = np.array((470.0, 700.0)), np.array((470.0, 880.0))
        cut = lp.trimmed(big, waist, hip, 50.0)
        self.assertEqual(cut[790, 470, 3], 255)              # the middle stays solid
        self.assertEqual(cut[790, 300, 3], 0)                # no block past the sides
        self.assertEqual(cut[900, 470, 3], 0)                # or below the hip
        self.assertTrue(0 < cut[870, 470, 3] < 255)          # the lower end fades, so it leaves no hem

    def test_reference_rules(self):
        small = Image.fromarray(self.ref, "RGBA").resize((512, 768))
        cropped = self.ref.copy()
        cropped[-1, 500] = (10, 10, 10, 255)
        with tempfile.TemporaryDirectory() as tmp:
            for pic, why in ((small, "generate it larger"), (Image.fromarray(cropped, "RGBA"), "edge")):
                path = os.path.join(tmp, "r.png")
                pic.save(path)
                with self.assertRaisesRegex(lp.Rejected, why):
                    lp.reference(path)


class TwoBuilds(unittest.TestCase):
    """The same call on different proportions, with nothing set per character."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.rigs = {}
        builds = dict(tall=dict(), short=dict(hip=(480, 960), leg=300, chest=(170, 240), head=210, stride=70, width=84))
        for name, kw in builds.items():
            layers = figure(**kw)
            ref = reference_of(layers)
            out, spec, report = lp.bind(ref, {k: keyed(v) for k, v in layers.items()})
            folder = os.path.join(cls.tmp, name)
            os.makedirs(os.path.join(folder, "layers"))
            for layer, arr in out.items():
                box = Image.fromarray(arr[..., 3]).getbbox()
                Image.fromarray(arr, "RGBA").crop(box).save(os.path.join(folder, "layers", layer + ".png"))
                spec["puppet"]["layers"][layer].update(image=f"layers/{layer}.png", offset=[box[0], box[1]])
            Image.fromarray(ref, "RGBA").save(os.path.join(folder, "source.png"))
            spec.update(name=name, weapon="none", cloth=[], style={"speed": 1.0, "bounce": 0.8}, _dir=folder)
            cls.rigs[name] = (spec, report)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def renderer(self, spec):
        clips = build_clips(spec.get("style"), gait=spec["gait"])
        return Renderer(spec, 256, clips={"walk": clips["walk"]}), clips["walk"]

    def test_both_builds_walk_clean(self):
        for name, (spec, report) in self.rigs.items():
            with self.subTest(name):
                self.assertGreater(report["cover"], lp.MIN_COVER)
                r, clip = self.renderer(spec)
                self.assertEqual(pc.check_layers(r.art.puppet), [])
                self.assertEqual(pc.check_motion(r, clip, 8, 15), [])

    def test_the_legs_set_the_stride(self):
        tall, short = (self.rigs[n][0]["gait"]["walk"]["stride"] for n in ("tall", "short"))
        self.assertAlmostEqual(tall, short, delta=1.0)     # legs are the rig's unit, so the stride is too

    def test_fold_is_caught_and_located(self):
        spec = self.rigs["tall"][0]
        r, clip = self.renderer(spec)
        real = r.art.puppet.meshes

        def flipped(cv, sk, cloth, ground_contact=False):
            for layer, verts in real(cv, sk, cloth, ground_contact):
                if layer.name == "leg_near":
                    verts = verts.copy()
                    j, i = layer.cells[len(layer.cells) // 2]
                    verts[j - 2:j + 3, i - 2:i + 3] = verts[j - 2:j + 3, i - 2:i + 3][::-1]
                yield layer, verts
        with mock.patch.object(r.art.puppet, "meshes", flipped):
            found = pc.check_motion(r, clip, 3, 15)
        self.assertTrue(any(f.startswith("fold: leg_near: walk frame ") for f in found), found)

    def test_kink_is_caught_and_located(self):
        spec = self.rigs["tall"][0]
        r, clip = self.renderer(spec)
        zigzag = np.array([[0, 0], [10, 0], [10, 10], [20, 10], [20, 20]], float)
        with mock.patch.object(r, "cloth_at", lambda c, t: {"cape": zigzag}):
            found = pc.check_motion(r, clip, 2, 15)
        self.assertTrue(any(f.startswith("kink: cape: walk frame 0") for f in found), found)

    def test_crouch_is_caught(self):
        spec = dict(self.rigs["tall"][0])
        spec["body"] = dict(spec["body"], hip_h=spec["body"]["hip_h"] - 6)
        r, clip = self.renderer(spec)
        found = pc.check_motion(r, clip, 8, 15)
        self.assertTrue(any(f.startswith("crouch: walk") for f in found), found)

    def test_hole_below_the_belt_is_caught_and_located(self):
        spec = self.rigs["tall"][0]
        r, clip = self.renderer(spec)
        frames = [to_u8(r.render(clip, frame_time(clip, i, 4, 8))) for i in range(4)]
        self.assertEqual(pc.check_core(r, clip, frames, 8), [])
        cv = Canvas(r.size, 1, r.unit, GROUND_FRAC, 1, False, (0, 0, 0))
        sk = solve(full_pose(clip.sample(frame_time(clip, 2, 4, 8))), r.art.body)
        core = pc.core_mask((r.size, r.size), cv.T(sk["waist"]), cv.T(sk["hip"]), r.art.puppet.core_radius * r.unit)
        holed = [f.copy() for f in frames]
        holed[2][core] = 0
        found = pc.check_core(r, clip, holed, 8)
        self.assertTrue(found and found[0].startswith("hole: walk frame 2"), found)

    def test_a_deliberate_crouch_is_not_a_fault(self):
        spec = self.rigs["tall"][0]
        clips = build_clips(spec.get("style"), gait=spec["gait"])
        r = Renderer(spec, 256, clips={"crouch_walk": clips["crouch_walk"]})
        found = pc.check_motion(r, clips["crouch_walk"], 8, 15)
        self.assertFalse(any(f.startswith("crouch:") for f in found), found)

    def test_blurred_hand_is_caught(self):
        spec = self.rigs["tall"][0]
        r, clip = self.renderer(spec)
        frames = [to_u8(r.render(clip, frame_time(clip, i, 4, 8))) for i in range(4)]
        self.assertEqual(pc.check_hands(r, spec, clip, frames, 8), [])
        soft = [np.asarray(Image.fromarray(f, "RGBA").filter(ImageFilter.GaussianBlur(3))) for f in frames]
        found = pc.check_hands(r, spec, clip, soft, 8)
        self.assertTrue(found and found[0].startswith("hand:"), found)


class FittedClips(unittest.TestCase):
    """Rules that fit the full clip set to a character's own proportions."""

    def test_body_rules_keep_default_clips_unchanged(self):
        plain, fitted = build_clips(), build_clips(body=Body())
        for name in ("idle", "idle_look", "roll", "attack_3"):
            with self.subTest(name):
                self.assertEqual(plain[name].sample(0.2)["root_y"], fitted[name].sample(0.2)["root_y"])

    def test_a_long_weapon_on_short_arms_leaves_the_face_clear(self):
        body = Body(up_arm=10.9, lo_arm=10.9, head_size=1.1, weapon_front=38.0, weapon_back=19.0)
        before = build_clips()["attack_3"]
        after = build_clips(body=body)["attack_3"]
        keys = lambda clip: [dict(zip(CH, row.tolist())) for row in clip.curve.v]
        self.assertLess(min(face_gap(p, body) for p in keys(before)), 0)     # the fault is real
        self.assertGreaterEqual(min(face_gap(p, body) for p in keys(after)), 0)

    def test_shared_poses_stay_shared(self):
        body = Body(up_arm=10.9, lo_arm=10.9, head_size=1.1, weapon_front=38.0, weapon_back=19.0)
        clips = build_clips(body=body)
        for channel in ("arm_n_up", "wep"):
            self.assertEqual(clips["attack_2"].curve.v[-3][CH.index(channel)], clips["attack_3"].curve.v[0][CH.index(channel)])

    def test_a_long_leg_stands_short_of_locked_knees(self):
        body = Body(thigh=19.5, shin=19.5, hip_h=43.3, leg_soft=0.975)
        start = build_clips(body=body)["idle"].sample(0.0)
        self.assertLessEqual(stance_reach(dict(start, root_y=start["root_y"] + 0.8), body), STANCE_REACH + 0.002)

    def test_spinning_feet_turn_the_short_way(self):
        pose = dict(build_clips()["roll"].sample(0.0), root_rot=330.0, ik_body=0.7)
        off = abs(solve(full_pose(pose), Body())["fr_n"])
        on = abs(solve(full_pose(pose), Body(foot_wrap=True))["fr_n"])
        self.assertGreater(off, 150)
        self.assertLess(on, 60)


class Chains(unittest.TestCase):
    def spin(self):
        return build_clips()["roll"]

    def chain(self, swing):
        return ChainDef("tail", ("hip", "body_rot", (-4.0, 6.0)), 7, 7.0, rest=(-0.7, -0.7), follow=1.0, stiff=0.05,
                        rest_frame="body_rot", ground=False, max_bend=34.0, max_curl=75.0, swing=swing)

    def worst_turn(self, pos):
        d = np.diff(pos, axis=1)
        return float(np.degrees(np.abs(np.arctan2(d[:, :-1, 0] * d[:, 1:, 1] - d[:, :-1, 1] * d[:, 1:, 0], (d[:, :-1] * d[:, 1:]).sum(2)))).max())

    def test_a_chain_stays_behind_a_flipping_body(self):
        off_rest = lambda bake: float(np.abs(bake.pos[:, -1] - bake.pos[:, 0]).max())
        free = simulate(self.chain(None), self.spin(), Body())
        fan = simulate(self.chain((-50.0, 50.0)), self.spin(), Body())
        self.assertLessEqual(self.worst_turn(fan.pos), 34.5)
        self.assertLess(off_rest(fan), off_rest(free) + 7.0)

    def test_turning_toward_a_far_shape_keeps_the_chain_whole(self):
        shape = np.stack([np.arange(7.0) * 7, np.zeros(7)], 1)
        target = np.stack([-np.arange(7.0) * 7, np.zeros(7)], 1)      # the other way round
        half = turn_to(shape, target + 0.01 * np.arange(7)[:, None], 0.5, 7.0)
        self.assertAlmostEqual(float(np.hypot(*np.diff(half, axis=0).T).min()), 7.0, places=6)
        faded = shape * 0.5 + target * 0.5
        self.assertLess(float(np.hypot(*np.diff(faded, axis=0).T).min()), 0.1)      # what points would do


class Mesh(unittest.TestCase):
    def test_a_crossed_mesh_is_relaxed_and_a_clean_one_is_left_alone(self):
        vy, vx = np.mgrid[0:9, 0:9].astype(float) * 14
        clean = np.stack([vx, vy], -1)
        cells = np.argwhere(np.ones((8, 8), bool))
        self.assertIs(puppet.flipped(clean, cells).any(), np.False_)
        self.assertTrue((puppet.untangle(clean, cells) == clean).all())
        crossed = clean.copy()
        crossed[4, 4] += (24, 24)
        self.assertTrue(puppet.flipped(crossed, cells).any())
        self.assertFalse(puppet.flipped(puppet.untangle(crossed, cells), cells).any())

    def test_fold_counts_area_not_crushed_cells(self):
        vy, vx = np.mgrid[0:9, 0:9].astype(float) * 14
        mesh = np.stack([vx, vy], -1)
        cells = np.argwhere(np.ones((8, 8), bool))
        mesh[4, 4] += (0.0, 13.99)
        crushed = mesh.copy()
        crushed[4, 5] = crushed[4, 4] + (0.01, 0.0)
        crushed[4, 5, 0] -= 0.02                       # a cell with nothing left of it, wound backwards
        self.assertLess(pc.inverted(crushed, cells), pc.FOLD_SHARE)

    def test_a_tight_corner_gets_a_longer_arc(self):
        a, b = np.array((0.0, 0.0)), np.array((100.0, 0.0))
        self.assertAlmostEqual(puppet.corner_run(a, b, np.array((130.0, 40.0)), 20.0, 0.68), 20.0)     # a gentle bend
        self.assertGreater(puppet.corner_run(a, b, np.array((40.0, 40.0)), 20.0, 0.68), 40.0)


class Smear(unittest.TestCase):
    def test_a_blurred_patch_is_caught_and_drawn_art_is_not(self):
        layers = figure()
        sharp = Image.fromarray(keyed(layers["torso"]), "RGBA").crop((360, 500, 600, 880))
        self.assertEqual(pc.smear_tiles(sharp)[0], 0)
        bad, filled = pc.smear_tiles(sharp.filter(ImageFilter.GaussianBlur(5)))
        self.assertGreater(bad / filled, pc.SMEAR_SHARE)

    @unittest.expectedFailure
    def test_a_patch_blurred_to_one_flat_colour(self):
        # Known gap: blur strong enough to wash out all contrast leaves a plain tile, and a plain tile
        # is what undyed cloth looks like too, so only a person looking at the layer can tell.
        layers = figure()
        sharp = Image.fromarray(keyed(layers["torso"]), "RGBA").crop((360, 500, 600, 880))
        bad, filled = pc.smear_tiles(sharp.filter(ImageFilter.GaussianBlur(14)))
        self.assertGreater(bad / filled, pc.SMEAR_SHARE)


class Key(unittest.TestCase):
    def test_background_goes_and_edge_keeps_no_magenta(self):
        im = canvas()
        ImageDraw.Draw(im).ellipse((300, 300, 700, 700), fill=(200, 200, 200))
        a = keyed(im.filter(ImageFilter.GaussianBlur(1.5)))
        self.assertEqual(a[10, 10, 3], 0)
        self.assertEqual(a[500, 500, 3], 255)
        edge = a[(a[..., 3] > 40) & (a[..., 3] < 215)]
        self.assertGreater(len(edge), 0)
        self.assertLess(np.abs(edge[:, 0].astype(int) - edge[:, 1]).mean(), 45)     # grey, not pink


if __name__ == "__main__":
    unittest.main()
