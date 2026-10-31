"""Soldier art: gear, heads and guns on top of the shared limb and canvas code."""
import math
import random

from .art import CharacterArt, blob, capsule
from .mathx import add, catmull_closed, rot, scale
from .weapons import GUN_SCALE, WEAPONS


def _splash(pts, x0, floor=0.8):
    """A blast fired into the floor spreads along it instead of passing through: points below the
    floor land on it, pushed away from the source by the depth they had to lose."""
    out = []
    for x, y in pts:
        if y < floor:
            x += (floor - y) * (1.0 if x >= x0 else -1.0)
            y = floor
        out.append((x, y))
    return out


class SoldierArt(CharacterArt):
    def __init__(self, spec):
        super().__init__(spec)
        # Free-arm clips all carry the primary weapon; aimed clips are held up by IK.
        w = WEAPONS[self.spec["weapons"][0]]
        self.body.weapon_front = w["muzzle"][0] * GUN_SCALE
        self.body.weapon_back = -w["butt"] * GUN_SCALE
        self.body.weapon_margin = 2.8 + w["muzzle"][1] * GUN_SCALE     # the barrel sits above the grip

    def blade_points(self, sk):
        """Melee smear path: the gun's butt-to-muzzle span."""
        w = WEAPONS[self.active]
        return sk["wr_n"], add(sk["wr_n"], scale(sk["wep_dir"], w["muzzle"][0] * GUN_SCALE))

    @property
    def primary(self):
        return self.spec["weapons"][0]

    def extent_points(self, sk, pose):
        """Every point that must stay inside the frame on this pose, muzzle flash included."""
        pts = [sk[j] for j in ("wr_n", "wr_f", "an_n", "an_f", "kn_n", "kn_f", "hip", "neck", "head_base")]
        pts.append(add(sk["head_base"], rot((0, 36 * self.body.head_size), sk["head_rot"])))
        span = self.weapon_span(sk)
        pts += [span[0], span[1]]
        w = WEAPONS[self.active]
        if pose["flash"] > 0.02:
            pts.append(add(span[1], scale(sk["wep_dir"], 13 * w["flash"] * 1.7)))
            if w["kind"] == "rocket":
                pts.append(add(span[0], scale(sk["wep_dir"], -13 * w["flash"] * 1.5)))
        return pts

    def weapon_span(self, sk):
        """Gun as (butt, muzzle, radius) for clipping checks."""
        w = WEAPONS[self.active]
        return self.gun_point(sk, (w["butt"], w["muzzle"][1])), self.gun_point(sk, w["muzzle"]), 2.6

    def muzzle(self, sk, weapon):
        return self.gun_point(sk, WEAPONS[weapon]["muzzle"])

    @staticmethod
    def gun_point(sk, p):
        return add(add(sk["wr_n"], scale(sk["wep_dir"], p[0] * GUN_SCALE)), scale(sk["gun_n"], p[1] * GUN_SCALE))

    # -- body -------------------------------------------------------------------------

    def pelvis(self, cv, sk):
        c = self.c
        hip, br = sk["hip"], sk["body_rot"]
        q = self.bulk * 1.14

        def H(x, y):
            return add(hip, rot((x * q, y), br))

        shape = [tuple(p) for p in catmull_closed([H(-8.2, 7), H(8.2, 7), H(8.6, 0), H(7, -6), H(-7, -6), H(-8.6, 0)], 5)]
        cv.group([(shape, c["pants"])], shade=0.9)
        holster = blob(H(-5.5, -1.5), [(-3.2, 3.5), (3.2, 3.5), (3.6, -3), (0, -5), (-3.6, -3)], br, 1.0, 4)
        cv.group([(holster, c["belt"])], stroke_scale=0.6, shade=0.5)

    def torso(self, cv, sk):
        c = self.c
        b = self.body
        waist, cr = sk["waist"], sk["chest_rot"]
        q = self.bulk * 1.14
        L = b.chest_len

        def C(x, y):
            return add(waist, rot((x * q, y), cr))

        if self.spec.get("backpack"):
            pack = blob(C(-11, L * 0.55), [(-5, 9), (4, 10), (5, 0), (4, -10), (-5, -9), (-7, 0)], cr, 1.0, 4)
            cv.group([(pack, c["vest"])], shade=0.9)
            cv.details([([C(-16, L * 0.5), C(-8, L * 0.5), C(-8, L * 0.5 - 1.6), C(-16, L * 0.5 - 1.6)], c["belt"][1], 255)])
        shirt = [tuple(p) for p in catmull_closed(
            [C(-5.5, L + 1), C(5, L + 1), C(9.4, L - 6), C(8.9, L * 0.3), C(8, -3), C(-8, -3), C(-8.6, L * 0.45), C(-9.4, L - 6)], 5)]
        cv.group([(shirt, c["tunic"])])
        vest = [tuple(p) for p in catmull_closed(
            [C(-4.5, L - 0.8), C(5, L - 1.2), C(9.2, L - 7.5), C(9.3, 1.2), C(-8.2, 1.2), C(-8.8, L - 7.5)], 5)]
        cv.group([(vest, c["vest"])], stroke_scale=0.7, shade=0.8)
        det = []
        for k in range(3):
            x = 1.8 + k * 2.5
            det.append(([C(x, 8.4), C(x + 2.1, 8.4), C(x + 2.1, 2.2), C(x, 2.2)], c["vest"][0], 255))
            det.append(([C(x + 0.2, 8.4), C(x + 1.9, 8.4), C(x + 1.9, 7.2), C(x + 0.2, 7.2)], c["vest"][2], 255))
        det.append(([C(-4.4, L - 1), C(-2.2, L - 1), C(-2.0, 10), C(-4.2, 10)], c["vest"][0], 255))
        det.append(([C(-7.4, 9.5), C(-1, 9.5), C(-1, 8.3), C(-7.4, 8.3)], c["vest"][0], 255))
        cv.details(det)
        belt = [C(-8.8, 1.6), C(9.4, 1.6), C(9.2, -2.4), C(-8.6, -2.4)]
        cv.group([(belt, c["belt"])], stroke_scale=0.55, shade=0.5)
        buckle = blob(C(7.0, -0.4), [(-1.8, 1.6), (1.8, 1.6), (2.1, 0), (1.8, -1.6), (-1.8, -1.6), (-2.1, 0)], cr, 1.0, 3)
        cv.group([(buckle, c["accent"])], stroke_scale=0.4, shade=0.4)

    # -- head -------------------------------------------------------------------------

    def face(self, cv, H, B, pose):
        c = self.c
        e = max(0.0, min(1.0, pose["eye"]))
        ey, eh = 13.5, 4.4 * e + 0.55

        def oval(cx, cy, rx, ry, n=12):
            return [H(cx + math.cos(i / n * math.tau) * rx, cy + math.sin(i / n * math.tau) * ry) for i in range(n)]

        det = [(oval(6.9, ey, 2.6, eh), c["eye"][1], 255), (oval(13.3, ey, 1.5, eh * 0.9), c["eye"][1], 255)]
        if e > 0.45:
            det.append((oval(6.1, ey + eh * 0.42, 1.1, 1.3), (255, 255, 255), 255))
            det.append((oval(12.9, ey + eh * 0.42, 0.6, 0.95), (255, 255, 255), 255))
        bw = pose["brow"]
        by = ey + 6.2
        col = c["hair"][0]
        det.append(([H(3.8, by + 1.1 + bw * 0.9), H(9.8, by + 0.2 - bw * 1.8), H(9.8, by - 1.2 - bw * 1.8), H(3.8, by - 0.3 + bw * 0.9)], col, 255))
        det.append(([H(12.0, by - 0.2 - bw * 1.6), H(15, by + 0.6 + bw * 0.5), H(15, by - 0.7 + bw * 0.5), H(12.0, by - 1.5 - bw * 1.6)], col, 255))
        m = pose["mouth"]
        if m > 0.12:
            det.append(([H(8.6, 5.4 + 1.2 * m), H(12.6, 5.4 + 1.2 * m), H(12.0, 5.4 - 2.6 * m), H(9.2, 5.4 - 2.6 * m)], (120, 50, 50), 255))
        else:
            det.append(([H(8.3, 5.75), H(12.7, 6), H(12.7, 5.05), H(8.3, 4.9)], c["skin"][0], 255))
        det.append(([H(14.5, 10.4), H(16.2, 9.4), H(14.5, 8.7)], c["skin"][0], 255))
        cv.details(det)

    def head(self, cv, sk, pose, bakes):
        c = self.c
        hs = self.body.head_size
        o, r = sk["head_base"], sk["head_rot"]

        def H(x, y):
            return add(o, rot((x * hs, y * hs), r))

        def B(ctrl, sub=6):
            return [tuple(p) for p in catmull_closed([H(*p) for p in ctrl], sub)]

        kind = self.spec["head"]
        skull = B([(-13.5, 15), (-12, 25), (-3, 30.5), (8, 29), (14, 22), (15.5, 13), (14.6, 6.5),
                   (10, 1.2), (3, -0.3), (-5, 2.5), (-11.5, 7)])
        if kind == "balaclava":
            cv.group([(skull, c["hair"])])
            window = B([(1.5, 18.5), (9, 19.6), (15.6, 18.5), (15.8, 10), (9, 9.4), (1.8, 10.4)], 4)
            cv.details([(window, c["skin"][1], 255)])
            self.face(cv, H, B, dict(pose, mouth=0))
            cv.details([(B([(0.8, 11), (8, 8.6), (15.7, 8.8), (15.7, 2), (2, 1.6)], 4), c["hair"][1], 255)])
            return
        if kind in ("hair", "headband", "cap", "beret"):
            back = B([(-15, 10), (-15.8, 20), (-11, 29), (-3, 33), (7, 32), (13.5, 27), (9, 25), (-1, 24),
                       (-6, 17), (-6.5, 8), (-11, 4)])
            cv.group([(back, c["hair"])])
        cv.group([(skull, c["skin"])])
        self.face(cv, H, B, pose)
        ear = blob(H(-6.2, 12.0), [(-1.9, 2.4), (1.7, 2.6), (2.1, -0.9), (0, -3.0), (-2.2, -0.9)], r, hs, 4)

        if kind == "helmet":
            dome = B([(-16, 10.5), (-16.6, 20), (-12, 30), (-2, 35), (9, 33.5), (15.5, 27), (17.8, 21.5), (9, 20.6),
                      (-2, 20.6), (-6, 12), (-5.6, 9.6)], 5)
            cv.group([(dome, c["helmet"])])
            cv.details([(B([(-14, 25), (-4, 30), (8, 29.4), (10, 27), (-3, 27.6), (-13, 23)], 3), c["helmet"][2], 255),
                         ([H(-16, 21), H(17.4, 22.6), H(17.6, 20.7), H(-15.8, 19)], c["helmet"][0], 255)])
            strap = [H(-5.6, 10), H(-3.6, 10), H(3, 0.2), H(1, -0.2)]
            cv.details([(strap, c["belt"][1], 255)])
            if self.spec.get("goggles"):
                g = B([(-3, 30.5), (8, 31), (14, 28), (13.4, 24), (-2.6, 25.6)], 3)
                cv.group([(g, c["metal"])], stroke_scale=0.6, shade=0.5)
                cv.details([(B([(2, 29.4), (11.6, 29), (11.6, 25.6), (2, 26.6)], 3), (120, 190, 220), 255)])
        elif kind == "beret":
            cv.details([(ear, c["skin"][0], 255)])
            top = B([(-15, 22), (-15.5, 30), (-6, 35.5), (7, 35), (15, 30), (13, 26.5), (2, 24.5), (-9, 23)], 5)
            cv.group([(top, c["helmet"])])
            cv.details([(B([(-14.6, 21.5), (2, 24.4), (13.5, 26.6), (14, 25), (2, 22.4), (-14.2, 19.8)], 3), c["belt"][1], 255),
                        (B([(5, 29), (8, 30), (9, 28), (7, 26.8), (5, 27.4)], 3), c["accent"][1], 255)])
        elif kind == "cap":
            cv.details([(ear, c["skin"][0], 255)])
            top = B([(-14.5, 21), (-14, 28), (-5, 33.4), (7, 33), (14, 27.5), (15, 23), (2, 23), (-10, 21)], 5)
            bill = B([(9, 25.5), (17, 25), (23, 22.6), (22.4, 21), (13, 22.2), (9, 23)], 3)
            cv.group([(top, c["helmet"]), (bill, c["helmet"])])
            cv.details([(B([(-1, 29), (5, 29.4), (5.6, 25.6), (-1, 25.4)], 3), c["accent"][1], 255)])
        elif kind == "headband":
            cv.details([(ear, c["skin"][0], 255)])
            spikes = B([(-13, 27), (-5, 33.4), (6, 33.2), (13.2, 28.6), (16.2, 23.5), (14, 24.4), (11.6, 23), (9.4, 25),
                        (6.4, 22.6), (3, 25), (-1.5, 22.6), (-4.5, 24.6), (-8, 21.8), (-11.8, 23)], 3)
            cv.group([(spikes, c["hair"])], shade=0.8)
            band = B([(-14.8, 21.4), (-1, 24.4), (15.2, 22.6), (15.4, 19), (-1, 20.6), (-14.4, 17.6)], 4)
            cv.group([(band, c["cape"])], stroke_scale=0.55, shade=0.5)
        else:
            cv.details([(ear, c["skin"][0], 255)])
            bangs = B([(-13, 27), (-5, 33), (6, 33), (13.2, 28.5), (16.4, 20.5), (14.2, 22.6), (12.4, 18.8), (9.8, 23.6),
                       (6.2, 19), (3, 24.5), (-1.5, 21), (-4.5, 24), (-8, 17.5), (-11.8, 21)], 3)
            cv.group([(bangs, c["hair"])], shade=0.8)

    # -- guns -------------------------------------------------------------------------

    def gun(self, cv, sk, pose, name):
        c = self.c
        steel, poly, wood, metal = c["gun"], c["gun2"], c["wood"], c["metal"]
        G = lambda x, y: self.gun_point(sk, (x, y))

        def Q(*pts):
            return [G(*p) for p in pts]

        slide = pose["pump"]
        have_mag = pose["mag"] > 0.5
        if name == "rifle":
            if have_mag:
                cv.group([(Q((4, 3.2), (9.5, 3.2), (8.4, -8), (2.8, -9)), poly)], stroke_scale=0.7, shade=0.6)
            cv.group([(Q((-20.5, 7.6), (-6, 8), (-6, 3.6), (-12, 2.8), (-18, -1.5), (-20.8, -1.5)), poly),
                      (Q((-3.5, 3.2), (2.5, 3.2), (1, -4.4), (-3.8, -4.4)), poly)], stroke_scale=0.8, shade=0.6)
            cv.group([(Q((23, 6.5), (31, 6.5), (31, 4.8), (23, 4.8)), steel), (Q((31, 7.1), (35.5, 7.1), (35.5, 4.2), (31, 4.2)), steel),
                      (Q((10, 7.8), (23, 7.6), (23, 3.4), (10, 3)), poly), (Q((-7, 8.4), (10, 8.4), (10, 2.6), (-7, 2.6)), steel)],
                     stroke_scale=0.8, shade=0.55)
            cv.group([(Q((-3, 8.4), (5, 8.4), (5, 10.6), (3.4, 10.8), (3, 9.6), (-1, 9.6), (-1.5, 10.8), (-3, 10.6)), steel),
                      (Q((20, 7.6), (22, 7.6), (22, 10), (20.8, 10)), steel)], stroke_scale=0.6, shade=0.4)
            det = [(Q((11 + k * 2.6, 6.6), (12.2 + k * 2.6, 6.6), (12.2 + k * 2.6, 4.2), (11 + k * 2.6, 4.2)), poly[2], 255) for k in range(4)]
            det.append((Q((-1 - slide * 3, 7), (5, 7), (5, 5.4), (-1 - slide * 3, 5.4)), steel[2], 255))
            cv.details(det)
        elif name == "smg":
            if have_mag:
                cv.group([(Q((3.4, 3.2), (7.2, 3.2), (6.6, -11), (2.8, -11)), poly)], stroke_scale=0.7, shade=0.6)
            cv.group([(Q((-3, 3.2), (2.2, 3.2), (1, -4.4), (-3.4, -4.4)), poly),
                      (Q((-15, 7), (-5, 7), (-5, 5.8), (-13.4, 5.8), (-13.4, 1.6), (-15, 1.6)), steel)], stroke_scale=0.7, shade=0.5)
            cv.group([(Q((14, 6.4), (21, 6.4), (21, 4.8), (14, 4.8)), steel), (Q((-6, 8), (14, 8), (14, 3), (-6, 3)), steel)],
                     stroke_scale=0.8, shade=0.55)
            cv.details([(Q((0 - slide * 3, 7), (6, 7), (6, 5.6), (0 - slide * 3, 5.6)), steel[2], 255)])
        elif name == "pistol":
            k = -3.5 * slide
            cv.group([(Q((-3, 3.4), (3, 3.4), (1.6, -4.2), (-3.6, -4.2)), poly)], stroke_scale=0.8, shade=0.5)
            cv.group([(Q((-2, 4.6), (11, 4.6), (11, 2.6), (-2, 2.6)), poly)], stroke_scale=0.7, shade=0.5)
            cv.group([(Q((-4 + k, 7.8), (14 + k, 7.8), (14 + k, 4.2), (-4 + k, 4.2)), steel)], stroke_scale=0.8, shade=0.55)
            cv.details([(Q((-2.5 + k, 7), (1 + k, 7), (1 + k, 6), (-2.5 + k, 6)), steel[2], 255),
                        (Q((5 + k, 6.8), (9.6 + k, 6.8), (9.6 + k, 5.4), (5 + k, 5.4)), steel[0], 255)])
        elif name == "shotgun":
            k = -7 * slide
            cv.group([(Q((-21, 7.4), (-6, 7.8), (-6, 3.6), (-12, 2.6), (-19, -2), (-21.4, -2)), wood),
                      (Q((-3.4, 3.2), (2.4, 3.2), (1, -4), (-3.8, -4)), wood)], stroke_scale=0.8, shade=0.6)
            cv.group([(Q((8, 3.8), (31, 3.8), (31, 1.8), (8, 1.8)), steel), (Q((8, 7.4), (37.5, 7.4), (37.5, 4.6), (8, 4.6)), steel),
                      (Q((-7, 8.2), (10, 8.2), (10, 2.4), (-7, 2.4)), steel)], stroke_scale=0.8, shade=0.55)
            cv.group([(Q((15 + k, 3.8), (24 + k, 3.8), (24 + k, 0.6), (15 + k, 0.6)), wood)], stroke_scale=0.7, shade=0.5)
            det = [(Q((16.2 + i * 1.6 + k, 3.2), (16.9 + i * 1.6 + k, 3.2), (16.9 + i * 1.6 + k, 1.1), (16.2 + i * 1.6 + k, 1.1)), wood[0], 255) for i in range(5)]
            cv.details(det)
        elif name == "sniper":
            if have_mag:
                cv.group([(Q((3.4, 3.2), (8, 3.2), (7.4, -4.4), (3.4, -4.4)), poly)], stroke_scale=0.7, shade=0.6)
            cv.group([(Q((-23, 8), (-6, 8.4), (-6, 3.4), (-13, 2.4), (-20, -3), (-23.4, -3)), poly),
                      (Q((-3.4, 3.2), (2.4, 3.2), (1, -4.2), (-3.8, -4.2)), poly)], stroke_scale=0.8, shade=0.6)
            cv.group([(Q((24, 6.4), (47, 6.2), (47, 4.9), (24, 4.8)), steel), (Q((47, 7), (53, 7), (53, 4.2), (47, 4.2)), steel),
                      (Q((-7, 8.4), (24, 8), (24, 2.8), (-7, 2.8)), steel)], stroke_scale=0.8, shade=0.55)
            cv.group([(Q((-3, 13.6), (3, 13), (15, 13), (19, 13.8), (19, 10), (15, 11), (3, 11), (-3, 10.2)), poly)], stroke_scale=0.7, shade=0.6)
            cv.details([(Q((1, 10.9), (3.4, 10.9), (3.4, 8.2), (1, 8.2)), steel[1], 255), (Q((12, 10.9), (14.4, 10.9), (14.4, 8.2), (12, 8.2)), steel[1], 255),
                        (Q((17.6, 13.4), (18.8, 13.6), (18.8, 10.3), (17.6, 10.8)), (120, 190, 220), 255)])
            bolt = (-3 - slide * 6, 8.8)
            cv.group([(capsule(G(*bolt), 1.0, G(bolt[0] - 1, bolt[1] + 2.6), 1.5, 3), metal)], stroke_scale=0.5, shade=0.4)
        elif name == "rocket":
            cv.group([(Q((-3.2, 2), (2.4, 2), (1, -4), (-3.6, -4)), poly), (Q((10, 2), (14.4, 2), (13.6, -1.4), (10.4, -1.4)), poly)],
                     stroke_scale=0.7, shade=0.5)
            cv.group([(Q((-28, 11.8), (-23, 10.2), (34, 10.2), (34, 1.8), (-23, 1.8), (-28, 0.2)), c["helmet"])], stroke_scale=0.9, shade=0.8)
            cv.details([(Q((-14, 10.2), (-11, 10.2), (-11, 1.8), (-14, 1.8)), c["helmet"][0], 255),
                        (Q((20, 10.2), (23, 10.2), (23, 1.8), (20, 1.8)), c["helmet"][0], 255)])
            if have_mag:
                cone = Q((33, 8.8), (37, 9.6), (44, 6), (37, 2.4), (33, 3.2))
                cv.group([(cone, c["vest"])], stroke_scale=0.8, shade=0.6)

    def held_mag(self, cv, sk, name, pose):
        c = self.c
        if pose["gren"] > 0.5:
            g = blob(sk["wr_f"], [(-3, 3), (3, 3), (3.6, 0), (3, -3), (-3, -3), (-3.6, 0)], 0, 1.0, 4)
            cv.group([(g, c["helmet"])], stroke_scale=0.7, shade=0.6)
        if pose["mag_hand"] > 0.5:
            w = WEAPONS[name]
            a = sk["fa_f"]
            if w["kind"] == "tube":
                p = capsule(sk["wr_f"], 1.7, add(sk["wr_f"], (4.5, 1.5)), 1.7, 3)
                cv.group([(p, c["cape"])], stroke_scale=0.6, shade=0.4)
            elif w["kind"] == "rocket":
                cone = blob(sk["wr_f"], [(-8, 3), (4, 3.4), (10, 0), (4, -3.4), (-8, -3)], -30, 1.0, 3)
                cv.group([(cone, c["vest"])], stroke_scale=0.8, shade=0.6)
            else:
                p = capsule(sk["wr_f"], 2.2, add(sk["wr_f"], rot((0, 8), a)), 2.2, 3)
                cv.group([(p, c["gun2"])], stroke_scale=0.7, shade=0.5)

    def dropped_mag(self, cv, sk, name, pose):
        t = pose["mag_t"]
        if t < 0 or t > 0.5 or WEAPONS[name]["kind"] not in ("mag", "bolt"):
            return
        start = (sk["sh_n"][0] + 14, sk["sh_n"][1] - 12)
        p = (start[0] - 16 * t, start[1] - 180 * t * t)
        ang = t * 420
        a, b = add(p, rot((0, -4), ang)), add(p, rot((0, 4), ang))
        cv.group([(capsule(a, 2.0, b, 2.0, 3), self.c["gun2"])], stroke_scale=0.7, shade=0.5)

    def flash_fx(self, cv, sk, pose, name):
        level = pose["flash"]
        if level <= 0.02:
            return
        w = WEAPONS[name]
        o = self.muzzle(sk, name)
        d, n = sk["wep_dir"], sk["gun_n"]
        rng = random.Random(int(pose["flash_seed"]) * 7 + 1)
        size = 13 * w["flash"] * (0.55 + 0.45 * level)
        layers = (((255, 170, 60), 1.0), ((255, 226, 120), 0.68), ((255, 255, 255), 0.36))
        spikes = [(rng.uniform(0.75, 1.2), rng.uniform(0.3, 0.46)) for _ in range(9)]
        for col, k in layers:
            pts = []
            for i in range(18):
                ang = (i / 18 - 0.5) * math.tau
                s = spikes[(i // 2) % 9]
                r = (s[0] if i % 2 == 0 else s[1]) * size * k
                along = max(math.cos(ang), 0) ** 1.4 * 1.6 + 0.45
                x, y = math.cos(ang) * r * along, math.sin(ang) * r * 0.62
                pts.append(add(add(o, scale(d, x + size * 0.1)), scale(n, y)))
            cv.details([(_splash(pts, o[0]), col, 255)])
        if w["kind"] == "rocket":
            # Back-blast: a cone out of the rear of the tube.
            b = self.gun_point(sk, (-28, 6))
            for col, k in layers:
                ln, wd = size * 1.5 * k, size * 0.55 * k
                tip = add(b, scale(d, -ln))
                cone = [add(b, scale(n, wd)), add(add(b, scale(d, -ln * 0.5)), scale(n, wd * 0.8)), tip,
                        add(add(b, scale(d, -ln * 0.5)), scale(n, -wd * 0.8)), add(b, scale(n, -wd))]
                cv.details([(_splash(cone, b[0]), col, 255)])

    def shells(self, cv, sk, pose, name):
        w = WEAPONS[name]
        t0, T = pose["shot_t"], pose["shot_T"]
        if t0 < 0 or not w["shell"]:
            return
        delay = 0.3 * T if w["kind"] in ("tube", "bolt") else 0.0
        port = self.gun_point(sk, w["port"])
        n = sk["gun_n"]
        d = sk["wep_dir"]
        for k in range(3):
            a = t0 + k * T - delay
            if a < 0 or a > 0.3:
                continue
            p = (port[0] + (-d[0] * 26 + n[0] * 66) * a, port[1] + (-d[1] * 26 + n[1] * 66) * a - 330 * a * a)
            ang = a * 1500 + k * 40
            ln = 1.7 * w["shell"]
            e = add(p, rot((0, ln), ang))
            s = add(p, rot((0, -ln), ang))
            cv.group([(capsule(s, 0.95 * w["shell"], e, 0.95 * w["shell"], 2), self.c["accent"])], stroke_scale=0.4, shade=0.3)

    # -- frame ------------------------------------------------------------------------

    def draw(self, cv, sk, pose, cloth, smear_hist=None, layer=None, weapon=None):
        c = self.c
        weapon = weapon or self.spec["weapons"][0]
        self.active = weapon
        up = layer in (None, "upper")
        low = layer in (None, "lower")
        cv.set_squash(pose["squash"], 0.0)
        if up:
            if smear_hist:
                self.smear(cv, smear_hist[0], smear_hist[1], pose["smear"])
            if "scarf" in cloth:
                self.scarf(cv, cloth["scarf"])
            self.arm(cv, sk, "f", True)
        if low:
            self.leg(cv, sk, "f", True)
            self.leg(cv, sk, "n", False)
            self.pelvis(cv, sk)
        if up:
            self.torso(cv, sk)
            if "scarf" in cloth:
                self.neck_wrap(cv, sk)
            if "hair" in cloth:
                self.tail(cv, cloth["hair"], c["hair"], 7.0, 1.4)
            if "headband" in cloth:
                self.tail(cv, cloth["headband"], c["cape"], 4.2, 1.6)
            self.head(cv, sk, pose, cloth)
            self.held_mag(cv, sk, weapon, pose)
            self.gun(cv, sk, pose, weapon)
            self.dropped_mag(cv, sk, weapon, pose)
            self.shells(cv, sk, pose, weapon)
            self.arm(cv, sk, "n", False)
            self.flash_fx(cv, sk, pose, weapon)

