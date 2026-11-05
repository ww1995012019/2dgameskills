---
name: game-sprite-animator
description: >
  Generate and review supported 2D game character animation sets and export them as sprite sheets,
  atlases and engine-ready files. Covers idle, walk, run, skid, the full jump chain (start, rise,
  apex, fall, land, double jump), crouch, roll, dash, wall slide, three-hit combos, air attack, cast,
  block, hurt and death, in HD or pixel-art style. Use this skill whenever the user wants game sprites,
  a sprite sheet, a character walk or run cycle, jump or attack animation, frame animation, 序列帧,
  精灵图, 角色动画, 2D 素材, 走路跳跃动画, 像素小人, or complains that a sprite animation stutters,
  feels 卡顿, has foot sliding or a bad loop — even if they never say "sprite" and just ask for a
  "game character that can walk and jump". Also use for rigging a user's own layered character art
  and for Unity, Godot, Cocos, Phaser, PixiJS or H5/mini-game animation assets. Not for 3D models or
  rigs, video editing, or static illustrations with no animation.
---

# Game Sprite Animator

Head/neck continuity and natural hands are mandatory from reference generation through delivery.
Use the fixed species-aware neck/hand constraints in `sprite_anim/layer_slots.py`; inspect the
source, isolated head/torso and both arm layers at full size. A triangular neck flap over a collar,
an exposed internal cut, rigid pasted-on head motion, exaggerated empty-hand clawing or a broken
wrist is a blocker. Read [visual-review.md](references/visual-review.md): every applicable clip
requires the new head/neck and near/far hand close-ups plus full motion playback and explicit
observations. Do not equate alpha contact, preserved finger detail or a small head oscillation
with natural motion. Fail the art/motion stage, preserve the issue and repair the general cause
within the existing attempt budget; do not tune one character or add a collar/patch to hide it.

For complete aligned layers with known joints, prefer the [zero-generation binding entry](references/known-joint-binding.md). Reuse existing pixels and joint metadata; hand-hint generation is unnecessary for this entry. Visual review remains required.


Frames are computed from a skeleton. Continuous joint curves, fixed bone lengths and a passing
numeric report do not establish that the painted body follows those joints or that clothing stays
closed. Review both the rendered pixels and the actual driving skeleton before delivery.
Reference images can't be traced; a look is described through a character spec or
supplied as layered art.

Requires Python 3 with `pillow` and `numpy`. Scripts are in `scripts/`, run from the skill root.

## Binding and garment continuity are release blockers

Read [skin-binding-audit.md](references/skin-binding-audit.md) when binding existing artwork or
integrating a custom mesh renderer. Preserve a complete pelvis/garment bridge. Cutting one painted
pair of trousers down the middle and letting each half follow only its own leg is not a valid
layered rig: two copies of the same source boundary can separate even while every bone length and
hip landmark is correct. Do not hide that defect with a belt, flat colour, torso overlap or an
unreviewed patch. If the source lacks the needed hidden fabric, stop that binding at a failed
art/resource stage rather than claiming a continuous animation.

For every delivered full-body humanoid clip, inspect `review/hips_*.png` at full size, alongside
the original source and the driving bones: waist, near/far hip, crotch, thigh roots and both knees.
Inspect rest, deepest crouch, maximum leg separation, landings and source-pose switches. A straight
cut edge, background slit, doubled trouser panel or bone emerging from the wrong painted joint is
a blocker. Mandatory `rig_alignment` and `pelvis_continuity` observations must name the actual
clip/frame. Missing trace or missing close-up evidence cannot become a pass.

For an external/custom atlas skin, export its **actual** source points, skin weights, per-frame
matrices and isolated RGBA frames to a binding manifest, then run
`python scripts/audit_skin_binding.py binding_manifest.json --out out/c/binding_audit.json`.
This checks registered landmarks and declared shared seams; a numeric pass still requires visual
review. Preserve the manifest and its assets with the report. A hand-written game renderer, its
unit tests, or unrelated synthetic output is not evidence that this skill reviewed the character.
If the runtime cannot export those data, state that the custom binding is unverified.

Rebuild and record the current review after any change to art, trace, atlas, sprite sheets or
runtime preview. Old/unversioned passes do not carry forward. Never claim the complete set is
approved when only a few sampled poses or the skeleton math have been checked.


