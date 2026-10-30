# Side-view wolf integration

Use `animations.json` for FPS, loop flags, per-clip `speed_px_s`, fixed `pivot`, frame regions,
page files and events. Move at `speed_px_s × scale`, or even correctly authored paws will slide.
All four clips face right; horizontal flip about the shared pivot handles left movement.

`footstep_hind_near`, `footstep_hind_far`, `footstep_front_near`, `footstep_front_far` occur on
sampled touchdown frames, not rounded nominal times. Trot emits both diagonal foot events together.
The preview's `QuadrupedController` uses the exact exported `SpritePlayer`, keeps loop phase on gait
changes, and suppresses repeated current-frame events when switching clips.

```js
// Load every atlas page, rather than assuming one atlas.png.
const wolf = new QuadrupedController(doc, images, 2);
const events = wolf.update(dtMs, { direction: left ? -1 : right ? 1 : 0, gait: 'trot' });
wolf.player.draw(ctx, wolf.x, floorY, { flip: wolf.flip, scale: wolf.scale });
```

- Godot: copy all atlas pages, the exported `.import` files and `sprite_frames.tres`; import in the
  editor. `.import` disables Fix Alpha Border so HD transparent edge colour is retained.
- Phaser/PixiJS: load each JSON-hash atlas in `pages`, find frame pages by name (`walk_003`, etc.),
  and preserve the full-cell pivot after trimming. Retain normalized phase on loop changes.
- CSS: keep `engine/web/sprites.css` and `sheets/` at their generated relative locations.
- Unity importer is provided but has not been compiled; Cocos `.plist` receives structural checks.

Export resources do not create a game state machine. Native engine frame restoration/playback
checks are distinct from the Canvas controller's actual movement, foot-event and keyboard tests.
The wolf now has attack/hurt/death one-shots; independent aim and top-down views are not included. Gait changes keep
phase but do not create a physically blended transition between different contact schedules.

Repository checks: `dev/verify_exports_sprite.py`, `dev/godot_smoke.py`, `dev/web_engines.js`,
`dev/test_quadruped_controller.js`, `dev/test_quadruped_preview.js`. Read the latest HANDOVER.md
for which native engines and complete output sets were actually checked.

First-version native validation: both `hd` and `pixel` were imported and all four loops played
in Godot 4.3, Phaser 3.80.1 and PixiJS 8.6.6 at 60 and 144 Hz. Source frames were restored and
compared, with no playback failures. Both Chromium previews passed keyboard walk/trot/run,
left/right and stop checks. The native tools use `--all-clips` so idle is not the only loop tested.
Unity remains uncompiled; Cocos remains structurally checked only. Native loop tests do not
prove contact-preserving gait changes inside those engines.

Combat controls: J plays a planted forward lunge/bite, H reacts, X dies/revives. Attack uses
`hit_on`/`hit_off`; consumers apply damage in that window. The preview training target records
one hit on `hit_on` only when facing it within range. Hurt and attack recover to idle, death
holds its final collapsed, closed-eye frame until revive. Reaction inputs interrupt locomotion;
movement is locked during the reaction. There is no airborne root-motion pounce or autonomous AI.
