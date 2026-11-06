---
name: game-animator
description: Generate and inspect 2D game character sprite animations for side-view humanoids, side-view shooters, eight-direction top-down humanoids, and side-view wolves. Use for character sprites, animation sheets, custom humanoid actions, and supported engine exports; select the matching mode before generating.
---

# Game Animator

This is the package to install; the four former standalone skills are deprecated copies of its modes.

For humanoid art, the side-view mode's
[release gates](modes/game-sprite-animator/references/release-gates.md) apply before binding and
before delivering any clip: neck, hands, waist/garment continuity and run rhythm are checked on the
actual pixels and in playback, and numeric QA never clears them. For complete aligned layers with
known joints, prefer the [zero-generation binding entry](modes/game-sprite-animator/references/known-joint-binding.md).
When the user rejects a result, follow the [repair loop](modes/game-sprite-animator/references/repair-loop.md):
show quick before/after GIFs from `scripts/compare_clips.py` first and run full verification only
after they approve.

Choose a mode using the character, camera and movement. Read only that mode's `SKILL.md`, and run
its scripts from that mode's directory. Each mode is bundled here and requires Python with Pillow
and NumPy; no separate skill installation is needed.

| Request | Mode |
|---|---|
| Side-view humanoid, custom cut-out art, melee or spell | `modes/game-sprite-animator/` |
| Custom side-view rifle carrier, idle/run only | Humanoid mode's guarded `side-rifle-carry-v1` profile |
| Side-view shooter, gun aiming or layered firing | `modes/game-shooter-animator/` |
| 3/4 top-down eight-direction humanoid | `modes/game-topdown-animator/` |
| Side-view wolf with quadruped gait or combat | `modes/game-quadruped-animator/` |
| Experimental side-view flying creature with user-provided PNG parts | `references/creature-rig.md` |

Read the chosen mode's `SKILL.md` for its commands, supported character configuration, review and
export process. For supplied character pictures or AI-generated side-view art, follow the humanoid mode's
`references/basic-character-workflow.md`: fixed prompts, short/fitted clothing, short hair, no weapon
or one single-handed sword, mandatory hand hints, isolated-layer review, idle + walk only and bounded
repairs. The agent handles the prompts and reviews; the user supplies the picture. Advanced layered
features remain experimental, not a fallback around a rejected basic job. Numeric QA alone never clears delivery.
For a fitted character carrying a rifle in idle/run only, read
`modes/game-sprite-animator/references/rifle-carry.md` and explicitly select that separate guarded
profile. It retains the original upper-body pixels, both gripping hands and rifle on one surface;
every-frame source-carry review is mandatory. It provides no aiming, firing or reload actions and
does not expand the basic profile's weapon scope or reset an existing task's attempt budget.
For other side-view custom art and actions, use its `references/ai-art.md` and
`references/character-spec.md`; test custom actions in the preview and inspect joints visually.

## Shared character identity: side and top-down

`assets/shared_character_example.json` demonstrates one manifest for a side-view humanoid and a
top-down humanoid. Generate each view into a new output directory:

```bash
python scripts/generate_character.py --manifest assets/shared_character_example.json --view side --preset pixel --out out/hero-side
python scripts/generate_character.py --manifest assets/shared_character_example.json --view topdown --preset pixel --out out/hero-topdown
python modes/game-sprite-animator/scripts/qa_motion.py out/hero-side
python modes/game-topdown-animator/scripts/qa_motion.py out/hero-topdown
```

The top-level `name` and `palette` are shared. Palette keys are `skin`, `hair`, `coat`, `trim`,
`pants`, `boots`, and `ink`; coat maps to side-view `tunic`, trim to side-view `accent`. Each view
can name an existing `base` spec path relative to the manifest and optionally supply `overrides`;
view overrides take precedence. With a base, image paths in its `parts` and in view overrides are
relative to that base file; without one, they are relative to the manifest. The resolved spec is
saved with the output for inspection. `body` applies only to the side-view rig: top-down proportions
are not configurable and top-down does not support cut-out PNGs. The two views use their own art,
so matching palette and name do not guarantee a matching character design. The wrapper requires a
new output directory, and QA and visual review are still separate steps.

These modes retain their existing implementations under one entry point; the exporter, skeleton
integrity checks and applicable math routines are shared within this bundle. A PNG part from one view does not automatically
work in another. The experimental flight workflow can
generate rigid-part motion but is not a visually validated bird, bat or dragon product. Arbitrary
creature locomotion, full scene generation, and AI art for the top-down mode are not implemented.
Do not advertise an engine integration as verified beyond the mode's integration documentation.
