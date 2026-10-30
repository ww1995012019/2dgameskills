const assert=require('node:assert/strict'),fs=require('node:fs');
const {TopDownController}=require('../game-topdown-animator/assets/engine/web/sprite-player.js');
const doc=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const make=()=>new TopDownController(doc,[]);
let reference;
for(const dir of doc.direction_order){
 const c=make(),v=doc.directions[dir].vector;
 for(let i=0;i<30;i++)c.update(1000/60,{x:v[0],y:v[1]});
 const distance=Math.hypot(c.x,c.y);if(reference===undefined)reference=distance;
 assert.ok(Math.abs(distance-reference)<1e-6,'diagonal speed must match axial speed');
 assert.equal(c.direction,dir);
}
const c=make();c.update(135,{x:1});
const phase=()=> (c.player.frame+c.player.acc*c.player.clip.fps/1000)/c.player.clip.frames.length;
const before=phase();const events=c.update(0,{x:0,y:-1});assert.ok(Math.abs(phase()-before)<1e-9,'turn must preserve gait phase');assert.deepEqual(events,[]);
c.update(0,{x:0,y:-1,run:true});assert.ok(Math.abs(phase()-before)<1e-9,'walk/run must preserve phase');
const x=c.x,y=c.y;c.update(1,{attack:true});assert.equal(c.action,'attack');
let hits=0;
for(let i=0;i<100 && c.locked;i++)hits+=c.update(10,{x:1,y:1}).filter(e=>e==='hit_on').length;
assert.equal(hits,1,'attack event exactly once');assert.equal(c.x,x);assert.equal(c.y,y);
c.update(10,{death:true});for(let i=0;i<200;i++)c.update(10,{x:1,y:1});assert.equal(c.action,'death');assert.equal(c.player.done,true);
c.update(0,{revive:true});assert.equal(c.action,'idle');assert.equal(c.locked,false);
console.log('topdown controller: 8 directions, equal speed, phase, events and locks OK');
