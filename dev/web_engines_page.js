// Runs inside the page for dev/web_engines.js: shared helpers, then one function per engine.
const load = (src) => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src; });
const pixels = (src, size) => { const c = document.createElement("canvas"); c.width = c.height = size;
  const g = c.getContext("2d"); g.drawImage(src, 0, 0); return g.getImageData(0, 0, size, size).data; };
// Premultiplied compare; both sides come back through getImageData, so only GPU rounding differs.
// Returns [max error, "x,y got rgba want rgba" at the worst pixel].
function frameError(a, b, size) {
  let worst = 0, at = 0;
  for (let i = 0; i < a.length; i += 4) {
    const aa = a[i + 3], bb = b[i + 3];
    let e = Math.abs(aa - bb);
    for (let k = 0; k < 3; k++) e = Math.max(e, Math.abs(((a[i + k] * aa) / 255) - ((b[i + k] * bb) / 255)));
    if (e > worst) { worst = e; at = i; }
  }
  const px = (d) => Array.from(d.slice(at, at + 4)).join(",");
  return [worst, ((at / 4) % size) + "," + Math.floor(at / 4 / size) + " got " + px(a) + " want " + px(b)];
}
const pad = (i) => String(i).padStart(3, "0");
function pickClips(doc) {
  if (window.SMOKE_ALL_CLIPS) return Object.keys(doc.clips);
  const seen = {}, out = [];
  for (const [n, c] of Object.entries(doc.clips)) { const k = c.fps + "_" + c.loop; if (!seen[k]) { seen[k] = 1; out.push(n); } }
  return out;
}
// shown: frame index per tick. Same rules as dev/godot/smoke_test.gd.
function judge(fail, name, c, hz, shown, finished) {
  const n = c.frames.length, per = hz / c.fps, runs = [];
  for (const f of shown) { if (runs.length && runs[runs.length - 1][0] === f) runs[runs.length - 1][1]++; else runs.push([f, 1]); }
  for (let k = 0; k < runs.length; k++) {
    const want = c.loop ? k % n : Math.min(k, n - 1);
    if (runs[k][0] !== want) { fail(name + " @" + hz + "Hz: frame order " + runs.map((r) => r[0]).join(",")); return; }
    if (k > 0 && k < runs.length - 1 && Math.abs(runs[k][1] - per) > 1) fail(name + " @" + hz + "Hz: frame " + runs[k][0] + " held " + runs[k][1] + " ticks, expected " + per.toFixed(1));
  }
  if (c.loop && finished) fail(name + ": looping clip reported complete");
  if (!c.loop && !finished) fail(name + ": one-shot clip never reported complete");
}
const ticksFor = (c, hz) => Math.ceil(hz * c.frames.length / c.fps) * (c.loop ? 2 : 1) + Math.ceil(2 * hz / c.fps) + 4;

