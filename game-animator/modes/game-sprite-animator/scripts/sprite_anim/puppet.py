"""Layered puppet: whole layers bent along the skeleton, instead of rigid parts hinged at joints.

Each layer is complete art on the reference picture's canvas (see layer_slots.py) and is bound to a
curve through that picture's joints. A pixel keeps its place along the curve and its distance from
it, so when the skeleton moves a sleeve bends with the arm, a knee rounds instead of hinging, and a
cloth follows its simulated chain as one sheet. Joints do not intentionally cut the source layer;
independent layer attachments, mesh folds and visual occlusion still require explicit checks.
"""
import math
import os

import numpy as np
from PIL import Image

from .mathx import rot

GRID = 14          # source pixels between mesh vertices
CURVE_STEPS = 32   # samples per bone along a curve
BLUR_PASSES = 6    # smoothing of each vertex's place along the curve: keeps wide cloth from shearing
INNER_LIMIT = 0.8  # how close the inner side of a bend may come to the curve's centre of turning
EASE_PASSES = 5    # smoothing of the bent mesh. A rotation passes through it unchanged, a crease doesn't
UNTANGLE_PASSES = 80   # most relaxations of a mesh that still has cells turned inside out
ANKLE_TURN = 62.0      # degrees a foot may turn from the shin's line as drawn. Past that, boot and shin cross
SKIRT_SWING = 40.0     # degrees hanging panels may leave the body's line: past that the thighs lift clear of them


def mesh_points(layer, verts, source):
    """Map registered source points through the same two triangles as raster()."""
    p = np.asarray(source, float) - layer.offset
    i = np.clip(np.searchsorted(layer.gx, p[..., 0], side='right') - 1, 0, len(layer.gx) - 2)
    j = np.clip(np.searchsorted(layer.gy, p[..., 1], side='right') - 1, 0, len(layer.gy) - 2)
    u = (p[..., 0] - layer.gx[i]) / (layer.gx[i + 1] - layer.gx[i])
    v = (p[..., 1] - layer.gy[j]) / (layer.gy[j + 1] - layer.gy[j])
    a, b, c, d = verts[j, i], verts[j, i + 1], verts[j + 1, i], verts[j + 1, i + 1]
    first = a + u[..., None] * (b - a) + v[..., None] * (c - a)
    second = d + (1-u)[..., None] * (c-d) + (1-v)[..., None] * (b-d)
    return np.where((u+v <= 1)[..., None], first, second)


def neck_blend_weights(head, torso, seat, waist):
    """Infer a basal neck band from registered opaque overlap, preserving the skull.

    This changes mesh positions only. A painted cut/collar triangle is still bad
    source art and must be repaired; alpha overlap cannot certify its appearance.
    """
    seat, waist = np.asarray(seat, float), np.asarray(waist, float)
    length = float(np.linalg.norm(seat-waist))
    if length < GRID:
        raise ValueError('neck skin: degenerate source chest')
    axis = (seat-waist)/length
    across = np.array([-axis[1], axis[0]])
    hy, hx = np.nonzero(np.asarray(head.image)[..., 3] > 128)
    points = np.stack((hx, hy), -1) + head.offset
    tx, ty = np.rint(points-torso.offset).astype(int).T
    alpha = np.asarray(torso.image)[..., 3] > 128
    inside = (tx >= 0) & (ty >= 0) & (tx < alpha.shape[1]) & (ty < alpha.shape[0])
    overlap = np.zeros(len(points), bool)
    overlap[inside] = alpha[ty[inside], tx[inside]]
    longitudinal, lateral = (points-seat)@axis, (points-seat)@across
    overlap &= ((longitudinal > -.35*length) & (longitudinal < .12*length)
                & (np.abs(lateral) < .2*length))
    if overlap.sum() < 16:
        raise ValueError('neck skin: no registered opaque head/torso neck overlap')
    longitudinal, lateral = longitudinal[overlap], lateral[overlap]
    root = float(np.quantile(longitudinal, .05))
    basal = lateral[longitudinal <= root + max(GRID, .04*length)]
    lo, hi = np.quantile(basal, (.05, .95))
    center, half = float((lo+hi)/2), max(GRID, float((hi-lo)/2))
    # A source seam lies inside a triangle, not necessarily on a grid row.
    # Lock one complete surrounding cell before tapering toward the skull.
    attach = min(root+GRID, -GRID*.5)
    band = max(GRID*.5, min(-attach, 2*half, .2*length))
    grid = np.stack((head.vx, head.vy), -1) + head.offset
    along = (grid-seat)@axis
    cross = (grid-seat)@across
    smooth = lambda x: np.clip(x, 0, 1)**2 * (3-2*np.clip(x, 0, 1))
    weights = (1-smooth((along-attach)/band)) * (1-smooth((np.abs(cross-center)-half*1.25-GRID)/(half*.75)))
    weights[along >= 0] = 0.  # the upper head remains exactly on its rigid skull transform
    # Only source points represented by the parent mesh can be attached to it.
    local = grid-torso.offset
    weights *= ((local[..., 0] >= 0) & (local[..., 0] <= torso.gx[-1])
                & (local[..., 1] >= 0) & (local[..., 1] <= torso.gy[-1]))
    seam = points[overlap][longitudinal <= root]
    seam = seam[np.argsort((seam-seat)@across)]
    seam = seam[np.linspace(0, len(seam)-1, min(12, len(seam))).astype(int)]
    return weights, dict(root=root, attachment_start=attach, half_width=half, band=band, lateral_center=center,
                         source_points=seam.tolist(),
                         overlap_pixels=int(overlap.sum()), method='registered_neck_overlap')


def pelvis_blend_weights(child, parent, seat, distal):
    """Attach a registered garment root to the original pelvis surface.

    Only vertices move: no texture, alpha, waistband or patch is invented.
    The whole proximal overlap is sampled, including its left/right edges.
    """
    seat, distal = np.asarray(seat, float), np.asarray(distal, float)
    length = float(np.linalg.norm(distal-seat))
    if length <= GRID:
        raise ValueError('pelvis skin: degenerate proximal segment')
    axis = (distal-seat)/length
    y, x = np.nonzero(np.asarray(child.image)[..., 3] > 128)
    points = np.column_stack((x, y))+child.offset
    px, py = np.rint(points-parent.offset).astype(int).T
    alpha = np.asarray(parent.image)[..., 3] > 128
    inside = (px >= 0)&(py >= 0)&(px < alpha.shape[1])&(py < alpha.shape[0])
    overlap = np.zeros(len(points), bool)
    overlap[inside] = alpha[py[inside], px[inside]]
    # Locate the actual proximal contour in every lateral slice. An opaque
    # hidden overlap is not all one sewn surface: locking its entire depth
    # would freeze the shorts around a moving thigh and invert their mesh.
    along = (points-seat)@axis
    across = (points-seat)@np.array([-axis[1], axis[0]])
    overlap &= along <= (.65 if child.name == 'torso' else .2)*length
    points = points[overlap]
    if len(points) < 4:
        raise ValueError(f'pelvis skin: {child.name} lacks registered pelvis overlap; repair source art')
    along, across = along[overlap], across[overlap]
    bins = np.floor(across/max(1., child.radius/6)).astype(int)
    contour = np.zeros(len(points), bool)
    for value in np.unique(bins):
        group = bins == value
        contour |= group & (along <= along[group].min()+max(1., .01*length))
    points = points[contour]
    attach = float(along[contour].max())+2*GRID
    fade = max(.35*length, 2*child.radius)
    grid = np.stack((child.vx, child.vy), -1)+child.offset
    s = np.clip(((grid-seat)@axis-attach)/fade, 0, 1)
    weights = 1-s*s*(3-2*s)
    carried = getattr(child, 'source_upper_carry', None)
    if carried is not None:
        start, end = float(carried['protected_y']), float(carried['blend_end_y'])
        # The complete grid cell containing the source hem follows the pelvis.
        end = min(end, float(points[:, 1].min())-GRID)
        if child.name != 'torso' or end-start < GRID:
            raise ValueError('source upper carry requires a separate garment blend below both hands')
        blend = np.clip((grid[..., 1]-start)/(end-start),0,1)
        weights *= blend*blend*(3-2*blend)
    # Grid sampling plus extrema covers the full attachment, not only a centre seat.
    points = points[np.lexsort((points[:, 0], points[:, 1]))]
    sample = points[np.linspace(0, len(points)-1, min(96, len(points))).astype(int)]
    extremes = points[[points[:, 0].argmin(), points[:, 0].argmax(), points[:, 1].argmin(), points[:, 1].argmax()]]
    sample = np.unique(np.vstack((sample, extremes)), axis=0)
    report = dict(method='registered_pelvis_overlap', parent=parent.name,
                  source_points=sample.tolist(), overlap_pixels=len(points),
                  attachment_start=attach, fade=fade)
    if carried is not None:
        report['source_upper_carry'] = dict(carried)
    return weights, report


