"""Bounded whole-part registration, including modest independent axis scaling.

No clipping mask, per-joint deformation, painted pixels, or character landmarks.
Acceptance remains the caller's full-resolution geometry and visual review.
"""
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.optimize import differential_evolution


def warp(image, params, size, resample=Image.Resampling.BICUBIC):
    sx,sy,dx,dy=params
    return image.transform((size,size),Image.Transform.AFFINE,
                           (1/sx,0,-dx/sx,0,1/sy,-dy/sy),resample)


def fit(image, structure, joints, rules):
    size=image.width;resolution=128;ratio=size/resolution
    alpha=image.getchannel('A').resize((resolution,resolution),Image.Resampling.BILINEAR)
    def reduced(mask):
        return np.asarray(Image.fromarray(mask.astype('uint8')*255).resize(
            (resolution,resolution),Image.Resampling.NEAREST))>0
    core=reduced(ndi.binary_erosion(structure,iterations=8))
    allowed=reduced(ndi.binary_dilation(structure,iterations=rules['envelope_px']))
    yy,xx=np.indices((resolution,resolution))
    anchors=[(xx-x/ratio)**2+(yy-y/ratio)**2<=(12/ratio)**2 for x,y in joints.values()]
    def objective(params):
        a=np.asarray(warp(alpha,params,resolution,Image.Resampling.BILINEAR),dtype=float)/255
        coverage=float(a[core].mean());inside=float(a[allowed].sum()/max(a.sum(),1))
        support=np.array([a[m].mean() for m in anchors])
        # Optimize the actual required coverage/support, not just intersection/union.
        return (max(rules['core_coverage']-coverage,0)**2+
                max(rules['inside_envelope']-inside,0)**2+
                np.square(np.maximum(.98-support,0)).sum()+.00001*(1-coverage))
    delta=rules['max_scale_delta'];travel=rules['max_translation_fraction']*resolution
    identity=[1.,1.,0.,0.]
    if objective(identity)<1e-8:
        local=np.array(identity)
    else:
        result=differential_evolution(objective,[(1-delta,1+delta)]*2+[(-travel,travel)]*2,
                    seed=0,maxiter=110,popsize=9,tol=.00001,polish=False)
        local=result.x if result.fun<objective(identity) else np.array(identity)
    params=[float(local[0]),float(local[1]),float(local[2]*ratio),float(local[3]*ratio)]
    source_alpha=np.asarray(image)[:,:,3]
    y,x=np.nonzero(source_alpha>128)
    tx=x*params[0]+params[2];ty=y*params[1]+params[3]
    clipped=int(((tx<0)|(tx>=size)|(ty<0)|(ty>=size)).sum())
    return warp(image,params,size),{'method':'bounded_whole_part_axis_scaling_v2',
            'parameters':params,'clipped_source_pixels':clipped,
            'max_axis_scale_delta':delta,'max_translation_fraction':rules['max_translation_fraction'],
            'per_joint_deformation':False,'silhouette_clipping':False}
