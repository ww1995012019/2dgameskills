# Release gates for bound artwork

Read this before binding existing or AI-generated art, and again before delivering any clip of a
bound character. Each rule here came from a defect that passed the numbers and was caught by eye.
None of them may be skipped, relaxed or carried forward from an earlier build.

## Head, neck and hands

Head/neck continuity and natural hands are mandatory from reference generation through delivery.
Use the fixed species-aware neck/hand constraints in `sprite_anim/layer_slots.py`; inspect the
source, isolated head/torso and both arm layers at full size. A triangular neck flap over a collar,
an exposed internal cut, rigid pasted-on head motion, exaggerated empty-hand clawing or a broken
wrist is a blocker. Read [visual-review.md](visual-review.md): every applicable clip
requires the new head/neck and near/far hand close-ups plus full motion playback and explicit
observations. Do not equate alpha contact, preserved finger detail or a small head oscillation
with natural motion. Fail the art/motion stage, preserve the issue and repair the general cause
within the existing attempt budget; do not tune one character or add a collar/patch to hide it.

Frames are computed from a skeleton. Continuous joint curves, fixed bone lengths and a passing
numeric report do not establish that the painted body follows those joints or that clothing stays
closed. Review both the rendered pixels and the actual driving skeleton before delivery.

## Binding and garment continuity

Read [skin-binding-audit.md](skin-binding-audit.md) when binding existing artwork or
integrating a custom mesh renderer. Preserve a complete pelvis/garment bridge. Cutting one painted
pair of trousers down the middle and letting each half follow only its own leg is not a valid
layered rig: two copies of the same source boundary can separate even while every bone length and
hip landmark is correct. Do not hide that defect with a belt, flat colour, torso overlap or an
unreviewed patch. If the source lacks the needed hidden fabric, stop that binding at a failed
art/resource stage rather than claiming a continuous animation.

For every delivered full-body humanoid clip, inspect `review/hips_*.png` at full size, alongside
the original source and the driving bones: waist, near/far hip, crotch, thigh roots and both knees.
Inspect rest, deepest crouch, maximum leg separation, landings and source-pose switches. A straight
cut edge, background slit, doubled trouser panel or bone emerging from the wrong painted joint is
a blocker. Mandatory `rig_alignment` and `pelvis_continuity` observations must name the actual
clip/frame. Missing trace or missing close-up evidence cannot become a pass.
The numeric report marks unavailable rig/part/binding checks `n/a` and emits an evidence warning
when the trace or part/binding results are missing. Existing faults still fail even if other
evidence is incomplete. Source-carry garment checks are required by the rifle profile OR actual
source drawing owner; deleting the presentation flag cannot skip that gate. These are evidence
and dispatch protections, not an automatic recognition of every visible waist defect. An export-only
archive without its trace, source and visual report cannot establish full artwork acceptance.

## Waist band and hidden garment edges

Basic jobs require `registered_garment_v3`. The lower torso and originally hidden waistband
cuts share their registered garment owner; a free cloth band connects that rim to each rotating
thigh. Rotating a whole leg cap can expose its original cut, pocket top or duplicate waistband
even when its hip registration is exact. Do not freeze an entire thigh overlap to hide it.
The source rest joints and actual hip seats must agree; knee radii use local opaque knee width.
Every exported frame needs final seam/hip, thigh AND waist-band strain measurements, plus native
alpha evidence that each originally hidden proximal edge stays under its recorded source depth
owners. One output pixel is the fixed contact tolerance. Missing source edges, frame/part coverage,
changed RGBA pixels or exposed internal edges block acceptance. Rebind earlier basic rigs.
Zero drift and positive triangle winding do not establish preserved anatomy: a solver can make
all triangles positive by flattening them. Mandatory opaque thigh-shaft strain checks measure
thickness, stretch and area, independently of the joint rotation. Missing shape evidence also
blocks acceptance. Inspect complete thighs AND knees at native size and during playback; a
pinched root, flattened leg, C-shaped thigh or displaced shorts hem is a blocker, even if a
numeric connection check passes. Compare the same clip/frame with the pre-change rendering.
Material checks include triangles touched by opaque pixel footprints, even when their centres
are transparent. An opaque waist-boundary triangle outside the existing strain limits is a
blocker on its own; the 1% interior allowance cannot hide a small curled corner. Cloth rotations
are constrained by the pelvis and thigh owners. Final-mesh polar rotations are checked independently:
turning outside that interval by more than one native output pixel over a source mesh edge blocks
acceptance. Missing boundary or turn measurements, including older reports, require regeneration.
These checks cannot recognize a bad fold already painted into the source or certify natural cloth.
Do not treat a dilated connected component, a covered centre strip, or a single joint contact as
proof that a whole waist is closed. Inspect ALL generated waist frames on the new hips sheets,
including both outer edges, on the checkerboard and a light background. Compare the waistband,
jacket hem and crotch with `binding_reference.png`; connected pixels can still be the wrong
garment height. Fill both `source_garment_registration` and `limb_shape_preservation` with actual
per-frame observations. Do not batch-fill passing anatomy claims from a template or carry an
earlier visual conclusion forward without looking at the current pixels. The hidden core must not
be lifted or enlarged to fill pixels outside the registered source silhouette. Numeric geometry
still does not identify a wrong opaque material, painted cut line, hand anatomy or naturalness.

