"""What numbers can say about a layered puppet: the faults a person sees first on cut-up art.

    smear  a layer holds a blurred patch (a chest repainted as fog)
    hand   the hand lost its drawing on the way to the frame (a bun for a fist)
    fold   the mesh turned inside out somewhere (a limb creased at the joint)
    kink   a cloth chain breaks into straight pieces (a cape in segments)
    crouch the standing leg stays bent in the walk (a stroll on folded knees)
    hole   background shows through the body below the belt (no layer behind a split robe)
    shoulder  far arm drawn over the torso
    arm_chain  an arm layer follows the other arm's joints
    arm_spacing  separated reference arms collapsed together in idle

Thresholds and how each was set are in references/layered-art.md.
"""
import os
import math

import numpy as np
from PIL import Image

from .puppet import winding
from .rig import full_pose, solve

TILE = 24             # px of a layer's art
SMEAR_RANGE = 30      # 0-255: a tile must change this much to count as having content
SMEAR_STEEP = 0.16    # steepest step between neighbours, as a share of the tile's range. Drawn art has
                      # an inked edge or a shading boundary; a blur only ramps
SMEAR_SHARE = 0.03    # of a layer's filled tiles
HAND_DETAIL = 0.55    # of the reference's edge energy at the same size
HAND_FRAMES = 4       # frames sampled over the clip
NECK_DRIFT_PX = 1.0   # same rendered-pixel tolerance as registered seam landmarks
ARM_SPACING_SHARE = 0.5  # gross compression relative to readable reference arms, idle only
FOLD_SHARE = 0.002    # of a layer's drawn mesh area inverted in any frame
KINK_DEG = 42.0       # between neighbouring segments of a cloth chain
CORE_END = 0.85       # of the way from waist to hip
HOLE_SHARE = 0.01     # of the core's pixels that may be see-through
CROUCH_DEG = 30.0     # mean knee bend in the walk while the planted foot carries the body: ahead of or under
                      # the hip. Behind the hip the knee has to bend to push off, 40-50 degrees in any human walk


def smear_tile_report(rgba):
    """Locate the existing soft-gradient heuristic; this is not semantic blur detection.

    Coordinates are half-open source-layer pixel bounds, before any animation.
    Keep all thresholds and the opaque-tile denominator identical to smear_tiles.
    """
    a = np.asarray(rgba, dtype=np.float32)
    solid = a[..., 3] > 250
    h, w = solid.shape
    candidates = []
    filled = 0
    for y in range(0, h - TILE + 1, TILE):
        for x in range(0, w - TILE + 1, TILE):
            if not solid[y:y + TILE, x:x + TILE].all():
                continue
            filled += 1
            t = a[y:y + TILE, x:x + TILE, :3]     # by channel: red against gold is nearly one grey
            span = float((t.max((0, 1)) - t.min((0, 1))).max())
            if span < SMEAR_RANGE:
                continue
            step = max(float(np.abs(np.diff(t, axis=0)).max()), float(np.abs(np.diff(t, axis=1)).max()))
            if step < SMEAR_STEEP * span:
                candidates.append(dict(bounds=[x, y, x + TILE, y + TILE],
                                       span=span, max_step=step, step_share=step / span))
    return dict(bad=len(candidates), filled=filled, candidates=candidates)


def smear_tiles(rgba):
    """Legacy count interface; the evidence report must not change gate decisions."""
    report = smear_tile_report(rgba)
    return report["bad"], report["filled"]


def check_layers(puppet):
    out = []
    names = [layer.name for layer in puppet.layers]
    if "arm_far" in names and "torso" in names and names.index("arm_far") > names.index("torso"):
        out.append("shoulder: arm_far is in front of the torso; rebind with side-view depth order")
    for layer in puppet.layers:
        if layer.name in ("arm_near", "arm_far"):
            side = "n" if layer.name == "arm_near" else "f"
            if tuple(getattr(layer, "bones", ()) or ()) != ("sh_" + side, "el_" + side, "wr_" + side):
                out.append(f"arm_chain: {layer.name} does not follow its own shoulder, elbow and wrist")
        bad, filled = smear_tiles(layer.image)
        if filled and bad / filled > SMEAR_SHARE:
            out.append(f"smear: {layer.name}: {bad} of {filled} tiles are blurred with no drawn edge; make this layer again")
    return out


def edge_energy(rgb):
    """Mean size of the step between neighbouring pixels, on grey, where the art is."""
    g = np.asarray(rgb, dtype=np.float32)
    grey, on = g[..., :3].mean(2), g[..., 3] > 128
    dx, dy = np.abs(np.diff(grey, axis=1)), np.abs(np.diff(grey, axis=0))
    keep_x, keep_y = on[:, 1:] & on[:, :-1], on[1:, :] & on[:-1, :]
    n = int(keep_x.sum() + keep_y.sum())
    return float((dx[keep_x].sum() + dy[keep_y].sum()) / max(n, 1))