def joint_socket_binding(child, parent):
    """Registered opaque joint with a cap that rotates with its own thigh.

    Overlapping leg/pelvis pixels are separate surfaces, not a welded seam.
    Never apply the pelvis's rigid rotation to the whole upper leg.
    """
    root, knee = child.rest[:2]
    axis = (knee-root)/np.linalg.norm(knee-root)
    for layer in (child, parent):
        x, y = np.rint(root-layer.offset).astype(int)
        alpha = np.asarray(layer.image)[..., 3]
        if not (0 <= x < alpha.shape[1] and 0 <= y < alpha.shape[0] and alpha[y, x] > 128):
            raise ValueError(f'joint socket: {child.name} source joint lacks opaque {layer.name} coverage')
    y, x = np.nonzero(np.asarray(child.image)[..., 3] > 128)
    points = np.column_stack((x, y))+child.offset
    depth = (points-root)@axis
    points = points[(depth >= -GRID)&(depth <= 0)]
    if len(points) < 4:
        raise ValueError(f'joint socket: {child.name} lacks a complete proximal cap')
    points = points[np.lexsort((points[:, 0], points[:, 1]))]
    indices = np.linspace(0, len(points)-1, min(96, len(points))).astype(int)
    transverse = (points-root)@np.array([-axis[1], axis[0]])
    samples = np.unique(np.vstack((points[indices],points[[transverse.argmin(),transverse.argmax()]])),axis=0)
    return dict(method='registered_articulated_socket_v2',parent=parent.name,
                source_joint=root.tolist(),source_points=samples.tolist())


def mask_interior(mask, passes=1):
    """Four-neighbour source interior; preserve originally hidden cut edges."""
    result = mask.copy()
    for _ in range(passes):
        p = np.pad(result, 1)
        result = p[1:-1,1:-1]&p[:-2,1:-1]&p[2:,1:-1]&p[1:-1,:-2]&p[1:-1,2:]
    return result


def hidden_garment_edges(child, occluders, up):
    """Actual proximal alpha boundaries hidden by later source surfaces.

    A waistband's internal cut must stay inside the garment. Its own rigid
    thigh rotation is insufficient evidence: that rotation can expose it.
    """
    mask = np.asarray(child.image)[...,3] > 128
    y,x = np.nonzero(mask&~mask_interior(mask))
    points = np.column_stack((x,y))+child.offset
    proximal = (points-child.rest[0])@up >= -GRID
    covered = np.zeros(len(points),bool)
    for parent in occluders:
        alpha = mask_interior(np.asarray(parent.image)[...,3]>250,2)
        xy = np.rint(points-parent.offset).astype(int)
        inside = ((xy[:,0]>=0)&(xy[:,1]>=0)
                  &(xy[:,0]<alpha.shape[1])&(xy[:,1]<alpha.shape[0]))
        covered[inside] |= alpha[xy[inside,1],xy[inside,0]]
    points = points[proximal&covered]
    if len(points) < 4:
        raise ValueError(f'garment rim: {child.name} lacks an original hidden proximal edge')
    return dict(method='registered_garment_rim_v1',parent='hips',
                source_joint=child.rest[0].tolist(),source_points=points.tolist(),
                occluders=[p.name for p in occluders])


