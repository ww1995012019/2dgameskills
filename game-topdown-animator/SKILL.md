---
name: game-topdown-animator
description: Generate eight-direction 3/4 top-down humanoid game sprites for free movement, including idle, walk, run, attack, hurt and death. Use for 俯视角色、八方向、自由移动、top-down RPG sprites. Exports PNG frames, atlases and engine animation files.
---

# Top-down animator

Requires Python 3, Pillow and NumPy. Run scripts from this skill's root. This is a standalone
folder; no pip package installation, sibling skills, API keys or image model is required.

Default: 3/4 camera, eight directions, free movement, sword humanoid, all six actions.
Templates: `wanderer` (hair, blue coat), `warden` (hood, green coat). Copy a character JSON to
customize colours and `head` (`hair` or `hood`). Prefer `hd` (256px, 30fps) or `pixel` (64px, 15fps).

1. Generate (outputs are replaced only inside the selected output's frames/sheets/engine folders):

   ```bash
   python scripts/generate.py --character assets/characters/wanderer.json --preset pixel --out out/wanderer
   ```

2. Run motion QA; investigate any FAIL without loosening thresholds:

   ```bash
   python scripts/qa_motion.py out/wanderer
   ```

3. Build and look at **every** review sheet. Do not call sheet generation a visual approval.
   Check front/back facing, limb attachment, depth ordering, foot contact, slash readability,
   death pose, clipping and differences across directions. See `references/qa.md` for limits.

   ```bash
   python scripts/visual_review.py out/wanderer
   ```

4. Inspect `preview.html`: WASD/arrow combinations move in eight directions, Shift runs,
   J attacks, H simulates a hit, X toggles death/revival. Check start/stop/turning and diagonal speed.
   A preview must be played to judge feel; static visual review cannot prove it.

5. Deliver the atlas, animations.json and relevant engine files. Follow `references/integration.md`;
   describe each export's actual validation level. No runtime state machine is generated.

All eight directions are baked. `mirror_of` describes left-facing source art; do not flip those
frames again. Mirroring changes equipment handedness. A fixed-side shield or asymmetric character
needs separately authored left art; this first version does not support that.

Optional flags: `--clips idle,walk` (always all eight directions per selected action; idle is included for recovery), `--fps 30`,
`--size 192`; presets `hd`, `hd60`, `hd512`, `pixel48`, `pixel`, `pixel96`.

Limits: humanoids only; fixed 3/4 projection; sword only; no independent aim direction, layered PNG
binding, physics cloth or custom keyframes. Quadrupeds, monsters and true overhead cameras require
new art/rig work. Numeric tests do not prove semantic facing or visual quality.