def disc_crop(a, x, y, r):
    h, w = a.shape[:2]
    return a[max(int(y - r), 0):min(int(y + r), h), max(int(x - r), 0):min(int(x + r), w)]


def check_hands(renderer, spec, clip, frames, fps):
    """The hand in the frames against the hand in the reference, shrunk to the same size."""
    from .art import Canvas
    from .render import GROUND_FRAC, frame_time
    puppet = renderer.art.puppet
    source = spec["puppet"].get("source")
    if not source:
        return []
    path = os.path.join(spec.get("_dir", "."), source)
    if not os.path.isfile(path):
        return [f"hand: reference {source} not found next to the character"]
    size = renderer.size
    scale = renderer.unit / puppet.px_per_unit
    ref = Image.open(path).convert("RGBA")
    source_size = ref.size
    ref = np.asarray(ref.resize((max(1, round(ref.width * scale)), max(1, round(ref.height * scale))), Image.LANCZOS))
    layers = {layer.name:layer for layer in puppet.layers}
    masks = {}
    def arm_mask(index, side, pose, sk):
        """Only the same arm's support; neighbouring opaque clothes are context."""
        if index not in masks:
            from .puppet import raster
            native = Canvas(size,renderer.ss,renderer.unit,GROUND_FRAC,1,False,(0,0,0))
            native.set_squash(pose['squash'],0.)
            masks[index] = {}
            for layer,verts in puppet.meshes(native,sk,renderer.cloth_at(clip,frame_time(clip,index,len(frames),fps)),
                                              'ground' in clip.tags):
                if layer.name not in ('arm_near','arm_far'):
                    continue
                alpha = raster(layer,verts,puppet.mip(layer,native.s/puppet.px_per_unit),native.w,native.h)[...,3]
                masks[index][layer.name] = np.asarray(Image.fromarray(np.uint8(np.clip(alpha,0,1)*255+.5)).resize(
                    (size,size),Image.Resampling.LANCZOS))
        return masks[index]['arm_near' if side=='n' else 'arm_far']
    out = []
    measurements = {}
    cv = Canvas(size, 1, renderer.unit, GROUND_FRAC, 1, False, (0, 0, 0))
    for side in "nf":
        wrist, elbow = puppet.rest_arm[side]
        radius = 0.5 * float(np.hypot(*np.subtract(wrist, elbow))) * scale
        rx, ry = (wrist[0] + (wrist[0] - elbow[0]) * 0.28) * scale, (wrist[1] + (wrist[1] - elbow[1]) * 0.28) * scale
        layer = layers['arm_near' if side=='n' else 'arm_far']
        same_arm = layer.source_frame and layer.tip_lock
        reference = ref
        if same_arm:
            alpha = Image.new('L',source_size)
            alpha.paste(layer.image.getchannel('A'),tuple(int(round(v)) for v in layer.offset))
            alpha = np.asarray(alpha.resize((ref.shape[1],ref.shape[0]),Image.Resampling.LANCZOS))
            reference = ref.copy();reference[...,3] = np.minimum(reference[...,3],alpha)
        want = edge_energy(disc_crop(reference, rx, ry, radius))
        got = []
        for i in np.linspace(0, len(frames) - 1, HAND_FRAMES).astype(int):
            pose = full_pose(clip.sample(frame_time(clip, int(i), len(frames), fps)))
            sk = solve(pose, renderer.art.body)
            wr, el = np.array(sk["wr_" + side]), np.array(sk["el_" + side])
            x, y = cv.T(tuple(wr + (wr - el) * 0.28))
            actual = frames[int(i)]
            if same_arm:
                actual = actual.copy()
                actual[...,3] = np.minimum(actual[...,3],arm_mask(int(i),side,pose,sk))
            got.append(edge_energy(disc_crop(actual, x, y, radius)))
        measurements[side] = dict(method='same_arm_alpha_context_v1' if same_arm else 'legacy_composite_crop',
                                  reference_energy=want,frame_energies=got,
                                  detail_ratio=float(np.mean(got))/want if want else None,limit=HAND_DETAIL)
        if want > 0 and float(np.mean(got)) < HAND_DETAIL * want:
            out.append(f"hand: {side}: {clip.name}: {np.mean(got) / want:.0%} of the reference's detail; the hand lost its drawing")
    if not hasattr(renderer,'hand_detail_checks'):
        renderer.hand_detail_checks = {}
    renderer.hand_detail_checks[clip.name] = measurements
    return out