class GarmentBand:
    """Constrained ARAP on the free cloth band between waist and thigh.

    The hidden rim and distal leg positions are fixed. Local rotations and a
    Laplacian solve preserve material instead of flattening inverted triangles
    to a tiny positive area. Existing fold/strain checks still reject failures.
    """
    def __init__(self, layer, weights):
        width = layer.vx.shape[1]
        j,i = layer.cells.T
        a = j*width+i; b = a+1; c = a+width; d = c+1
        edges = np.concatenate([np.stack(pair,1) for pair in
                                ((a,b),(a,c),(b,c),(b,d),(c,d))])
        edges = np.unique(np.sort(edges,axis=1),axis=0)
        self.i,self.j = np.concatenate((edges,edges[:,::-1])).T
        source = np.stack((layer.vx,layer.vy),-1).reshape(-1,2)
        self.edges = source[self.i]-source[self.j]
        self.count = len(source)
        self.free = np.flatnonzero(((weights>1e-12)&(weights<1-1e-12)&layer.used).ravel())
        lookup = np.full(self.count,-1)
        lookup[self.free] = np.arange(len(self.free))
        degree = np.bincount(self.i,minlength=self.count)
        matrix = np.diag(degree[self.free].astype(float))
        u,v = lookup[self.i],lookup[self.j]
        both = (u>=0)&(v>=0)
        np.add.at(matrix,(u[both],v[both]),-1.)
        self.inverse = np.linalg.inv(matrix) if len(self.free) else None
        boundary = (u>=0)&(v<0)
        self.boundary_free,self.boundary_fixed = u[boundary],self.j[boundary]
        triangles = np.concatenate((np.stack((a,b,c),1),np.stack((d,c,b),1)))
        active = (lookup[triangles]>=0).any(1)
        colors = np.concatenate((2*(j%2)+i%2,4+2*(j%2)+i%2))[active]
        triangles = triangles[active]
        self.triangle_groups = [np.flatnonzero(colors==color) for color in range(8)]
        self.triangles = triangles
        self.triangle_source = source[triangles]
        se = np.stack((self.triangle_source[:,1]-self.triangle_source[:,0],
                       self.triangle_source[:,2]-self.triangle_source[:,0]),-1)
        self.triangle_inverse = np.linalg.inv(se)
        self.movable = np.zeros(self.count,bool)
        self.movable[self.free] = True

    def solve(self, vertices, scale):
        if not len(self.free):
            return vertices
        flat = vertices.reshape(-1,2).copy()
        fixed = np.zeros((len(self.free),2))
        np.add.at(fixed,self.boundary_free,flat[self.boundary_fixed])
        edge = self.edges*scale
        for _ in range(48):
            delta = flat[self.i]-flat[self.j]
            dot,cross = np.zeros(self.count),np.zeros(self.count)
            np.add.at(dot,self.i,np.sum(delta*edge,axis=1))
            np.add.at(cross,self.i,delta[:,1]*edge[:,0]-delta[:,0]*edge[:,1])
            angle = np.arctan2(cross,dot)
            co,si = np.cos(angle),np.sin(angle)
            c,s = (co[self.i]+co[self.j])*.5,(si[self.i]+si[self.j])*.5
            target = np.stack((c*edge[:,0]-s*edge[:,1],s*edge[:,0]+c*edge[:,1]),1)
            rhs = np.zeros((self.count,2))
            np.add.at(rhs,self.i,target)
            flat[self.free] = self.inverse@(rhs[self.free]+fixed)
        # ARAP alone can converge to a folded local minimum in a wide garment.
        # Project actual material strain as well, keeping both boundary owners
        # fixed. These are solver targets; the independent QA limits are unchanged.
        # The final feasibility pass moves only distressed triangles. Repeatedly
        # expanding every mildly compressed neighbour can keep re-folding the
        # same corner. Both passes preserve the fixed rim and distal leg.
        for rounds,lower,upper,area_floor,target_floor in ((80,.5,1.8,0.,.6),(160,.28,2.8,.18,.45)):
            for _ in range(rounds):
                changed = False
                # Same-colour triangles share no vertices.
                for group in self.triangle_groups:
                    if not len(group):
                        continue
                    ids = self.triangles[group]
                    points = flat[ids]
                    de = np.stack((points[:,1]-points[:,0],points[:,2]-points[:,0]),-1)
                    jac = de@self.triangle_inverse[group]/scale
                    u,s,vh = np.linalg.svd(jac)
                    reflected = np.linalg.det(u@vh)<0
                    bad = reflected|(s[:,1]<lower)|(s[:,0]>upper)
                    if area_floor:
                        area = np.linalg.det(jac)
                        bad |= (area<area_floor)|(area>upper)
                    if not bad.any():
                        continue
                    changed = True
                    u,s,vh = u[bad],s[bad],vh[bad]
                    u[reflected[bad],:,-1] *= -1
                    corrected = (u*np.clip(s,target_floor,1.6)[:,None,:])@vh
                    source = self.triangle_source[group[bad]]
                    target = ((source-source.mean(1,keepdims=True))*scale)@corrected.transpose(0,2,1)
                    target += points[bad].mean(1,keepdims=True)
                    ids = ids[bad]
                    delta = (target-points[bad])*self.movable[ids][...,None]
                    flat[ids.ravel()] += .8*delta.reshape(-1,2)
                if not changed:
                    break
        return flat.reshape(vertices.shape)


def corner_run(a, b, c, radius, reach):
    """How far along each bone the arc at corner b starts. A sharper corner needs a longer run to
    keep the same radius; a limb half as wide as that radius would otherwise pinch to a point."""
    u, v = b - a, c - b
    turn = abs(math.atan2(u[0] * v[1] - u[1] * v[0], u @ v))
    run = radius * max(1.0, math.tan(min(turn, 2.6) / 2))
    return min(run, reach * np.hypot(*u), reach * np.hypot(*v))


def rounded(points, radius):
    """Polyline -> dense curve, each inner corner replaced by a quadratic arc. Every call on the same
    number of points gives the same number of samples, so two curves match index by index."""
    pts = [np.asarray(p, dtype=np.float64) for p in points]
    reach = 0.68 if len(pts) == 3 else 0.45     # a bone with one corner has room for a longer arc
    runs = [0.0] + [corner_run(pts[i - 1], pts[i], pts[i + 1], radius, reach) for i in range(1, len(pts) - 1)] + [0.0]
    t = _STEPS[:, None]
    out = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        length = np.hypot(*(b - a)) or 1e-6
        u = (b - a) / length
        start = a + u * runs[i] if i else a
        end = b - u * runs[i + 1] if i < len(pts) - 2 else b
        out.append(start + (end - start) * t)
        if i < len(pts) - 2:
            next_len = np.hypot(*(pts[i + 2] - b)) or 1e-6
            tail = b + (pts[i + 2] - b) / next_len * runs[i + 1]
            out.append(_ARC[0] * end + _ARC[1] * b + _ARC[2] * tail)
    out.append(pts[-1][None])
    return np.concatenate(out)


# Sample positions along one bone or corner arc, and the arc's quadratic Bezier weights.
_STEPS = np.linspace(0, 1, CURVE_STEPS, endpoint=False)
_ARC = ((1 - _STEPS) ** 2)[:, None], (2 * _STEPS * (1 - _STEPS))[:, None], (_STEPS * _STEPS)[:, None]


def frames_of(curve):
    """Unit tangents along a curve."""
    tan = np.gradient(curve, axis=0)
    return tan / (np.hypot(tan[:, 0], tan[:, 1])[:, None] + 1e-9)


def extended(curve, reach):
    """Straight run-outs past both ends, so art beyond the first or last joint has a place."""
    tan = frames_of(curve)
    head = curve[0] - tan[0] * np.linspace(reach, 0, CURVE_STEPS, endpoint=False)[:, None]
    tail = curve[-1] + tan[-1] * np.linspace(0, reach, CURVE_STEPS + 1)[1:, None]
    return np.concatenate([head, curve, tail])


def blur(field, passes):
    f = field.copy()
    for _ in range(passes):
        f[1:-1, 1:-1] = (f[1:-1, 1:-1] * 2 + f[:-2, 1:-1] + f[2:, 1:-1] + f[1:-1, :-2] + f[1:-1, 2:]) / 6
    return f


