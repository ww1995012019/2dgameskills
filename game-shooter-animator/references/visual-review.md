# AI visual review

The numeric checks can only find what someone thought to measure. A body hovering above the floor
passes every clipping test, because nothing penetrates. So the agent running this skill looks at the
frames itself, as an art lead would, and that verdict is part of the QA gate.

## Run it

```bash
python scripts/qa_motion.py out/c        # first: flagged frames go into the sheets
python scripts/visual_review.py out/c
```

Read every `out/c/review/sheet_NN.png` with your image-reading tool. Don't skip a sheet because QA
passed: the sheets exist to catch what QA passes. `out/c/review/index.json` lists the clips per sheet, the
QA reason for each flagged frame, and the near-duplicate aim angles that were left out.

How to read a sheet: each clip has a row of poses with the frame number, then the same poses as black
silhouettes. The orange line is the ground. A red border means QA flagged that frame. Each clip is
cropped to its art so a small character fills the cell; its title gives the zoom. Don't judge a face or
a joint from a cell alone: on anything that looks off, open that frame in `frames/` and enlarge it.

`joints_00.png` is the sheet that catches what the others can't: each knee and elbow at its sharpest
bends across all clips, and the head at the frames the arms are most folded, all enlarged. Trouble at a
joint is a few pixels across and only appears at a sharp bend, so a full-body cell hides it. Judge every
cell: the outside of a bend must be one smooth curve, with no step, nub, square end, stripe or hole.
`--record` refuses a verdict that leaves this sheet out.

### Head, neck and both hands: mandatory close-up and motion review

`neck_*.png` shows clean enlarged head/neck/collar pixels and the driving neck/chest bones for
EVERY applicable clip, including first/last poses and head-world/chest-world/relative-angle
extremes when exported. `hands_*.png` shows the NEAR hand above the FAR hand, including wrist
travel extremes. Pose lists are not truncated across the whole animation set. Native layered
humanoids require complete neck and both wrist traces. Lower-body-only clips are outside this
head/hand scope; upper-body clips are included when their trace supplies these joints.

Open each sheet AND its indexed `neck_motion_*.gif` / `hands_motion_*.gif`. These contain the
entire clip, with a fixed crop throughout, at the exported duration (GIF timing is quantized to
10ms). Identical held frames may be coalesced by the format, retaining their combined duration.
For unusually high rates above 100fps, use the actual runtime preview for accurate timing.
Watch at least two cycles at normal speed and inspect slow/stepped playback in the preview.
For a non-looping clip, inspect anticipation, action and recovery as well as the repeat boundary.
If your tool cannot play GIFs, play the same clip in `preview.html`; cite that playback and the
indexed evidence file. Static crops and angle measurements alone cannot clear naturalness.

Inspect the original reference, registered isolated head/torso and both arms at full size too:

- Neck: one continuous jaw-to-neck-to-shoulder structure. No floating head, shelf/triangle at
  the neck base, visible internal cut, doubled skin/scales or neck tab painted over the collar.
  The lower neck should join the chest while the upper neck allows bounded head movement.
  Alpha contact can pass while a triangular cut is plainly visible; do not clear it on that basis.
- Head motion: skull/face shape remains stable, gaze and nod respond to weight and chest
  movement with appropriate counterrotation and lag. Neither a head welded to the torso nor
  an independently sliding/hinging cardboard neck is acceptable. Small nonzero rotations do
  not prove natural motion. Do not add arbitrary wobble, change facial expression or distort
  horns to manufacture an angle range. An intentionally still gaze can be valid if the neck
  response looks continuous and the review explains why it fits that action.
- Hands: correct palm/thumb and species-specific digit count/scale; empty hands have gentle,
  slightly varied finger curls and neutral wrists. Species-specific claws are retained without
  automatic fan-splaying, spider-like extension or theatrical grasping. A holding hand stays
  securely closed around its handle. Honor an explicitly requested expressive gesture while
  still inspecting anatomy. No fused/extra fingers, hook-like overcurl, sudden finger popping,
  stretched palm or wrist kink; both near AND far hands must be reviewed.

These are dedicated semantic checks, not a new automatic vision classifier. The existing 95%
static neck overlap measures contact; the hand edge-energy check measures retained detail.
Neither judges a painted cut, natural fingers or stiffness. User-reported defects withdraw the
old acceptance immediately; retain the report as history and record the failure before repairs.
Repair source/reference art or the general binding/motion mechanism at the failed stage. Do not
cover a seam, re-pose landmark-only hand hints, tune one character, weaken a threshold or reset
the three-attempt generation budget. A generic fix is not proof that old artwork was repaired.

