"""Experimental horizontal cage deformation of complete, reviewed limb art.

This is a separate operation after global registration, not a looser acceptance
test. It stretches existing pixels only; never fills alpha or clips to a stencil.
Height, joint definitions and the source image remain unchanged. All ordinary
coverage/attachment/content checks still apply to the resulting picture.
"""
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

MAX_LOCAL_STRETCH = 1.25
MAX_EDGE_SHIFT = 28.0


def deform(image, required_structure):
    pixels=np.asarray(image.convert('RGBA'),dtype=np.float32)/255
    h,w=pixels.shape[:2]
    if required_structure.shape!=(h,w):raise ValueError('source and structure sizes differ')
    mask=pixels[:,:,3]>.5
    core=ndi.binary_erosion(required_structure,iterations=8)
    left=np.zeros(h);width=np.ones(h);dl=np.zeros(h);dr=np.zeros(h);active=np.zeros(h,bool)
    for y in range(h):
        src=np.flatnonzero(mask[y]);target=np.flatnonzero(core[y])
        # Empty rows cannot invent a missing limb segment; thin tips are protected.
        if len(src)<24 or not len(target):continue
        left[y]=src[0];width[y]=src[-1]-src[0]+1;active[y]=True
        dl[y]=max(-MAX_EDGE_SHIFT,min(0,float(target[0]-src[0])))
        dr[y]=min(MAX_EDGE_SHIFT,max(0,float(target[-1]-src[-1])))
    # Smooth corrections across the limb. No character-specific points or bands.
    sigma=max(h,w)/64
    dl=ndi.gaussian_filter1d(dl,sigma);dr=ndi.gaussian_filter1d(dr,sigma)
    dl[~active]=0;dr[~active]=0
    growth=dr-dl;budget=(MAX_LOCAL_STRETCH-1)*width
    factor=np.minimum(1,budget/np.maximum(growth,1e-8));dl*=factor;dr*=factor
    scale=1+(dr-dl)/width
    yy,xx=np.indices((h,w),dtype=np.float32)
    source_x=left[:,None]+(xx-left[:,None]-dl[:,None])/scale[:,None]
    # Premultiplied resampling avoids importing RGB hidden in transparent pixels.
    premul=pixels.copy();premul[:,:,:3]*=premul[:,:,3:4]
    out=np.empty_like(premul)
    for ch in range(4):
        out[:,:,ch]=ndi.map_coordinates(premul[:,:,ch],[yy,source_x],order=1,
                                       mode='constant',cval=0,prefilter=False)
    alpha=out[:,:,3:4]
    out[:,:,:3]=np.divide(out[:,:,:3],alpha,out=np.zeros_like(out[:,:,:3]),where=alpha>1e-6)
    result=Image.fromarray(np.rint(np.clip(out,0,1)*255).astype('uint8'))
    sy,sx=np.nonzero(mask)
    mapped_x=left[sy]+dl[sy]+(sx-left[sy])*scale[sy]
    clipped=int(((mapped_x<0)|(mapped_x>w-1)).sum())
    return result,{'method':'horizontal_cage_v1','source_pixels_painted':0,
        'alpha_filled':False,'silhouette_clipping':False,'vertical_displacement':0,
        'min_horizontal_jacobian':float(scale.min()),
        'max_horizontal_jacobian':float(scale.max()),
        'max_edge_displacement_px':float(max(abs(dl).max(),abs(dr).max())),
        'clipped_source_pixels':clipped,
        'limits':{'max_local_stretch':MAX_LOCAL_STRETCH,'max_edge_displacement_px':MAX_EDGE_SHIFT},
        'note':'Local geometry deformation, in addition to the earlier bounded global fit. Not an art or binding approval.'}