class Layer:
    """One picture layer: image (premultiplied), its mesh, and each vertex's place on its curve."""

    def __init__(self, name, data, base):
        self.name = name
        self.root_lock = bool(data.get("root_lock", False))
        self.tip_lock = bool(data.get("tip_lock", False))
        self.source_frame = bool(data.get("source_frame", False))
        self.draw_owner = data.get('draw_owner')
        self.source_upper_carry = data.get('source_upper_carry')
        self.kind = data["kind"]        # tube | rigid | cloth
        self.bones = data.get("bones", [])
        self.rest = [np.array(p, dtype=np.float64) for p in data.get("rest", [])]
        self.radius = float(data.get("radius", 20.0))
        self.chain = data.get("chain")
        self.foot = data.get("foot")
        self.anchor, self.follow = data.get("anchor"), data.get("follow")
        self.neck_skin = data.get('neck_skin')
        self.pelvis_skin = data.get('pelvis_skin')
        self.pelvis_joint = data.get('pelvis_joint')
        self.pelvis_garment = data.get('pelvis_garment')
        im = Image.open(os.path.join(base, data["image"])).convert("RGBA")
        self.offset = np.array(data.get("offset", (0, 0)), dtype=np.float64)
        self.image = im
        self.front_mask = None
        if data.get('front_mask'):
            self.front_mask=Image.open(os.path.join(base,data['front_mask'])).convert('L')
            if self.front_mask.size!=im.size:
                raise ValueError('neck front material mask must match the parent image')
        a = np.asarray(im, dtype=np.float32) / 255
        ys, xs = np.nonzero(a[..., 3] > 0.02)
        self.box = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        w, h = im.size
        gx = np.arange(0, w + GRID, GRID, dtype=np.float64)
        gy = np.arange(0, h + GRID, GRID, dtype=np.float64)
        self.gx, self.gy = gx, gy
        vx, vy = np.meshgrid(gx, gy)
        self.vx, self.vy = vx, vy
        keep = np.zeros((len(gy) - 1, len(gx) - 1), bool)
        solid = a[..., 3] > 0.02
        for j in range(len(gy) - 1):
            y0, y1 = int(gy[j]), min(int(gy[j + 1]) + 1, h)
            for i in range(len(gx) - 1):
                x0, x1 = int(gx[i]), min(int(gx[i + 1]) + 1, w)
                if y0 < h and x0 < w and solid[y0:y1, x0:x1].any():
                    keep[j, i] = True
        self.cells = np.argwhere(keep)
        self.used = np.zeros(vx.shape, bool)
        for dj, di in ((0, 0), (0, 1), (1, 0), (1, 1)):
            self.used[self.cells[:, 0] + dj, self.cells[:, 1] + di] = True
        self.bind_curve()

    def bind_curve(self):
        if self.kind == "rigid":
            return
        if self.source_frame:
            rest_points = np.asarray(self.rest)
            if (rest_points.ndim != 2 or rest_points.shape[1] != 2 or len(rest_points) < 2
                    or not np.isfinite(rest_points).all()
                    or np.any(np.linalg.norm(np.diff(rest_points, axis=0), axis=1) < 1e-8)):
                raise ValueError(f'{self.name}: source-frame joints must be finite and consecutive joints distinct')
        rest = rounded(self.rest, self.radius)
        reach = float(max(self.image.size)) * 1.5
        self.rest_curve = extended(rest, reach)
        self.reach = reach
        cur = self.rest_curve
        px = self.vx.ravel() + self.offset[0]
        py = self.vy.ravel() + self.offset[1]
        idx = np.zeros(px.size, dtype=np.float64)
        for start in range(0, px.size, 4000):
            stop = start + 4000
            d = (px[start:stop, None] - cur[:, 0][None]) ** 2 + (py[start:stop, None] - cur[:, 1][None]) ** 2
            idx[start:stop] = d.argmin(1)
        self.place = blur(idx.reshape(self.vx.shape), BLUR_PASSES)
        tan = frames_of(cur)
        at = self.place.round().astype(int).clip(0, len(cur) - 1)
        dx = self.vx + self.offset[0] - cur[at, 0]
        dy = self.vy + self.offset[1] - cur[at, 1]
        self.along = dx * tan[at, 0] + dy * tan[at, 1]
        self.across = -dx * tan[at, 1] + dy * tan[at, 0]
        if self.source_frame:
            # Bind and animate with the SAME fractional curve frames. Rounding
            # only during binding shifts even an unchanged source pose. Nor
            # should an elbow already painted bent be compressed a second time.
            c, t, self.source_curvature = self.curve_frames(cur, self.place)
            dx = self.vx + self.offset[0] - c[..., 0]
            dy = self.vy + self.offset[1] - c[..., 1]
            self.along = dx * t[..., 0] + dy * t[..., 1]
            self.across = -dx * t[..., 1] + dy * t[..., 0]
        if self.foot:
            ankle, along = np.array(self.foot["ankle"]), np.array(self.foot["shin_dir"])
            rx, ry = self.vx + self.offset[0] - ankle[0], self.vy + self.offset[1] - ankle[1]
            # The boot's upper reaches above the ankle ahead of the shin: all of it turns with the foot.
            ahead = rx * along[1] - ry * along[0]
            depth = rx * along[0] + ry * along[1] + 0.9 * np.maximum(ahead - self.foot["width"], 0)
            s = np.clip((depth + self.foot["blend"]) / (2 * self.foot["blend"]), 0, 1)
            self.foot_w = s * s * (3 - 2 * s)

    @staticmethod
    def curve_frames(cur, place):
        """Fractional positions, unit tangents and curvature for source-preserving rigs."""
        tan = frames_of(cur)
        i0 = np.floor(place).astype(int).clip(0, len(cur) - 2)
        f = place - i0
        c = cur[i0] * (1 - f[..., None]) + cur[i0 + 1] * f[..., None]
        t = tan[i0] * (1 - f[..., None]) + tan[i0 + 1] * f[..., None]
        length = np.linalg.norm(t, axis=-1)[..., None]
        if np.any(length <= 1e-12):
            raise ValueError('source-frame curve has an undefined tangent; inspect folded or coincident joints')
        t = np.divide(t, length, out=np.zeros_like(t), where=length > 1e-12)
        angle = np.unwrap(np.arctan2(tan[:, 1], tan[:, 0]))
        step = np.hypot(*np.gradient(cur, axis=0).T) + 1e-9
        bend = np.gradient(angle) / step
        return c, t, bend[i0] * (1 - f) + bend[i0 + 1] * f

    def mapped(self, points, scale, sel=None):
        """Mesh vertices for a curve through this frame's joints, in output pixels.

        sel (a mask over the vertex grid) maps only those vertices; each vertex is independent
        until relaxation, so the selected values equal the same entries of the full grid."""
        cur = extended(rounded(points, self.radius * scale), self.reach * scale)
        place = self.place if sel is None else self.place[sel]
        along = self.along if sel is None else self.along[sel]
        across = self.across if sel is None else self.across[sel]
        if self.source_frame:
            c, t, k = self.curve_frames(cur, place)
            rest_k = self.source_curvature if sel is None else self.source_curvature[sel]
            # Only newly added inward bending compresses the artwork. Existing
            # source curvature and a rigid rotation/scale preserve its shape.
            added = np.maximum(np.abs(k) - np.maximum(np.sign(k) * rest_k / scale, 0), 0)
            k = np.sign(k) * added
        else:
            # Preserve the original arithmetic for already-exported bindings.
            tan = frames_of(cur)
            i0 = np.floor(place).astype(int).clip(0, len(cur) - 2)
            f = (place - i0)[..., None]
            c = cur[i0] * (1 - f) + cur[i0 + 1] * f
            t = tan[i0] * (1 - f) + tan[i0 + 1] * f
            t /= np.hypot(t[..., 0], t[..., 1])[..., None] + 1e-9
            ang = np.unwrap(np.arctan2(tan[:, 1], tan[:, 0]))
            step = np.hypot(*np.gradient(cur, axis=0).T) + 1e-9
            bend = np.gradient(ang) / step
            k = bend[i0] * (1 - f[..., 0]) + bend[i0 + 1] * f[..., 0]
        n = np.stack([-t[..., 1], t[..., 0]], -1)
        # Art wider than a tight bend compresses rather than crossing itself.
        across = across * scale
        inner = across * k > 0
        limit = INNER_LIMIT / (np.abs(k) + 1e-6)
        x = np.abs(across) / limit
        eased = np.where(inner, np.sign(across) * limit * x / (1 + x ** 4) ** 0.25, across)
        return c + t * along[..., None] * scale + n * eased[..., None]


