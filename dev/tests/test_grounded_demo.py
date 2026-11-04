"""Demo wiring in a mocked DOM; explicitly not browser playback validation."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

@unittest.skipUnless(shutil.which('node'), 'Node required')
class GroundedDemo(unittest.TestCase):
    def test_export_page_schema_loading_buttons_and_draw_wiring(self):
        code = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const dir=process.argv[1],html=fs.readFileSync(path.join(dir,'grounded-walk.html'),'utf8');
const scripts=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]).filter(Boolean);
let draws=0,loaded=[],raf=[],listeners={};
const ctx={clearRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},save(){},restore(){},translate(){},scale(){},drawImage(){draws++},globalAlpha:1};
const els={'#status':{},canvas:{getContext(){return ctx}},'#go':{},'#stop':{}};
const doc={pages:[{file:'atlas.png',w:16,h:16}],frame_size:16,pivot:[8,14],regions:[{page:0,x:0,y:0,w:16,h:16,ox:0,oy:0}],clips:{walk:{loop:true,fps:24,frames:Array(20).fill(0),events:[],locomotion:{profile:'natural_walk_v1',period_s:5/6,duty:.6,speed_px_s:50}}}};
const context=vm.createContext({console,Promise,Image:class{set src(value){loaded.push(value);assert.equal(value,'../../atlas.png');this.onload()}},
 document:{querySelector(s){return els[s]},addEventListener(k,v){listeners[k]=v}},
 addEventListener(k,v){listeners[k]=v},requestAnimationFrame(fn){raf.push(fn)},fetch:async url=>{assert.equal(url,'../../animations.json');return {ok:true,json:async()=>doc}}});
vm.runInContext(fs.readFileSync(path.join(dir,'sprite-player.js'),'utf8'),context);
vm.runInContext(scripts[0],context);
setImmediate(()=>{assert.equal(loaded.length,1);assert.equal(raf.length,1);raf.shift()(0);assert.equal(draws,1);
 els['#go'].onclick();raf.shift()(100);assert(els['#status'].textContent.startsWith('resume'));
 els['#stop'].onclick();for(let t=200;t<3000;t+=100)raf.shift()(t);assert(els['#status'].textContent.startsWith('hold'));
 listeners.keydown({key:'ArrowRight',preventDefault(){}});raf.shift()(3000);listeners.visibilitychange();
 assert(draws>20);console.log('demo resource schema, controls and canvas wiring passed (mock DOM)');});
'''
        run = subprocess.run(['node', '-e', code, str(ROOT/'game-sprite-animator/assets/engine/web')], capture_output=True, text=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
