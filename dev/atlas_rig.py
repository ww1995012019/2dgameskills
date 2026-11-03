"""Experimental atlas adapter: connected parts -> measured humanoid manifest.

No character-specific landmarks or painted masks. Art ownership must be reviewed.
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'game-sprite-animator/scripts'))
import layer_parts as lp

TOP=('head','torso','arm_near','arm_far')
BOTTOM=('hips','leg_near','leg_far','weapon')


def extract(path, folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    a=np.array(Image.open(path).convert('RGBA'));labels,n=ndi.label(a[...,3]>128)
    objects=[]
    for i,slices in enumerate(ndi.find_objects(labels),1):
        if slices is None:continue
        area=int((labels[slices]==i).sum())
        if area>a.shape[0]*a.shape[1]*.005:
            ys,xs=np.nonzero(labels==i);objects.append((float(xs.mean()),float(ys.mean()),i))
    if len(objects)!=8:raise ValueError(f'expected eight separate complete components, got {len(objects)}')
    distance,indices=ndi.distance_transform_edt(labels==0,return_indices=True)
    nearest=labels[tuple(indices)]
    rows=sorted(objects,key=lambda p:p[1]);top=sorted(rows[:4]);bottom=sorted(rows[4:])
    result={}
    for name,(_,_,i) in zip((*TOP,*BOTTOM),(*top,*bottom)):
        keep=(nearest==i)&(distance<=2)&(a[...,3]>16)
        out=a.copy();out[~keep]=0;out[...,3][out[...,3]>=248]=255
        image=Image.fromarray(out);box=image.getbbox();image=image.crop(box)
        image.save(folder/(name+'.png'))
        result[name]=dict(box=list(box),size=list(image.size))
    (folder/'extraction.json').write_text(json.dumps(result,indent=2))
    return result


def landmarks(image,slot):
    a=np.array(image);mask=a[...,3]>128
    if slot.startswith('arm'):
        root,tip=lp.root_and_tip(mask)
        yy,xx=np.indices(mask.shape);dist=(xx-root[0])**2+(yy-root[1])**2
        r,g,b=[a[...,i].astype(float) for i in range(3)]
        skin=mask&(r>120)&(r>g*1.12)&(g>b*1.05)&(r-b>30)&(dist>np.sum((tip-root)**2)*.4)
        labs,n=ndi.label(skin)
        if n:
            sizes=np.bincount(labs.ravel());sizes[0]=0;skin=labs==sizes.argmax()
        if skin.sum()<12:raise ValueError(slot+': cannot locate an exposed hand reliably')
        row=lp.read_arm(mask,skin)
        ys,xs=np.nonzero(skin);row['grip']=np.array([xs.mean(),ys.mean()])
        return row
    if slot.startswith('leg'):return lp.read_leg(mask)
    return {}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('atlas');p.add_argument('out');args=p.parse_args()
    result=extract(args.atlas,args.out)
    for n in (*TOP,*BOTTOM):
        im=Image.open(Path(args.out)/(n+'.png'))
        row=landmarks(im,n)
        if row:
            result[n]['joints']={k:np.asarray(v).tolist() for k,v in row.items()}
            if n.startswith('arm'):
                print(n, result[n]['joints'], 'lengths',lp.check_limb(n,np.array(im)[...,3]>128,[row[k] for k in ('shoulder','elbow','wrist')]))
    (Path(args.out)/'measurements.json').write_text(json.dumps(result,indent=2))


def remove_neck_stub(image):
    """Head owns bare neck; remove the torso atlas's redundant skin stub.

    Detect only skin connected to the upper attachment, not fabric or a fixed
    silhouette. A small outline allowance removes its painted cut-edge rim.
    Return a new alpha matte and retain the source unchanged.
    """
    a=np.array(image);r,g,b=[a[...,i].astype(float) for i in range(3)]
    solid=a[...,3]>128;yy=np.indices(solid.shape)[0]
    skin=solid&(r>25)&(b<r*.85)&(g<r*.94)&(yy<image.height*.18)
    labels,n=ndi.label(skin)
    seeds=np.unique(labels[(yy<image.height*.04)&skin]);seeds=seeds[seeds>0]
    if not len(seeds):return image.copy(),0
    selected=np.isin(labels,seeds)
    selected=ndi.binary_fill_holes(ndi.binary_closing(selected,iterations=1))
    # Close upward to the attachment boundary so neutral-coloured cut-edge
    # highlights are removed with the skin, rather than left as a dotted rim.
    boundary=np.full(image.width,-1,dtype=int)
    sy,sx=np.nonzero(selected)
    np.maximum.at(boundary,sx,sy)
    boundary=ndi.maximum_filter1d(boundary,size=9)
    selected=(yy<=boundary[None,:]+3)&(boundary[None,:]>=0)
    removed=int((selected&(a[...,3]>0)).sum());a[selected]=0
    return Image.fromarray(a),removed


def assemble(parts, out, canvas=(1280,1536), character_name="character"):
    """Assemble one standard adult proportion profile from measured isolated parts.

    Shared anatomical ratios, never per-character coordinate overrides. Whole-part
    similarity transforms preserve drawing proportions; no painted patches/stencils.
    """
    parts=Path(parts);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'layers').mkdir(exist_ok=True)
    images={n:Image.open(parts/(n+'.png')).convert('RGBA') for n in (*TOP,*BOTTOM)}
    local={n:landmarks(images[n],n) for n in (*TOP,*BOTTOM)}
    neck_removed=0
    torso=images['torso'];tm=np.array(torso)[...,3]>128
    row,columns,height=lp.neck_core(tm)
    neck_local=np.array([float(columns.mean()),float(row)])
    waist_row=round(torso.height*.64);xs=np.flatnonzero(tm[waist_row])
    waist_local=np.array([float(np.median(xs)),float(waist_row)])
    scale=500./torso.height
    transforms={'torso':(scale,0.,np.array([430.,260.]))}
    neck=neck_local*scale+transforms['torso'][2]
    waist=waist_local*scale+transforms['torso'][2]
    # Hidden pelvis is deliberately behind the garment and both thighs.
    hips=images['hips'];hm=np.array(hips)[...,3]>128
    hy,hx=np.nonzero(hm);hip_scale=(float(xs.max()-xs.min())*scale*.92)/(hx.max()-hx.min())
    hip_top=np.array([float(np.median(hx[hy<hy.min()+max(2,hips.height*.08)])),float(hy.min()+hips.height*.06)])
    hip_local=np.array([float(np.median(hx)),float(hy.min()+hips.height*.67)])
    offset=waist-hip_top*hip_scale
    transforms['hips']=(hip_scale,0.,offset);hip=hip_local*hip_scale+offset
    # Both complete legs use one scale; preserve measured near/far proportions.
    leg_scale=650./np.mean([images[n].height for n in ('leg_near','leg_far')])
    spread=min(18.,float(xs.max()-xs.min())*scale*.08)
    for n,sign in (('leg_near',1),('leg_far',-1)):
        at=hip+np.array([spread*sign,0.])
        transforms[n]=(leg_scale,0.,at-local[n]['hip']*leg_scale)
    # Keep hand and shoulder positions as measured, do not ask for landmark art.
    leg_bones=np.mean([np.linalg.norm(local[n]['knee']-local[n]['hip'])+np.linalg.norm(local[n]['ankle']-local[n]['knee']) for n in ('leg_near','leg_far')])*leg_scale
    for n,side in (('arm_near',1),('arm_far',-1)):
        chain=[local[n][k] for k in ('shoulder','elbow','wrist')]
        length=sum(np.linalg.norm(np.diff(chain,axis=0),axis=1))
        arm_scale=leg_bones*.65/length
        seat=np.array([transforms['torso'][2][0]+torso.width*scale*.28,
                       transforms['torso'][2][1]+torso.height*scale*.20])
        seat+=np.array([side*7.,0.])
        transforms[n]=(arm_scale,0.,seat-local[n]['shoulder']*arm_scale)
    head=images['head'];mask=np.array(head)[...,3]>128
    head_scale=(500./.4*.16)/head.height
    cy,cx=np.nonzero(tm[:max(3,round(torso.height*.035))])
    cap=np.column_stack((cx,cy))*scale+transforms['torso'][2]
    candidates=[];solid=np.array(head)[...,3]>248
    for y in range(int(head.height*.68),int(head.height*.89)):
        col=np.flatnonzero(mask[y])
        if not len(col):continue
        x=float(np.median(col));offset=neck-np.array([x,y])*head_scale
        sample=np.rint((cap-offset)/head_scale).astype(int)
        valid=(sample[:,0]>=0)&(sample[:,0]<head.width)&(sample[:,1]>=0)&(sample[:,1]<head.height)
        covered=np.zeros(len(sample),bool);covered[valid]=solid[sample[valid,1],sample[valid,0]]
        if covered.mean()>=.995:candidates.append((abs(y-head.height*.85),y,x))
    if not candidates:raise ValueError('head: cannot cover the exposed neck cap')
    _,seat_y,seat_x=min(candidates)
    local['head']={'head_base':np.array([seat_x,float(seat_y)])}
    transforms['head']=(head_scale,0.,neck-local['head']['head_base']*head_scale)
    local['hips']={'hip':hip_local,'waist':hip_top}
    def point(n,p):
        s,angle,o=transforms[n];a=np.radians(angle);rot=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
        return o+s*(rot@p)
    weapon=images['weapon'];wm=np.array(weapon)[...,3]>128
    widths=wm.sum(axis=1);guard=int(np.argmax(widths));grip_y=int(guard+(weapon.height-1-guard)*.53)
    grip_x=float(np.median(np.flatnonzero(wm[grip_y])))
    local['weapon']={'grip':np.array([grip_x,float(grip_y)])}
    sword_scale=leg_bones*.95/weapon.height
    angle=45.;a=np.radians(angle);rot=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
    transforms['weapon']=(sword_scale,angle,point('arm_near',local['arm_near']['grip'])-sword_scale*(rot@local['weapon']['grip']))
    order=['arm_far','hips','leg_far','leg_near','head','torso','weapon','arm_near']
    joints={};report={};composite=Image.new('RGBA',canvas)
    for name in order:
        s,angle,o=transforms[name]
        arr=np.array(images[name]);yy,xx=np.nonzero(arr[...,3]>128)
        rad=np.radians(angle);rotation=np.array([[np.cos(rad),-np.sin(rad)],[np.sin(rad),np.cos(rad)]])
        mapped=np.column_stack((xx,yy))@rotation.T*s+o
        if ((mapped[:,0]<0)|(mapped[:,0]>=canvas[0])|(mapped[:,1]<0)|(mapped[:,1]>=canvas[1])).any():
            raise ValueError(name+': source art would be clipped')
        fit=dict(s=s,deg=angle,dx=float(o[0]),dy=float(o[1]),cx=0.,cy=0.)
        placed=Image.fromarray(lp.placed(arr,fit,canvas))
        placed.save(out/'layers'/(name+'.png'));composite.alpha_composite(placed)
        joints[name]={k:point(name,np.asarray(p)).tolist() for k,p in local[name].items()}
        report[name]=dict(scale=s,angle=angle,offset=o.tolist())
    # Head anchor and garment collar are the same measured assembly seat.
    joints['head']['head_base']=neck.tolist()
    composite.save(out/'assembled.png')
    overlay=Image.new('RGBA',canvas,(225,230,237,255));overlay.alpha_composite(composite)
    draw=ImageDraw.Draw(overlay)
    for name,values in joints.items():
        for key,p in values.items():
            if key in ('tip','heel','toe','grip'):continue
            x,y=p;draw.ellipse((x-4,y-4,x+4,y+4),fill='cyan');draw.text((x+5,y),name+':'+key,fill='black')
    overlay.convert('RGB').save(out/'joints.jpg')
    (out/'input.json').write_text(json.dumps(dict(name=character_name,canvas=list(canvas),order=order,layers={n:'layers/'+n+'.png' for n in order},joints=joints),ensure_ascii=False,indent=2))
    report['preprocessing']={'torso_neck_stub_pixels_removed':neck_removed,'rule':'head owns skin neck; torso owns garment','new_pixels_painted':0}
    (out/'assembly_transforms.json').write_text(json.dumps(report,indent=2))
    return out/'input.json'


def install_collar_overlay(rig):
    """Place original neck behind the head and original garment in front.

    Both torso copies have identical geometry/UVs. Only the front copy's alpha
    removes redundant bare neck, so neither hidden texture nor skin is painted.
    """
    import copy,hashlib
    rig=Path(rig);spec=json.loads((rig/'character.json').read_text())
    layers=spec['puppet']['layers']
    if 'torso_front' in layers:raise ValueError('collar overlay already installed')
    source=rig/layers['torso']['image']
    with Image.open(source) as im:garment,removed=remove_neck_stub(im.convert('RGBA'))
    if not removed:return 0
    garment.save(rig/'layers/torso_front.png')
    front=copy.deepcopy(layers['torso']);front['image']='layers/torso_front.png'
    order=['arm_far','hips','leg_far','leg_near','torso','head','torso_front','weapon','arm_near']
    layers['torso_front']=front
    spec['puppet']['layers']={n:layers[n] for n in order if n in layers}
    (rig/'character.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2))
    report=dict(method='shared_geometry_collar_overlay',neck_pixels_removed_from_front_copy=removed,
                source_rgb_painted=0,source_image_unchanged=True,visual_approval='pending')
    (rig/'collar_overlay.json').write_text(json.dumps(report,indent=2))
    provenance=json.loads((rig/'provenance.json').read_text())
    provenance['derived_collar_overlay']=report
    provenance['runtime_assets']={str(p.relative_to(rig)):hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in rig.rglob('*') if p.is_file() and p.name!='provenance.json'}
    (rig/'provenance.json').write_text(json.dumps(provenance,indent=2))
    return removed
