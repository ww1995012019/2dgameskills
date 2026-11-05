---
name: game-animator
description: Generate and inspect 2D game character sprite animations for side-view humanoids, side-view shooters, eight-direction top-down humanoids, and side-view wolves. Use for character sprites, animation sheets, custom humanoid actions, and supported engine exports; select the matching mode before generating.
---

# Game Animator

For humanoid art and animation, also enforce the selected mode's
[head, neck and hand review](modes/game-sprite-animator/references/visual-review.md).
Inspect the original head/torso and both complete hands before binding. Exposed neck cuts,
a pasted-on head, rigid head/torso motion, unnatural finger splaying and broken wrists are blockers.
Every applicable clip needs `neck_*.png`, `hands_*.png` and their complete motion playback,
with current frame-specific and temporal observations. Pixel contact or a nonzero head angle
cannot certify natural anatomy or motion. Do not carry forward older visual passes.

For complete aligned layers with known joints, prefer the [zero-generation binding entry](modes/game-sprite-animator/references/known-joint-binding.md). Reuse existing pixels and joint metadata; hand-hint generation is unnecessary for this entry. Visual review remains required.

For humanoid binding, read the selected mode's
[skin and garment audit](modes/game-sprite-animator/references/skin-binding-audit.md).
Source-preserving pixels and valid bone lengths do not prove a connected waist/crotch or correct
painted joint placement. Do not split trousers into independent half-images without a pelvis
bridge or shared boundary constraint. Full-body clips need current hip close-ups and explicit
alignment/continuity findings. Custom game renderers must supply their actual weights, matrices,
rendered frames and review evidence; the skill cannot inherit a pass from game unit tests.


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
