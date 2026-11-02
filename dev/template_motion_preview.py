"""Offline idle/walk review from actual baked frames, atlas and sealed binding."""
import argparse
import base64
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image,ImageDraw,ImageOps
import template_puppet as tp
import template_binding as tb

ROOT=Path(__file__).resolve().parents[1]


def prepare(folder):
    folder=Path(folder).resolve();rig=folder/'rig';build=folder/'build'
    provenance=tp.read(rig/'provenance.json');stage=Path(provenance['stage']);tb.approved(stage)
    if provenance['processor_sha256']!=tp.sha(ROOT/'dev/template_binding.py'):raise ValueError('binding processor changed')
    for n,h in provenance['assets'].items():
        if tp.sha(rig/n)!=h:raise ValueError('exported rig changed: '+n)
    if tp.sha(stage/'static_user_approval.json')!=provenance['source_approval_sha256']:raise ValueError('source approval changed')
    doc=tp.read(build/'animations.json');qa=tp.read(build/'qa_report.json');trace=tp.read(build/'rig_trace.json')
    if set(doc['clips'])!={'idle','walk'}:raise ValueError('preview only accepts idle and walk')
    for name,clip in doc['clips'].items():
        count=len(clip['frames']);tr=trace['traces'].get(name,{})
        if len(tr.get('contacts',{}).get('n',[]))!=count:raise ValueError('render/trace incomplete: '+name)
        if qa['clips'][name]['frames']!=count:raise ValueError('render/QA incomplete: '+name)
    if trace.get('part_problems'):raise ValueError('motion parts remain blocked: '+str(trace['part_problems']))
    if any(v=='FAIL' for row in qa['clips'].values() for v in row.values() if isinstance(v,str)):raise ValueError('motion QA failed')
    regions=doc['regions'];x0=min(r['ox'] for r in regions)-24;y0=min(r['oy'] for r in regions)-24
    x1=max(r['ox']+r['w'] for r in regions)+24;y1=max(max(r['oy']+r['h'] for r in regions),doc['pivot'][1])+32
    crop=(x0,y0,x1,y1);size=(round((x1-x0)*2),round((y1-y0)*2));floor=(doc['pivot'][1]-y0)*2
    for name,clip in doc['clips'].items():
        paths=sorted((build/'frames'/name).glob('*.png'))
        if len(paths)!=len(clip['frames']):raise ValueError('missing actual frames')
        frames=[];durations=[];n=len(paths)
        for i,path in enumerate(paths):
            a=Image.open(path).convert('RGBA').crop(crop).resize(size,Image.Resampling.LANCZOS)
            bg=Image.new('RGBA',size,(225,230,237,255));draw=ImageDraw.Draw(bg);draw.line((0,floor,size[0],floor),fill=(110,130,146),width=2)
            travel=clip['speed_px_s']*clip['duration']*i/n*2
            for k in range(-1,round(size[0]/42)+2):
                x=k*42-travel%42;draw.line((x,floor+4,x-12,floor+18),fill=(166,179,191),width=2)
            bg.alpha_composite(a);frames.append(bg.convert('RGB'))
            durations.append(max(10,round(clip['duration']*(i+1)/n*100)*10-round(clip['duration']*i/n*100)*10))
        frames[0].save(folder/(name+'.gif'),save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2)
    pages=['data:image/png;base64,'+base64.b64encode((build/p['file']).read_bytes()).decode() for p in doc['pages']]
    script=(ROOT/'game-sprite-animator/assets/engine/web/sprite-player.js').read_text()
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>剑客待机与走路预览</title><style>
*{box-sizing:border-box}body{margin:0;background:#111925;color:#e9eff6;font:16px/1.6 system-ui,sans-serif}main{max-width:900px;margin:auto;padding:28px}h1{font-size:28px;margin:8px 0}p{color:#b2c0d1}.badge{color:#efc786}canvas{max-width:100%;display:block;margin:20px auto;border-radius:12px;background:#e1e6ed}.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center}button,select{font:inherit;background:#29415f;color:white;border:1px solid #45607f;border-radius:8px;padding:8px 14px}input{vertical-align:middle}#seek{width:min(360px,65vw)}.frame{font-variant-numeric:tabular-nums}</style><main><span class="badge">动态初稿 · 待确认</span><h1>剑客：待机与走路</h1><p>切换动作查看效果，也可以暂停后逐帧检查。</p><div class="controls"><select id="clip"><option value="idle">待机</option><option value="walk">走路</option></select><button id="play">暂停</button><label>速度 <select id="speed"><option value="1">正常</option><option value="0.5">半速</option><option value="0.25">四分之一</option></select></label></div><canvas id="stage" width="__W__" height="__H__"></canvas><div class="controls"><input id="seek" type="range" min="0" value="0"><span class="frame" id="counter"></span></div></main><script>__PLAYER__</script><script>
const doc=__DOC__,urls=__PAGES__,crop=__CROP__,images=[],canvas=document.getElementById('stage'),ctx=canvas.getContext('2d');let player,playing=true,last=null,travel=0;
function draw(){if(!player)return;ctx.fillStyle='#e1e6ed';ctx.fillRect(0,0,canvas.width,canvas.height);const floor=(doc.pivot[1]-crop[1])*2;ctx.strokeStyle='#6e8292';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,floor);ctx.lineTo(canvas.width,floor);ctx.stroke();ctx.strokeStyle='#a6b3bf';for(let k=-1;k<canvas.width/42+2;k++){const x=k*42-travel%42;ctx.beginPath();ctx.moveTo(x,floor+4);ctx.lineTo(x-12,floor+18);ctx.stroke()}player.draw(ctx,(doc.pivot[0]-crop[0])*2,(doc.pivot[1]-crop[1])*2,{scale:2});document.getElementById('seek').value=player.frame;document.getElementById('counter').textContent=(player.frame+1)+' / '+player.clip.frames.length}
function choose(name){player.play(name,{restart:true});travel=0;document.getElementById('seek').max=player.clip.frames.length-1;draw()}
function pause(){playing=false;document.getElementById('play').textContent='播放'}
Promise.all(urls.map(url=>new Promise(resolve=>{let im=new Image();images.push(im);im.onload=resolve;im.src=url}))).then(()=>{player=new SpritePlayer(doc,images);choose('idle');window.preview={player,doc,draw,pause,choose,canvas};requestAnimationFrame(tick)});
function tick(now){const dt=last===null?0:Math.min(100,now-last);last=now;if(playing){const speed=+document.getElementById('speed').value;player.update(dt,speed);travel+=dt/1000*speed*player.clip.speed_px_s*2;draw()}requestAnimationFrame(tick)}
document.getElementById('clip').onchange=e=>choose(e.target.value);document.getElementById('play').onclick=()=>{playing=!playing;document.getElementById('play').textContent=playing?'暂停':'播放'};document.getElementById('seek').oninput=e=>{pause();player.frame=+e.target.value;player.acc=0;travel=player.frame/player.clip.fps*player.clip.speed_px_s*2;draw()};
</script></html>'''
    for key,value in {'__W__':size[0],'__H__':size[1],'__PLAYER__':script,'__DOC__':json.dumps(doc),'__PAGES__':json.dumps(pages),'__CROP__':json.dumps(crop)}.items():html=html.replace(key,str(value))
    (folder/'preview.html').write_text(html)
    runtime=ROOT/'game-sprite-animator/scripts/sprite_anim'
    record={'status':'preview_ready_needs_visual_review','clips':{n:len(c['frames']) for n,c in doc['clips'].items()},
      'binding_provenance_sha256':tp.sha(rig/'provenance.json'),'qa_sha256':tp.sha(build/'qa_report.json'),
      'runtime_sha256':{n:tp.sha(runtime/n) for n in ('rig.py','motions.py','art.py','puppet.py','constraints.py','render.py')},
      'assets':{str(p.relative_to(folder)):tp.sha(p) for p in [folder/'preview.html',folder/'idle.gif',folder/'walk.gif',build/'animations.json',build/'rig_trace.json']},
      'user_motion_approval':'pending','final_visual_pass':False,'engine_playback':False}
    tp.write(folder/'preview_provenance.json',record);return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder');a=p.parse_args();print(prepare(a.folder))