def core_mask(size, waist, hip, radius):
    """A square-ended strip from the waist toward the hip, in a frame of (w, h). It stops short of the
    hip joint: below that the legs part, and the gap between them is meant to be open."""
    yy, xx = np.mgrid[0:size[1], 0:size[0]].astype(np.float32)
    a, b = np.array(waist, np.float32), np.array(hip, np.float32)
    u = b - a
    s = ((xx - a[0]) * u[0] + (yy - a[1]) * u[1]) / (u @ u + 1e-6)
    return (s >= 0) & (s <= CORE_END) & ((xx - a[0] - u[0] * s) ** 2 + (yy - a[1] - u[1] * s) ** 2 <= radius * radius)


def check_core(renderer, clip, frames, fps):
    """The body between belt and hips is solid in every frame. The silhouette can't show a hole here,
    because what hangs around it stays in place: the background shows through the middle of the figure."""
    from .art import Canvas
    from .render import GROUND_FRAC, frame_time
    radius = renderer.art.puppet.core_radius * renderer.unit
    if not radius:
        return []
    cv = Canvas(renderer.size, 1, renderer.unit, GROUND_FRAC, 1, False, (0, 0, 0))
    worst, at = 0.0, 0
    for i, frame in enumerate(frames):
        pose = full_pose(clip.sample(frame_time(clip, i, len(frames), fps)))
        sk = solve(pose, renderer.art.body)
        cv.set_squash(pose["squash"], 0.0)
        core = core_mask((frame.shape[1], frame.shape[0]), cv.T(sk["waist"]), cv.T(sk["hip"]), radius)
        share = float((frame[core][:, 3] < 128).mean()) if core.any() else 0.0
        if share > worst:
            worst, at = share, i
    if worst > HOLE_SHARE:
        return [f"hole: {clip.name} frame {at}: {worst:.0%} of the body below the belt is see-through; make the hips layer again"]
    return []


def neck_surface_errors(puppet, meshes):
    """Actual final triangle maps of shared opaque source neck points, in canvas pixels."""
    from .puppet import mesh_points
    layers = {layer.name: (layer, verts) for layer, verts in meshes}
    out = {}
    for name, (parent, _, report) in puppet.neck_bindings.items():
        source = np.asarray(report['source_points'], float)
        head, verts = layers[name]
        _, body_verts = layers[parent.name]
        errors = np.linalg.norm(mesh_points(head, verts, source)-mesh_points(parent, body_verts, source), axis=-1)
        out[name] = float(errors.max())
    return out


def check_neck(renderer, clip, n, fps):
    """Check moving neck roots independently of optional limb-attachment checks.

    This measures skin correspondence, not the appearance of a painted cut edge.
    Missing legacy neck skinning remains outside this numerical scope and still
    requires the mandatory semantic head/neck review.
    """
    from .art import Canvas
    from .render import GROUND_FRAC, frame_time
    puppet = renderer.art.puppet
    if not puppet.neck_bindings:
        return []
    cv = Canvas(renderer.size, renderer.ss, renderer.unit, GROUND_FRAC, 1, False, (0, 0, 0))
    worst, at = 0., 0
    for i in range(n):
        t = frame_time(clip, i, n, fps)
        pose = full_pose(clip.sample(t)); sk = solve(pose, renderer.art.body)
        cv.set_squash(pose['squash'], 0.)
        meshes = list(puppet.meshes(cv, sk, renderer.cloth_at(clip, t), 'ground' in clip.tags))
        error = max(neck_surface_errors(puppet, meshes).values())/renderer.ss
        if error > worst:
            worst, at = error, i
    if not hasattr(renderer, 'neck_checks'):
        renderer.neck_checks = {}
    renderer.neck_checks[clip.name] = dict(frames=n, max_drift_px=round(worst, 4),
                                          worst_frame=at, limit_px=NECK_DRIFT_PX,
                                          method='native_final_triangle_correspondence')
    if worst > NECK_DRIFT_PX:
        return [f'neck: {clip.name} frame {at}: shared head/torso neck root differs by {worst:.2f}px; repair the skin correspondence']
    return []


def material_triangles(layer, vertices):
    """Actual source/final triangles and opaque material sample locations."""
    j,i = layer.cells.T;w = vertices.shape[1]
    triangles = np.concatenate((np.stack((j*w+i,j*w+i+1,(j+1)*w+i),-1),
        np.stack(((j+1)*w+i+1,(j+1)*w+i,j*w+i+1),-1)))
    source = (np.stack((layer.vx,layer.vy),-1)+layer.offset).reshape(-1,2)[triangles]
    dest = vertices.reshape(-1,2)[triangles]
    centers = source.mean(1)
    local = np.rint(centers-layer.offset).astype(int);alpha = np.asarray(layer.image)[...,3]
    inside = ((local[:,0]>=0)&(local[:,1]>=0)&(local[:,0]<alpha.shape[1])&(local[:,1]<alpha.shape[0]))
    solid = np.zeros(len(local),bool);solid[inside] = alpha[local[inside,1],local[inside,0]]>200
    return source,dest,centers,solid