## AI-generated characters: read this first

For a supplied character picture or new AI-generated humanoid, use
`references/basic-character-workflow.md` and `scripts/character_workflow.py` as the DEFAULT route.
The agent prepares and uses every fixed prompt; the user does not write prompts or mark joints.
Start with `prepare --image input.png --weapon none --out NEW_JOB` (or `--weapon sword`). Inspect
identity, regenerate a standard side-view reference, then accept the reference, isolated layers,
numerical bind, idle + walk and versioned visual review in that order. Both hand hints are mandatory.
Only short/fitted clothing, short hair and no weapon/one simple single-handed sword are in scope.
The first real trial failed isolated-leg generation after three attempts; the workflow remains a
guarded trial, not a production-validated promise. Report a failed job honestly with no animation pass.
Do not silently preserve unsupported long robes, wide sleeves, capes, spears or two-handed weapons.
Record adaptations or stop if essential identity cannot be kept. Log each repair; at three attempts
per stage stop and report the remaining blocker. Never reset the job to bypass that limit.
Do not render or publish a failed basic job through the lower-level `layer_parts.py bind` or
`generate.py` commands. The binder rejects basic-job inputs, and the generator rechecks the owning
job, current layer review and exact exported rig before writing output. Numeric QA, a diagnostic
folder name or a "prototype" label cannot clear a failed art stage. Record the actual failure;
delivery still requires the current versioned visual review and `visual_review.py --check`.

Numerical checks do not recognize complete art; the agent must inspect full-size layers and motion.
Short/stump arms, broken garments, ghosting and extra weapons are blockers. No per-character joint
coordinates, pixel patches or threshold changes. The general layered binder described in
`references/layered-art.md` remains experimental for older/advanced work; never use it to bypass a
basic profile refusal. Show the running walk preview and wait for the user's approval before adding
clips. The basic route has no full-set or attack switch. `cut_parts.py` remains a quick-test route.

## Existing programmatic and custom-action workflow

For supplied pictures, follow the basic workflow above instead of asking the user to configure
these technical choices. The remaining steps apply to existing specs and custom actions.

1. **Pin down four choices.** Ask only about what the user left open and that changes the output:

   | Choice | Default | Options |
   |---|---|---|
   | Style | HD cartoon | `--preset hd`, `hd60`, `hd512`; pixel: `pixel48`, `pixel` (64), `pixel96` |
   | Character | closest of hero / knight / mage / ninja / goblin | a new spec, the user's layered art, or AI-generated art |
   | Clips | all 27 | any subset, plus custom clips |
   | Target | all exports | Unity, Godot, Cocos, Phaser/PixiJS, H5/mini-game |

2. **Write the character spec** (`references/character-spec.md`). Copy the nearest file from
   `assets/characters/` and change colours, `head`, `weapon`, `cloth`, `body`, `style`. Use `style` to
   express personality: a heavy knight is `speed: 0.85, bounce: 0.75`, a nimble ninja is
   `speed: 1.2, bounce: 1.25`. For a request outside the 27 built-in clips (a wave, drinking a potion),
   add a `custom_clips` entry rather than editing the library; see the same reference.
   Describe the desired anticipation, main pose, timing, recovery and any event; build and visually
   review the motion. A new custom clip appears in the preview's custom-action selector and is
   triggered with Q in the playable demo. Existing named clips keep their usual controls. Do not
   claim a game engine will trigger the animation or its effects without controller integration.

   For the user's own look made with an image generator, follow `references/ai-art.md` instead: you
   use an available image tool or prepare a prompt for the user, mark the joints and
   `scripts/cut_parts.py` cuts it into parts and checks every joint in motion.

3. **Check the look on a contact sheet before the full render.** It takes seconds, a full set about a
   minute, and a wrong palette is cheapest to catch here. Read the image and look at it.

   ```bash
   python scripts/contact_sheet.py --character c.json --clips idle,run,attack_1 --size 192 --max-frames 8 --out sheet.png
   ```

4. **Generate the set.**

   ```bash
   python scripts/generate.py --character c.json --preset hd --out out/c
   ```

