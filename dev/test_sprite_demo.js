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
el('custom-controls').classList.add('hidden');
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
  let sparks = 0;
  const update = hero.update.bind(hero);
  hero.update = (...args) => { const events = update(...args); sparks += events.filter(e => e === 'block_spark').length; return events; };
  const advance = (n) => { for (let i = 0; i < n; i++) tick(); };
  const until = (test) => { for (let i = 0; i < 300; i++) { if (test()) return; tick(); } assert.fail('state timeout: ' + P.state); };
  const tap = (code) => { send('keydown', code); tick(); send('keyup', code); };
  if (process.argv.includes('--locomotion')) {
    const control = win.__demo.locomotion;
    assert.ok(control, 'the normal preview must use the exported walk controller');
    const scale = hero.doc.frame_size < 128 ? Math.max(2, Math.round(180/hero.doc.frame_size)) : 1.15*256/hero.doc.frame_size;
    const origin = P.x, distance = control.distance;
    const allowed = new Set(['walk', ...(control.settleBanks || []).map(b => b.clip)]);
    const check = () => {
      assert.strictEqual(win.__demo.locomotion, control, 'ordinary movement must retain its phase clock');
      assert.ok(allowed.has(hero.name), 'start/stop must not reset to the unrelated authored idle');
      assert.equal(hero.frame, control.player.frame);
      assert.ok(Math.abs(P.x-origin-(control.distance-distance)*scale) < 1e-7, 'root movement must use phase displacement');
      if (hero.name === 'walk') {
        const m = hero.doc.clips.walk.locomotion, n = hero.clip.frames.length;
        const sample = ((control.phase%m.period_s)+m.period_s)%m.period_s/m.period_s*n;
        assert.equal(hero.frame, Math.floor(sample+1e-10)%n, 'display must retain walk phase');
      }
    };
    const sampleTicks = n => { for(let i=0;i<n;i++){ tick(); check(); } };
    sampleTicks(30);
    for (const offset of [1,7,19,37,59]) {
      send('keydown','KeyD'); sampleTicks(offset);
      send('keyup','KeyD');
      for(let i=0;i<300 && control.state!=='hold';i++){ tick(); check(); }
      assert.equal(control.state,'hold');
      const phase = control.phase, x = P.x, frame = hero.frame;
      sampleTicks(30);
      assert.equal(control.phase,phase); assert.equal(P.x,x); assert.equal(hero.frame,frame);
      const m = hero.doc.clips.walk.locomotion;
      const p = Math.floor(((phase%m.period_s)+m.period_s)%m.period_s/m.period_s*hero.doc.clips.walk.frames.length+1e-10)/hero.doc.clips.walk.frames.length;
      assert.ok(p<m.duty && (p+.5)%1<m.duty, 'stop must display two-foot support');
    }
    if (hero.doc.clips.attack_1) {
      tap('KeyJ'); assert.equal(P.state,'attack_1'); assert.equal(win.__demo.locomotion,null);
      until(() => P.state==='idle');
      assert.ok(win.__demo.locomotion, 'actions must return to a usable locomotion stance');
      send('keydown','KeyD'); advance(60); send('keyup','KeyD');
      until(() => win.__demo.locomotion.state==='hold');
    }
    console.log('main preview: phase-preserving start/stop and exact displacement OK');
    return;
  }
  if (process.argv.includes('--subset')) {
    // Reduced exports are supported by --clips. Missing actions must not crash the loop.
    let drawScale;
    const draw = hero.draw.bind(hero);
    hero.draw = (...args) => { drawScale = args[3].scale; return draw(...args); };
    for (const code of ['KeyL', 'KeyK', 'KeyU', 'Space', 'KeyH', 'KeyX', 'KeyJ']) {
      tap(code); advance(120);
    }
    send('keydown', 'KeyS'); send('keydown', 'KeyD'); advance(30);
    send('keyup', 'KeyS'); send('keyup', 'KeyD'); advance(30);
    assert.ok(hero.clip, 'the demo always has a playable clip');
    assert.ok(Number.isFinite(P.x) && Number.isFinite(P.y));
    if (process.argv.includes('--no-idle')) {
      assert.ok(el('custom-controls').classList.contains('hidden'), 'custom controls require idle');
      assert.match(el('missing-actions').textContent, /idle/, 'explain the missing idle');
    }
    if (process.argv.includes('--custom')) {
      if (P.state === 'death') tap('KeyX');
      until(() => P.state === 'idle');
      const custom = el('custom-action').value;
      assert.ok(custom && hero.doc.clips[custom], 'a custom action must be offered');
      tap('KeyQ');
      assert.equal(P.state, custom, 'Q must start the selected custom action');
      send('keydown', 'KeyD'); advance(5); send('keyup', 'KeyD');
      assert.equal(P.state, custom, 'movement must not interrupt a custom action');
      if (process.argv.includes('--switch-custom')) {
        el('custom-action').value = 'test_second';
        tap('KeyQ');
        assert.equal(P.state, 'test_second', 'Q must switch to the selected custom action');
        advance(5); tap('KeyQ');
      } else if (hero.doc.clips[custom].loop) { advance(10); tap('KeyQ'); }
      until(() => P.state === 'idle');
    }
    if (hero.doc.frame_size >= 128) {
      assert.ok(Math.abs(drawScale * hero.doc.frame_size - 1.15 * 256) < 1e-6,
        'HD sprite should keep the same on-screen size at any output resolution');
    }
    console.log('sprite subset controls: OK');
    return;
  }
  const holdFrame = hero.doc.clips.block.frames.length - 1;
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
