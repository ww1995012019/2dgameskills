# Experimental reference head registration

`dev/head_registration.py` is an opt-in development adapter for already reviewed
rigs. It does not replace the packaged binder or infer anatomical/material ownership.
The cap-coverage assumption is unsuitable when the torso's upper pixels are an
intact standing garment collar. Do not remove brown/gold garment as presumed skin.

## Inputs and rule

Supply at least three noncollinear corresponding landmarks on each original head
and torso, and the matching points in one identity reference. Use distributed
anatomical/garment features, not just a pair of neck seam endpoints. Record the
coordinates and image hashes as fixture evidence. Coordinates are annotations,
not per-character output transforms or magic offsets in the implementation.

Both parts fit the common reference with orientation-preserving similarities.
The existing torso transform remains fixed. Inverting its reference fit gives
the reference-to-assembly transform; compose that with the head's source-to-reference
fit to obtain uniform whole-head scale, rotation and translation. This preserves
reference head/body proportions rather than enlarging a head merely to cover a cap.
No anisotropic scaling, neck-only deformation, paint, garment masking or cutout
reconstruction is performed.

Each fit rejects maximum landmark residual above 5% of the reference landmark
span, degenerate/near-collinear inputs, nonfinite data and reflected fits. The
fixed 5% geometric tolerance is a coarse annotation-consistency screen, not an
identity or visual pass. Concentrated or misidentified landmarks may still pass;
review source/reference overlays and actual rendered poses independently.

`create_reference_candidate` requires a new output directory and a rigid head.
It preserves the source rig, body, joints, motions and other layer definitions and
pixels. It rasterizes the original head once, checks canvas containment, rebuilds
the rest composite from active layer images/offsets, archives stale binding
artifacts and prior source, refreshes provenance hashes and invalidates approvals.
Rerun generation/QA and inspect actual head/neck poses after this change. Existing
head bone/anchor data remain fixed; the reference-derived art is positioned around
that anchor rather than silently rebinding or modifying animation.

## Evidence and limits

External male-adventurer and female-warrior fixtures have `collar-registration/`
versioned candidates, landmark reports and nine-pose idle/walk/cast contacts.
Male maximum residual: head 1.22%, torso 4.63%; female: head 1.49%, torso 3.25%.
These annotations were visually inspected. Two-proportion synthetic tests cover
resolution scaling, residual fault injection, reflection/degeneracy rejection,
rotation, source preservation, clipping, malformed transforms and candidate isolation.
The male correction enlarges the whole head about 40% relative to the prior generic
adult-profile head, restoring the reference ratio. This is not silent seam fitting.
A visual review is distinct from numerical tests, full-motion QA and user approval.

## Canvas padding and visible-proportion limits (recovered fixture pass)

`create_reference_candidate(..., pad_canvas=True)` may grow the source canvas
rather than clip registered art. It computes integer padding from occupied head
pixels and the existing interpolation guard, retains complete old layer rectangles,
and translates the whole supported source frame. Joints, rest-arm positions,
layer offsets/anchors/rest points and foot ankles move together. Body dimensions,
local vectors, angles, motion and original layer files are unchanged. Provenance
records `unpadded_offset` and `canvas_padding` (before, after, translation, trailing).
Default behavior still rejects clipping. This adapter deliberately rejects nonempty
chains, unsupported layer kinds/fields and fractional layer offsets rather than
guess their coordinate semantics. Synthetic tests cover both resolutions, inverse
translation, composite pixels and fractional-transform raster invariance.

A recovered male trial exposed an important limitation of the earlier fit rule.
Six distributed head and five torso landmarks passed the unchanged 5% geometric
screen (3.49% and 4.72% maximum residual), yet the candidate failed independent
full-body visual review. The larger head improved the chin/collar join but made
whole-body proportions visibly wrong. The current pelvis garment hides much of
the torso's lower artwork; fitting that full source torso does not establish the
proportions visible in the final composite. This candidate was rejected, not
promoted as an identity correction. Its canvas needed seven pixels of top padding;
whole-frame translation preserved motion and all non-head artwork.

Before applying head registration, review the visible assembled collar, actual
belt/waist, pelvis, knees and soles against the identity. Source landmarks hidden
by other garment layers cannot stand in for visible anatomy or garment anchors.
If the body layout is inconsistent, correct the general assembly/reference contract
first or reject the candidate. Never compensate with an arbitrary head multiplier,
collar deletion, or garment translation. A low registration residual remains only
an annotation-consistency check, not a full-body fidelity gate.
