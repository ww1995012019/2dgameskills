# Engine integration

All clips face right and share one feet pivot, `pivot` in `animations.json`. Mirror with the engine's
flip for left. Whatever the engine, keep these three:

1. Anchor on the manifest pivot, not on each frame's bounds.
2. Move the character at the clip's `speed_px_s`, multiplied by your sprite scale.
3. Drive gameplay from `events`, which are frame numbers.

Verification status, so you can tell the user what is proven:

| Export | Checked how |
|---|---|
| `atlas.png`, `animations.json`, `sprite-player.js` | Frames rebuilt from the atlas match the source; player run in a browser and at 30-240 Hz |
| `atlas.json` (JSON-hash) | Loaded in Phaser 3.80 and PixiJS 8.6 in Chromium as shown below: every frame matches its source frame, playback order and timing checked at 60 and 144 Hz |
| `sprites.css` | Played in Chromium: every frame matches its source frame; not checked in Safari or on phones |
| Godot `.tres` + `.import` | Imported into Godot 4.3: every frame matches its source frame, `AnimatedSprite2D` playback order, timing and loop checked at 60 and 144 Hz |
| Cocos `.plist` | Parsed and cross-referenced; not imported into the editor |
| Unity `SpriteSetImporter.cs` | Never compiled or run |

## H5, Canvas, WeChat mini-games

`engine/web/sprite-player.js` plays `animations.json`:

```js
const doc = await (await fetch("animations.json")).json();
const img = new Image(); img.src = "atlas.png"; await img.decode();
const hero = new SpritePlayer(doc, [img]);
hero.play("run");
let last = performance.now();
function tick(now) {
  const events = hero.update(now - last); last = now;
  events.forEach(onAnimationEvent);
  ctx.clearRect(0, 0, w, h);
  hero.draw(ctx, x, groundY, { flip: facingLeft });
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
```

In WeChat mini-games, use `wx.createImage()`, `canvas.requestAnimationFrame`, and bundle the JSON with
`require` or read it via the file system manager. Keep the atlas at or under 2048 px for low-end
devices: render at `--size 192` or lower `--fps-override` on slow clips.

## Follow-up clips and held guard

`next` is a controller hint, not an automatic engine transition. `next_frame`, when present,
is the zero-based entry frame in that next clip (default 0). `block_hit` resumes the last frame
of `block`, keeping GUARD raised; replaying frame 0 would repeat the idle-to-guard entry.
The generator computes the index from the actual output frame count, including FPS overrides.
The outgoing cloth blend and motion QA use the same target pose.

For the Canvas player, when the controller decides to take a finished clip's follow-up:

```js
const finished = hero.clip;
if (hero.done && finished.next && doc.clips[finished.next]) {
  hero.play(finished.next, { restart: true, frame: finished.next_frame ?? 0 });
}
```

While guard is held, keep the final `block` frame displayed. In the playable preview, I holds
guard and H simulates a hit: a fully raised guard plays `block_hit`; otherwise H plays `hurt`.
Releasing I during the reaction returns to idle after it finishes. Repeated hits must each
trigger exactly one `block_spark`.

Godot, Phaser, PixiJS, Unity and Cocos controllers must likewise use the manifest's entry frame
when wiring their own state transitions; the exported animation resources do not create a state
machine. The held-guard controller path is exercised by the Node preview test. Existing engine
smoke tests verify imported frames and playback, not this gameplay transition in each engine.

## Pure CSS for activity pages

For a looping mascot on a web page with no JS. `engine/web/sprites.css` references `../../sheets/`, so
keep that layout or edit the paths. It uses per-frame keyframes rather than a single `steps()` strip,
because a 72-frame strip at 256 px is 18432 px wide, past mobile texture limits.

```html
<link rel="stylesheet" href="engine/web/sprites.css">
<div class="sprite idle"></div>
```

Swap the second class to change clip. For a page with several clips, Canvas costs less memory.

## Phaser 3

