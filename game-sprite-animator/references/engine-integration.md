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
| `atlas.json` (JSON-hash) | Structure and bounds only; not loaded in Phaser or PixiJS |
| `sprites.css` | Structure only; not played in a browser |
| Godot `.tres`, Cocos `.plist` | Parsed and cross-referenced; not imported into the editors |
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
this.load.atlas("hero", "atlas.png", "atlas.json");
this.load.json("hero_anims", "animations.json");
// create():
const doc = this.cache.json.get("hero_anims");
for (const [key, c] of Object.entries(doc.clips)) {
  this.anims.create({
    key,
    frames: c.frames.map((_, i) => ({ key: "hero", frame: `${key}_${String(i).padStart(3, "0")}` })),
    frameRate: c.fps,
    repeat: c.loop ? -1 : 0,
  });
}
const hero = this.add.sprite(x, y, "hero").setOrigin(doc.pivot[0] / doc.frame_size, doc.pivot[1] / doc.frame_size);
```

## PixiJS

```js
const sheet = await PIXI.Assets.load("atlas.json");
const hero = new PIXI.AnimatedSprite(sheet.animations.run);
hero.animationSpeed = 30 / 60;   // clip fps / ticker fps
hero.anchor.set(doc.pivot[0] / doc.frame_size, doc.pivot[1] / doc.frame_size);
hero.play();
```

## Godot 4

Copy `atlas.png` and `engine/godot/sprite_frames.tres` to the project root (the `.tres` expects
`res://atlas.png`; edit that path otherwise). On an `AnimatedSprite2D`, set `sprite_frames` to the
resource. Set `offset` so the feet sit on the node origin: `offset = (frame_size/2 - pivot.x, frame_size/2 - pivot.y)`.
In import settings, use Lossless compression and, for pixel art, `Nearest` filtering on the node.

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