`shoulders_*.png` shows the neck, torso and both upper arms at rest, recovery and each arm's
forward/backward extremes. The upper row is the art; the lower row adds the shoulder seats and
upper-arm bones (near cyan, far orange). Inspect both together: a sleeve cap is not an anatomical
joint, and a joint can be numerically valid while the arm appears to emerge from the back.
The two arms keep their own measured attachment seats; screen-space coincidence alone is neither
required nor proof of correct anatomy. The far arm stays behind the torso and the near arm stays
in front. Check that the far sleeve is occluded at the
shoulder and reappears naturally below it as the arm moves. The verdict must cover these sheets.

`arms_*.png` extends the crop and coloured paths through both elbows and wrists, including the
frames where upper arms or hands come closest. Trace each complete shoulder -> elbow -> wrist
path against the art. A readable shoulder cap is insufficient if the second forearm appears to
branch out of the first arm. Inspect the complete carried pose, including the weapon arm, before
marking idle or recovery poses as passing. These sheets are mandatory when both arms are traced.

`hips_*.png` is mandatory for every full-body side-view humanoid clip. It enlarges the waist,
pelvis, crotch and both thigh roots, first as clean art and then with the actual rendered
waist/hip/knee/ankle skeleton. The index lists exact clip/frame observations for rest, first/last
poses, maximum leg separation, lowest pelvis/deepest crouch and hip/knee bend extremes. When
source-frame switches are recorded, their neighbouring frames are included too. Coverage is per
clip, not the globally worst eight poses. Read every row, then open the full RGBA frame and source
art for any questionable seam. A valid skeleton beside a ripped pair of trousers is a failed rig.

Trace each bone against the painted body. Check waist-to-pelvis continuity and the two hip seats
separately; then inspect the fabric bridge between them. A natural opening below the crotch is
different from a new background slit through previously continuous cloth. Reject straight cut
edges, horizontal shelves, detached panels, duplicated waistbands and an arm or leg attached at
the wrong painted joint. An opaque belt/torso must not conceal the absence of necessary pelvis
pixels. The existing body-core check stops above the leg split and cannot establish this.

For current registered basic exports, hips sheets include EVERY exported frame. Look at both
outer waist edges, the complete jacket/trouser boundary, and the inner thighs at native crop size;
do not let a dark page background or a centreline contact hide a one-pixel split. Compare the
registered `binding_reference.png` with rest, all extremes and the sequence: a trouser core that
climbs beside the jacket, a shifted waistband or an invented extra panel fails the mandatory
`source_garment_registration` check even if there is no transparent hole. Registered connection
evidence checks all frames and rejects missing coverage or changed source/output pixels. It
measures geometry; it cannot certify garment colours, painted cuts or anatomy. A manual pass
must describe the source comparison, not infer it from a green numerical report.

For an external/custom mesh, also inspect the source-point and runtime overlays from
`audit_skin_binding.py` ([contract](skin-binding-audit.md)). The tool checks declared landmarks
and shared boundaries only. It cannot identify every unmarked seam or judge all anatomy.
Missing runtime trace/source data is unverified; game tests and unrelated procedural examples
cannot substitute for that renderer's evidence.

Check a QA flag the same way before acting on it. Open the frame enlarged and confirm the problem is
there: a flag is a measurement, and a measurement can be wrong.

The review narrows the risk, it doesn't remove it. Say which sheets you read, and that the set still
needs a person to watch it play before it counts as done.

## Checklist

Look at each clip for these, in this order. Name the clip and frame when something is wrong.

**Regression review after a connection fix**

- A zero-drift connection or positive triangle area is not an anatomy verdict. Positive triangles
  can be nearly flat; a rigid thigh can also follow the wrong parent's rotation.
- Compare the same clip/frame before and after the change at equal world/pixel scale. When a
  cadence change alters frame count, compare nearby normalized cycle phases and label both frame
  numbers; equal frame indices then no longer mean equal poses. Keep whole
  thighs and knees visible; the previous waist-only crop hid thigh regressions.
- `limb_shape_preservation` is mandatory for every hips-sheet pose. Inspect thickness, thigh
  direction, knee location, shorts/trouser hems and the full playback. Do not batch-generate
  passing visual claims from a checklist template.
- Current basic exports require `registered_garment_surfaces_v3` evidence. The original hidden
  waist rim follows its garment owner; a free deformation band connects it to the moving thigh.
  The opaque shaft Jacobians are checked outside the
  knee envelope (two local knee radii): min singular scale 0.25, max 3, signed area ratio 0.15–3;
  over 1% distressed shaft material is a blocker. These conservative limits identify catastrophic
  collapse/stretch, not every unnatural silhouette. Existing fold/contact limits remain intact.