```js
// preload(): the manifest, then every atlas page it lists (big sets split into atlas_0, atlas_1...)
this.load.json("hero_anims", "animations.json");
this.load.once("filecomplete-json-hero_anims", (key, type, doc) => {
  doc.pages.forEach((p, i) => this.load.atlas(`hero${i}`, p.file, p.file.replace(".png", ".json")));
});
// create():
const doc = this.cache.json.get("hero_anims");
const pageOf = {};
doc.pages.forEach((p, i) => this.textures.get(`hero${i}`).getFrameNames().forEach((f) => { pageOf[f] = `hero${i}`; }));
const frameName = (clip, i) => `${clip}_${String(i).padStart(3, "0")}`;
for (const [key, c] of Object.entries(doc.clips)) {
  this.anims.create({
    key, frameRate: c.fps, repeat: c.loop ? -1 : 0,
    frames: c.frames.map((_, i) => ({ key: pageOf[frameName(key, i)], frame: frameName(key, i) })),
  });
}
const hero = this.add.sprite(x, y, "hero0").setOrigin(doc.pivot[0] / doc.frame_size, doc.pivot[1] / doc.frame_size);
hero.play("run");
```

## PixiJS

```js
const doc = await (await fetch("animations.json")).json();
// One sheet per atlas page; frames are looked up by name, so a clip may span pages.
const sheets = await Promise.all(doc.pages.map((p) => PIXI.Assets.load(p.file.replace(".png", ".json"))));
const textures = Object.assign({}, ...sheets.map((s) => s.textures));
const clipTextures = (name) => doc.clips[name].frames.map((_, i) => textures[`${name}_${String(i).padStart(3, "0")}`]);
const hero = new PIXI.AnimatedSprite(clipTextures("run"));
hero.animationSpeed = doc.clips.run.fps / 60;   // clip fps / ticker fps
hero.loop = doc.clips.run.loop;
hero.anchor.set(doc.pivot[0] / doc.frame_size, doc.pivot[1] / doc.frame_size);
hero.play();
```

## Godot 4

Copy the atlas pages (`atlas.png`, or `atlas_0.png`, `atlas_1.png`... for big sets), their `.import` files from
`engine/godot/`, and `engine/godot/sprite_frames.tres` to the project root (the `.tres` expects
`res://atlas.png` and so on; edit the paths otherwise). On an `AnimatedSprite2D`, set `sprite_frames` to the
resource. Set `offset` so the feet sit on the node origin: `offset = (frame_size/2 - pivot.x, frame_size/2 - pivot.y)`.
The `.import` file sets Lossless compression and turns off Fix Alpha Border: that default recolours pixels
under about 7% alpha and gives soft HD edges a faint dark fringe; the atlas is already edge-bled. For pixel
art, set `Nearest` filtering on the node.

## Cocos Creator

Import `atlas.png` and `engine/cocos/atlas.plist` together; Creator creates a SpriteAtlas. Build clips
with an `Animation` component from frames `<clip>_000.png` onward at the clip's fps. Keep the `Sprite`
component's Trim off (RAW or Custom size) so frames keep their source size and the pivot holds.

## Unity

1. Copy `engine/unity/SpriteSetImporter.cs` to `Assets/Editor/`.
2. Copy `atlas.png` and `animations.json` to a folder under `Assets/`.
3. Select `animations.json`, then Tools > Sprite Set > Import Selected.

It slices the sprites with the shared pivot and writes an `.anim` per clip, with events calling
`OnSpriteEvent(string)` on the GameObject. Add a receiver, or Unity logs a missing-method warning:

```csharp
public void OnSpriteEvent(string name) { /* footstep, hit_on, takeoff... */ }
```

Set Filter Mode to Point for pixel-art sets. Set Pixels Per Unit to match your world scale.

## Texture budget

| Set | Frames | Atlas |
|---|---|---|
| hd, 256 px, 30 fps, all clips | about 610 | about 3200×2700 |
| hd with `--fps-override idle=15,crouch_idle=15,idle_look=15` | about 510 | smaller |
| pixel, 64 px, 15 fps | about 310 | under 1024×1024 |

Atlases larger than 4096 px split across `atlas_0.png`, `atlas_1.png`, and so on.
