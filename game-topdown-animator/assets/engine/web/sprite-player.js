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

if (typeof module !== "undefined") module.exports = { SpritePlayer };

// Free ground-plane movement. Direction changes preserve normalized gait phase.
class TopDownController {
  constructor(doc, images, scale = 1) {
    this.doc = doc;
    this.player = new SpritePlayer(doc, images);
    this.scale = scale; this.x = 0; this.y = 0;
    this.direction = 'down'; this.action = 'idle'; this.locked = false;
    this.player.play('idle_down');
  }
  select(action, direction, keepPhase = false) {
    const p = this.player;
    const name = action + '_' + direction;
    if (p.name === name) return;
    const phase = keepPhase ? (p.frame + p.acc * p.clip.fps / 1000) / p.clip.frames.length : 0;
    const oldAction = this.action;
    this.action = action; this.direction = direction;
    const n = this.doc.clips[name].frames.length;
    p.play(name, { frame: Math.min(n - 1, Math.floor(phase * n)) });
    if (keepPhase && oldAction !== 'death') {
      p.acc = (phase*n - Math.floor(phase*n)) * 1000 / p.clip.fps;
      p._pending = []; // Turning within a gait must not emit the current footstep twice.
    }
  }
  update(dtMs, input = {}) {
    const p = this.player;
    if (input.revive && this.action === 'death') { this.locked = false; this.select('idle', this.direction); }
    if (!this.locked) {
      const action = input.death ? 'death' : input.hurt ? 'hurt' : input.attack ? 'attack' : null;
      if (action && this.doc.clips[action+'_'+this.direction]) {
        this.select(action, this.direction); this.locked = true;
      } else {
        let x = input.x || 0, y = input.y || 0;
        const length = Math.hypot(x,y);
        if (length > 0) {
          x /= length; y /= length;
          const angle = (Math.round(Math.atan2(y,x) / (Math.PI/4)) + 8) % 8;
          const dir = this.doc.direction_order[angle];
          const movement = input.run && this.doc.clips['run_'+dir] ? 'run' : this.doc.clips['walk_'+dir] ? 'walk' : 'idle';
          this.select(movement, dir, ['walk','run'].includes(this.action) && movement !== 'idle');
          const speed = this.player.clip.speed_px_s * this.scale;
          this.x += x * speed * dtMs / 1000;
          this.y += y * speed * dtMs / 1000;
        } else this.select('idle', this.direction, this.action === 'idle');
      }
    }
    const events = p.update(dtMs);
    if (this.locked && p.done && this.action !== 'death') {
      this.locked = false;
      this.select('idle', this.direction);
    }
    return events;
  }
}
if (typeof module !== 'undefined') module.exports = { SpritePlayer, TopDownController };
