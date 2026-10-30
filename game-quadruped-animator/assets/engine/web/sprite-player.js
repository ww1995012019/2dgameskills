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

// Side-view movement, with normalized loop phase retained on gait changes.
class QuadrupedController {
  constructor(doc,images,scale=1) {
    this.doc=doc;this.player=new SpritePlayer(doc,images);this.scale=scale;this.x=0;this.flip=false;
    this.player.play('idle');
  }
  update(dtMs,input={}) {
    if(input.revive&&this.player.name==='death'){this.locked=false;this.player.play('idle');}
    const reaction=input.death?'death':input.hurt?'hurt':input.attack?'attack':null;
    if(reaction&&this.doc.clips[reaction]&&this.player.name!=='death'&&(!this.locked||reaction!=='attack')){
      this.player.play(reaction,{restart:true});this.locked=true;
    }
    if(this.locked){const events=this.player.update(dtMs);if(this.player.done&&this.player.name!=='death'){this.locked=false;this.player.play('idle');}return events;}
    const direction=Math.sign(input.direction||0);
    let name=direction?(input.gait||'walk'):'idle';
    if(!this.doc.clips[name])name=this.doc.clips.walk?'walk':'idle';
    const p=this.player;
    if(p.name!==name){
      const preserve=p.name!=='idle'&&name!=='idle';
      const phase=preserve?(p.frame+p.acc*p.clip.fps/1000)/p.clip.frames.length:0;
      const n=this.doc.clips[name].frames.length;
      p.play(name,{frame:Math.min(n-1,Math.floor(phase*n))});
      if(preserve){p.acc=(phase*n-Math.floor(phase*n))*1000/p.clip.fps;p._pending=[];}
    }
    if(direction){this.flip=direction<0;this.x+=direction*p.clip.speed_px_s*this.scale*dtMs/1000;}
    return p.update(dtMs);
  }
}
if(typeof module!=='undefined')module.exports={SpritePlayer,QuadrupedController};
