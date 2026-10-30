---
name: game-quadruped-animator
description: Generate side-view wolf animations with a four-legged canine rig: idle, walk, diagonal-pair trot, gallop, bite, hurt and death. Use for 四足动物、狼、四足步态、quadruped sprites. Includes four-paw ground-contact QA, simulated tail and game-engine exports.
---

# Quadruped animator

Python 3 with Pillow and NumPy. This folder installs independently; run scripts from its root.
The first version is a right-facing wolf with four looping gaits and three one-shots: idle, walk, trot, run, attack, hurt, death.
Leftward movement uses runtime horizontal flip. This is not the top-down eight-direction skill.

1. Generate, using a copy of `assets/characters/wolf.json` for colour customization:

   ```bash
   python scripts/generate.py --character assets/characters/wolf.json --preset pixel --out out/wolf
   ```

2. Run numerical QA and fix actual causes, never loosen thresholds to hide failures:

   ```bash
   python scripts/qa_motion.py out/wolf
   ```

3. Build and inspect all four colour/silhouette sheets. Check canine elbows/stifles/hocks,
   all four legs, spine, head/neck, paws on the floor, tail attachment, footfall order and clipping.
   Record observations and limitations in `review/verdict.json`. Static review is not playback proof.

   ```bash
   python scripts/visual_review.py out/wolf
   ```

4. Play `preview.html`: A/D or arrows move; 1/2/3 select walk/trot/run; Shift temporarily gallops.
   Movement follows manifest `speed_px_s`. Gait changes retain normalized loop phase but do not
   synthesize contact-preserving gait blends. Judge transitions in the actual game.
5. Deliver frames, atlas, manifest and the relevant engine files. Read `references/integration.md`
   and report the validation level actually executed, rather than equating export with native support.

`--clips idle,walk` selects actions (idle is always included); `--fps` and `--size` override presets.
Presets: hd (256px/30fps), hd60, hd512, pixel48, pixel (64px/15fps), pixel96.
Output uses one feet pivot, fixed bone lengths, per-foot touchdown events and the existing shared
Verlet-chain solver for the tail. See `references/qa.md` for coverage and limitations.

Limits: side-view canine only, one facing plus mirror, no top-down views, no quadruped top-down
views, no custom layered art or separate dog/horse rigs. JSON currently changes colours/name, not
arbitrary bone proportions. No joint editor or runtime state machine is produced.

Combat controls: J plays a planted forward lunge/bite, H reacts, X dies/revives. Attack uses
`hit_on`/`hit_off`; consumers apply damage in that window. The preview training target records
one hit on `hit_on` only when facing it within range. Hurt and attack recover to idle, death
holds its final collapsed, closed-eye frame until revive. Reaction inputs interrupt locomotion;
movement is locked during the reaction. There is no airborne root-motion pounce or autonomous AI.