def lock_tip(layer, verts, points, scale, root=False, sel=None, turn=0.0):
    """Keep distal hand art rigid; blend only on the proximal side of the wrist.

    Source joints and pixels remain unchanged. Existing rigs opt out by default.
    This runs after mesh relaxation so the hand is not smoothed out of its seat.
    """
    end, adjacent = (0, 1) if root else (-1, -2)
    source = layer.rest[end] - layer.rest[adjacent]
    target = points[end] - points[adjacent]
    source_angle = math.atan2(source[1], source[0])
    target_angle = math.atan2(target[1], target[0])
    vx, vy = (layer.vx, layer.vy) if sel is None else (layer.vx[sel], layer.vy[sel])
    held = rigid(vx + layer.offset[0], vy + layer.offset[1],
                 layer.rest[end], points[end], target_angle - source_angle + turn, scale)
    axis = source / max(float(np.linalg.norm(source)), 1e-9)
    depth = ((vx + layer.offset[0] - layer.rest[end][0]) * axis[0]
             + (vy + layer.offset[1] - layer.rest[end][1]) * axis[1])
    blend = min(max(layer.radius * 1.5, GRID * 2), float(np.linalg.norm(source)) * .4)
    weight = np.clip(1 + depth / blend, 0, 1)
    weight = weight * weight * (3 - 2 * weight)
    return verts * (1 - weight[..., None]) + held * weight[..., None]


def winding(verts, cells):
    """Doubled signed area of each cell's two triangles: negative is wound the other way from the
    picture, i.e. drawn mirrored."""
    j, i = cells[:, 0], cells[:, 1]
    a, b, c, d = verts[j, i], verts[j, i + 1], verts[j + 1, i], verts[j + 1, i + 1]
    cross = lambda o, u, v: (u[:, 0] - o[:, 0]) * (v[:, 1] - o[:, 1]) - (u[:, 1] - o[:, 1]) * (v[:, 0] - o[:, 0])
    return cross(a, b, c), cross(d, c, b)


def flipped(verts, cells):
    one, two = winding(verts, cells)
    return (one < 0) | (two < 0)


def untangle(verts, cells, pinned=None):
    """Relax only the mesh around cells that crossed themselves on the tight side of a sharp bend,
    until none do. Everywhere else the mesh stays exactly where the bend put it."""
    if not len(cells):
        return verts
    if pinned is not None:
        # Project signed triangle areas directly. Averaging neighbours cannot
        # reliably untangle a boundary constrained to another body surface.
        # Fixed source correspondences remain exact throughout the solve.
        h, w = verts.shape[:2]
        j, i = cells.T
        a, b, c, d = j*w+i, j*w+i+1, (j+1)*w+i, (j+1)*w+i+1
        triangles = np.concatenate((np.stack((a,b,c),1),np.stack((d,c,b),1)))
        flat = verts.reshape(-1,2).copy()
        free = (~pinned.reshape(-1)).astype(float)
        for _ in range(UNTANGLE_PASSES):
            points = flat[triangles]
            x, y, z = points[:,0], points[:,1], points[:,2]
            area = (y[:,0]-x[:,0])*(z[:,1]-x[:,1])-(y[:,1]-x[:,1])*(z[:,0]-x[:,0])
            bad = area <= 1e-6
            if not bad.any():
                break
            tri = triangles[bad];x,y,z = x[bad],y[bad],z[bad]
            gradient = np.stack((np.stack((y[:,1]-z[:,1],z[:,0]-y[:,0]),1),
                                 np.stack((z[:,1]-x[:,1],x[:,0]-z[:,0]),1),
                                 np.stack((x[:,1]-y[:,1],y[:,0]-x[:,0]),1)),1)
            movable = free[tri]
            denom = (np.sum(gradient*gradient,2)*movable).sum(1)
            amount = np.divide(1e-5-area[bad],denom,out=np.zeros_like(denom),where=denom>1e-12)
            delta = gradient*(amount[:,None]*movable)[...,None]
            correction = np.zeros_like(flat);count = np.zeros(len(flat))
            np.add.at(correction,tri.reshape(-1),delta.reshape(-1,2))
            np.add.at(count,tri.reshape(-1),movable.reshape(-1))
            flat += correction/np.maximum(count[:,None],1)
        return flat.reshape(verts.shape)
    v = verts.copy()
    h, w = v.shape[:2]
    for _ in range(UNTANGLE_PASSES):
        bad = cells[flipped(v, cells)]
        if not len(bad):
            break
        near = np.zeros((h, w), bool)
        for dj in range(-1, 3):
            for di in range(-1, 3):
                near[np.clip(bad[:, 0] + dj, 1, h - 2), np.clip(bad[:, 1] + di, 1, w - 2)] = True
        mean = (v[:-2, 1:-1] + v[2:, 1:-1] + v[1:-1, :-2] + v[1:-1, 2:]) / 4
        v[1:-1, 1:-1][near[1:-1, 1:-1]] = mean[near[1:-1, 1:-1]]
    return v


def floor_contact(verts, floor, band):
    """A monotone soft floor for loose fabric, in screen coordinates.

    Away from contact this is the identity. Below-floor material gathers into
    a thin layer above the floor; x positions and the body's joints stay put.
    """
    result = verts.copy()
    result[..., 1] = floor - band * np.logaddexp(0, (floor - result[..., 1]) / band)
    return result


def rigid(vx, vy, pivot_src, pivot_out, angle, scale):
    """Vertices turned clockwise on screen by angle about the pivot and carried to pivot_out."""
    c, s = math.cos(angle), math.sin(angle)
    x, y = (vx - pivot_src[0]) * scale, (vy - pivot_src[1]) * scale
    return np.stack([pivot_out[0] + x * c - y * s, pivot_out[1] + x * s + y * c], -1)


RASTER_BUDGET = 1 << 21   # bounding-box pixels evaluated at once while rasterising triangles


def measured_surface(puppet, indexed, name, scale):
    """Actual draw geometry with a registered part's analysis-only alpha mask.

    Source-owned arms are landmarks, not independent painted draws. Their
    measurements must follow their real drawing owner, including a missing
    owner's pixels. This temporary mask never enters the exported artwork.
    """
    layer, vertices = indexed[name]
    if not getattr(layer, 'draw_owner', None):
        return layer, vertices, puppet.mip(layer, scale)
    owner, vertices = indexed[layer.draw_owner]
    if (layer.name not in ('arm_near','arm_far') or owner.name != 'torso'
            or not getattr(owner,'source_upper_carry',None)):
        raise ValueError('unsupported source drawing owner')
    import copy
    key = (layer.name, owner.name)
    cache = getattr(puppet, 'measured_owner_layers', {})
    if key not in cache:
        alpha = Image.new('L',owner.image.size)
        alpha.paste(layer.image.getchannel('A'),tuple(np.rint(layer.offset-owner.offset).astype(int)))
        image = np.asarray(owner.image).copy()
        image[...,3] = np.minimum(image[...,3],np.asarray(alpha))
        proxy = copy.copy(owner)
        proxy.name = owner.name+':measured:'+layer.name
        proxy.image = Image.fromarray(image,'RGBA')
        cache[key] = proxy
        puppet.measured_owner_layers = cache
    return owner, vertices, puppet.mip(cache[key],scale)


