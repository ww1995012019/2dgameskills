---
name: game-shooter-animator
description: >
  Generate side-scrolling 2D shooter character animation sets: soldiers with pistol, SMG, rifle,
  shotgun, sniper and rocket launcher, 9-direction aiming, firing with recoil and muzzle flash, weapon
  specific reloads, grenades, melee, run-and-gun, roll, slide, hurt and death, in HD or pixel-art style.
  Exports layered upper and lower body sprites plus baked full-body clips, muzzle positions per frame,
  and Unity, Godot, Cocos, Phaser, PixiJS and H5 files. Use this skill whenever the user wants a gun
  game character, shooter sprites, a run-and-gun game like Contra or Metal Slug, 枪战, 射击游戏素材,
  横版射击, 魂斗罗, 合金弹头, 持枪动作, 开枪动画, 换弹动画, soldier sprite sheets, or an H5 or mini-game
  with a character that shoots, even if they never say "sprite". For a sword or magic character
  with no guns, use game-sprite-animator. Not for top-down shooters, first-person weapon views or 3D.
---

# Game Shooter Animator

Every frame is computed from a skeleton, so frame rates, aim angles and weapons are all available
without redrawing. Joint limits, floor contact and clipping checks keep poses believable, and you
review the frames by eye before delivery. Reference images can't be traced; a look is described through a character spec.

Requires Python 3 with `pillow` and `numpy`. Scripts are in `scripts/`, run from the skill root.

## Why layers

A shooter needs every movement to combine with every aim angle and weapon. Baking that matrix would
take tens of thousands of frames. So the set is split, as Metal Slug did:

- **Lower body:** legs and pelvis (`idle`, `walk`, `run`, `backpedal`, `crouch_*`, jump chain). Each
  frame carries an `anchor`, the offset where the upper body sits.
- **Upper body, per weapon:** torso, head, arms and gun (`rifle_aim_p45`, `rifle_fire_0`, `rifle_reload`,
  `rifle_throw`, `rifle_melee`, `rifle_draw`). Each frame carries the `muzzle` position.
- **Full body:** actions that move everything (`sprint`, `roll`, `slide`, `hurt`, `death`, `death_blast`, `victory`).
- **Combos:** baked lower + upper pairs (`run_fire_0`, `idle_aim_0`) for engines or pages that want
  one sprite per state. Choose these when simplicity matters more than free aiming.

Pick layers for free aiming and running while reloading. Pick combos for a simple fixed-direction
game, CSS playback or a quick H5 mini-game.

## Workflow

1. **Pin down what's open.** Ask only about what the user left out and that changes the output:

   | Choice | Default | Options |
   |---|---|---|
   | Style | HD cartoon | `--preset hd`, `hd60`, `hd512`; pixel: `pixel48`, `pixel` (64), `pixel96` |
   | Character | closest of commando / swat / ghost / mercenary | a new spec |
   | Weapons | as in the spec | `pistol smg rifle shotgun sniper rocket`, first is primary |
   | Aim | 9 angles, every 22.5 degrees | `--aim-steps 5` halves the frames |
   | Integration | layers + default combos | `--combos run:fire_0,idle:aim_0` or `--combos none` |

   Each weapon adds about 130 frames at 30 fps, so request only what the game uses.

2. **Write the character spec** (`references/character-spec.md`). Copy the nearest file from
   `assets/characters/` and change colours, `head`, `weapons`, `body`, `style`.

3. **Check the look on a contact sheet before the full render.** Read the image and look at it.

   ```bash
   python scripts/contact_sheet.py --character c.json --clips run_fire_0,rifle_reload,death --size 192 --max-frames 8 --out sheet.png
   ```

   Lower and upper clips render alone here, showing half a soldier. That is correct. View a combo to
   see the whole character.

4. **Generate the set.**

   ```bash
   python scripts/generate.py --character c.json --preset hd --out out/c
   ```

5. **Run motion QA and fix what it reports.** Treat a FAIL as a bug in the motion. Work out the cause
   before touching thresholds. `references/motion-qa.md` maps each check to its cause.

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

7. **Show the result.** Give the user `out/c/preview.html`: every clip, a lower + upper picker, and a
   playable range with mouse aim, targets, grenades and weapon switching. That demo is also the
   reference implementation for the game side. Then point them at the files for their engine
   (`references/integration.md`).

## Output

```
out/c/
├── preview.html        clip gallery + playable demo, one file
├── atlas.png/.json     trimmed atlas (JSON-hash: Phaser, PixiJS); splits into pages past 4096 px
├── animations.json     fps, loop, events, speed, layer, weapon, aim, anchors, muzzle, pivot
├── frames/<clip>/      loose PNGs
├── sheets/<clip>.png   one sheet per clip
├── fx.png/.json        dust, sparks, bullet, impact, explosion, grenade, rocket
├── engine/             godot/, cocos/, unity/, web/ (player + CSS for full-body clips)
├── review/             sheets for the visual review
├── visual_report.json  recorded verdict
└── qa_report.json
```

## What keeps a shooter from feeling choppy

- **Fire rate lands on whole frames.** A 0.1 s rifle at 30 fps is exactly 3 frames per shot. A rate
  between frames would drop the flash on some shots, which reads as stutter even if the animation is
  right. `shot_frames` handles this; combo lengths snap to whole shots for the same reason.
- **Aim eases through the angles.** Don't jump from 0 to 45 degrees. Turn the aim value at about 700 degrees
  per second and pick the nearest sprite, as the demo does.
- **Keep the firing frame when the aim changes.** Copy `frame` to the new `fire_*` clip so the rate
  doesn't reset. Reset it and a player sweeping their aim fires slower.
- **Spawn bullets from the manifest.** `muzzle[frame]` plus the lower `anchor` is the barrel tip on that
  frame. A fixed offset drifts off the gun at any angle except 0.
- **Trigger from events.** Use `shot` for bullets and ammo, `reload_done` for refilling, `grenade`,
  `hit_on`, `takeoff`, `footstep`. These are frame-accurate.
- **Game speed comes from `speed_px_s`,** times your sprite scale, or feet slide. It's negative on
  `backpedal`. Use the absolute value.
- **Buffer input for about 130 ms,** and restart a finished one-shot even if its name is unchanged.

## Reference files

- `references/character-spec.md`: every spec field, weapon data, adding a weapon
- `references/motion-qa.md`: QA checks, skeleton constraints, causes and fixes, timing tables
- `references/visual-review.md`: how to do the AI visual review, the checklist and the verdict format
- `references/integration.md`: engine setup, layered drawing, aim and firing logic

## Limits to be upfront about

- Side view only, one facing: mirror with the engine's flip. No top-down or first-person view.
- Humanoid rig only: vehicles, turrets, and non-human enemies need new work.
- In layered mode, head-attached cloth uses an idle wind, so a headband won't stream while running.
  Combos and full-body clips simulate it properly.
- Upper-body clips have no torso lean from the legs. It reads fine at run angles; baked combos have it.
- Procedural art has a clean cartoon look. There is no cut-out mode for the user's own art here.
- Engine exports haven't been opened in those engines. `references/integration.md` lists what was
  actually verified. Tell the user when handing them over, and fix whatever the import reports.
