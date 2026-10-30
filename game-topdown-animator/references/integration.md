# Eight-direction integration

`animations.json` is the source of truth. It contains 48 clips: six actions × eight directions.
`direction_order` follows screen-space angles clockwise from right:
right, down_right, down, down_left, left, up_left, up, up_right.
Each `directions` entry has a unit screen vector. `speed_px_s` is a scalar screen speed;
`velocity_px_s` is that speed multiplied by the direction vector, so diagonals are not faster.

Use the common feet `pivot` for every frame, including trimmed atlas regions. Draw in world Y order
when several characters overlap. The camera is fixed 3/4, not a true overhead camera.

All eight sets of frames are already baked. `mirror_of` is provenance, **not** an instruction to
flip them again. Leftward equipment is mirrored and changes handedness. Asymmetric equipment needs
separately authored left-facing art; that is outside this first version.

## Canvas and mini-games

`engine/web/sprite-player.js` contains `SpritePlayer` and `TopDownController` (also CommonJS exports).
Load every page from `doc.pages`; a single `atlas.png` must not be assumed.

```js
const doc = await (await fetch('animations.json')).json();
const images = await Promise.all(doc.pages.map(p => new Promise((ok, no) => {
  const im = new Image(); im.onload = () => ok(im); im.onerror = no; im.src = p.file;
})));
const hero = new TopDownController(doc, images, 2);
// Every simulation tick. x/y may be keyboard differences; the controller normalizes them.
const events = hero.update(1000 / 60, { x: right-left, y: down-up, run: shift, attack: justPressedJ });
hero.player.draw(ctx, hero.x, hero.y, { scale: hero.scale });
```

`attack`, `hurt`, `death` are edge-triggered inputs. They lock movement during their one-shot.
Attack and hurt recover to idle; death remains down until `revive`. The controller keeps phase
when turning or switching walk/run, suppresses duplicate current-frame events on turns, and
emits `footstep`, `hit_on`, `hit_off` and `body_thud` from the manifest.
`preview.html` is self-contained and uses this exact controller. It has keyboard eight-way movement,
run, attack, hurt, death/revive and an eight-direction gallery.

## Engine files

- **Godot:** copy *every* atlas PNG, its `engine/godot/*.import`, and `sprite_frames.tres` into a
  project; let the editor import. The `.import` settings preserve transparent edge colour.
  Use `AnimatedSprite2D`, set its clip name from action + direction, retain phase when turning,
  and translate by the normalized input vector times the scalar manifest speed.
- **Phaser / PixiJS:** load each page's JSON-hash atlas from `pages`. A frame is named
  `<clip>_<zero-padded index>`, e.g. `walk_up_right_003`. Find its page by frame name; do not assume
  all clips fit one page. Anchor reconstructed full cells on `pivot / frame_size`.
- **CSS:** keep `engine/web/sprites.css` and `sheets/` in their generated relative layout.
- **Cocos:** `.plist` receives structural verification only. Unity importer is provided for parity
  with the existing skills but has not been compiled or imported into Unity.

Animation resources do not create engine gameplay state machines. Engine smoke tests exercise
atlas restoration and individual clip playback, not the full eight-way gameplay controller in each
engine. The Canvas controller and preview receive their own movement/turning/event tests.

## Validation

Repository commands (from the repository root):

```bash
python dev/verify_exports_sprite.py <set-directory>
python dev/godot_smoke.py <set-directory>
CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node dev/web_engines.js <set-directory>
node dev/test_topdown_controller.js <set-directory>/animations.json
CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium node dev/test_topdown_preview.js <set-directory>
```

Read HANDOVER.md for the current run's evidence. Do not equate generated files, structural checks,
native import/playback and gameplay integration; report what was actually executed.

Current first-version evidence: both templates in `hd` and `pixel` (four complete 48-clip sets)
were checked with Godot 4.3, Phaser 3.80.1 and PixiJS 8.6.6 in Chromium. Every exported frame was
restored and compared, and representative looping/one-shot clips played at 60/144 Hz. The four
Canvas previews also received actual keyboard movement/attack checks. Unity remains untested;
Cocos is structural only. These results do not establish engine gameplay state-machine behavior.
