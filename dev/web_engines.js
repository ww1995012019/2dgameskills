// Loads a generated set in Phaser 3 and PixiJS 8 in Chromium, following engine-integration.md.
//   npm install --prefix dev/engines          # once
//   node dev/web_engines.js <set dir> [phaser|pixi ...]
// For each engine:
// 1. Loads animations.json and every atlas page with the code from engine-integration.md, and
//    checks every clip's frame count, rate and loop flag.
// 2. Draws every frame anchored on the manifest pivot and compares the canvas with the source PNG.
// 3. Plays a looping and a one-shot clip per fps at 60 and 144 Hz with a manual clock, and checks
//    the frame order, how long each frame stays up, loop wrap and the completion event.
// Prints one "FAIL ..." line per problem and "RESULT <engine> ok|fail"; exits 1 on failure.
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const LIBS = path.join(__dirname, "engines", "node_modules");
const SCRIPTS = { phaser: "phaser/dist/phaser.min.js", pixi: "pixi.js/dist/pixi.min.js" };
const MIME = { ".png": "image/png", ".json": "application/json", ".js": "text/javascript", ".html": "text/html" };

// Runs in the page: helpers and one function per engine.
const PAGE = fs.readFileSync(path.join(__dirname, "web_engines_page.js"), "utf8");

(async () => {
  const [setArg, ...which] = process.argv.slice(2);
  const setDir = path.resolve(setArg);
  const allClips = which.includes("--all-clips");
  const selected = which.filter(x => x !== "--all-clips");
  const engines = selected.length ? selected : ["phaser", "pixi"];
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  let ok = true;
  for (const eng of engines) {
    const page = await browser.newPage({ deviceScaleFactor: 1 });
    await page.route("http://engines.test/**", (route) => {
      const url = new URL(route.request().url()).pathname;
      let file;
      if (url === "/") return route.fulfill({ contentType: "text/html", body: `<!doctype html><body style="margin:0"><script src="/lib/${SCRIPTS[eng]}"></script><script>window.SMOKE_ALL_CLIPS=${allClips};${PAGE}</script>` });
      if (url.startsWith("/set/")) file = path.join(setDir, decodeURIComponent(url.slice(5)));
      else if (url.startsWith("/lib/")) file = path.join(LIBS, url.slice(5));
      if (!file || !fs.existsSync(file)) return route.fulfill({ status: 404, body: "" });
      route.fulfill({ contentType: MIME[path.extname(file)] || "application/octet-stream", body: fs.readFileSync(file) });
    });
    const fails = [];
    page.on("pageerror", (e) => fails.push("page error: " + e.message));
    await page.goto("http://engines.test/");
    const res = await page.evaluate(async (fn) => {
      const out = [];
      const r = await window[fn]((m) => out.push(m));
      return { ...r, fails: out };
    }, eng === "phaser" ? "runPhaser" : "runPixi").catch((e) => ({ checked: 0, played: [], fails: ["page error: " + e.message] }));
    fails.push(...res.fails);
    fails.forEach((f) => console.log("FAIL", eng, f));
    console.log(`${eng}: frames checked ${res.checked}, played ${res.played.join(" ")}`);
    console.log(`RESULT ${eng} ${fails.length ? "fail" : "ok"}`);
    ok = ok && !fails.length && res.checked > 0;
    await page.close();
  }
  await browser.close();
  process.exit(ok ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(1); });
