// Exercise the actual sprite preview script with a DOM stub and a manual clock.
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const src = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));
const noop = () => {};
const ctx = new Proxy({}, { get: (t, k) => k in t ? t[k] : (k === 'createLinearGradient' ? () => ({ addColorStop: noop }) : noop), set: (t, k, v) => (t[k] = v, true) });
const els = {};
const mk = (id) => ({
  id, style: {}, dataset: {}, children: [], checked: false, value: '1', textContent: '', innerHTML: '', width: 960, height: 440, options: [],
  classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); }, contains(c) { return this._s.has(c); } },
  getContext: () => ctx, append(...k) { this.children.push(...k); }, focus: noop, add(o) { this.options.push(o); if (!this.value || this.value === '1') this.value = o.value; },
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 960, height: 440 }),
});
const el = (id) => els[id] || (els[id] = mk(id));
el('paneB').classList.add('hidden');
const listeners = {};
let raf = [], clock = 1000;
const win = {};
const sandbox = {
  console, Math, JSON, Object, Promise, Set, Error, setTimeout,
  document: { getElementById: el, createElement: () => mk('x'), querySelectorAll: () => [] },
  Image: class { set src(v) { Promise.resolve().then(() => this.onload()); } },
  Option: class { constructor(t, v) { this.text = t; this.value = v; } },
  performance: { now: () => clock }, requestAnimationFrame: (f) => raf.push(f),
  addEventListener: (n, f) => { (listeners[n] = listeners[n] || []).push(f); }, window: win,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const tick = (ms = 1000 / 60) => { clock += ms; const q = raf; raf = []; q.forEach((f) => f(clock)); };
const send = (type, code) => listeners[type].forEach((f) => f({ code, repeat: false, preventDefault: noop }));

(async () => {
  await new Promise((r) => setTimeout(r, 0));
  el('tabB').onclick();
  const { P, hero } = win.__demo;
  const holdFrame = hero.doc.clips.block.frames.length - 1;
  let sparks = 0;
  const update = hero.update.bind(hero);
  hero.update = (...args) => { const events = update(...args); sparks += events.filter(e => e === 'block_spark').length; return events; };
  const advance = (n) => { for (let i = 0; i < n; i++) tick(); };
  const until = (test) => { for (let i = 0; i < 300; i++) { if (test()) return; tick(); } assert.fail('state timeout: ' + P.state); };
  const tap = (code) => { send('keydown', code); tick(); send('keyup', code); };
  send('keydown', 'KeyI');
  until(() => P.state === 'block' && hero.done);
  assert.equal(hero.frame, holdFrame);
  for (let hit = 1; hit <= 2; hit++) {
    tap('KeyH');
    assert.equal(P.state, 'block_hit', 'a guarded hit must not be overwritten by normal input');
    until(() => P.state === 'block');
    assert.equal(hero.frame, holdFrame, 'recovery must resume the held guard, without replaying entry');
    assert.equal(sparks, hit, 'one block_spark per guarded hit');
    // The next hit can arrive immediately on the resumed hold frame, before clip.done.
  }
  until(() => hero.done);
  advance(15);
  assert.equal(P.state, 'block');
  assert.equal(hero.frame, holdFrame);
  tap('KeyH');
  send('keyup', 'KeyI');
  until(() => P.state === 'idle');
  assert.equal(sparks, 3);
  send('keydown', 'KeyI');
  until(() => P.state === 'block' && hero.done);
  send('keyup', 'KeyI');
  tap('KeyH');
  assert.equal(P.state, 'hurt', 'an unguarded hit must play hurt');
  until(() => P.state === 'idle');
  console.log('sprite guard recovery: OK');
})().catch(e => { console.error(e); process.exitCode = 1; });
