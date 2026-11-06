---
name: game-sprite-animator
description: >
  (Deprecated: use game-animator.) Generate and review supported 2D game character animation sets and export them as sprite sheets,
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

> **Deprecated standalone package.** Install `game-animator` instead; it contains this mode
> unchanged. This folder is generated from `game-animator/modes/game-sprite-animator/` and is kept only for
> existing installs.

# Game Sprite Animator

Read [release-gates.md](references/release-gates.md) before binding art and again before delivering
any clip of a bound character. In short, each of these blocks delivery even when numeric QA passes:

- Neck flaps, exposed cuts, pasted-on heads, clawing empty hands or broken wrists
  (`review/` head/neck and near/far hand close-ups at full size, during playback).
- Split trousers, waist slits, doubled panels, pinched or C-shaped thighs, exposed hidden
  waistband cuts (`review/hips_*.png`, `garment_edges_*.png`, all frames, against the source).
- Ordinary-run limp, uneven steps or abrupt drops (`run_support_00.png` and fixed-ground playback).
- Any change to art, trace, atlas, sheets or preview invalidates the previous visual review.

For complete aligned layers with known joints, prefer the [zero-generation binding entry](references/known-joint-binding.md).
When the user rejects what they saw, follow the [repair loop](references/repair-loop.md): render only
the affected clips, show `compare_clips.py` GIFs, and run the full verification once they approve.

Procedural and bound frames are computed from a skeleton; a look is described through a character spec or supplied as
layered art (reference images can't be traced). An independently drawn frame sheet can also be packaged
without binding. Requires Python 3 with `pillow` and `numpy`.
Scripts are in `scripts/`, run from the skill root.


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
For a fitted, short-haired character carrying a rifle in **idle and run only**, use the separate
guarded [source-preserved carry profile](references/rifle-carry.md). It keeps the registered
upper-body illustration, both hands and rifle on one drawing surface. It does not add two-hand
weapon support to the basic profile, and does not provide aiming, firing or reload animation.
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

## Skateboard and independently drawn frames

For a **procedural empty-handed** character, set `gait.skateboard.profile` to `glide_v1` and export
`idle,skateboard`. The in-place loop renders the board behind the rider, keeps both sole proxies on
the deck, and adds `board` evidence to motion QA. It does not animate mount/dismount or advance the
game world. Board width and colors are configurable; see `references/character-spec.md`. This
profile rejects puppet and cut-out art until those inputs have a separately validated board workflow.
Inspect the actual shoes and board in all frames; numeric checks do not establish painted contact.

To package an independently created, complete transparent frame sheet, use `scripts/import_frames.py`
as documented in `references/character-spec.md`. Its output uses the normal atlas, manifest, engine
adapters and preview, and records `source.kind: precomposed_frames` and `skeleton_binding: false`.
The source sheet already contains the whole character and prop; import does not create or verify a
rig, feet, joints, cloth, or transitions. The owner of a basic-side or rifle-carry job may not use
this route to sidestep its stage gates, and the importer rejects assets inside those jobs. Inspect
each frame and playback; report the absence of rig/contact evidence.

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

- `references/release-gates.md`: every blocker for bound art (head/neck/hands, waist and garments, run rhythm)
- `references/repair-loop.md`: after a user rejection: quick comparison GIFs first, full verification after approval
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
