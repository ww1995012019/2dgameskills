"""Standalone limb range test using production puppet mesh/raster code.

Not a complete rig, walk, foot-contact test or engine integration claim.
"""
import argparse
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image,ImageDraw

import template_puppet as tp
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'game-sprite-animator/scripts'))
from sprite_anim import puppet as pp
from sprite_anim import puppet_check as pc


def rotate(v,angle):
    c,s=math.cos(angle),math.sin(angle)
    return np.array([v[0]*c-v[1]*s,v[0]*s+v[1]*c])


def run(out,frames=20):
    out=Path(out);job,contract=tp.validate(out);folder=out/'motion_probe'
    if folder.exists():raise ValueError('motion test exists; preserve previous results')
    folder.mkdir();layers={};records={};tiles={}
    for slot,bones in [('arm_near',('shoulder','elbow','wrist')),('leg_near',('hip','knee','ankle'))]:
        path,selection=tp.selected_part(out,slot)
        if selection['geometry']['blockers']:raise ValueError('part geometry is still blocked')
        image=Image.open(path).convert('RGBA');box=image.getchannel('A').getbbox()
        image.crop(box).save(folder/(slot+'.png'))
        rest=np.array([contract['slots'][slot]['joints'][b] for b in bones],dtype=float)
        mask=np.asarray(image)[:,:,3]>128
        length=np.linalg.norm(np.diff(rest,axis=0),axis=1).sum()
        radius=float(mask.sum()/(2*length))
        layer=pp.Layer(slot,{'kind':'tube','image':slot+'.png','offset':list(box[:2]),
                  'bones':list(bones),'rest':rest.tolist(),'radius':radius},str(folder))
        pixels=np.asarray(layer.image,dtype=np.float32)/255;pixels[:,:,:3]*=pixels[:,:,3:4]
        # Production raster samples one extra neighbor at the edge.
        mip=(np.pad(pixels,((0,1),(0,1),(0,0)),mode='edge'),1.)
        records[slot]={'source_sha256':tp.sha(path),'source_file':str(path.relative_to(out)),
                       'frames':[],'bone_lengths':np.linalg.norm(np.diff(rest,axis=0),axis=1).tolist()}
        layers[slot]=(layer,mip,rest)
    gif=[]
    for frame in range(frames):
        combined=Image.new('RGB',(1024,550),(235,238,242));draw=ImageDraw.Draw(combined)
        draw.text((20,10),'JOINT RANGE TEST / ISOLATED LIMBS / NOT IDLE OR WALK',fill='black')
        for column,slot in enumerate(('arm_near','leg_near')):
            layer,mip,rest=layers[slot];points=rest.copy()
            phase=.5-.5*math.cos(2*math.pi*frame/frames)
            bend=math.radians(-35 if slot=='arm_near' else 45)*phase
            points[2]=points[1]+rotate(rest[2]-rest[1],bend)
            vertices=pp.untangle(pp.blur(layer.mapped(points*.5,.5),pp.EASE_PASSES),layer.cells)
            fold=pc.inverted(vertices,layer.cells)
            occupied=vertices[layer.used]
            clipped=bool((occupied[:,0]<0).any() or (occupied[:,0]>=512).any() or
                         (occupied[:,1]<0).any() or (occupied[:,1]>=512).any())
            error=float(np.abs(np.linalg.norm(np.diff(points,axis=0),axis=1)-records[slot]['bone_lengths']).max())
            record={'frame':frame,'bend_degrees':math.degrees(bend),'fold_share':float(fold),
                    'clipped':clipped,'max_bone_length_error_px':error,'joints':points.tolist()}
            records[slot]['frames'].append(record)
            rendered=pp.raster(layer,vertices,mip,512,512)
            flat=np.clip(rendered[:,:,:3]+np.array([.86,.88,.90])*(1-rendered[:,:,3:4]),0,1)
            im=Image.fromarray(np.rint(flat*255).astype('uint8'));im.save(folder/f'{slot}_{frame:03d}.png')
            combined.paste(im,(column*512,35));draw.text((column*512+15,25),slot,fill='black')
            if frame in (0,5,10,15):
                review=im.copy();d=ImageDraw.Draw(review)
                for point in points*.5:
                    x,y=point;d.ellipse((x-4,y-4,x+4,y+4),fill='cyan',outline='black')
                tiles[(slot,frame)]=review
        gif.append(combined)
    gif[0].save(folder/'joint_range.gif',save_all=True,append_images=gif[1:],duration=90,loop=0)
    sheet=Image.new('RGB',(1536,860),(240,242,245));d=ImageDraw.Draw(sheet)
    for row,slot in enumerate(('arm_near','leg_near')):
        for col,frame in enumerate((0,5,10,15)):
            im=tiles[(slot,frame)].resize((384,384));sheet.paste(im,(col*384,row*430+35))
            d.text((col*384+10,row*430+12),slot+' / frame '+str(frame),fill='black')
    sheet.save(folder/'joint_review.jpg')
    failures=[{'slot':slot,**f} for slot,r in records.items() for f in r['frames']
              if f['fold_share']>pc.FOLD_SHARE or f['clipped'] or f['max_bone_length_error_px']>1e-6]
    report={'status':'pass' if not failures else 'fail','scope':'standalone limb numerical range test only',
            'full_character_bound':False,'idle_walk_generated':False,'production_fold_limit':pc.FOLD_SHARE,
            'contract_sha256':job['contract_sha256'],'parts':records,'failures':failures,
            'limitations':['No ground contact or hand/weapon gripping test.','Not a full-character animation or final visual approval.']}
    tp.write(folder/'report.json',report)
    return {'status':report['status'],'failures':failures,'gif':str(folder/'joint_range.gif')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out');a=p.parse_args()
    print(run(a.out))
