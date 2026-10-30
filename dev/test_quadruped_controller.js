const assert=require('node:assert/strict'),fs=require('node:fs');
const {QuadrupedController}=require('../game-quadruped-animator/assets/engine/web/sprite-player.js');
const doc=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const make=()=>new QuadrupedController(doc,[],2);
for(const gait of ['walk','trot','run']){
 const c=make();let events=[];
 const clip=doc.clips[gait];
 for(let i=0;i<clip.frames.length;i++)events.push(...c.update(1000/clip.fps,{direction:1,gait}));
 // update() reports the pending first-frame event and the next loop's first-frame event.
 const atZero=clip.events.filter(e=>e.frame===0).length;
 assert.equal(events.length,clip.events.length+atZero);
 assert.ok(Math.abs(c.x-clip.speed_px_s*2*clip.frames.length/clip.fps)<1e-6,'ground movement follows clip speed');
 const before=c.x;c.update(100,{direction:-1,gait});assert.ok(c.x<before);assert.equal(c.flip,true);
 c.update(0,{direction:0});assert.equal(c.player.name,'idle');
}
const c=make();c.update(135,{direction:1,gait:'walk'});
const phase=()=> (c.player.frame+c.player.acc*c.player.clip.fps/1000)/c.player.clip.frames.length;
const before=phase();c.update(0,{direction:1,gait:'trot'});assert.ok(Math.abs(phase()-before)<1e-9);
c.update(0,{direction:-1,gait:'run'});assert.ok(Math.abs(phase()-before)<1e-9);
const result=c.update(0,{direction:-1,gait:'run'});assert.deepEqual(result,[]);
console.log('quadruped controller: speeds, all foot events, left/right, stop and gait phase OK');
const fighter=make();let hits=0,offs=0;fighter.update(0,{attack:true});
while(fighter.locked){const ev=fighter.update(10,{direction:1});hits+=ev.filter(x=>x==='hit_on').length;offs+=ev.filter(x=>x==='hit_off').length;}
assert.equal(hits,1);assert.equal(offs,1);assert.equal(fighter.x,0);assert.equal(fighter.player.name,'idle');
fighter.update(0,{hurt:true});while(fighter.locked)fighter.update(20);assert.equal(fighter.player.name,'idle');
fighter.update(0,{death:true});fighter.update(3000,{direction:1});assert.equal(fighter.player.name,'death');assert.equal(fighter.player.done,true);assert.equal(fighter.x,0);
fighter.update(0,{revive:true});assert.equal(fighter.player.name,'idle');
console.log('combat: one hit window, recovery, movement lock and death/revive OK');
const spam=make();spam.update(0,{attack:true});let strike=0;
for(let i=0;i<30;i++)strike+=spam.update(10,{attack:i<25}).filter(e=>e==='hit_on').length;
assert.equal(strike,1,'repeated attack input must not restart a locked bite');
