"""Actual exported JS clock: repeat/interruption and Python phase parity checks."""
import json
import shutil
import subprocess
import sys
import unittest
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'game-sprite-animator/scripts'))
from sprite_anim.motions import build_clips
from sprite_anim.rig import Body


@unittest.skipUnless(shutil.which('node'), 'Node required for exported player test')
class GroundedPlayer(unittest.TestCase):
    def test_natural_export_contains_exact_clock_and_demo(self):
        self._check_export(24)

    def test_odd_frame_count_export_preserves_settle_pixels(self):
        self._check_export(30)

    def _check_export(self, fps):
        spec = json.loads((ROOT/'game-sprite-animator/assets/characters/hero.json').read_text())
        spec.setdefault('gait', {})['walk'] = {'profile': 'natural_walk_v1'}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp/'character.json'
            source.write_text(json.dumps(spec))
            result = subprocess.run([sys.executable, str(ROOT/'game-sprite-animator/scripts/generate.py'),
                '--character', str(source), '--size', '64', '--fps', str(fps), '--clips', 'walk',
                '--no-fx', '--grounded-settle', '--out', str(tmp/'out')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            doc = json.loads((tmp/'out/animations.json').read_text())
            meta = doc['clips']['walk']['locomotion']
            self.assertEqual(meta['profile'], 'natural_walk_v1')
            self.assertEqual(meta['period_s'], 5/6)
            self.assertEqual(len(meta['settle_banks']), 2)
            self.assertEqual(meta['idle_mode'], 'settled_double_support')
            self.assertTrue((tmp/'out/engine/web/grounded-walk.html').is_file())
            # Numeric pose equality cannot catch independently initialized cloth.
            # Check real rendered pixels at both bank handoffs.
            walk_frames = sorted((tmp/'out/frames/walk').glob('*.png'))
            for bank in meta['settle_banks']:
                bank_frames = sorted((tmp/'out/frames'/bank['clip']).glob('*.png'))
                expected = np.asarray(Image.open(walk_frames[bank['source_frame']]))
                actual = np.asarray(Image.open(bank_frames[0]))
                np.testing.assert_array_equal(actual, expected,
                    err_msg=bank['clip'] + ' must enter from the displayed walk pixels')
            code = "const fs=require('fs');const {GroundedWalkController}=require(process.argv[1]);const c=new GroundedWalkController(JSON.parse(fs.readFileSync(process.argv[2])),[]);c.setMoving(true);c.update(900);c.setMoving(false);c.update(2000);if(c.state!=='hold')process.exit(1);"
            result = subprocess.run(['node', '-e', code, str(tmp/'out/engine/web/sprite-player.js'),
                str(tmp/'out/animations.json')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_standalone_settle_retains_source_cloth_and_reverses(self):
        from sprite_anim.render import Renderer
        from sprite_anim.motions import GroundedGaitSettle
        spec = json.loads((ROOT/'game-sprite-animator/assets/characters/hero.json').read_text())
        walk = build_clips(body=Body(), gait={'walk': {'profile': 'natural_walk_v1'}})['walk']
        settle = walk.standing().settle()
        registry = {settle.name: settle}
        renderer = Renderer(spec, 32, clips=registry)
        self.assertEqual(list(registry), [settle.name])
        self.assertIs(renderer.clips['walk'], walk)
        source = renderer.cloth_at(walk, settle.phase_time)
        start = renderer.cloth_at(settle, 0.)
        reverse = GroundedGaitSettle(walk, settle.phase_time, reverse=True)
        for name in source:
            np.testing.assert_allclose(start[name], source[name], atol=1e-12)
        held = renderer.cloth_at(settle.hold(), 0.)
        endpoint = renderer.cloth_at(settle, .25)
        for name in held:
            np.testing.assert_allclose(held[name], endpoint[name], atol=1e-12)
        for t in (0., .08, .17, .25):
            forward = renderer.cloth_at(settle, t)
            backward = renderer.cloth_at(reverse, .25-t)
            for name in forward:
                np.testing.assert_allclose(forward[name], backward[name], atol=1e-12)

    def test_phase_clock_and_repeated_commands(self):
        walk = build_clips(body=Body(), gait={'walk': {'profile': 'natural_walk_v1'}})['walk']
        hold = walk.standing()
        start = hold.resume(.3)
        stop = walk.stop(start.phase_time(.3) + .41, .3)
        expected = dict(start=[start.phase_time(t) for t in (.03,.1,.2,.3)],
                        stop_duration=stop.duration, stop_phase=stop.phase_time(stop.duration))
        player = str(ROOT/'game-sprite-animator/assets/engine/web/sprite-player.js')
        code = r'''
const assert=require('assert');
const {SpritePlayer,GroundedWalkController}=require(process.argv[1]);
const expected=JSON.parse(process.argv[2]);
const close=(a,b)=>assert(Math.abs(a-b)<1e-9,`${a} != ${b}`);
function make(n=20){return {clips:{walk:{loop:true,fps:24,frames:Array.from({length:n},(_,i)=>i),events:[{frame:0,name:'step'},{frame:Math.floor(n/2),name:'step'}],locomotion:{profile:'natural_walk_v1',period_s:5/6,duty:.6,speed_px_s:123}}},regions:[],pivot:[0,0]};}
const a=new GroundedWalkController(make(),[]);
assert.equal(a.state,'hold'); close(a.update(500).dx,0);
a.setMoving(true); a.setMoving(true);
let prev=0;
[.03,.1,.2,.3].forEach((t,i)=>{const r=a.update((t-prev)*1000);close(r.phase,expected.start[i]);prev=t;});
assert.equal(a.state,'walk');a.update(410);a.setMoving(false);
close(a.ramp.duration,expected.stop_duration);
const before=a.distance;
a.update(expected.stop_duration*1000);assert.equal(a.state,'hold');close(a.phase,expected.stop_phase);
close(a.distance-before,(expected.stop_phase-(expected.start[3]+.41))*123);
const phase=a.phase, distance=a.distance, frame=a.player.frame;
a.setMoving(false);a.update(7000);close(a.phase,phase);close(a.distance,distance);assert.equal(a.player.frame,frame);
// Last command wins during a ramp; never rebuild an in-flight clock.
a.setMoving(true);a.update(80);const ramp=a.ramp;a.setMoving(false);a.setMoving(true);a.setMoving(false);assert.strictEqual(a.ramp,ramp);
a.update(3000);assert.equal(a.state,'hold');
// Partition invariance, dropped frames, and independent display rates.
for(const fps of [24,30,60,90,144]){
 const one=new GroundedWalkController(make(25),[]),many=new GroundedWalkController(make(25),[]);
 one.setMoving(true);many.setMoving(true);one.update(2100);
 let left=2100;while(left>0){const dt=Math.min(left,1000/fps);many.update(dt);left-=dt;}
 close(one.phase,many.phase);close(one.distance,many.distance);assert.equal(one.player.frame,many.player.frame);
 one.setMoving(false);many.setMoving(false);one.update(3000);left=3000;
 while(left>0){const dt=Math.min(left,1000/fps);many.update(dt);left-=dt;}
 close(one.phase,many.phase);close(one.distance,many.distance);assert.equal(one.state,'hold');assert.equal(many.state,'hold');
}
for(const bad of [-1,NaN,Infinity])assert.throws(()=>a.update(bad));
assert.throws(()=>a.setMoving(1));assert.throws(()=>new GroundedWalkController(make(),[],{rampSeconds:0}));
assert.throws(()=>new GroundedWalkController(make(3),[]));
const legacy=make();delete legacy.clips.walk.locomotion;assert.throws(()=>new GroundedWalkController(legacy,[]));
const old=new SpritePlayer(legacy,[]);old.play('walk');old.update(1000/24);assert.equal(old.frame,1);

function withBanks(n=20){
 const doc=make(n),m=doc.clips.walk.locomotion;
 m.settle_banks=[0,1].map(i=>{
  const phase=(.05+.5*i)*m.period_s, frame=Math.floor(phase/m.period_s*n+1e-10), name='walk_settle_'+i;
  doc.clips[name]={loop:false,fps:24,frames:[100,101,102,103,104,105,106],events:[]};
  return {clip:name,duration_s:.25,source_frame:frame,sample_time_s:frame*m.period_s/n,clock_phase_s:phase};
 });return doc;
}
const settled=new GroundedWalkController(withBanks(),[]);
assert.equal(settled.player.name,'walk_settle_0');assert.equal(settled.player.frame,6);
settled.setMoving(true);assert.equal(settled.state,'unsettle');close(settled.update(125).dx,0);assert.equal(settled.player.frame,3);
settled.setMoving(false);settled.update(125);assert.equal(settled.state,'settle');close(settled.update(250).dx,0);assert.equal(settled.state,'hold');close(settled.distance,0);
settled.setMoving(true);settled.update(550);assert.equal(settled.state,'walk');settled.setMoving(false);settled.update(5000);assert.equal(settled.state,'hold');assert(settled.poseSettled);assert.equal(settled.player.frame,6);
for(const n of [20,25])for(const fps of [30,60,144]){
 const one=new GroundedWalkController(withBanks(n),[]),many=new GroundedWalkController(withBanks(n),[]);
 function advance(total){one.update(total);let left=total;while(left>0){const dt=Math.min(left,1000/fps);many.update(dt);left-=dt;}}
 one.setMoving(true);many.setMoving(true);advance(167);one.setMoving(false);many.setMoving(false);advance(930);
 close(one.phase,many.phase);close(one.distance,many.distance);assert.equal(one.state,many.state);assert.equal(one.player.frame,many.player.frame);
 one.setMoving(true);many.setMoving(true);advance(1823);one.setMoving(false);many.setMoving(false);advance(3000);
 close(one.phase,many.phase);close(one.distance,many.distance);assert.equal(one.state,'hold');assert.equal(one.player.frame,many.player.frame);assert.equal(one.player.name,many.player.name);
}
const badBank=withBanks();badBank.clips.walk.locomotion.settle_banks[0].source_frame=0;assert.throws(()=>new GroundedWalkController(badBank,[]));
console.log('grounded player parity, interruptions, cadence, settle banks and legacy checks pass');

'''
        result = subprocess.run(['node', '-e', code, player, json.dumps(expected)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
