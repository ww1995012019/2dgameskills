"""Ground support from source alpha boundaries on the actual puppet meshes."""
import numpy as np

from .art import Canvas
from .puppet import mask_interior, mesh_points
from .rig import full_pose, solve


class PaintedGround:
    method = 'opaque_source_boundary_mesh_v1'

    def __init__(self, puppet, body):
        if any(layer.kind=='cloth' for layer in puppet.layers):
            raise ValueError('measured ground roll requires the fitted basic layers, without cloth chains')
        self.puppet,self.body = puppet,body
        self.canvas = Canvas(2,1,1.,0.,1.,False,(0,0,0))
        self.boundaries = {}

    def boundary(self, layer):
        raw = layer.image.getchannel('A').tobytes()
        entry = self.boundaries.get(layer.name)
        if entry is None or entry[0]!=raw:
            mask = np.frombuffer(raw,np.uint8).reshape(layer.image.height,layer.image.width)>127
            y,x = np.nonzero(mask & ~mask_interior(mask))
            if not len(x):
                raise ValueError('ground contact: empty source material '+layer.name)
            centres = np.column_stack((x,y)).astype(float)
            corners = np.concatenate([centres+(dx,dy) for dx,dy in
                                      ((-.5,-.5),(.5,-.5),(-.5,.5),(.5,.5))])
            entry = raw,corners
            self.boundaries[layer.name] = entry
        return entry[1]+layer.offset

    def __call__(self, pose):
        cv = self.canvas
        cv.set_squash(pose['squash'],0.)
        sk = solve(full_pose(pose),self.body)
        low = float('inf')
        for layer,vertices in self.puppet.meshes(cv,sk,{},False):
            pixels = mesh_points(layer,vertices,self.boundary(layer))
            low = min(low,-float(pixels[:,1].max()))
        if not np.isfinite(low):
            raise ValueError('ground contact: no rendered source surfaces')
        return low


def painted_floor(seq, ground_y, unit_px):
    """Independent native-RGBA check; keep the existing one-rig-unit floor limit."""
    if not np.isfinite(unit_px) or unit_px<=0:
        raise ValueError('painted ground: invalid native world scale')
    limit = max(1.,float(unit_px))  # At least one native pixel for raster quantization.
    intrusions,failed = [],[]
    for index,frame in enumerate(seq):
        y,_ = np.nonzero(frame[...,3]>.5)
        if not len(y):
            raise ValueError('painted ground: empty rendered frame')
        depth = max(0.,float(y.max())+.5-ground_y)
        intrusions.append(depth)
        if depth>limit:
            failed.append(index)
    return dict(status='FAIL' if failed else 'PASS',frames=len(seq),
                max_intrusion_px=round(max(intrusions,default=0.),4),limit_px=round(limit,4),
                bad_frames=failed,method='native_rgba_alpha_0.5')