def material_strain(source, dest, chosen, scale):
    """Orientation-independent strain; positive winding alone is insufficient."""
    from .integrity import THIGH_DEFORMATION_LIMITS as limits
    if not chosen.any():
        return dict(samples=0,bad_share=1.,min_scale=0.,max_scale=0.,min_area=0.,max_area=0.)
    se = np.stack((source[:,1]-source[:,0],source[:,2]-source[:,0]),-1)
    de = np.stack((dest[:,1]-dest[:,0],dest[:,2]-dest[:,0]),-1)
    jac = de[chosen]@np.linalg.inv(se[chosen])/scale
    singular = np.linalg.svd(jac,compute_uv=False);area = np.linalg.det(jac)
    bad = ((singular[:,1]<limits['min_scale'])|(singular[:,0]>limits['max_scale'])
           |(area<limits['min_area'])|(area>limits['max_area']))
    return dict(samples=int(chosen.sum()),bad_share=round(float(bad.mean()),6),
                min_scale=round(float(singular[:,1].min()),6),max_scale=round(float(singular[:,0].max()),6),
                min_area=round(float(area.min()),6),max_area=round(float(area.max()),6))


def thigh_strain(layer, vertices, scale):
    """Opaque thigh shaft, excluding its existing two-radius knee envelope."""
    from .integrity import THIGH_DEFORMATION_LIMITS as limits
    source,dest,centers,solid = material_triangles(layer,vertices)
    axis = layer.rest[1]-layer.rest[0]
    length = float(np.linalg.norm(axis));axis = axis/length
    along = (centers-layer.rest[0])@axis/length
    across = (centers-layer.rest[0])@np.array([-axis[1],axis[0]])
    end = min(.75,1-limits['knee_exclusion_radii']*layer.radius/length)
    chosen = solid&(along>=limits['root_start'])&(along<=end)&(np.abs(across)<=layer.radius*.75)
    return material_strain(source,dest,chosen,scale)


def garment_strain(layer, vertices, scale, report):
    """Also inspect the waist transition that the thigh-only ROI excluded."""
    from .puppet import GRID
    source,dest,centers,solid = material_triangles(layer,vertices)
    depth = (centers-np.asarray(report['origin']))@(-np.asarray(report['up']))
    start = report['attachment_depth']
    chosen = solid&(depth>=start-GRID)&(depth<=start+report['fade']+GRID)
    return material_strain(source,dest,chosen,scale)


def garment_visibility(puppet, meshes, cv):
    """Native final alpha coverage of originally hidden proximal cut edges.

    Check actual rendered occluders within one output pixel of each mapped
    edge point. This does not dilate the composite body or infer shirt colours.
    """
    from .puppet import mesh_points,raster
    from .integrity import GARMENT_EDGE_LIMITS as limits
    bindings = puppet.garment_bindings
    mapped = {name:mesh_points(meshes[name][0],meshes[name][1],report['source_points'])
              for name,(_,_,report,_) in bindings.items()}
    points = np.vstack(list(mapped.values()))
    margin = math.ceil(cv.ss*limits['contact_radius_px'])+2
    lo = np.maximum(0,np.floor(points.min(0)).astype(int)-margin)
    hi = np.minimum((cv.w,cv.h),np.ceil(points.max(0)).astype(int)+margin+1)
    if np.any(hi<=lo):
        return {name:dict(samples=len(p),exposed=len(p),exposed_indices=list(range(len(p))))
                for name,p in mapped.items()}
    masks = {}
    parents = {p for _,_,report,_ in bindings.values() for p in report['occluders']}
    for name in parents:
        layer,verts = meshes[name]
        masks[name] = raster(layer,verts-lo,puppet.mip(layer,cv.s/puppet.px_per_unit),
                             int(hi[0]-lo[0]),int(hi[1]-lo[1]))[...,3]
    radius = cv.ss*limits['contact_radius_px']
    offsets = np.arange(-margin,margin+1)
    dx,dy = np.meshgrid(offsets,offsets)
    offsets = np.column_stack((dx.ravel(),dy.ravel()))
    result = {}
    for name,(_,_,report,_) in bindings.items():
        p = mapped[name]-lo
        near = np.rint(p).astype(int)[:,None,:]+offsets
        alpha = np.maximum.reduce([masks[n] for n in report['occluders']])
        valid = ((near[...,0]>=0)&(near[...,1]>=0)
                 &(near[...,0]<alpha.shape[1])&(near[...,1]<alpha.shape[0]))
        covered = np.zeros(valid.shape,bool)
        y,x = near[...,1],near[...,0]
        covered[valid] = alpha[y[valid],x[valid]]>=limits['occluder_alpha']
        covered &= np.sum((near-p[:,None,:])**2,axis=-1)<=radius*radius+1e-9
        bad = np.flatnonzero(~covered.any(1)).tolist()
        result[name] = dict(samples=len(p),exposed=len(bad),exposed_indices=bad)
    return result


