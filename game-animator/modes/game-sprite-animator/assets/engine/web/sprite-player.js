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
    // Retimed phase deltas can sum to one ulp below an exact frame boundary.
    // Keep selection/events on that boundary instead of holding the old frame
    // for another simulation tick. This tolerance is a fraction of one frame.
    while (this.acc + stepMs * 1e-10 >= stepMs) {
      this.acc = Math.max(0, this.acc - stepMs);
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

// Phase-preserving walk clock. Idle is a held double-support walk pose, NOT the
// authored idle clip. No image crossfade or skeletal interpolation is performed.
// Pass update().dx to the world's x position; drawing at a fixed x is in-place
// preview only. Baked poses retain ordinary frame-quantization contact error.
class GroundedWalkController {
  constructor(doc, images, {name = 'walk', rampSeconds = 0.3} = {}) {
    const clip = doc.clips[name], m = clip && clip.locomotion;
    if (!clip || !clip.loop || !m || !['natural_walk_v1', 'phase_walk_v1'].includes(m.profile) ||
        !Number.isFinite(m.period_s) || m.period_s <= 0 ||
        !Number.isFinite(m.duty) || m.duty <= 0.5 || m.duty >= 1 ||
        !Number.isFinite(m.speed_px_s) || m.speed_px_s <= 0 ||
        !clip.frames.length || !Number.isFinite(rampSeconds) || rampSeconds <= 0)
      throw new Error('grounded walk requires supported phase-walk metadata and positive rampSeconds');
    this.period = m.period_s;
    const holdPhase = m.hold_phase === undefined ? (m.duty - 0.5) / 2 : m.hold_phase;
    if (!Number.isFinite(holdPhase) || holdPhase < 0 || holdPhase >= m.duty - 0.5)
      throw new Error('walk hold phase must be inside double support');
    this.centre = holdPhase * this.period;
    this.speed = m.speed_px_s;
    this.rampSeconds = rampSeconds;
    // The held baked sample must itself show both planted feet. Low-frame-count
    // exports can miss the support windows and are rejected, never guessed.
    for (const phase of [this.centre, this.centre + this.period / 2]) {
      const p = Math.floor(phase / this.period * clip.frames.length + 1e-10) / clip.frames.length;
      if (!(p < m.duty && (p + 0.5) % 1 < m.duty))
        throw new Error('baked walk has no sampled double-support hold; increase export FPS');
    }
    this.walkName = name;
    this.walkClip = clip;
    this.settleBanks = m.settle_banks || null;
    if (this.settleBanks) {
      if (!Array.isArray(this.settleBanks) || this.settleBanks.length !== 2)
        throw new Error('grounded settle requires two banks');
      this.settleBanks.forEach((bank, side) => {
        const b = doc.clips[bank.clip], phase = this.centre + side * this.period / 2;
        const frame = Math.floor(phase / this.period * clip.frames.length + 1e-10);
        if (!b || b.loop || b.frames.length < 2 || !Number.isFinite(bank.duration_s) || bank.duration_s <= 0 ||
            bank.source_frame !== frame || !Number.isFinite(bank.sample_time_s) ||
            Math.abs(bank.sample_time_s - frame*this.period/clip.frames.length) > 1e-9 ||
            !Number.isFinite(bank.clock_phase_s) || Math.abs(bank.clock_phase_s-phase)>1e-9)
          throw new Error('invalid grounded settle bank registration');
      });
    }
    this.player = new SpritePlayer(doc, images);
    this.player.play(name);
    this.player.clip = {...clip, fps: clip.frames.length / this.period};
    this.phase = this.centre;
    const sample = this.phase / this.period * clip.frames.length;
    this.player.frame = Math.floor(sample + 1e-10);
    this.player.acc = (sample - this.player.frame) * 1000 / this.player.clip.fps;
    this.player._pending = []; // construction is not a crossed footstep
    this.state = 'hold';
    this.moving = false;
    this.distance = 0;
    this.ramp = null;
    this.settling = null;
    this.poseSettled = !!this.settleBanks;
    if (this.settleBanks) this._showBank(this.settleBanks[0], 1);
  }

  setMoving(moving) {
    if (typeof moving !== 'boolean') throw new Error('setMoving expects a boolean');
    this.moving = moving;
    this._settle(); // while ramping, retain only the latest requested state
  }

  _showWalk() {
    this.player.play(this.walkName, {restart: true});
    this.player.clip = {...this.walkClip, fps: this.walkClip.frames.length / this.period};
    const sample = ((this.phase % this.period) + this.period) % this.period / this.period * this.walkClip.frames.length;
    this.player.frame = Math.floor(sample + 1e-10) % this.walkClip.frames.length;
    this.player.acc = Math.max(0, sample - Math.floor(sample + 1e-10)) * 1000 / this.player.clip.fps;
    this.player._pending = [];
  }

  _showBank(bank, progress) {
    this.player.play(bank.clip);
    this.player.frame = Math.round(progress * (this.player.clip.frames.length - 1));
    this.player._pending = [];
  }

  _beginSettle(reverse) {
    const side = ((Math.round((this.phase - this.centre) / (this.period / 2)) % 2) + 2) % 2;
    const bank = this.settleBanks[side];
    this.settling = {bank, elapsed: 0, reverse};
    this.state = reverse ? 'unsettle' : 'settle';
    this._showBank(bank, reverse ? 1 : 0);
  }

  _settle() {
    if (this.ramp || this.settling) return;
    if (this.state === 'hold' && this.moving) {
      if (this.settleBanks && this.poseSettled) { this._beginSettle(true); return; }
      this._showWalk();
      this.state = 'resume';
      this.ramp = {source: this.phase, elapsed: 0, duration: this.rampSeconds};
    } else if (this.state === 'hold' && this.settleBanks && !this.poseSettled) {
      this._beginSettle(false);
    } else if (this.state === 'walk' && !this.moving) {
      const half = this.period / 2;
      const end = this.centre + Math.ceil((this.phase + this.rampSeconds / 2 - this.centre) / half) * half;
      this.state = 'stop';
      this.ramp = {source: this.phase, elapsed: 0, duration: 2 * (end - this.phase)};
    }
  }

  update(dtMs) {
    if (!Number.isFinite(dtMs) || dtMs < 0) throw new Error('update expects finite nonnegative milliseconds');
    let remaining = dtMs / 1000, events = [], dx = 0;
    this._settle();
    while (remaining > 0) {
      if (this.state === 'hold') break;
      if (this.settling) {
        const s = this.settling, step = Math.min(remaining, s.bank.duration_s - s.elapsed);
        s.elapsed += step;
        const u = Math.min(1, s.elapsed / s.bank.duration_s);
        this._showBank(s.bank, s.reverse ? 1-u : u);
        remaining -= step;
        if (s.elapsed >= s.bank.duration_s) {
          this.poseSettled = !s.reverse;
          this.settling = null;
          this.state = 'hold';
          if (s.reverse) this._showWalk();
          this._settle();
        }
        continue;
      }
      let next, step = remaining;
      if (this.ramp) {
        const r = this.ramp;
        step = Math.min(remaining, r.duration - r.elapsed);
        r.elapsed += step;
        const u = Math.min(1, r.elapsed / r.duration);
        const integral = u ** 4 * (2.5 + u * (-3 + u));
        next = r.source + r.duration * (this.state === 'stop' ? u - integral : integral);
      } else next = this.phase + step;
      const advance = Math.max(0, next - this.phase);
      events.push(...this.player.update(advance * 1000));
      dx += advance * this.speed;
      this.phase = next;
      remaining -= step;
      if (this.ramp && this.ramp.elapsed >= this.ramp.duration) {
        this.state = this.state === 'stop' ? 'hold' : 'walk';
        this.poseSettled = false;
        this.ramp = null;
        this._settle();
      }
    }
    this.distance += dx;
    let rate = this.state === 'hold' || this.settling ? 0 : 1;
    if (this.ramp) {
      const u = this.ramp.elapsed / this.ramp.duration;
      const eased = u*u*u*(10 + u*(-15 + 6*u));
      rate = this.state === 'stop' ? 1-eased : eased;
    }
    return {events, dx, speed: this.speed * rate, state: this.state, phase: this.phase};
  }

  draw(ctx, x, y, opts = {}) { this.player.draw(ctx, x, y, opts); }
}

if (typeof module !== 'undefined') module.exports.GroundedWalkController = GroundedWalkController;
