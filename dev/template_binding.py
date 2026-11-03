"""Bind approved full-template layers to the existing humanoid runtime.

Development adapter: known source joints, existing writer, mesh and idle/walk.
No inferred replacement joints, new art, generation-budget reset or final pass.
"""
import argparse
from pathlib import Path
import sys
import numpy as np
from PIL import Image
import template_puppet as tp
import template_full_character as full
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'game-sprite-animator/scripts'))
import layer_parts as lp


def approved(stage):
    stage=Path(stage);job,c=tp.validate(stage);a=tp.read(stage/'static_user_approval.json')
    if a['contract_sha256']!=tp.sha(stage/'contract.json'):raise ValueError('static approval contract changed')
    for n,h in a['assets'].items():
        if tp.sha(stage/n)!=h:raise ValueError('static approval asset changed: '+n)
    qa=tp.read(stage/'static_checks.json');report=tp.read(stage/'assembly_report.json')
    if qa['status']!='static_numerical_checks_met' or report['blockers']:raise ValueError('static geometry remains blocked')
    for slot in full.ORDER:
        _,entry,_=full.selected(stage,slot)
        if entry['geometry']['blockers']:raise ValueError('part remains blocked: '+slot)
        if tp.sha(stage/'assembled_layers'/(slot+'.png'))!=qa['assets'][slot]:raise ValueError('assembled layer changed: '+slot)
    return report,c


from known_joint_rig import canonical_arm, build_spec


def bind(stage,out):
    stage=Path(stage).resolve();out=Path(out).resolve();report,c=approved(stage)
    if out.exists():raise ValueError('binding destination exists; preserve prior rig')
    images={s:Image.open(stage/'assembled_layers'/(s+'.png')).convert('RGBA') for s in full.ORDER}
    spec,metrics=build_spec(images,report['joints'],c['order']);out.mkdir(parents=True)
    arrays={s:np.asarray(images[s]) for s in c['order']};ref=np.asarray(Image.open(stage/'character_draft.png').convert('RGBA'))
    state=dict(layers=arrays,joint_chains={s:spec['puppet']['layers'][s].get('rest',[]) for s in c['order'] if spec['puppet']['layers'][s]['kind']=='tube'},
      scope='known-joint numerical binding only; motion and visual approval separate',static_user_approval_sha256=tp.sha(stage/'static_user_approval.json'))
    lp.write_binding(str(out),'Template character',ref,arrays,spec,metrics,state)
    provenance={'stage':str(stage),'assets':{str(p.relative_to(out)):tp.sha(p) for p in out.rglob('*') if p.is_file()},
      'source_approval_sha256':tp.sha(stage/'static_user_approval.json'),'source_contract_sha256':tp.sha(stage/'contract.json'),
      'source_assembled_layers':{s:tp.sha(stage/'assembled_layers'/(s+'.png')) for s in full.ORDER},
      'processor_sha256':tp.sha(__file__),'full_character_bound':True,'motion_approved':False,'final_visual_pass':False}
    tp.write(out/'provenance.json',provenance);return metrics


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage');p.add_argument('out');a=p.parse_args();print(bind(a.stage,a.out))
