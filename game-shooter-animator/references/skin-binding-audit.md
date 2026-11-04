# Source landmarks and shared cloth boundaries

This audit is for source-preserving custom skinning. It does not generate missing fabric or
approve an illustration's anatomy. Keep the original source, the binding manifest, exact runtime
matrices/weights, isolated RGBA frames and the report together.

## The defect this catches

A flat painted pair of trousers is one connected garment. If it is cut into near/far halves and
each half uses only its own leg bones, the same source boundary can move to two different places.
Both hips can still hit their intended skeleton points; bone lengths and foot IK can all pass.
The original cloth nevertheless develops a vertical slit, horizontal shelf or open crotch.

Use a complete pelvis/garment owner with supported attachment coverage, or a mesh whose shared
source vertices have a consistent mapping. Independent limb tubes are insufficient proof of a
closed garment. Do not add a flat-colour patch, stretch a belt or switch to unrelated trousers
just to conceal the measurement. If hidden texture is missing, the art stage remains blocked.

Existing known-joint binding requires `hips` plus complete limb layers. Its parent-contact and
body-core checks do not establish all inter-leg cloth continuity. Full-size source/rest and
moving pelvis review remains required even when those measurements pass.

## Audit actual runtime data

```bash
python scripts/audit_skin_binding.py binding_manifest.json --out binding_audit.json
python scripts/audit_skin_binding.py --check binding_audit.json
```

Do not type in idealized output coordinates to replace the renderer's actual mapping. Export
the source samples and their real skin influences, per-frame matrices and driving skeleton.
The manifest uses schema version 1:

- `sources`: image ID to original/registered source PNG, relative to the manifest.
- `parts`: part ID to `{source: image_id}`. Every audited part needs registered landmarks.
- `landmarks`: entries with `id`, `part`, target skeleton `joint`, source `point: [x,y]`, and
  `influences: [[bone_index, weight], ...]`.
- `seams`: entries with `id`, two `parts`, and `samples`. Each sample has one original `point`
  and an `influences` map containing both parts' weights for that **same** source point. The
  source is opaque cloth there; do not declare an original transparent leg opening a seam.
- `clips`: clip name to `{frames: [...]}`. Each frame supplies `image`, actual `skeleton` joint
  coordinates and `matrices` for each part. A matrix is `[a,b,c,d,tx,ty]`, mapping source pixels
  to rendered image pixels as `(a*x+c*y+tx, b*x+d*y+ty)`.

Files must stay inside the manifest directory tree so the evidence can be archived. Frames
must be isolated RGBA characters with transparent background; a street-scene screenshot cannot
establish the character's alpha coverage. Preserve source pixels rather than repainting them.

The tool evaluates every declared clip/frame. Shared-source seam samples must map within
0.5 rendered pixels; mapped landmarks must match their registered driving joints within 1 pixel.
These are fixed registration constraints, not thresholds for judging garment style. Do not raise
them to rescue a failed rig. Weights must be finite, nonnegative and normalized; absent matrices,
source/pose data or required landmarks are invalid evidence.

These are the **declared samples' linear-blend mappings**, not a measurement of every final GPU
pixel. Most mesh renderers skin vertices, then interpolate positions across triangles; evaluating
the weight function directly at an interior source point can differ from that rasterized mapping.
Prefer actual shared mesh vertices. To audit an interior point exactly, export the true triangle
vertices/indices and its barycentric mapping in the producer's evidence rather than relabelling
an analytic sample as pixel ground truth. The retained game regression uses analytic LBS samples;
an independent mesh comparison confirms the same rejection, with the differences documented in
the fixture README. Image inspection remains required.

An external renderer's `rig_trace.json` must declare `binding_audit_required: true`. Include
`binding_audit.json` beside `animations.json`, covering the delivered full-body clips and frames.
The visual gate must reject a missing required report; deleting a failed report is not a repair.
Each audited frame must match the reviewed frame's decoded RGBA pixels and dimensions. A matching
clip name and frame count do not establish that the audit measured the same artwork.

The report separates numeric `status` from `visual_status: pending`. `fail` and `invalid` block
the visual delivery gate. `--check` recomputes the current evidence; editing a manifest, source,
rendered frame or report does not carry an earlier pass forward. Source-point/runtime review
images must be inspected along with the full-body and hip sheets. Marked points can themselves
be anatomically wrong, and unmarked seams remain outside this measurement.

## Record visual findings

```bash
python scripts/visual_review.py out/character
python scripts/visual_review.py out/character --record verdict.json
python scripts/visual_review.py out/character --check
```

For every required hip pose, record `rig_alignment` and `pelvis_continuity` observations with
the exact clip and frame. Compare source pixels, clean runtime art and actual bones; do not look
only at the skeleton overlay, which can hide a slit. Deep crouch, leg separation, landings and
source-pose switches must remain covered. `pelvis_gap` and `rig_misalignment` are structural
blockers. A numeric pass never clears them, and a changed image alone never proves a repair.

If a hand-written game renderer has no current manifest/trace/review, state that it has **not**
passed skill review. Keep its failed frames as regression evidence. Do not present a procedural
sample's results, game unit-test count or a partial pose gallery as that character's approval.
