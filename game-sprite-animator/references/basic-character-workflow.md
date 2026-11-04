# Basic side-view character production

Use this as the default when a user supplies a character picture or asks for AI character art.
Read the workflow once, then run it for the user. The user supplies the picture and desired equipment;
the agent supplies every prompt, visual inspection, review JSON, repair and command. Infer compatible
equipment from the picture unless the user states a preference; do not ask for technical settings. Do not ask the
user to write prompts, cut layers, mark joints or tune per-character rig values.

## What this profile actually supports

`basic-side-v1`: side-view two-arm/two-leg humanoid, short hair, fitted or short sleeves with exposed
hands, short upper garment ending at the hips, fitted trousers, simple shoes, opaque crisp art.
Equipment is `none` or ONE simple single-handed straight `sword`. First output is idle + walk only.

Wide sleeves, long hair, capes, floor-length/wraparound robes, loose panels, dangling accessories,
shields, bows, guns, spears, two-handed weapons and arbitrary creatures are outside this profile.
The general binder retains experimental features for older work, but do not switch a basic job to
that path to bypass a refusal. Source art may contain unsupported features: first describe needed
adaptations. If those features are essential to the character and must be preserved, report the
scope conflict rather than promising an exact reconstruction or silently changing the design.

A source illustration is an identity reference, not a ready-to-bind image. The first AI step may
change pose and reconstruct hidden details. Preserve face, build, palette, motifs and style; explicitly
record what was simplified. Never claim recovery of invisible original anatomy or guarantee one-shot
AI generation. The workflow gates measurable constraints plus reviewer attestations; it does not
contain an automatic semantic vision model. Real-art quality still requires visual and motion review.

## 1. Prepare from the user's picture

First look at the incoming picture and infer whether it is empty-handed or carries one supported
sword. Identify any essential out-of-scope feature before proceeding. Run from this mode's directory
and select the corresponding `--weapon` without asking the user to configure it. Use a NEW job folder:

```bash
python scripts/character_workflow.py prepare --image input.png --name Hero --weapon none --out hero
```

`--weapon sword` is the only other equipment choice. Defaults for character and style refer to the
attached source, so no description is required from the user. Optional `--who` / `--style` are identity
and style descriptions only, never geometry or joint offsets. Do not insert conflicting pose or
unsupported equipment instructions there.

Inspect `hero/source.png` using the image-reading tool and follow `prompts/00_identity.txt`.
Write `identity_notes.md`: visible face/build/palette/motifs/equipment/style, uncertainty, and every
adaptation. If keeping the source's essential design is impossible in scope, stop and explain why.

Use the image editing tool with `source.png` as the FIRST reference and the fixed `pose_guide.png`
as the SECOND reference, plus the EXACT `prompts/01_reference.txt` to generate
`hero/reference.png`. This is a new standard right-facing side-view pose, not a cut-up of the source. The complete forward
upper arm must be visible from shoulder to elbow, not a forearm emerging from the waist; the guide
exists to make this attachment geometry explicit.
The standard canvas is 1024 x 1536 with a roughly 85%-height figure and solid magenta background.
Do not silently rescale/reposition image output to disguise failure of the generation contract.
If the image tool is unavailable, report that blocked generation step and provide the prepared
prompts; do not fabricate completed art or label the job successful.

If the original attachment is visible to the agent/image tool but no local bytes are available, do
not pretend a generated copy is the uploaded original. A working generated identity proxy may be
prepared with `--source-proxy-note "..."`; this explicitly records `source_kind` and the original's
availability. Compare identity against the actual visible attachment, preserve that provenance in
all case reports, and never claim the proxy's hash certifies original bytes. Count a proxy produced
as a reference attempt against the SAME reference budget, not a fresh job. Prefer the original file
whenever it is readable.

## 2. Approve the standard reference BEFORE generating layers

```bash
python scripts/character_workflow.py reference --job hero
```

