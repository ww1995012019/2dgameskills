// Minimal canvas player for animations.json. Works in browsers and WeChat mini-game canvases.
// Timing uses an accumulator, not "advance one frame per requestAnimationFrame": frame pacing
// then stays correct on 60/90/120 Hz displays and through dropped frames.
class SpritePlayer {
  constructor(doc, images) {
    this.doc = doc;
    this.images = images;
    this.name = null;
    this.frame = 0;
    this.acc = 0;
    this.done = false;
  }

  play(name, opts = {}) {
    const clip = this.doc.clips[name];
    if (!clip) throw new Error("unknown clip " + name);
    if (this.name === name && !opts.restart) return;
    this.name = name;
    this.clip = clip;
    this.frame = opts.frame || 0;
    this.acc = 0;
    this.done = false;
    this._pending = clip.events.filter((e) => e.frame === this.frame).map((e) => e.name);
  }

  // Returns the event names crossed during this update.
  update(dtMs, speed = 1) {
    const out = this._pending || [];
    this._pending = [];
    if (!this.clip || this.done) return out;
    const stepMs = 1000 / this.clip.fps;
    this.acc += dtMs * speed;
    const n = this.clip.frames.length;
    while (this.acc >= stepMs) {
      this.acc -= stepMs;
      if (this.frame + 1 >= n) {
        if (this.clip.loop) this.frame = 0;
        else { this.done = true; this.acc = 0; break; }
      } else this.frame++;
      for (const e of this.clip.events) if (e.frame === this.frame) out.push(e.name);
    }
    return out;
  }

  // (x, y) is the feet pivot in canvas space.
  draw(ctx, x, y, { flip = false, scale = 1, frame = null, alpha = 1 } = {}) {
    if (!this.clip) return;
    const idx = this.clip.frames[frame === null ? this.frame : frame];
    const r = this.doc.regions[idx];
    const [px, py] = this.doc.pivot;
    ctx.save();
    ctx.globalAlpha *= alpha;
    ctx.translate(x, y);
    ctx.scale(flip ? -scale : scale, scale);
    ctx.drawImage(this.images[r.page], r.x, r.y, r.w, r.h, r.ox - px, r.oy - py, r.w, r.h);
    ctx.restore();
  }
}

// Layered shooter sprites: the upper body sits on the lower clip's per-frame anchor.
function drawLayered(ctx, lower, upper, x, y, opts = {}) {
  const k = opts.scale || 1, s = opts.flip ? -1 : 1;
  const a = lower.clip.anchors ? lower.clip.anchors[lower.frame] : [0, 0];
  lower.draw(ctx, x, y, opts);
  upper.draw(ctx, x + a[0] * k * s, y + a[1] * k, opts);
}

// World position of the muzzle on the current frame: where bullets and flashes spawn.
function muzzleAt(lower, upper, x, y, opts = {}) {
  const k = opts.scale || 1, s = opts.flip ? -1 : 1;
  const a = lower.clip.anchors ? lower.clip.anchors[lower.frame] : [0, 0];
  const m = upper.clip.muzzle[upper.frame];
  return [x + (m[0] + a[0]) * k * s, y + (m[1] + a[1]) * k];
}

if (typeof module !== "undefined") module.exports = { SpritePlayer, drawLayered, muzzleAt };