def ordinary_run_report(clip, body, n, fps):
    """Measure the requested ordinary-run style against this body's leg length."""
    from .render import frame_time
    legs = min(sum(body.leg_bones(side)) for side in 'nf')
    samples = []
    for i in range(n):
        pose = full_pose(clip.sample(frame_time(clip,i,n,fps)))
        sk = solve(pose,body)
        angles = [abs(math.degrees(math.atan2(sk['kn_'+s][0]-sk['hip_'+s][0],
                    sk['hip_'+s][1]-sk['kn_'+s][1]))) for s in 'nf']
        samples.append(dict(foot_span_ratio=abs(sk['an_n'][0]-sk['an_f'][0])/legs,
                            lift_ratio=max(pose['foot_n_y'],pose['foot_f_y'])/legs,
                            thigh_deg=max(angles),lean_deg=abs(sk['chest_rot']),
                            pelvis_y_ratio=sk['hip'][1]/legs,
                            head_y_ratio=sk['head_base'][1]/legs,
                            near_contact=clip.contacts(frame_time(clip,i,n,fps))['n'],
                            far_contact=clip.contacts(frame_time(clip,i,n,fps))['f']))
    phase_samples = []
    for i in range(240):
        t = clip.duration*i/240
        sk = solve(full_pose(clip.sample(t)),body)
        contacts = clip.contacts(t)
        phase_samples.append(dict(phase=i/240,pelvis_y_ratio=sk['hip'][1]/legs,
                                  head_y_ratio=sk['head_base'][1]/legs,
                                  near_contact=contacts['n'],far_contact=contacts['f']))
    return dict(profile=getattr(clip,'profile','legacy_run'),frames=n,leg_length=legs,
                stride_ratio=clip.L/legs,lift_ratio=clip.lift/legs,bob_ratio=clip.bob/legs,
                samples=samples,rhythm=dict(method='phase_sampled_run_support_v1',
                                           phase_samples=phase_samples))