This runs numerical preflight and creates `reference_review.template.json`; it does not approve art.
Open the standard image at full size. Inspect strict side view, both complete readable arm chains,
two separate legs/shoes on a ground line, empty background, and equipment count. Compare identity
with the source. Check the five basic-scope items too. No sleeve may hide a missing forearm; a complete
hand at the end of a cuff does not establish a complete arm.

The reference also requires `natural_neck_attachment` and `natural_hand_pose`. Enlarge the neck
and BOTH hands: neck enters the collar without a skin/scales triangle, cut line or detached-head
appearance; empty hands have gentle finger curvature, a coherent palm/thumb and neutral wrist.
Keep species-specific claws and digit count without defaulting to a fan-splayed threatening grasp.
A sword hand stays closed securely around its handle. User-requested expressive poses take
precedence over the relaxed default but still require anatomical continuity. Fix a bad reference
before separating layers; hints and binding cannot repair its gesture.

Copy the template to a reviewer input such as `reference_verdict.json`, fill reviewer and every
check with `status: pass` plus observed visual evidence only after inspection. Failed checks require
a regenerated reference, not a passing value to unblock code.

```bash
python scripts/character_workflow.py reference --job hero --review hero/reference_verdict.json
```

Only this accepted step releases the fixed per-layer prompts. A failed new review invalidates older
acceptance. The review is bound to the exact standard image, source and declared weapon; changing it requires review again.

## 3. Generate and inspect isolated layers

Use the accepted `reference.png` as the input to each released art prompt. Save results in `layers/`
with the prompt's basename. Preserve the full canvas, pose, position, scale, linework and colours.
Required art is `arm_far`, `leg_far`, `leg_near`, `hips`, `torso`, `head`, `arm_near`, and `weapon`
only when the job requests a sword. No optional robe/cloth/hair-back layers are allowed here.

After both COMPLETE arms are generated, run the two hand-hint prompts on their respective FINISHED
arm images, never on the full reference. Save `hand_near_hint.png` and `hand_far_hint.png`; both are
mandatory landmarks, not rendered art. Generating a hand hint cannot repair a stump arm.

```bash
python scripts/character_workflow.py layers --job hero
```

Open `layer_review.png` for comparison, then EACH original full-size layer. The overview is not
sufficient for judging fingers or seams. Complete `layer_review.template.json` into a reviewer input
such as `layer_verdict.json`. Every layer and hand hint needs these five base checks:

| Check | Look for |
|---|---|
| complete_shape | Arm: shoulder, upper arm, elbow, forearm, wrist, whole hand. Leg: hip, thigh, knee, shin, complete shoe. Head: one face plus bare neck. Torso: complete neck-to-hips shape. Hips: solid hidden core. Weapon: complete hilt/blade. Hint: whole hand at actual wrist. |
| exclusive_contents | Exactly its assigned anatomy/material; no second limb, stray fragment, doubled cloth, weapon in an arm/torso, or hand in a weapon layer. |
| sharp_art | Crisp matching fingers, seams and contours; no smear, translucent ghost, stretched fill or blurry patch. |
| unchanged_pose | Original canvas, pose, scale and location; no isolated part enlarged or centred. |
| valid_attachment | Reconstructed hidden root and unoutlined overlapping cut, correct neck overlap, own shoulder, actual wrist hint; no separate floating attachment. |

Head and torso additionally require `natural_neck_attachment`; arm layers and both hand hints
require `natural_hand_pose`. Inspect the registered head/torso composite against the original:
internal neck cuts must stay hidden INSIDE the matching neck, not overlap the front of the scarf
or collar. A narrow alpha intersection alone is insufficient. Hints preserve the finished hand
exactly; repair the source/reference or arm first rather than re-posing fingers in a hint.

```bash
python scripts/character_workflow.py layers --job hero --review hero/layer_verdict.json
python scripts/character_workflow.py bind --job hero
```