- Apply those same strain limits separately to the waist transition; the previous thigh ROI
  excluded exactly that region. Native alpha checks also require every originally hidden source
  cut-edge point to remain under the recorded later garment surfaces, within one output pixel.
  A rotating cap is not sufficient proof that a trouser rim or pocket top remains hidden.
- Complete `hidden_garment_edges` and `motion_style_match` for each required pose. Open the blue
  `garment_edges_*.png` waist macros, where a small folded corner is large enough to inspect.
- The explicit `ordinary_run_v1` profile is body-scaled; ordinary-run evidence limits stride to
  1 leg length, lift to 0.3 legs, horizontal ankle separation to 1 leg, thigh angle to 65 degrees,
  torso lean to 15 degrees and bob to 0.05 legs. These are conservative bounds for ordinary running,
  not universal limits for a sprint or an action pose. Watch the actual cycle and compare the user's
  intent; a fixed large-step template can pass skeletal integrity and still be the wrong motion.
- Revoke the actual current visual pass when a user identifies an omitted defect. Preserve the
  failure and show changed-frame evidence for that same issue before accepting another result.

**Contact**
- Feet on the orange line in ground clips, neither above nor below it
- Nothing hovering: a roll or lying body rests on the line
- Hands on the weapon, with no gap at the grip
- Weapon stops at the ground

**Anatomy**
- Both arms connect at the shoulder region; neither begins on the back, neck or waist
- The far shoulder remains behind the torso in rest, raised-arm and recovery poses
- Limbs bend the right way, with no reversed knee or elbow
- Joints not folded past what a body can do
- Neck not twisted, head attached to the shoulders
- One face only, with no doubled chin, ear or hairline when the head turns
- No colour patch or stripes at a joint that the character doesn't have
- Both arms have a complete shoulder -> elbow -> wrist -> hand path; a short stump is a blocker
- Garments are complete, without broken pieces or duplicated/ghost art
- Exactly the intended weapons are present, without extras left in arm or torso layers
- Limb lengths look constant across the row
- Actual shoulder/elbow/wrist and hip/knee/ankle bones match the painted joints in both source/rest and moving poses
- Waist, pelvis and crotch remain joined; both thigh roots retain their cloth connection during crouch and leg separation
- No exposed middle cut, new background slit or overlapping copy of a trouser/waist panel

**Readability**
- Silhouette says what the action is, without colour
- Weapon visible, not lost against the body
- Face not covered on poses that hold
- The extreme pose of the action is clear, with a real difference between anticipation and strike

**Weight and timing**
- Body lowers on impact and recovers after, instead of popping up
- Fast actions have enough in-between frames or a smear
- Clothing and hair trail the motion, without knots or sudden jumps

**Frame**
- Nothing cut off by the cell edge, including effects
- The character stays the same size and proportions across clips

## Severity

- **blocker:** a player would notice it as a bug. Hovering, cut-off art, a reversed joint, a hand off the
  gun, a pose that doesn't read. Missing or stump limbs, ghosting, broken garments and extra weapons
  are always blockers; never downgrade them to polish. Wrong painted joint attachments and an
  open waist/crotch seam are blockers too. Fix it before delivering.
- **polish:** a matter of taste or a small flaw. Record it, and fix it if it's cheap.

Fix the cause, not the frame. A roll that hovers needs a contact rule, not a nudged key. When a
visual issue slipped past QA and can be measured, consider adding a check for it.

## Record the verdict

Start from `review/verdict_template.json`, which is pending and cannot pass as generated.
Write a JSON file covering exactly every sheet. Copy `review_id` from `review/index.json`.
It hashes the current frames, review index/coverage, review sheets, exported sprite sheets/atlas,
runtime preview/engine files, animation metadata, rig trace, QA and binding-audit evidence.
Declared custom and nested delivery page filenames are followed too. A replaced, missing or
unreadable atlas invalidates the pass; declared pages cannot point outside the export folder.
Image recompression alone does not change decoded-pixel hashes. Changes invalidate
the verdict; rebuild sheets and review again. Rebuilding or a rejected recording removes the old
current `visual_report.json`; archived reviews remain in `review/history/`.