def check_connections(renderer, clip, n, fps, bindings=None):
    """Check the torso seam, rotating thigh caps and thigh material every frame.

    The torso shares its pelvis surface. Each thigh cap follows its own bone,
    while its joint stays in its registered pelvis socket. Both cap edges and
    material strain are checked on the final mesh, without alpha dilation.
    Bindings may be supplied by a read-only audit of an older export.
    """
    from .art import Canvas
    from .puppet import mesh_points,rigid
    from .mathx import rot
    from .integrity import THIGH_DEFORMATION_LIMITS
    from .render import GROUND_FRAC, frame_time
    puppet = renderer.art.puppet
    garment = getattr(puppet,'garment_bindings',{})
    if bindings is None:
        bindings = dict(puppet.pelvis_bindings,**getattr(puppet,'socket_bindings',{}),
                        **{name:(parent,weights,report) for name,(parent,weights,report,_) in garment.items()})
    required = {'torso', 'leg_near', 'leg_far'}
    if set(bindings) != required:
        return [f'connection: {clip.name} frame 0: missing full pelvis attachment evidence']
    cv = Canvas(renderer.size, renderer.ss, renderer.unit, GROUND_FRAC, 1, False, (0, 0, 0))
    values = {part: [] for part in required}
    shapes = {part: [] for part in set(getattr(puppet,'socket_bindings',{}))|set(garment)}
    garment_shapes = {part:[] for part in garment}
    edges = {part:[] for part in garment}
    for i in range(n):
        t = frame_time(clip, i, n, fps)
        pose = full_pose(clip.sample(t)); sk = solve(pose, renderer.art.body)
        cv.set_squash(pose['squash'], 0.)
        meshes = {layer.name: (layer, vertices) for layer, vertices in
                  puppet.meshes(cv, sk, renderer.cloth_at(clip, t), 'ground' in clip.tags)}
        for name, (parent, _, report) in bindings.items():
            source = np.asarray(report['source_points'], float)
            child, verts = meshes[name]
            if report.get('method') == 'registered_articulated_socket_v2':
                side = child.bones[0][-1];root,knee = child.rest[:2]
                target,next_joint = np.array(cv.T(sk['hip_'+side])),np.array(cv.T(sk['kn_'+side]))
                axis = knee-root;direction = next_joint-target
                angle = np.arctan2(direction[1],direction[0])-np.arctan2(axis[1],axis[0])
                expected = rigid(source[:,0],source[:,1],root,target,float(angle),cv.s/puppet.px_per_unit)
                error = np.linalg.norm(mesh_points(child,verts,source)-expected,axis=-1)
                # The virtual socket follows measured pelvis coordinates plus
                # the authored hip twist. Its cap rotates with its own bone.
                shift = np.array(rot((pose['hp']*(1 if side=='n' else -1),0),sk['body_rot']))
                shift = np.array(cv.T(shift))-np.array(cv.T((0.,0.)))
                parent_joint = mesh_points(parent,meshes[parent.name][1],np.asarray([root]))[0]+shift
                child_joint = mesh_points(child,verts,np.asarray([root]))[0]
                worst = max(float(error.max()),float(np.linalg.norm(child_joint-parent_joint)))
                shapes[name].append(thigh_strain(child,verts,cv.s/puppet.px_per_unit))
            else:
                error = np.linalg.norm(mesh_points(child, verts, source)-
                                       mesh_points(parent, meshes[parent.name][1], source), axis=-1)
                worst = float(error.max())
                if name in garment:
                    joint = np.asarray([report['source_joint']],float)
                    side = 'n' if name == 'leg_near' else 'f'
                    at = mesh_points(child,verts,joint)[0]
                    worst = max(worst,float(np.linalg.norm(at-np.asarray(cv.T(sk['hip_'+side])))))
                    shapes[name].append(thigh_strain(child,verts,cv.s/puppet.px_per_unit))
                    garment_shapes[name].append(garment_strain(child,verts,cv.s/puppet.px_per_unit,report))
            values[name].append(round(worst/renderer.ss, 5))
        if garment:
            for name,row in garment_visibility(puppet,meshes,cv).items():
                edges[name].append(row)
    if not hasattr(renderer, 'connection_checks'):
        renderer.connection_checks = {}
    renderer.connection_checks[clip.name] = dict(frames=n,parts=values,shape_parts=shapes,
                                                garment_shapes=garment_shapes,edge_visibility=edges)
    faults = [f'connection: {name}: {clip.name} frame {i}: registered attachment separates by {error:.3f}px'
              for name, errors in values.items() for i, error in enumerate(errors) if error > 1.0]
    faults += [f'shape: {name}: {clip.name} frame {i}: {row["bad_share"]:.1%} of opaque thigh shaft collapses or stretches'
               for name, rows in shapes.items() for i,row in enumerate(rows)
               if not row['samples'] or row['bad_share']>THIGH_DEFORMATION_LIMITS['max_bad_share']]
    faults += [f'garment shape: {name}: {clip.name} frame {i}: {row["bad_share"]:.1%} of waist material collapses or stretches'
               for name,rows in garment_shapes.items() for i,row in enumerate(rows)
               if not row['samples'] or row['bad_share']>THIGH_DEFORMATION_LIMITS['max_bad_share']]
    faults += [f'garment edge: {name}: {clip.name} frame {i}: {row["exposed"]} originally hidden cut-edge samples exposed'
               for name,rows in edges.items() for i,row in enumerate(rows) if row['exposed']]
    if garment and clip.name == 'run':
        from .integrity import ordinary_run_faults
        renderer.ordinary_run_checks = ordinary_run_report(clip,renderer.art.body,n,fps)
        faults += [f'ordinary run: run frame {row["frame"]}: {row["what"]}'
                   for row in ordinary_run_faults(renderer.ordinary_run_checks,n)]
    return faults


def attachment_faults(alpha, parent_alpha, root, next_joint, radius):
    """Isolated layer continuity and local parent contact, never composite coverage.

    Both alpha arrays are normalized 0..1 raster outputs. A partial curved root
    cap is sufficient; no filled disc or coincident near/far seats is assumed.
    Antialiasing permits one pixel of contact adjacency, not a geometric gap.
    """
    from .integrity import components
    root, end = np.asarray(root, float), np.asarray(next_joint, float)
    length = float(np.linalg.norm(end - root))
    if length <= 1e-6:
        return ['degenerate proximal bone']
    yy, xx = np.indices(alpha.shape)
    reach = max(1.5, min(float(radius), length * .15))

    def disc(point, r):
        return (xx - point[0]) ** 2 + (yy - point[1]) ** 2 <= r * r

    labels = components(alpha > .5)
    seats = set(np.unique(labels[disc(root, reach)])) - {0}
    if not seats:
        return ['no limb pixels at root seat']
    connected = seats.copy()
    for fraction in (.25, .45, .65):
        at = root + (end - root) * fraction
        connected &= set(np.unique(labels[disc(at, reach)])) - {0}
    if not connected:
        return ['limb root and proximal bone lack connected same-layer pixels']
    parent = parent_alpha > .5
    padded = np.pad(parent, 1)
    touch = np.zeros_like(parent)
    for dy in range(3):
        for dx in range(3):
            touch |= padded[dy:dy + parent.shape[0], dx:dx + parent.shape[1]]
    near_root = disc(root, max(reach, float(radius) * 1.5))
    supported = np.isin(labels, list(connected))
    if not np.any(supported & near_root & touch):
        return ['connected limb root has no local parent contact']
    return []


