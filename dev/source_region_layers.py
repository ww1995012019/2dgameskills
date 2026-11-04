"""Experimental visible color regions, NOT anatomical layers or animation inputs.

Every pixel is owned once. Source colors, coordinates and canvas are unchanged.
This deliberately does not infer hidden anatomy, invent layers, or bind joints.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage


def partition(rgb, colors=12, max_regions=24):
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError('expected uint8 RGB canvas')
    if colors < 2 or max_regions < 1:
        raise ValueError('positive region limit and at least two colors required')
    pixels=rgb.reshape(-1,3).astype(np.float32)
    # Fixed deterministic sampling and farthest-first initialization, no character coordinates.
    sample=pixels[::max(1,len(pixels)//18000)]
    centers=[sample[len(sample)//2]]
    for _ in range(colors-1):
        dist=np.min(np.sum((sample[:,None,:]-np.array(centers)[None,:,:])**2,axis=2),axis=1)
        centers.append(sample[int(np.argmax(dist))])
    centers=np.array(centers)
    for _ in range(15):
        labels=np.argmin(np.sum((sample[:,None,:]-centers[None,:,:])**2,axis=2),axis=1)
        updated=np.array([sample[labels==i].mean(axis=0) if (labels==i).any() else centers[i] for i in range(colors)])
        if np.max(abs(updated-centers))<.1: break
        centers=updated
    labels=np.empty(len(pixels),np.int16)
    for start in range(0,len(pixels),50000):
        block=pixels[start:start+50000]
        labels[start:start+len(block)]=np.argmin(np.sum((block[:,None,:]-centers[None,:,:])**2,axis=2),axis=1)
    labels=labels.reshape(rgb.shape[:2])
    candidates=[]
    for i in range(colors):
        connected,count=ndimage.label(labels==i)
        sizes=np.bincount(connected.ravel()); sizes[0]=0
        for component in np.argsort(sizes)[-max_regions:]:
            if sizes[component]>=max(4,rgb.shape[0]*rgb.shape[1]//2000):
                candidates.append((int(sizes[component]),connected==component,i))
    candidates.sort(key=lambda item:item[0],reverse=True)
    masks=[item[1] for item in candidates[:max_regions]]
    covered=np.logical_or.reduce(masks) if masks else np.zeros(labels.shape,bool)
    masks.append(~covered)
    validate_partition(masks,labels.shape)
    return masks


def validate_partition(masks,shape):
    if not masks or any(m.shape!=shape or m.dtype!=bool for m in masks):
        raise ValueError('nonempty boolean masks must share source canvas')
    ownership=np.sum(masks,axis=0)
    if (ownership!=1).any():
        raise ValueError('source ownership must cover every pixel exactly once')


def export(source,out,colors=12,max_regions=24):
    source,out=Path(source),Path(out)
    out.mkdir(parents=True,exist_ok=False)
    rgb=np.array(Image.open(source).convert('RGB'))
    masks=partition(rgb,colors,max_regions)
    rebuilt=np.zeros_like(rgb); layers=[]
    for i,mask in enumerate(masks):
        if not mask.any():continue
        y,x=np.nonzero(mask); left,top,right,bottom=int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)
        data=np.zeros((bottom-top,right-left,4),np.uint8)
        local=mask[top:bottom,left:right]
        data[local,:3]=rgb[top:bottom,left:right][local]; data[local,3]=255
        file=f'region-{i:02d}.png'; Image.fromarray(data).save(out/file)
        rebuilt[mask]=rgb[mask]
        layers.append(dict(name='Residual details' if i==len(masks)-1 else f'Visible region {i+1:02d}',file=file,offset=[left,top],pixels=int(mask.sum()),role='unclassified_visible_region',hidden_surface_pixels=0))
    delta=int(np.count_nonzero(np.any(rgb!=rebuilt,axis=2)))
    if delta:raise ValueError('source pixel preservation failure')
    Image.fromarray(rebuilt).save(out/'static-recomposition.png')
    report=dict(schema='visible-region-candidates-v1',status='needs_semantic_review_not_bindable',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),canvas=[rgb.shape[1],rgb.shape[0]],method='deterministic RGB clustering and four-connected components; not anatomy recognition',parameters=dict(colors=colors,max_regions=max_regions),layers=layers,proof=dict(changed_source_pixels=delta,ownership_overlap=0,unowned_source_pixels=0,hidden_surface_pixels=0),limits=['Background is retained and may occupy a candidate layer.','Regions are connected color fragments, not complete anatomical parts.','No joints, complete limbs, masks for hidden surfaces or animation were inferred.','Source JPEG anti-aliasing and background fringes are retained.','Removing a region exposes missing pixels, not a reconstructed surface.'])
    (out/'layers.json').write_text(json.dumps(report,indent=2)+'\n')
    packed=[]
    for layer in layers:
        packed.append(dict(layer,uri='data:image/png;base64,'+base64.b64encode((out/layer['file']).read_bytes()).decode()))
    html='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>可见区域候选 · 静态复原</title><style>body{background:#172523;color:#e1ebe5;font:15px system-ui;margin:0}header{padding:18px}h1{font-size:23px}main{display:flex;align-items:flex-start;gap:20px;padding:16px}canvas{width:min(65vw,700px);height:auto;background:repeating-conic-gradient(#aaa 0% 25%,#ddd 0% 50%) 0 / 20px 20px}aside{max-width:390px}label{display:block;padding:7px;border-bottom:1px solid #426058}button{padding:10px;margin:4px;cursor:pointer}p{line-height:1.6}.warning{color:#f4c889}@media(max-width:700px){main{display:block}canvas{width:100%}}</style><header><h1>原画像素分层候选 · 静态组合</h1><p class="warning">实验候选，不是完整身体图层，不可直接绑定。隐藏表面补画 0 像素，动画 0 帧。</p></header><main><canvas id="view" width="WIDTH" height="HEIGHT"></canvas><aside><p>颜色与连通区域自动拆分。每个原像素只属于一层，全部打开时逐像素复原原图。候选可能包含背景，不能把同色片段当作完整头、手或腿。</p><button id="all">全部显示</button><button id="none">全部隐藏</button><p>勾选可检查每片可见区域。隐藏某片会留下透明空缺，不会出现臆造的衣服或身体。</p><div id="list"></div><p id="status"></p></aside></main><script>const data=DATA;const c=document.getElementById('view'),ctx=c.getContext('2d');let images=[];function render(){ctx.clearRect(0,0,c.width,c.height);data.forEach((r,i)=>{if(r.enabled)ctx.drawImage(images[i],...r.offset)});document.getElementById('status').textContent=data.filter(r=>r.enabled).length+' / '+data.length+' 可见候选'}Promise.all(data.map((r,i)=>new Promise(ok=>{r.enabled=true;const im=new Image();images[i]=im;im.onload=ok;im.src=r.uri;const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=true;check.onchange=()=>{r.enabled=check.checked;render()};label.append(check,document.createTextNode(' '+r.name+' · '+r.pixels+' px'));document.getElementById('list').append(label)}))).then(()=>{render();window.layersReady=true});function all(value){data.forEach(r=>r.enabled=value);document.querySelectorAll('input').forEach(c=>c.checked=value);render()}document.getElementById('all').onclick=()=>all(true);document.getElementById('none').onclick=()=>all(false);</script>'''.replace('WIDTH',str(rgb.shape[1])).replace('HEIGHT',str(rgb.shape[0])).replace('DATA',json.dumps(packed))
    (out/'layers-review.html').write_text(html)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('--out',required=True);p.add_argument('--colors',type=int,default=12);p.add_argument('--max-regions',type=int,default=24)
    a=p.parse_args();r=export(a.source,a.out,a.colors,a.max_regions);print(json.dumps({'status':r['status'],'layer_count':len(r['layers']),'proof':r['proof']}))