def raster(layer, verts, mip, w, h):
    """Draw the layer's mesh into a premultiplied RGBA float image of (h, w).

    Each cell is two triangles, (p00, p10, p01) then (p11, p01, p10). All are tested at once
    in batches; pixels keep the same per-triangle, row-major order, so a later triangle still
    overwrites an earlier one where they share an edge, exactly as drawing them one by one.
    """
    img, k = mip
    out = np.zeros((h, w, 4), np.float32)
    ih, iw = img.shape[:2]
    cells = layer.cells
    if not len(cells):
        return out
    j, i = cells[:, 0], cells[:, 1]
    # Rounded mip dimensions can have different x/y scale factors. A single
    # factor compresses tall tight crops or stretches wide ones. Scalar mips
    # remain supported for callers that supply an unresized source image.
    kx, ky = (k, k) if np.isscalar(k) else k
    u_grid, v_grid = layer.gx * kx, layer.gy * ky
    p00, p10, p01, p11 = verts[j, i], verts[j, i + 1], verts[j + 1, i], verts[j + 1, i + 1]
    t00 = np.stack([u_grid[i], v_grid[j]], -1)
    t10 = np.stack([u_grid[i + 1], v_grid[j]], -1)
    t01 = np.stack([u_grid[i], v_grid[j + 1]], -1)
    t11 = np.stack([u_grid[i + 1], v_grid[j + 1]], -1)
    # Interleave the two triangles of each cell: (tri, corner, xy).
    pos = np.stack([np.stack([p00, p10, p01], 1), np.stack([p11, p01, p10], 1)], 1).reshape(-1, 3, 2)
    tex = np.stack([np.stack([t00, t10, t01], 1), np.stack([t11, t01, t10], 1)], 1).reshape(-1, 3, 2)
    lo, hi = pos.min(1), pos.max(1)
    if not np.isfinite(lo).all() or not np.isfinite(hi).all():
        raise ValueError("puppet mesh has non-finite vertices in layer " + layer.name)
    x0 = np.maximum(np.floor(lo[:, 0]).astype(np.int64), 0)
    x1 = np.minimum(np.ceil(hi[:, 0]).astype(np.int64) + 1, w)
    y0 = np.maximum(np.floor(lo[:, 1]).astype(np.int64), 0)
    y1 = np.minimum(np.ceil(hi[:, 1]).astype(np.int64) + 1, h)
    q0, q1, q2 = pos[:, 0], pos[:, 1], pos[:, 2]
    det = (q1[:, 0] - q0[:, 0]) * (q2[:, 1] - q0[:, 1]) - (q2[:, 0] - q0[:, 0]) * (q1[:, 1] - q0[:, 1])
    keep = np.flatnonzero((x1 > x0) & (y1 > y0) & (np.abs(det) >= 1e-9))
    if not len(keep):
        return out
    dst_y, dst_x, src_u, src_v = [], [], [], []

    def batch(sel):
        bw, bh = int((x1[sel] - x0[sel]).max()), int((y1[sel] - y0[sel]).max())
        if len(sel) > 1 and len(sel) * bw * bh > RASTER_BUDGET:
            half = len(sel) // 2
            batch(sel[:half])
            batch(sel[half:])
            return
        xx = (x0[sel, None, None] + np.arange(bw)[None, None, :]).astype(np.float64)
        yy = (y0[sel, None, None] + np.arange(bh)[None, :, None]).astype(np.float64)
        a0, b0, c0 = q0[sel], q1[sel], q2[sel]
        px, py = a0[:, 0, None, None], a0[:, 1, None, None]
        e1x, e1y = (b0[:, 0] - a0[:, 0])[:, None, None], (b0[:, 1] - a0[:, 1])[:, None, None]
        e2x, e2y = (c0[:, 0] - a0[:, 0])[:, None, None], (c0[:, 1] - a0[:, 1])[:, None, None]
        d = det[sel][:, None, None]
        a = ((xx - px) * e2y - e2x * (yy - py)) / d
        b = (e1x * (yy - py) - (xx - px) * e1y) / d
        inside = ((a >= -1e-3) & (b >= -1e-3) & (a + b <= 1.001)
                  & (xx < x1[sel, None, None]) & (yy < y1[sel, None, None]))
        n, r, c = np.nonzero(inside)
        if not len(n):
            return
        a, b = a[n, r, c], b[n, r, c]
        dst_y.append((y0[sel][n] + r).astype(np.int32))
        dst_x.append((x0[sel][n] + c).astype(np.int32))
        t = tex[sel][n]
        src_u.append(t[:, 0, 0] + a * (t[:, 1, 0] - t[:, 0, 0]) + b * (t[:, 2, 0] - t[:, 0, 0]))
        src_v.append(t[:, 0, 1] + a * (t[:, 1, 1] - t[:, 0, 1]) + b * (t[:, 2, 1] - t[:, 0, 1]))

    for start in range(0, len(keep), 4096):
        batch(keep[start:start + 4096])
    if not dst_y:
        return out
    yy, xx = np.concatenate(dst_y), np.concatenate(dst_x)
    u, v = np.concatenate(src_u), np.concatenate(src_v)
    # A mesh cell reaches past a layer cropped tight to its art. Past the picture there is nothing
    # to draw: clamping there would stretch the edge column into a band.
    inside = (u >= 0) & (u <= iw) & (v >= 0) & (v <= ih)
    yy, xx, u, v = yy[inside], xx[inside], u[inside].clip(0, iw - 1.001), v[inside].clip(0, ih - 1.001)
    u0, v0 = u.astype(np.int32), v.astype(np.int32)
    fu, fv = (u - u0)[:, None], (v - v0)[:, None]
    sample = (img[v0, u0] * (1 - fu) * (1 - fv) + img[v0, u0 + 1] * fu * (1 - fv)
              + img[v0 + 1, u0] * (1 - fu) * fv + img[v0 + 1, u0 + 1] * fu * fv)
    out[yy, xx] = sample
    return out