5. **Run motion QA and fix what it reports.** Treat a FAIL as a bug in the motion, and work out which
   change caused it before touching thresholds. `references/smoothness.md` maps each check to its cause.

   ```bash
   python scripts/qa_motion.py out/c
   ```

6. **Do the visual review.** Numbers can't see a body hovering above the floor. Build the review sheets, look
   at every one yourself, and record a verdict. Follow `references/visual-review.md`. Blockers get
   fixed before delivery.

   ```bash
   python scripts/visual_review.py out/c
   python scripts/visual_review.py out/c --record verdict.json
   python scripts/visual_review.py out/c --check
   ```

7. **Show the result.** Give the user `out/c/preview.html`. It is a self-contained page with every clip
   (speed control, frame stepping, onion skin) and a playable demo, which is the real test of whether
   the set feels smooth. Then state which engine files apply to their project
   (`references/engine-integration.md`).

## Output

```
out/c/
├── preview.html        clip gallery + playable demo, one file
├── atlas.png/.json     trimmed, deduplicated, colour-bled atlas (JSON-hash: Phaser, PixiJS)
├── animations.json     engine-neutral manifest: fps, loop, events, speed, pivot, next clip
├── frames/<clip>/      loose PNGs
├── sheets/<clip>.png   one sheet per clip, wrapped to a grid
├── fx.png/.json        dust, hit spark, block spark, projectile
├── engine/             godot/, cocos/, unity/, web/ (player + CSS)
├── review/             sheets for the visual review
├── visual_report.json  recorded verdict
└── qa_report.json
```

## Keeping it smooth when you change things

These are the rules behind the numbers. `references/smoothness.md` has the reasoning.

- **Frame budget:** 30 fps for HD gives 25 frames per walk and 17 per run. Lowering fps below about 24
  on HD reads as choppy, while pixel art holds up at 12-15 because of its discrete look. To save
  texture memory, drop fps on slow clips only: `--fps-override idle=15,crouch_idle=15`.
- **Game speed comes from the manifest.** Move the character at `speed_px_s` for `walk`, `run`, etc.
  Any other speed makes the feet slide even though the animation itself is correct. Scale it if you
  draw the sprite scaled.
- **Clips hand over at shared poses.** When adding keys to a clip that follows another, start from the
  same named pose (`STANCE`, `CROUCH`, `RISE`, ...) in `scripts/sprite_anim/motions.py` so the seam stays
  continuous; QA's transition table checks this.
- **Fast actions get 2-3 frames plus a smear.** A swing over one frame is a teleport. Bunch the keys,
  don't remove them, and set `smear` on the strike keys.
- **Respect the events.** `takeoff`, `hit_on`/`hit_off` and `footstep` are frame-accurate in
  `animations.json`. Trigger physics, hitboxes and dust from them instead of timers.

## Reference files

Read these when the task reaches them:

- `references/basic-character-workflow.md`: default picture-to-character workflow, all fixed prompts, bounded repairs and walk approval
- `references/layered-art.md`: the production route for AI art: input contract, fixed layers, gates, QA
- `references/character-spec.md`: every spec field, cut-out mode for the user's own layered art, custom clips
- `references/ai-art.md`: AI-generated characters: the prompt, marking joints, cutting and checking
- `references/smoothness.md`: QA checks, skeleton constraints, causes and fixes; diagnosing stutter
- `references/visual-review.md`: how to do the AI visual review, the checklist and the verdict format
- `references/animation-principles.md`: timing tables and how to author new poses
- `references/engine-integration.md`: Unity, Godot, Cocos, Phaser, PixiJS, CSS, mini-games

## Limits to be upfront about

- Humanoid side-view rig only. Quadrupeds, flying enemies and blobs need a new rig and motion set.
- One facing: mirror with the engine's flip. There are no top-down or front-view sets.
- Procedural art has a clean cartoon look. For a specific art style, use cut-out mode with the
  user's art or AI-generated art; the motion stays the same. Cut-outs don't change facial expression
  and don't simulate cloth (`references/ai-art.md` lists the limits).
- Engine exports are verified to different degrees: Godot, Phaser, PixiJS and the CSS have been
  imported and played; Cocos and Unity have not. The table in `references/engine-integration.md`
  says which. Tell the user when handing them over, and fix whatever the import reports.
