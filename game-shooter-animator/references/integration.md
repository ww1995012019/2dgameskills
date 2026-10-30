# Engine integration

All clips face right and share one feet pivot, `pivot` in `animations.json`. Mirror with the engine's
flip for left.

Verification status, so you can tell the user what is proven:

| Export | Checked how |
|---|---|
| `atlas.png`, `animations.json`, `sprite-player.js` | Frames rebuilt from the atlas match the source; demo state machine run scripted |
| `atlas.json` (JSON-hash) | Structure and bounds only; not loaded in Phaser or PixiJS |
| `sprites.css` | Structure only; not played in a browser |
| Godot `.tres`, Cocos `.plist` | Parsed and cross-referenced; not imported into the editors |
| Unity `SpriteSetImporter.cs` | Never compiled or run. It imports frames, not layer anchors |

## The layered contract

Use two sprites parented to one character node:

1. Draw the lower clip at the character position.
2. Draw the upper clip offset by `clips[lower].anchors[lowerFrame]`, as `[dx, dy]` in pixels, y down.
   Mirror `dx` when flipped, and multiply by your sprite scale.
3. When spawning a bullet: `position + (muzzle[upperFrame] + anchor) * scale`, mirroring x when flipped.
4. Choose the upper clip from aim: round the aim angle to the nearest key in `aims`, which maps an angle to
   its tag (`22` to `p22`), then `<weapon>_fire_<tag>` or `<weapon>_aim_<tag>`.

Full-body clips (`roll`, `slide`, `hurt`, `death`, combos) replace both layers: hide the upper sprite.

## H5, Canvas, WeChat mini-games

`engine/web/sprite-player.js` provides `SpritePlayer`, `drawLayered` and `muzzleAt`:

```js
const doc = await (await fetch("animations.json")).json();
const img = new Image(); img.src = "atlas.png"; await img.decode();
const legs = new SpritePlayer(doc, [img]), torso = new SpritePlayer(doc, [img]);
legs.play("run"); torso.play("rifle_fire_0");
let last = performance.now();
function tick(now) {
  const dt = now - last; last = now;
  legs.update(dt);
  for (const e of torso.update(dt)) {
    if (e === "shot") spawnBullet(...muzzleAt(legs, torso, x, groundY, { flip }));
  }
  ctx.clearRect(0, 0, w, h);
  drawLayered(ctx, legs, torso, x, groundY, { flip });
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
```

Changing aim while firing, keep the fire rate by carrying the frame across:

```js
const { frame, acc } = torso;
torso.play(`rifle_fire_${tag}`, { restart: true });
torso.frame = frame % torso.clip.frames.length;
torso.acc = acc;
```

The `step` function in `preview.html` is a complete working controller: aim easing, input buffering,
weapon switching, reloads, grenades and bullet spawning.

For WeChat mini-games, use `wx.createImage()` and `canvas.requestAnimationFrame`, and keep the atlas at
or under 2048 px on low-end devices: use a pixel preset, `--size 192`, `--aim-steps 5`, or fewer weapons.

## Pure CSS for activity pages

`engine/web/sprites.css` covers full-body clips and combos only, since CSS can't sync two layers:

```html
<link rel="stylesheet" href="engine/web/sprites.css">
<div class="sprite run_fire_0"></div>
```

## Phaser 3

```js
this.load.atlas("hero", "atlas.png", "atlas.json");
this.load.json("hero_anims", "animations.json");
// create():
const doc = this.cache.json.get("hero_anims");
for (const [key, c] of Object.entries(doc.clips)) {
  this.anims.create({
    key, frameRate: c.fps, repeat: c.loop ? -1 : 0,
    frames: c.frames.map((_, i) => ({ key: "hero", frame: `${key}_${String(i).padStart(3, "0")}` })),
  });
}
const origin = [doc.pivot[0] / doc.frame_size, doc.pivot[1] / doc.frame_size];
const legs = this.add.sprite(x, y, "hero").setOrigin(...origin);
const torso = this.add.sprite(x, y, "hero").setOrigin(...origin);
// update(): position torso from the legs' current anchor
const a = doc.clips[legs.anims.currentAnim.key].anchors[legs.anims.currentFrame.index - 1];
torso.setPosition(legs.x + a[0] * (legs.flipX ? -1 : 1), legs.y + a[1]);
```

## Godot 4

Copy `atlas.png` and `engine/godot/sprite_frames.tres` to the project root. Use two `AnimatedSprite2D`
nodes sharing the resource. On each frame change of the lower sprite, set the upper's `position` from
that frame's anchor, loaded from `animations.json`. Set `offset` on both so the feet sit on the node
origin: `offset = (frame_size/2 - pivot.x, frame_size/2 - pivot.y)`.

## Cocos Creator

Import `atlas.png` and `engine/cocos/atlas.plist` together. Use two child nodes with `Sprite` components,
and keep Trim off so frames hold their source size and pivot. Set the upper node's position from the
lower clip's anchor, with y negated since Cocos is y-up.

## Unity

1. Copy `engine/unity/SpriteSetImporter.cs` to `Assets/Editor/`.
2. Copy `atlas.png` and `animations.json` under `Assets/`.
3. Select `animations.json`, then Tools > Sprite Set > Import Selected.

Use two child `SpriteRenderer`s. Read `anchors` from the JSON at runtime and offset the upper one, dividing
by Pixels Per Unit. Add `public void OnSpriteEvent(string name)` to receive `shot`, `reload_done` and others.

## Texture budget

| Set | Frames | Atlas |
|---|---|---|
| hd, 2 weapons, 9 aims, default combos | about 1400 | about 4096×3400 |
| pixel, 64 px, 2 weapons, 9 aims | about 760 | about 800×670 |

Reduce with `--aim-steps 5`, fewer `weapons`, `--combos none`, or `--fps-override`. Slow-firing weapons
take the most frames, since the whole cooldown is a clip for every aim angle.
