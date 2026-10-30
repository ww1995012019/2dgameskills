// Runs the real inline script from the shooter preview in Node with a stub DOM and a manual clock.
const fs = require('fs'), path = require('path'), vm = require('vm');
const file = path.join(process.env.TEMP, 'spr', process.argv[2] || 's_hd', 'preview.html');
const html = fs.readFileSync(file, 'utf8');
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
  await new Promise((r) => setTimeout(r, 50));
  tick(); tick();
  el('tabB').onclick();
  const D = win.__demo, P = D.P;
  const state = () => P.full ? 'FULL:' + P.full : `${D.low.name}+${D.up.name}`;
  const rec = (label, fn) => {
    const seq = []; let last = '';
    fn(() => { const s = state(); if (s !== last) { last = s; seq.push(s); } });
    console.log(label.padEnd(20), seq.length > 12 ? seq.slice(0, 12).join(' > ') + ` ... (${seq.length})` : seq.join(' > '));
  };
  const stepN = (n, s) => { for (let i = 0; i < n; i++) { tick(); s(); } };
  const tapS = (c, s) => { send('keydown', c); stepN(3, s); send('keyup', c); };
  const until = (cond, s, max = 600) => { let i = 0; while (!cond() && i++ < max) { tick(); s(); } return i; };
  const idle = () => P.st === 'idle' && !P.full && P.upper === 'aim';
  // Ammo of the weapon in hand; weapons fill P.ammo in order, and start with a full magazine.
  const W = () => Object.keys(P.ammo)[P.wi];
  const MAG = { ...P.ammo };

  rec('idle', (s) => stepN(30, s));
  rec('walk', (s) => { send('keydown', 'KeyD'); stepN(30, s); send('keyup', 'KeyD'); stepN(5, s); });
  rec('run', (s) => { send('keydown', 'KeyD'); send('keydown', 'ShiftLeft'); stepN(30, s); send('keyup', 'KeyD'); send('keyup', 'ShiftLeft'); stepN(5, s); });
  rec('backpedal', (s) => { game = el('game'); game.onmousemove({ clientX: 900, clientY: 200 }); send('keydown', 'KeyA'); stepN(30, s); send('keyup', 'KeyA'); stepN(5, s); });
  console.log('   face', P.face, 'aim', Math.round(P.aim));
  const b0 = P.shots;
  rec('fire 1s', (s) => { send('keydown', 'KeyJ'); stepN(60, s); send('keyup', 'KeyJ'); stepN(10, s); });
  console.log('   shots in 1s', P.shots - b0, 'ammo', P.ammo[W()]);
  const m = D.up.clip;
  rec('aim sweep', (s) => { el('game').onmousemove({ clientX: 900, clientY: 0 }); stepN(50, s); el('game').onmousemove({ clientX: 900, clientY: 430 }); stepN(50, s); el('game').onmousemove({ clientX: 900, clientY: 200 }); stepN(30, s); });
  rec('run + fire + aim', (s) => { send('keydown', 'KeyD'); send('keydown', 'ShiftLeft'); send('keydown', 'KeyJ'); stepN(40, s); send('keyup', 'KeyD'); send('keyup', 'ShiftLeft'); send('keyup', 'KeyJ'); stepN(6, s); });
  rec('reload', (s) => { tapS('KeyR', s); until(idle, s); });
  console.log('   ammo after reload', P.ammo[W()]);
  rec('reload while run', (s) => { P.ammo[W()] = Math.min(3, MAG[W()] - 1); send('keydown', 'KeyD'); send('keydown', 'ShiftLeft'); tapS('KeyR', s); stepN(30, s); send('keyup', 'KeyD'); send('keyup', 'ShiftLeft'); until(idle, s); });
  rec('switch', (s) => { tapS('KeyQ', s); until(idle, s); });
  console.log('   weapon', P.wi);
  rec('shotgun fire', (s) => { send('keydown', 'KeyJ'); stepN(50, s); send('keyup', 'KeyJ'); stepN(40, s); });
  rec('back to rifle', (s) => { tapS('KeyQ', s); until(idle, s); });
  rec('throw', (s) => { tapS('KeyG', s); until(idle, s); stepN(90, s); });
  rec('melee', (s) => { tapS('KeyF', s); until(idle, s); });
  // A key pressed on the last frame of a busy upper action must run once it ends, not vanish.
  // Presses are buffered for 0.13 s, so earlier than the last frame may legitimately expire.
  const nearEnd = () => D.up.frame >= D.up.clip.frames.length - 1;
  const settled = (n) => () => D.up.name.endsWith(n) || D.up.name.includes('_aim_');
  P.ammo[W()] = MAG[W()] - 1;
  rec('R at throw end', (s) => { tapS('KeyG', s); until(nearEnd, s); tapS('KeyR', s); until(settled('_reload'), s); until(idle, s); });
  console.log('   ammo', P.ammo[W()], P.ammo[W()] === MAG[W()] ? 'ok' : 'SWALLOWED');
  P.ammo[W()] = MAG[W()] - 1;
  rec('G at reload end', (s) => { tapS('KeyR', s); until(nearEnd, s); tapS('KeyG', s); until(settled('_throw'), s); until(idle, s); });
  rec('jump + air fire', (s) => { tapS('Space', s); until(() => P.air, s); send('keydown', 'KeyJ'); stepN(20, s); send('keyup', 'KeyJ'); until(() => !P.air, s); until(idle, s); });
  rec('crouch fire', (s) => { send('keydown', 'KeyS'); stepN(15, s); send('keydown', 'KeyJ'); stepN(20, s); send('keyup', 'KeyJ'); send('keyup', 'KeyS'); until(idle, s); });
  rec('roll', (s) => { tapS('KeyL', s); until(idle, s); });
  rec('slide', (s) => { send('keydown', 'KeyD'); tapS('KeyC', s); send('keyup', 'KeyD'); until(idle, s); });
  rec('death revive', (s) => { tapS('KeyX', s); stepN(100, s); tapS('KeyX', s); stepN(5, s); });
  P.ammo[W()] = Math.min(2, MAG[W()]);
  rec('auto reload at 0', (s) => { send('keydown', 'KeyJ'); stepN(40, s); send('keyup', 'KeyJ'); until(idle, s); });
  console.log('final ammo', P.ammo[W()], 'bullets', D.bullets.length, 'fx', D.fxList.length, 'x', Math.round(P.x), 'hit targets', D.targets.filter((t) => t.hp < 4).length);
})();
