#!/usr/bin/env python3
"""Render the actual exported JS controller's frame choices, not a browser pass."""
import argparse
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    script = r'''
const fs=require('fs'),path=require('path');const root=path.resolve(process.argv[1]);
const doc=JSON.parse(fs.readFileSync(path.join(root,'animations.json')));
const {GroundedWalkController}=require(path.join(root,'engine/web/sprite-player.js'));
const c=new GroundedWalkController(doc,[]),records=[];
const commands=new Map([[15,true],[60,false],[113,true],[170,false],[173,true],[175,false]]);
for(let frame=0;frame<240;frame++){
 if(commands.has(frame))c.setMoving(commands.get(frame));
 const result=c.update(frame===0?0:1000/30);
 records.push({frame,time:frame/30,command:commands.has(frame)?commands.get(frame):null,
   ...result,distance:c.distance,clip:c.player.name,sprite_frame:c.player.frame});
}
console.log(JSON.stringify({fps:30,records}));
'''
    result = subprocess.run(['node', '-e', script, str(args.build.resolve())], capture_output=True, text=True, check=True)
    trace = json.loads(result.stdout)
    doc = json.loads((args.build/'animations.json').read_text())
    pages = [Image.open(args.build/p['file']).convert('RGBA') for p in doc['pages']]
    size = doc['frame_size']; ground = doc['pivot'][1]
    frames = []
    raw = args.out/'frames'; raw.mkdir(exist_ok=True)
    for r in trace['records']:
        region = doc['regions'][doc['clips'][r['clip']]['frames'][r['sprite_frame']]]
        im = Image.new('RGBA', (size, size+50), (226,231,236,255))
        draw = ImageDraw.Draw(im)
        draw.line((0,ground,size,ground), fill=(120,135,145), width=1)
        for x in range(-45,size+45,45):
            x -= r['distance'] % 45
            draw.line((x,ground,x-10,ground+10), fill=(135,145,155), width=1)
        tile = pages[region['page']].crop((region['x'],region['y'],region['x']+region['w'],region['y']+region['h']))
        im.alpha_composite(tile,(region['ox'],region['oy']))
        draw.text((8,size+5),f"{r['time']:.2f}s | {r['state']} | {r['clip']}:{r['sprite_frame']}",fill='black')
        draw.text((8,size+23),'Actual exported JS frame selection; not browser playback',fill='black')
        im.save(raw/f"{r['frame']:03}.png")
        frames.append(im.convert('RGB'))
    durations=[round((i+1)*100/30)*10-round(i*100/30)*10 for i in range(len(frames))]
    frames[0].save(args.out/'proof.gif',save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2)
    contact = Image.new('RGB',(size*4,(size+50)*3),(226,231,236))
    for i,frame in enumerate([0,18,27,43,61,78,101,119,138,171,195,235]):
        contact.paste(frames[frame],((i%4)*size,(i//4)*(size+50)))
    contact.save(args.out/'contact-sheet.jpg')
    trace['verification_scope']='Actual Node JS controller and atlas frames. Browser launch blocked; not browser visual playback.'
    (args.out/'trace.json').write_text(json.dumps(trace,indent=2))
    print(args.out/'proof.gif')


if __name__ == '__main__':
    main()