async function runPhaser(fail) {
  const doc = await (await fetch("/set/animations.json")).json();
  const size = doc.frame_size, [px, py] = doc.pivot;
  const scene = await new Promise((ok) => new Phaser.Game({
    type: Phaser.CANVAS, width: size, height: size, transparent: true, banner: false, audio: { noAudio: true },
    scene: {
      preload() {   // straight from engine-integration.md, with paths under /set/
        this.load.json("hero_anims", "/set/animations.json");
        this.load.once("filecomplete-json-hero_anims", (key, type, doc) => {
          doc.pages.forEach((p, i) => this.load.atlas(`hero${i}`, "/set/" + p.file, "/set/" + p.file.replace(".png", ".json")));
        });
      },
      create() { ok(this); },
    },
  }));
  const game = scene.game;
  game.loop.sleep();                 // drive the clock by hand from here on
  {   // create(), straight from engine-integration.md
    const doc = scene.cache.json.get("hero_anims");
    const pageOf = {};
    doc.pages.forEach((p, i) => scene.textures.get(`hero${i}`).getFrameNames().forEach((f) => { pageOf[f] = `hero${i}`; }));
    const frameName = (clip, i) => `${clip}_${String(i).padStart(3, "0")}`;
    for (const [key, c] of Object.entries(doc.clips)) {
      scene.anims.create({
        key, frameRate: c.fps, repeat: c.loop ? -1 : 0,
        frames: c.frames.map((_, i) => ({ key: pageOf[frameName(key, i)], frame: frameName(key, i) })),
      });
    }
  }
  const hero = scene.add.sprite(px, py, "hero0").setOrigin(px / size, py / size);
  let t = 0;
  const step = (dt) => { t += dt; game.step(t, dt); };
  let checked = 0;
  for (const [name, c] of Object.entries(doc.clips)) {
    const a = scene.anims.get(name);
    if (a.frames.length !== c.frames.length) fail(name + ": " + a.frames.length + " frames, manifest " + c.frames.length);
    if (a.frameRate !== c.fps) fail(name + ": frameRate " + a.frameRate);
    if (a.repeat !== (c.loop ? -1 : 0)) fail(name + ": repeat " + a.repeat);
    for (let i = 0; i < c.frames.length; i++) {
      hero.anims.stop();
      const af = a.frames[i];
      if (!af || !af.frame || af.frame.name !== name + "_" + pad(i)) { fail(name + "#" + i + ": frame missing from the atlas"); continue; }
      hero.setTexture(af.textureKey, af.textureFrame); step(16);
      const [err, where] = frameError(pixels(game.canvas, size), pixels(await load("/set/frames/" + name + "/" + name + "_" + pad(i) + ".png"), size), size);
      if (err > 3) fail(name + "#" + i + ": pixels differ from the source frame (max error " + err.toFixed(1) + " at " + where + ")");
      checked++;
    }
  }
  const played = [];
  for (const hz of [60, 144]) for (const name of pickClips(doc)) {
    const c = doc.clips[name]; let finished = false; const shown = [];
    hero.removeAllListeners(); hero.on("animationcomplete", () => { finished = true; });
    hero.play(name);
    for (let k = 0; k < ticksFor(c, hz); k++) { shown.push(Number(hero.frame.name.slice(-3))); step(1000 / hz); }
    judge(fail, name, c, hz, shown, finished); played.push(name + "@" + hz);
  }
  game.destroy(true);
  return { checked, played };
}

async function runPixi(fail) {
  const doc = await (await fetch("/set/animations.json")).json();
  const size = doc.frame_size, [px, py] = doc.pivot;
  const app = new PIXI.Application();
  await app.init({ width: size, height: size, backgroundAlpha: 0, preference: "webgl", autoStart: false, antialias: false,
                   preserveDrawingBuffer: true });
  // Straight from engine-integration.md, with paths under /set/:
  const sheets = await Promise.all(doc.pages.map((p) => PIXI.Assets.load("/set/" + p.file.replace(".png", ".json"))));
  const textures = Object.assign({}, ...sheets.map((s) => s.textures));
  const clipTextures = (name) => doc.clips[name].frames.map((_, i) => textures[`${name}_${String(i).padStart(3, "0")}`]);
  let checked = 0;
  const hero = new PIXI.Sprite();
  hero.anchor.set(px / size, py / size); hero.position.set(px, py);
  app.stage.addChild(hero);
  for (const [name, c] of Object.entries(doc.clips)) {
    const frames = clipTextures(name);
    for (let i = 0; i < c.frames.length; i++) {
      if (!frames[i]) { fail(name + "#" + i + ": frame missing from the atlas"); continue; }
      hero.texture = frames[i];
      // Read the canvas the page shows. renderer.extract.canvas came back with soft edges
      // darkened by their own alpha, while the canvas on screen matches the source.
      app.renderer.render(app.stage);
      const [err, where] = frameError(pixels(app.canvas, size), pixels(await load("/set/frames/" + name + "/" + name + "_" + pad(i) + ".png"), size), size);
      if (err > 3) fail(name + "#" + i + ": pixels differ from the source frame (max error " + err.toFixed(1) + " at " + where + ")");
      checked++;
    }
  }
  const played = [];
  for (const hz of [60, 144]) for (const name of pickClips(doc)) {
    const c = doc.clips[name]; let finished = false; const shown = [];
    const anim = new PIXI.AnimatedSprite(clipTextures(name), false);
    anim.animationSpeed = c.fps / 60;        // clip fps / ticker fps, as the docs say
    anim.loop = c.loop; anim.onComplete = () => { finished = true; };
    anim.play();
    for (let k = 0; k < ticksFor(c, hz); k++) { shown.push(anim.currentFrame); anim.update({ deltaTime: 60 / hz, deltaMS: 1000 / hz }); }
    judge(fail, name, c, hz, shown, finished); played.push(name + "@" + hz);
  }
  app.destroy();
  return { checked, played };
}
