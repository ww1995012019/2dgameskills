// Run the generated preview script with a simulated DOM and manual animation clock.
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const src = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));
let drawn = 0, now = 1000, raf = [];
const noop = () => {};
const ctx = new Proxy({}, { get: (t, k) => k === 'drawImage' ? () => { drawn++; } : (t[k] || noop), set: (t, k, v) => (t[k] = v, true) });
const elements = {};
const el = id => elements[id] ||= { id, value: '', textContent: '', append(o) { if (!this.value) this.value = o.value; }, getContext: () => ctx };
const sandbox = { console, Math, JSON, Object, Promise, Error, performance: { now: () => now },
  document: { getElementById: el, createElement: () => ({ value: '', textContent: '' }) },
  Image: class { set src(_) { Promise.resolve().then(() => this.onload()); } },
  requestAnimationFrame: cb => raf.push(cb) };
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const tick = () => { now += 80; const callbacks = raf; raf = []; callbacks.forEach(cb => cb(now)); };
(async () => {
  await new Promise(resolve => setTimeout(resolve, 0));
  tick(); tick();
  assert.ok(drawn >= 2, 'preview must draw successive frames');
  el('action').value = 'hover'; el('action').onchange(); tick();
  assert.equal(el('status').textContent, 'hover', 'selecting another action must switch playback');
  el('restart').onclick(); tick();
  assert.ok(drawn >= 4);
  console.log('creature preview playback: OK');
})().catch(e => { console.error(e); process.exitCode = 1; });