def check_attachments(renderer, clip, n, fps):
    """Check every requested frame in isolated alpha buffers, locating first faults.

    Kept separate from composite QA so an opaque torso cannot hide missing arm
    pixels. Callers opt into this additional measured scope explicitly.
    """
    from .art import Canvas
    from .puppet import raster
    from .render import GROUND_FRAC, frame_time
    puppet = renderer.art.puppet
    definitions = {
        'arm_near': ('sh_n', 'el_n', ('torso',)),
        'arm_far': ('sh_f', 'el_f', ('torso',)),
        'leg_near': ('hip_n', 'kn_n', ('hips', 'torso')),
        'leg_far': ('hip_f', 'kn_f', ('hips', 'torso')),
    }
    layers = {layer.name: layer for layer in puppet.layers}
    active = {name: data for name, data in definitions.items() if name in layers}
    cv = Canvas(renderer.size, renderer.ss, renderer.unit, GROUND_FRAC, 1, False, (0, 0, 0))
    scale = cv.s / puppet.px_per_unit
    found = {}
    for i in range(n):
        t = frame_time(clip, i, n, fps)
        pose = full_pose(clip.sample(t))
        sk = solve(pose, renderer.art.body)
        cv.set_squash(pose['squash'], 0.)
        needed = set(active) | {p for _, _, parents in active.values() for p in parents}
        meshes = {layer.name: (layer, verts) for layer, verts in
                  puppet.meshes(cv, sk, renderer.cloth_at(clip, t), 'ground' in clip.tags)
                  if layer.name in needed}
        full_masks = {}

        def inspect(name, parents, root, end, radius, box):
            x0, y0, x1, y1 = box
            offset = np.array([x0, y0])
            w, h = x1 - x0, y1 - y0
            masks = {}
            for part in (name, *parents):
                if part not in meshes:
                    continue
                layer, verts = meshes[part]
                if box == (0, 0, cv.w, cv.h) and part in full_masks:
                    masks[part] = full_masks[part]
                    continue
                # Integer translation keeps the original supersampling and
                # subpixel grid. Only the output allocation/triangle ROI shrinks.
                masks[part] = raster(layer, verts - offset, puppet.mip(layer, scale), w, h)[..., 3]
                if box == (0, 0, cv.w, cv.h):
                    full_masks[part] = masks[part]
            parent = np.zeros((h, w), dtype=float)
            for part in parents:
                if part in masks:
                    parent = np.maximum(parent, masks[part])
            return attachment_faults(masks[name], parent, root - offset, end - offset, radius)

        for name, (root, end, parents) in active.items():
            if name in found:
                continue
            start, finish = np.array(cv.T(sk[root])), np.array(cv.T(sk[end]))
            radius = layers[name].radius * scale
            reach = max(1.5, min(radius, float(np.linalg.norm(finish - start)) * .15))
            contact = max(reach, radius * 1.5)
            distal = start + (finish - start) * .65
            lo = np.floor(np.minimum(start - contact, distal - reach)).astype(int) - 2
            hi = np.ceil(np.maximum(start + contact, distal + reach)).astype(int) + 3
            x0, y0 = max(0, int(lo[0])), max(0, int(lo[1]))
            x1, y1 = min(cv.w, int(hi[0])), min(cv.h, int(hi[1]))
            box = (x0, y0, x1, y1)
            problems = (inspect(name, parents, start, finish, radius, box)
                        if x1 > x0 and y1 > y0 else ['outside local ROI'])
            if problems:
                # A valid connected sleeve can leave this ROI and return. Local
                # success proves global success, but local failure does not prove
                # global failure. Consult the full-canvas oracle before reporting.
                problems = inspect(name, parents, start, finish, radius, (0, 0, cv.w, cv.h))
            if problems:
                found[name] = f"attachment: {name}: {clip.name} frame {i}: root {root}: {'; '.join(problems)}"
    return list(found.values())


def inverted(verts, cells):
    """Share of the mesh's drawn area wound the other way from the picture, i.e. turned inside out.
    By area, not by cell: a cell crushed to nothing at the centre of a sharp bend shows no art."""
    if not len(cells):
        return 0.0
    areas = np.concatenate(winding(verts, cells))
    return float(-areas[areas < 0].sum() / (np.abs(areas).sum() + 1e-9))


def arm_spacing(near, far):
    """Distal upper-arm centres and wrists: two independent visibility cues."""
    near, far = np.asarray(near), np.asarray(far)
    return np.array([np.linalg.norm((near[0] * 0.25 + near[1] * 0.75)
                                    - (far[0] * 0.25 + far[1] * 0.75)),
                     np.linalg.norm(near[2] - far[2])])


def spacing_fault(ratios, fps):
    """Catch at least two samples spanning 100ms, preserving intentional moving-clip crossings."""
    run = 0
    required = max(2, int(np.ceil(0.1 * fps)) + 1)
    for i, ratio in enumerate(ratios):
        run = run + 1 if np.min(ratio) < ARM_SPACING_SHARE else 0
        if run >= required:
            return i - run + 1
    return None


