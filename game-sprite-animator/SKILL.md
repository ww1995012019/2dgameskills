---
name: game-sprite-animator
description: >
  Generate complete, smooth 2D game character animation sets and export them as sprite sheets,
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

Every frame is computed from a skeleton, not drawn by an image model. That is what makes the output
smooth: poses come from continuous curves, so any frame rate is available, loops close exactly, and
feet stay planted. Joint limits, floor contact and clipping checks keep poses physically believable,
and you review the frames by eye before delivery. Reference images can't be traced; a look is described through a character spec or
supplied as layered art.

Requires Python 3 with `pillow` and `numpy`. Scripts are in `scripts/`, run from the skill root.

## Workflow

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
