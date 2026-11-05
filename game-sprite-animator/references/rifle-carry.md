# Source-preserved rifle carry (guarded trial)

Use only for fitted clothing, short hair, secured equipment, opaque crisp art, and the requested
idle/run loops. Start with `character_workflow.py prepare --image SOURCE --out NEW_JOB
--profile side-rifle-carry-v1 --weapon rifle`. The existing per-stage three-attempt budgets and
reference/layer acceptance gates apply. Do not reopen or rename a rejected job to reset them.

The accepted full registration image supplies the visible upper body, rifle and gripping hands.
Seven separated body layers and both hand hints remain required. Their common canvas is retained
without a free registration search: near/far means trigger/supporting arm, not image left/right.
No separate rifle generation is required. The two arm layers measure anatomy and landmarks;
`draw_owner: torso` prevents duplicate rendered arms. Source pixels are selected without repainting.
Keep the actual full rifle and both hands above the protected boundary. A low muzzle, hanging
equipment or arms crossing the lower garment transition is a reference blocker.

The real carried mesh follows one chest transform through the hand region. A separate lower
cloth transition, derived from hand-hint and original hem bounds, attaches the garment to the
existing registered pelvis. All original garment, shape, hidden-edge, neck, hand-detail, support
rhythm and native PNG checks still apply. Rendering refuses clips other than idle/run.

QA measures actual source-owned arm masks on their drawing owner's mesh; an invisible isolated
reconstruction cannot fill a hole in the actual draw surface. Blur checks inspect every actual
draw surface, including the complete source upper. Reconstructed landmark-only textures do not
count as visible output. This differs from bypassing a failed check on rendered art.

Every exported frame has an independent rigid-transform comparison of the protected source
mesh, with the unchanged one-output-pixel limit. Missing samples, owners, source/RGBA hashes or
unsupported clips fail the evidence gate. This detects deformation, not semantic gun/hand anatomy.
`carry_*.png` plus complete fixed-crop playback and a `carry_rigidity` observation for every frame
are mandatory: inspect stock, receiver, magazine, muzzle, both grips, elbows and garment boundary.
Occlusion within the baked source illustration is a visual judgment; the numeric occlusion report
only measures later external drawing surfaces. A correct wrist coordinate is insufficient.

This is a guarded single-character trial with synthetic proportion/fault tests, not a general
two-handed IK rig. No aiming, firing, recoil, reload, weapon swaps or engine rig import is claimed.
Source generation may adapt a front-facing reference into a side view; record that provenance.