class Puppet:
    def __init__(self, spec):
        data = spec["puppet"]
        base = spec.get("_dir", ".")
        self.px_per_unit = float(data["px_per_unit"])
        self.joints = {k: np.array(v, dtype=np.float64) for k, v in data["joints"].items()}
        self.rest_angles = data["rest_angles"]
        self.skirt_len = float(data.get("skirt_len", 0.0))
        self.robe_len = float(data.get("robe_len", 0.0))
        self.core_radius = float(data.get("core_radius", 0.0))
        self.rest_arm = {k: tuple(tuple(p) for p in v) for k, v in data.get("rest_arm", {}).items()}
        self.layers = [Layer(n, d, base) for n, d in data["layers"].items()]
        self.mips = {}
        self.neck_bindings = {}
        self.pelvis_bindings = {}
        self.socket_bindings = {}
        self.garment_bindings = {}
        indexed = {layer.name: layer for layer in self.layers}
        for layer in self.layers:
            if layer.neck_skin:
                parent = indexed.get(layer.neck_skin)
                if layer.name != 'head' or layer.kind != 'rigid' or parent is None or parent.kind != 'tube':
                    raise ValueError('neck skin requires a rigid head and its tube torso')
                weights, report = neck_blend_weights(layer, parent, self.joints['head_base'], self.joints['waist'])
                self.neck_bindings[layer.name] = (parent, weights, report)
            if layer.pelvis_skin:
                parent = indexed.get(layer.pelvis_skin)
                if parent is None or parent.kind != 'rigid' or parent.name != 'hips' or layer.kind != 'tube':
                    raise ValueError('pelvis skin requires a tube child and registered rigid hips')
                seat, distal = (self.joints['hip'], self.joints['waist']) if layer.name == 'torso' else layer.rest[:2]
                weights, report = pelvis_blend_weights(layer, parent, seat, distal)
                self.pelvis_bindings[layer.name] = (parent, weights, report)
            if layer.pelvis_joint:
                parent = indexed.get(layer.pelvis_joint)
                if (layer.name not in ('leg_near','leg_far') or layer.kind != 'tube'
                        or parent is None or parent.name != 'hips' or parent.kind != 'rigid'
                        or not layer.root_lock or layer.pelvis_skin):
                    raise ValueError('articulated pelvis requires independent, root-locked thigh tubes')
                self.socket_bindings[layer.name] = (parent,None,joint_socket_binding(layer,parent))
        garment = [layer for layer in self.layers if layer.pelvis_garment]
        if garment:
            if {layer.name for layer in garment} != {'leg_near','leg_far'}:
                raise ValueError('garment rim requires both registered leg layers')
            parent = indexed.get('hips')
            if parent is None or parent.kind != 'rigid':
                raise ValueError('garment rim requires the registered rigid hips surface')
            up = self.joints['waist']-self.joints['hip']
            up /= np.linalg.norm(up)
            reports = {}
            for layer in garment:
                if (layer.kind != 'tube' or not layer.root_lock or layer.pelvis_skin
                        or layer.pelvis_joint or layer.pelvis_garment != 'hips'):
                    raise ValueError('garment rim requires independent thigh tubes and one waist owner')
                # Keep the complete physical hip registration preflight.
                joint_socket_binding(layer,parent)
                later = self.layers[self.layers.index(layer)+1:]
                occluders = [p for p in later if p.name in ('leg_near','hips','torso')]
                reports[layer.name] = hidden_garment_edges(layer,occluders,up)
            points = np.vstack([r['source_points'] for r in reports.values()])
            origin = self.joints['hip']
            attach = float(((points-origin)@(-up)).max()+GRID*np.abs(up).sum())
            # A narrow transition cannot turn material as wide as a trouser leg.
            fade = max(2*GRID,2*max(l.radius for l in garment),
                       .5*min(np.linalg.norm(l.rest[1]-l.rest[0]) for l in garment))
            for layer in garment:
                source = np.stack((layer.vx,layer.vy),-1)+layer.offset
                s = np.clip(((source-origin)@(-up)-attach)/fade,0.,1.)
                weights = 1-s*s*(3-2*s)
                report = dict(reports[layer.name],origin=origin.tolist(),up=up.tolist(),
                              attachment_depth=attach,fade=fade)
                self.garment_bindings[layer.name] = (parent,weights,report,GarmentBand(layer,weights))

    def palette(self):
        cols = set()
        for layer in self.layers:
            q = layer.image.convert("RGB").quantize(colors=24).convert("RGB")
            cols |= {c for _, c in q.getcolors(1 << 16)}
        return sorted(cols)

    def mip(self, layer, scale):
        """The layer shrunk once, ahead of warping. Shrinking far inside a bilinear warp would
        alias fine lines; this keeps them, and the warp then moves it by less than a pixel's worth."""
        key = (layer.name, round(scale, 3))
        if key not in self.mips:
            # A rigid fingertip's fine lines must survive the final SS downsample.
            # Avoid an extra early low-resolution filter for preserved hand art.
            preserve_hand = getattr(layer,'tip_lock',False) and getattr(layer,'source_frame',False)
            k = min(1.0, scale * (2.0 if preserve_hand else 1.15))
            a = np.asarray(layer.image, dtype=np.float32) / 255
            a[..., :3] *= a[..., 3:]
            size = max(2, round(a.shape[1] * k)), max(2, round(a.shape[0] * k))
            bands = [Image.fromarray(a[..., c]).resize(size, Image.LANCZOS) for c in range(4)]
            uv_scale = (size[0] / a.shape[1], size[1] / a.shape[0])
            self.mips[key] = (np.clip(np.stack([np.asarray(b) for b in bands], -1), 0, 1), uv_scale)
        return self.mips[key]

    def tube_points(self, layer, sk, cv):
        return [np.array(cv.T(self.joint_at(b, sk))) for b in layer.bones]

    def joint_at(self, name, sk):
        if name not in ("skirt", "robe_hem"):
            return sk[name]
        # Hanging panels sit between the two thighs, so they swing by half of what either leg does.
        hip = np.array(sk["hip"])
        mean = (np.array(sk["kn_n"]) + np.array(sk["kn_f"])) / 2 - hip
        line = hip - np.array(sk["waist"])
        off = math.atan2(line[0] * mean[1] - line[1] * mean[0], line @ mean)
        limit = math.radians(SKIRT_SWING)
        turn = max(-limit, min(limit, off)) + math.atan2(line[1], line[0])
        length = self.robe_len if name == "robe_hem" else self.skirt_len
        return tuple(hip + np.array((math.cos(turn), math.sin(turn))) * length)

    def meshes(self, cv, sk, cloth, ground_contact=False, relax=True, used_only=False):
        """Each layer, back to front, with its mesh for this frame in canvas pixels.

        used_only (requires relax=False) yields only the vertices of cells holding art, as an
        (n, 2) array equal to verts[layer.used] of the full mesh: bounds without the empty grid."""
        if used_only and relax:
            raise ValueError("used_only vertices cannot be relaxed: relaxation needs the full grid")
        scale = cv.s / self.px_per_unit
        neck_bindings=getattr(self,'neck_bindings',{})
        parents = {parent.name for parent, _, _ in neck_bindings.values()}
        cached = {}
        for layer in self.layers:
            sel = layer.used if used_only and layer.name not in parents else None
            if layer.kind == "rigid":
                verts = self.rigid_verts(layer, sk, cv, scale, sel)
            elif layer.kind == "cloth":
                verts = layer.mapped([np.array(cv.T(p)) for p in cloth[layer.chain]], scale, sel)
            else:
                verts = layer.mapped(self.tube_points(layer, sk, cv), scale, sel)
                if layer.foot:
                    side = layer.foot["side"]
                    angle = self.foot_turn(layer, sk, cv)
                    vx, vy = (layer.vx, layer.vy) if sel is None else (layer.vx[sel], layer.vy[sel])
                    held = rigid(vx + layer.offset[0], vy + layer.offset[1], layer.foot["ankle"],
                                 cv.T(sk["an_" + side]), angle, scale)
                    foot_w = layer.foot_w if sel is None else layer.foot_w[sel]
                    verts = verts * (1 - foot_w[..., None]) + held * foot_w[..., None]
            if layer.kind != "rigid" and relax:
                verts = untangle(blur(verts, EASE_PASSES), layer.cells)
            if getattr(layer, 'source_upper_carry', None) is not None:
                # A carried illustration contains the original connected hands
                # and rifle. A spine tube bends that rigid object, even when its
                # logical wrist landmarks are correct. Transport its real mesh
                # in chest space, then attach only the lower garment below it.
                vx, vy = (layer.vx, layer.vy) if sel is None else (layer.vx[sel], layer.vy[sel])
                verts = rigid(vx+layer.offset[0], vy+layer.offset[1], self.joints['waist'],
                              cv.T(sk['waist']),
                              math.radians(sk['chest_rot']-self.rest_angles['chest_rot']),scale)
            if getattr(layer, 'root_lock', False) and layer.kind == "tube":
                verts = lock_tip(layer, verts, self.tube_points(layer, sk, cv), scale, root=True, sel=sel)
            if getattr(layer, 'tip_lock', False) and layer.kind == "tube":
                verts = lock_tip(layer, verts, self.tube_points(layer, sk, cv), scale, sel=sel,
                                 turn=-math.radians(sk.get("hand_n_turn", 0.)) if layer.bones[-1] == "wr_n" else 0.)
            if ground_contact and (layer.kind == "cloth" or layer.name == "robe"):
                # The chain supports its centreline. The painted sheet has
                # width too: compress the contacting fabric continuously onto
                # the floor without lifting the body or cutting source pixels.
                verts = floor_contact(verts, cv.oy, max(cv.s * 0.5, 1e-6))
                if relax:
                    verts = untangle(verts, layer.cells)
            if layer.name in neck_bindings:
                parent, weights, _ = neck_bindings[layer.name]
                if parent.name not in cached:
                    raise ValueError('neck skin: torso must precede head in draw order')
                source = np.stack((layer.vx, layer.vy), -1) + layer.offset
                if sel is not None:
                    source, weights = source[sel], weights[sel]
                attached = mesh_points(parent, cached[parent.name], source)
                verts = verts*(1-weights[..., None]) + attached*weights[..., None]
            if layer.name in getattr(self, 'pelvis_bindings', {}):
                parent, weights, _ = self.pelvis_bindings[layer.name]
                source = np.stack((layer.vx, layer.vy), -1)+layer.offset
                if sel is not None:
                    source, weights = source[sel], weights[sel]
                angle = parent.follow[1]
                attached = rigid(source[..., 0], source[..., 1], parent.anchor,
                                 self.carried(parent, sk, cv, scale),
                                 math.radians(sk[angle]-self.rest_angles[angle]), scale)
                verts = verts*(1-weights[..., None])+attached*weights[..., None]
                if relax:
                    pinned = weights >= 1-1e-12
                    if getattr(layer, 'source_upper_carry', None) is not None:
                        pinned |= source[..., 1] <= layer.source_upper_carry['protected_y']
                    if layer.foot:
                        pinned = pinned | (layer.foot_w >= 1-1e-12)
                    verts = untangle(verts, layer.cells, pinned=pinned)
            if layer.name in getattr(self,'garment_bindings',{}):
                parent,weights,_,band = self.garment_bindings[layer.name]
                source = np.stack((layer.vx,layer.vy),-1)+layer.offset
                if sel is not None:
                    source,weights = source[sel],weights[sel]
                attached = rigid(source[...,0],source[...,1],parent.anchor,
                                 self.carried(parent,sk,cv,scale),
                                 math.radians(sk[parent.follow[1]]-self.rest_angles[parent.follow[1]]),scale)
                verts = verts*(1-weights[...,None])+attached*weights[...,None]
                if relax:
                    verts = band.solve(verts,scale)
            if layer.name in parents:
                cached[layer.name] = verts
            yield layer, verts[layer.used] if used_only and layer.name in parents else verts

    def foot_turn(self, layer, sk, cv):
        """Radians the boot turns from the picture, clockwise on screen, kept within the ankle's reach."""
        side, foot = layer.foot["side"], layer.foot
        knee, ankle = cv.T(sk["kn_" + side]), cv.T(sk["an_" + side])
        shin = math.atan2(ankle[1] - knee[1], ankle[0] - knee[0]) - math.atan2(foot["shin_dir"][1], foot["shin_dir"][0])
        rel = (math.radians(sk["fr_" + side] - foot["rest_angle"]) - shin + math.pi) % math.tau - math.pi
        return shin + max(-math.radians(ANKLE_TURN), min(math.radians(ANKLE_TURN), rel))

    def draw(self, cv, sk, cloth, ground_contact=False):
        scale = cv.s / self.px_per_unit
        meshes=list(self.meshes(cv, sk, cloth, ground_contact))
        # The existing collar material is a separate source-derived depth
        # surface; the torso's reconstructed bare neck stays behind the head.
        surfaces=[];indexed={layer.name:(layer,verts) for layer,verts in meshes}
        for layer,verts in meshes:
            if getattr(layer, 'draw_owner', None):
                if layer.draw_owner not in indexed:
                    raise ValueError('missing declared source carry drawing owner')
                continue
            surfaces.append((layer,verts,self.mip(layer,scale)))
            if layer.neck_skin:
                parent,parent_verts=indexed[layer.neck_skin]
                if parent.front_mask is not None:
                    key=(parent.name+':neck_front',round(scale,3))
                    if key not in self.mips:
                        image,factor=self.mip(parent,scale)
                        mask=np.asarray(parent.front_mask.resize((image.shape[1],image.shape[0]),Image.Resampling.LANCZOS),float)/255.
                        self.mips[key]=(image*mask[...,None],factor)
                    surfaces.append((parent,parent_verts,self.mips[key]))
        for layer, verts, mip in surfaces:
            drawn = raster(layer, verts, mip, cv.w, cv.h)
            ys, xs = np.nonzero(drawn[..., 3] > 1e-3)
            if not len(ys):
                continue
            box = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            over = drawn[box[0]:box[1], box[2]:box[3]]
            under = cv.buf[box[0]:box[1], box[2]:box[3]].astype(np.float32) / 255
            ua = under[..., 3:]
            a = over[..., 3:]
            out_a = a + ua * (1 - a)
            rgb = over[..., :3] + under[..., :3] * ua * (1 - a)
            rgb = np.where(out_a > 1e-4, rgb / np.maximum(out_a, 1e-4), 0)
            cv.buf[box[0]:box[1], box[2]:box[3]] = np.clip(np.concatenate([rgb, out_a], -1) * 255 + 0.5, 0, 255).astype(np.uint8)

    def rigid_verts(self, layer, sk, cv, scale, sel=None):
        vx, vy = (layer.vx, layer.vy) if sel is None else (layer.vx[sel], layer.vy[sel])
        vx, vy = vx + layer.offset[0], vy + layer.offset[1]
        joint, angle_key = layer.follow
        pivot_src = np.array(layer.anchor)
        if layer.name == "weapon":     # the fist closes on it just past the wrist, as drawn weapons
            wr, el = np.array(sk["wr_n"]), np.array(sk["el_n"])
            pivot_out = np.array(cv.T(sk.get('weapon_grip',tuple(wr + (wr - el) * 0.14))))
        else:
            pivot_out = self.carried(layer, sk, cv, scale)
        # Clockwise on screen, in the rig's convention, except a weapon angle, measured the other way.
        turn = sk[angle_key] - self.rest_angles[angle_key]
        if angle_key == "wep_a":
            turn = -turn
        return rigid(vx, vy, pivot_src, pivot_out, math.radians(turn), scale)

    def carried(self, layer, sk, cv, scale):
        """Where a rigid layer's anchor lands: on its joint, with the bind offset turned with it."""
        joint, angle_key = layer.follow
        rest = self.joints[joint]
        delta = (np.array(layer.anchor) - rest) * (1, -1) / self.px_per_unit
        now = rot(rot(tuple(delta), -self.rest_angles[angle_key]), sk[angle_key])
        return np.array(cv.T((sk[joint][0] + now[0], sk[joint][1] + now[1])))