Layer review hashes cover all layers, hints, source, reference, identity notes and reference review.
Changed art/notes invalidates acceptance. Binding rechecks both reviews plus the numerical gates.
Inspect `rig/layers_check.png` and `rig/bind_joints.png`; trace both entire arms, do not judge a
shoulder cap alone. Never hand-edit the generated character configuration or individual pixels to
make it pass. Preview detects changes to the exported rig and requires rebinding the general fix.

## 4. Bounded repairs

Every first generation counts as attempt 1. BEFORE any replacement image, log a retry:

```bash
python scripts/character_workflow.py retry --job hero --stage arm_near --fault incomplete --reason "arm_near: no visible forearm between cuff and wrist"
```

`--stage` is `reference` or a required layer/hint. `--fault` is one of `reference`, `incomplete`,
`extra_art`, `blur`, `registration`, `neck`, `hand_pose`. This preserves the current image/reviews and the prompt used, records the observed
fault, invalidates acceptance and writes `prompts/retry_<stage>.txt` combining the original fixed
prompt, the observed failure as inspection data, and the fixed repair rule. The evidence must name
the actual unwanted anatomy/object or missing segment; it is not a per-character joint offset. The agent uses that prompt on the appropriate original input and
repeats all affected reviews. Do not patch the fixed prompts for one character.

At most THREE tracked generations per stage (initial + two replacements). If the third still fails,
stop and report the unresolved blocker and attempted repairs. Requesting a fourth attempt records
a terminal `blocked` phase; other stage commands cannot silently reopen that job. Do not create a fresh job or rename a
stage to reset the budget. Tools cannot observe image generations performed outside the workflow;
the agent must log each attempt honestly. A reference retry requires inspecting all layers again.
For `retry --stage reference --fault hand_pose`, the fixed `REFERENCE_HAND_REPAIR` prompt changes
only empty-hand finger curl while preserving the full registration plate, wrist positions and
any holding hand. Use the resulting reviewed reference to regenerate affected complete arms and
then their hand hints within the SAME stage budgets. Do not relax fingers in a hint image.

## 5. Idle and walk, then user's quality gate

```bash
python scripts/character_workflow.py preview --job hero
```

This generates only `idle,walk` at hd512 without effects, runs numerical QA and builds visual sheets.
Any nonzero result blocks further progress. It does not auto-record a passing verdict. Follow
`visual-review.md`: inspect every sheet plus flagged original frames, complete the versioned
verdict, record it and run `--check`. Short arms, missing swing, broken clothes, ghosting and extra
weapons are blockers regardless of numerical QA.

```bash
python scripts/visual_review.py hero/build --record hero/walk_verdict.json
python scripts/visual_review.py hero/build --check
```

Open `hero/build/preview.html` and show the running result to the user. Do not claim full production
acceptance from stills or synthetic tests. Wait for the user's walk approval before proposing more
clips. This command has no full-set/attack switch. Sword attacks, spear thrusts and other equipment
need separate validated motion work; the shared 27 clips are not automatically approved for this job.

`status --job hero` prints the recorded phase and retry history, not a fresh quality certification.

## Verification boundary

The first real wuxia-swordsman trial on 2026-11-02 FAILED before binding. A reference passed on
attempt 3 with the fixed pose guide, but the isolated rear leg retained a second thigh on all three
attempts; torso shoulder duplication and enlarged head were also unresolved. The job stopped with
0 animation frames. This is evidence of a live generation limitation, not a successful real-art
validation. The profile is a guarded trial workflow, not a proven reliable commercial generator.

Two synthetic body builds exercise prompt release, mandatory hints, isolated-layer inspection,
numerical bind/export and walk QA under the same rules. Registration is fixed to identity in those
tests because fixture layers already share a canvas. Fault tests reject incomplete reviews, wrong
scope/canvas, unsupported or missing layers, changed assets and exhausted retry budgets. These are
pipeline tests, not evidence that an image model reliably generated or visually passed two real
characters. That validation starts with an actual source picture and ends at user-approved motion.