Each sheet requires `verdict`, `checks` and `issues`. Every check requires `status` and concrete
`evidence` naming the observed poses/frames. Required checks are `complete_limbs`,
`continuous_garments`, `no_ghosting`, `expected_weapons`, `anatomy`, `readable_motion`.
Use `pass` or `fail`; only garments and weapons may be `not_applicable`, with a reason.
Hip sheets additionally require `rig_alignment` and `pelvis_continuity`: neither can be skipped.
Neck sheets require `neck_continuity` and `head_motion_naturalness`; hand sheets require
`hand_pose_naturalness` and `wrist_continuity`. None can be skipped. Each requires explicit
`observations` for every indexed clip/frame. Naturalness checks additionally require a
`playback` observation for EVERY indexed clip/file, naming what the complete moving sequence
shows. Blank, missing, duplicate or substituted playback evidence is rejected. Motion evidence
files, duration/frame-count/FPS metadata and pose coverage are bound into the current review.
For each, fill the template's `observations` with a concrete finding for **every** indexed
`{clip, frame}`. A generic sentence such as "looks fine" is not a substitute for those observations.
For example, an unresolved crotch defect is recorded as:

```json
"pelvis_continuity": {
  "status": "fail",
  "evidence": "crouch frame 6: original trouser bridge separates",
  "observations": [{"clip": "crouch", "frame": 6,
    "evidence": "background slit and a horizontal cut edge at the near thigh root"}]
}
```

The abbreviated example above does not replace the other required observations/checks. Use the
generated template, which contains the actual complete pose list. Missing full-body trace,
missing hip sheets, incomplete observations, old schema or altered coverage are refused.
Missing checks, failed checks under a pass verdict, or unresolved issues under a pass verdict
are refused. A fail sheet always makes the report fail, including cosmetic defects.

```json
{
  "reviewer": "reviewer name",
  "review_id": "COPY_CURRENT_INDEX_REVIEW_ID",
  "sheets": {
    "arms_00.png": {
      "verdict": "fail",
      "checks": {
        "complete_limbs": {"status": "fail", "evidence": "walk frame 4: weapon arm is a stump"},
        "continuous_garments": {"status": "pass", "evidence": "walk frames 0,4,8: coat intact"},
        "no_ghosting": {"status": "pass", "evidence": "walk frames 0,4,8: no doubled art"},
        "expected_weapons": {"status": "pass", "evidence": "walk frames 0,4,8: one sword"},
        "anatomy": {"status": "fail", "evidence": "walk frame 4: missing forearm"},
        "readable_motion": {"status": "fail", "evidence": "walk frame 4: no complete arm swing"}
      },
      "issues": [{"id": "weapon-arm", "clip": "walk", "frame": 4,
        "category": "missing_limb", "severity": "blocker",
        "what": "weapon arm is a short stump", "resolved": false}]
    }
  }
}
```

Categories are `missing_limb`, `broken_garment`, `pelvis_gap`, `rig_misalignment`, `neck_seam`,
`stiff_head`, `unnatural_hand`, `broken_wrist`, `ghosting`, `extra_weapon`, `anatomy`,
`unreadable_motion`, `cosmetic`. All except cosmetic require `blocker`. `resolved` must be a JSON
boolean. Any unresolved issue (including polish) or failed sheet returns exit 1; the report's
`status` is authoritative, not merely its `open_blockers` count.

Record the failed review before fixing. After fixing, regenerate the frames, rerun QA, rebuild
sheets, and inspect the changed art again. Keep each open issue's id, category and clip. Issues
cannot disappear from the registry. To resolve one, set `resolved: true` and include:

```json
"resolution": {
  "previous_review_id": "ID_OF_THE_RECORDED_FAILED_REVIEW",
  "change": "Describe the actual general fix and what the new frames show",
  "frames": [{"clip": "walk", "frame": 4}]
}
```

The recorder requires the prior archived open issue and verifies each cited frame exists in both
reviews and its decoded pixel hash changed. Unchanged frames cannot resolve an issue. It also requires
a new current checklist. Changed pixels do **not** prove that anatomy is fixed; the reviewer must
inspect them and describe the observed repair. Do not relabel categories or invent evidence to pass.
These checks enforce review consistency and provenance, not the truth of a visual judgment.
The final `--check` also validates the saved history and unresolved-issue registry. Editing the
current report's status/checks or deleting its issues cannot clear an already recorded failure.

```bash
python scripts/visual_review.py out/c --record verdict.json
python scripts/visual_review.py out/c --check  # mandatory before delivery; stale passes fail
```

Legacy unversioned verdicts must be reviewed again; do not copy an old pass into the new schema.

Stop after three rounds and tell the user what's still open, rather than iterating on taste.

Report honestly: name what you reviewed and what you left out. This is a reviewer's judgment,
not a mathematical guarantee of natural motion. The required full playback supplements the
still-frame review; user acceptance of the actual preview remains separate. Schema 3 invalidates
older passes rather than inheriting head/hand approval from unrelated anatomy checks.
