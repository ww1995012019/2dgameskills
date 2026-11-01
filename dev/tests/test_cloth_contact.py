"""A floor correction must not become a new Verlet impulse."""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "game-sprite-animator/scripts"))
from sprite_anim.cloth import ChainDef, simulate


class StillClip:
    duration = 1.0
    loop = True

    def vel(self, t):
        return (0.0, 0.0)


def sheet(length):
    return ChainDef("sheet", ("hip", "body_rot", (0, 0)), 7, length / 6,
                    rest=(-0.18, -0.98), gravity=320, drag=6, stiff=0.05,
                    ground=True, max_bend=34, max_curl=75, swing=(-92, 14))


class FloorContact(unittest.TestCase):
    def test_static_sheets_settle_at_different_lengths(self):
        # With the regression, each of these develops a sustained oscillation
        # despite a stationary anchor, no wind, and no flutter.
        for length in (24, 84, 140):
            with self.subTest(length=length):
                d = sheet(length)
                anchor = np.array([0.0, length * 0.94])
                bake = simulate(d, StillClip(), None,
                                state_at=lambda t: (anchor, 0.0))
                self.assertLess(np.linalg.norm(np.ptp(bake.pos[:, -1], axis=0)), 0.01)
                np.testing.assert_allclose(bake.pos[:, 0], np.tile(anchor, (len(bake.pos), 1)))
                self.assertGreaterEqual(bake.pos[:, 1:, 1].min(), 0.8 - 1e-9)
                # Floor projection can shorten the last segment slightly;
                # repacking must not stretch the whole sheet.
                lengths = np.linalg.norm(np.diff(bake.pos, axis=1), axis=2)
                self.assertLess(np.abs(lengths - d.seg).max(), d.seg * 0.03)

    def test_moving_anchor_keeps_driving_the_sheet(self):
        d = sheet(84)

        def state(t):
            return np.array([2 * np.sin(2 * np.pi * t), 79.0]), 0.0

        bake = simulate(d, StillClip(), None, state_at=state)
        relative_tip = bake.pos[:, -1] - bake.pos[:, 0]
        self.assertGreater(np.linalg.norm(np.ptp(relative_tip, axis=0)), 0.1)
        self.assertLess(np.linalg.norm(np.ptp(relative_tip, axis=0)), 10)
        self.assertGreaterEqual(bake.pos[:, 1:, 1].min(), 0.8 - 1e-9)
        # Wrapping the loop must be comparable to an ordinary simulation step.
        jumps = np.linalg.norm(np.diff(bake.pos[:, -1], axis=0), axis=1)
        self.assertLess(np.linalg.norm(bake.pos[0, -1] - bake.pos[-1, -1]),
                        max(jumps.max() * 2, 0.01))


if __name__ == "__main__":
    unittest.main()
