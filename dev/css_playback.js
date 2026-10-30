// Plays engine/web/sprites.css in Chromium and screenshots every frame of every clip.
//   node dev/css_playback.js <set dir> <out dir>
// Each clip's CSS animation is paused at the middle of each frame's time slot, so a keyframe
// that is off by one, or a wrong background-size/position, shows up as a different image.
// dev/tests/test_css_playback.py compares the screenshots with the source frames.
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const [setDir, outDir] = process.argv.slice(2).map((p) => path.resolve(p));
  const doc = JSON.parse(fs.readFileSync(path.join(setDir, "animations.json"), "utf8"));
  const page = path.join(setDir, "_css_playback.html");
  const clips = Object.keys(doc.clips).filter((n) => (doc.clips[n].layer || "full") === "full");
  fs.writeFileSync(page, `<!doctype html><link rel="stylesheet" href="engine/web/sprites.css">
<style>body{margin:0;background:transparent}</style>
${clips.map((n) => `<div class="sprite ${n}" id="c_${n}"></div>`).join("\n")}`);
  const browser = await chromium.launch();
  const tab = await browser.newPage({ deviceScaleFactor: 1 });
  await tab.goto("file://" + page);
  await tab.evaluate(() => Promise.all([...document.images].map((i) => i.decode())));
  for (const name of clips) {
    const c = doc.clips[name];
    const n = c.frames.length;
    const dur = (n / c.fps) * 1000;
    fs.mkdirSync(path.join(outDir, name), { recursive: true });
    const el = await tab.$(`#c_${name}`);
    await el.evaluate((e) => e.scrollIntoView());
    for (let i = 0; i < n; i++) {
      await el.evaluate((e, t) => e.getAnimations().forEach((a) => { a.pause(); a.currentTime = t; }), ((i + 0.5) / n) * dur);
      // Background images load lazily; wait until the sheet is decoded before the first shot.
      if (i === 0) await tab.waitForFunction((id) => {
        const url = getComputedStyle(document.getElementById(id)).backgroundImage.slice(5, -2);
        const img = new Image(); img.src = url; return img.complete && img.naturalWidth > 0;
      }, `c_${name}`);
      await el.screenshot({ path: path.join(outDir, name, `${String(i).padStart(3, "0")}.png`), omitBackground: true });
    }
  }
  await browser.close();
  fs.unlinkSync(page);
  console.log(`css playback: ${clips.length} clips`);
})().catch((e) => { console.error(e); process.exit(1); });