Also complete `hidden_garment_edges` and `motion_style_match`. Inspect the mandatory blue-background
`garment_edges_*.png` waist macros as well as the whole thighs and knees. A black folded rim or
loose trouser corner is a blocker even if no transparent hole appears. Compare clean art on a
light/blue background and watch every delivered loop; bone overlays alone can hide these edges.

## Ordinary run

Basic `run` uses the explicit `ordinary_run_v2` profile: stride/lift follow leg length, with a
short airborne phase and restrained hip motion. The legacy fixed 48-unit stride/19-unit lift
is an action-game sprint and is not the default ordinary run for measured artwork. Required
ordinary-run evidence bounds stride, lift, foot separation, thigh angle and torso lean against
the measured body. Those limits enforce this requested style, not all possible sprinting.
Do not claim natural motion merely because the envelope passes; inspect the actual cadence,
waist, leg recovery and foot support in the browser.

The previous support-height fit followed the recovering foot and overrode the declared bob.
Measure the actual pelvis/head trajectories, half-step equality, vertical speed/acceleration and
native rendered head-height changes. The configured bob is not evidence of the rendered motion.
Both steps share one smooth height curve, with its apex in flight; one constant support envelope
is fitted over the complete cycle. Export an even frame count and quantize both GIF half-cycles
identically. Inspect `run_support_00.png` and its complete fixed-canvas playback against a fixed
head/ground reference; fill every `support_rhythm` observation. Abrupt drops, unequal support or
limping rhythm are blockers even when every foot touches the ground and the loop closes.

## Grounded source rolls

`ordinary_roll_v1` fits the complete source silhouette to the floor as one body. Its generic
head/foot proxies are retained as diagnostic measurements; the authoritative body-ground metric
uses actual opaque source boundaries through the rendered mesh. Source rolls disable the competing
individual-foot floor correction only while this whole-body source constraint is active.
Independent QA also inspects each native RGBA frame of a grounded layered tumble, so a producer
claim that bones clear the floor cannot hide painted hair or boots penetrating it. This uses
the existing one-rig-unit ground limit, with a one-output-pixel minimum for raster quantization;
the check reports exact failing frame indices. Other clips keep their existing contact checks.
Inspect actual ground contact during the entire turn and recovery. The check does not certify
a natural roll, hand support or the absence of hovering; those still need native-frame and playback
review. Do not move a final PNG, crop it or add a cover to conceal a failed contact.

## External or custom skins

For an external/custom atlas skin, export its **actual** source points, skin weights, per-frame
matrices and isolated RGBA frames to a binding manifest, then run
`python scripts/audit_skin_binding.py binding_manifest.json --out out/c/binding_audit.json`.
This checks registered landmarks and declared shared seams; a numeric pass still requires visual
review. Preserve the manifest and its assets with the report. A hand-written game renderer, its
unit tests, or unrelated synthetic output is not evidence that this skill reviewed the character.
If the runtime cannot export those data, state that the custom binding is unverified.

## Re-review after any change

Rebuild and record the current review after any change to art, trace, atlas, sprite sheets or
runtime preview. Old/unversioned passes do not carry forward. Never claim the complete set is
approved when only a few sampled poses or the skeleton math have been checked.