def check_motion(renderer, clip, n, fps):
    """Mesh folds, cloth kinks and the planted knee across one clip."""
    from .art import Canvas
    from .render import GROUND_FRAC, frame_time
    puppet = renderer.art.puppet
    body = renderer.art.body
    cv = Canvas(renderer.size, renderer.ss, renderer.unit, GROUND_FRAC, 1, False, (0, 0, 0))
    out, worst_fold, worst_kink, planted = [], {}, {}, []
    worst_ground = {}
    arms = {layer.name: layer for layer in getattr(puppet, "layers", [])
            if layer.name in ("arm_near", "arm_far")}
    reference_spacing = None
    if clip.name == "idle" and len(arms) == 2:
        reference_spacing = arm_spacing(arms["arm_near"].rest, arms["arm_far"].rest) / puppet.px_per_unit
        width = (arms["arm_near"].radius + arms["arm_far"].radius) / puppet.px_per_unit
        # Judge only spacing that the source actually makes readable. Coincident
        # joints and intentional source overlaps are not inherently invalid.
        reference_spacing = np.where(reference_spacing > width, reference_spacing, 0.0)
    spacing_ratios = []
    for i in range(n):
        t = frame_time(clip, i, n, fps)
        pose = full_pose(clip.sample(t))
        sk = solve(pose, body)
        if reference_spacing is not None:
            actual = arm_spacing([sk[k] for k in ("sh_n", "el_n", "wr_n")],
                                 [sk[k] for k in ("sh_f", "el_f", "wr_f")])
            spacing_ratios.append(np.divide(actual, reference_spacing,
                                           out=np.ones(2), where=reference_spacing > 0))
        cloth = renderer.cloth_at(clip, t)
        cv.set_squash(pose["squash"], 0.0)
        for layer, verts in puppet.meshes(cv, sk, cloth, 'ground' in clip.tags):
            share = inverted(verts, layer.cells)
            if share > worst_fold.get(layer.name, (0,))[0]:
                worst_fold[layer.name] = (share, i)
            if 'ground' in clip.tags and (getattr(layer, 'kind', None) == 'cloth' or layer.name == 'robe'):
                below = max(0.0, float(verts[layer.used, 1].max()) - cv.oy)
                if below > worst_ground.get(layer.name, (0,))[0]:
                    worst_ground[layer.name] = (below, i)
        for name, pts in cloth.items():
            d = np.diff(np.asarray(pts), axis=0)
            turn = np.degrees(np.abs(np.arctan2(d[:-1, 0] * d[1:, 1] - d[:-1, 1] * d[1:, 0], (d[:-1] * d[1:]).sum(1))))
            if len(turn) and turn.max() > worst_kink.get(name, (0,))[0]:
                worst_kink[name] = (float(turn.max()), i)
        for side, down in clip.contacts(t).items():
            if down and sk["an_" + side][0] >= sk["hip_" + side][0]:
                a = np.subtract(sk["kn_" + side], sk["hip_" + side])
                b = np.subtract(sk["an_" + side], sk["kn_" + side])
                planted.append(np.degrees(np.arccos(np.clip(a @ b / (np.hypot(*a) * np.hypot(*b) + 1e-9), -1, 1))))
    if spacing_ratios:
        ratios = np.median(spacing_ratios, axis=0)
        short_fault = spacing_fault(spacing_ratios, fps)
        if float(ratios.min()) < ARM_SPACING_SHARE or short_fault is not None:
            detail = f"; first sustained fault frame {short_fault}" if short_fault is not None else ""
            out.append(f"arm_spacing: {clip.name}: separated reference arms collapse together "
                       f"(upper arms {ratios[0]:.0%}, wrists {ratios[1]:.0%} of reference"
                       f"{detail}); review both carried arms")
    for name, (share, i) in worst_fold.items():
        if share > FOLD_SHARE:
            out.append(f"fold: {name}: {clip.name} frame {i}: {share:.1%} of the mesh turned inside out; the bend is too sharp for this art")
    for name, (below, i) in worst_ground.items():
        if below > 0.5:
            out.append(f"garment_ground: {name}: {clip.name} frame {i}: {below:.1f} px below the floor")
    for name, (deg, i) in worst_kink.items():
        if deg > KINK_DEG:
            out.append(f"kink: {name}: {clip.name} frame {i}: bends {deg:.0f} degrees between segments; the cloth reads as pieces")
    if clip.name == "walk" and planted and float(np.mean(planted)) > CROUCH_DEG:
        out.append(f"crouch: {clip.name}: the knee carrying the body stays bent {np.mean(planted):.0f} degrees, over {CROUCH_DEG:.0f}: a walk on folded legs")
    return out
