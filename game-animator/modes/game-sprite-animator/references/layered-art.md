# Layered puppets: underlying binder and experimental extensions

For new supplied-picture/AI-art jobs, start with `basic-character-workflow.md`. Its bounded profile
is the default and requires hand hints plus isolated-layer review. This document describes the
underlying binder and older experimental features (robes, loose cloth and long hair); their historical
checks do not establish production approval for a new basic job.

The underlying binder takes one standard reference picture and
turns it into complete, separate layers that bend along the skeleton. Nothing is marked by hand and
nothing is set per character. Automatic checks cover measurable faults only. Semantic compliance must be judged visually and
recorded for the exact reference; absence of a numerical refusal is not approval.

`references/ai-art.md` describes the older route that cuts one picture along its bones. Keep it for
quick tests of tight-fitting characters. It can't do the things this route exists for: sleeves, robes,
capes and long hair.

## Why one picture can't be cut

One flat picture has no chest behind the arm, no thigh behind the robe and no sleeve apart from the
arm. Cutting it along bones gives these faults, and no tuning removes them:

| What people see | Cause | What this route does |
|---|---|---|
| Blurred chest | the arm hid it, so the fill invents pixels | the image model repaints the chest in its own layer |
| Hand like a bun | the hand is rebuilt from a few pixels at small size | the arm layer holds the whole hand, drawn |
| Cape in segments | rigid pieces between joints | cloth is one sheet bent along a simulated chain |
| Leg folded at the knee | two rigid pieces meet at a hinge | one mesh bends on a rounded curve |
| Sleeve still while the arm moves | the sleeve was cut into the torso | sleeve and arm are one layer |

Do not fix these with fills, masks or per-character tweaks. If one shows up, the art or the pipeline
is wrong: fix the general rule, in `layer_slots.py` or `layer_parts.py`, and test it on two characters.

## The contract

**Reference picture.** All of these are required. `plan` checks background, height and margins only;
it does not recognize side view, pose, occlusion or anatomy. It also writes a pending
`reference_review.json`. Inspect the exact reference and fill every semantic check with `status: pass`
and a concrete `evidence` description, plus `reviewer`. If any item fails, remake the reference.
Do not set checks to pass just to make bind run. `image_sha256` ties the review to the image; changing
the image requires a new review. The checks are `right_side_view`, `complete_separate_arms`,
`visible_separate_legs`, `planted_feet`, `unobscured_limbs`, `separate_garments`, and `expected_weapons`.
This is reviewer attestation, not automatic semantic recognition.

- Portrait canvas with the figure at least 900 px tall and a margin all round.
- Flat background, one colour or transparent. Magenta `#FF00FF` is standard, so the character uses no
  magenta or pink-purple.
- Strict side view facing right, small walking stride, both feet flat on one ground line.
- Front arm reaching forward and slightly bent, rear arm back. Both clear of the torso and legs.
- Weapon, if any, held in the front hand.
- Long hair and loose cloth hang or trail behind and do not cross the arms or legs.
- Even flat lighting: no glow, cast shadow or ground.

The prompt is `REFERENCE` in `scripts/sprite_anim/layer_slots.py`. Fill in the character and style
and change nothing else.

**Layers.** Fixed list, back to front. Optional ones are left out when the character has no such thing:

| Slot | Holds | Required |
|---|---|---|
| `appendage_back` | explicitly requested experimental rear biological appendage, kept as one rigid shape following the pelvis | no |
| `hair_back` | long hair behind the head and back | no |
| `cloth_back` | robe tail, sashes, cape | no |
| `arm_far` | rear arm: hand further left, with sleeve | yes |
| `leg_far` | rear leg: foot further left | yes |
| `leg_near` | front leg: foot further right | yes |
| `hips` | solid under-layer from waist to crotch, mostly hidden by the torso | yes |
| `robe` | optional complete connected wraparound skirt, including front panels, train and lining, drawn in front of the legs | no |
| `torso` | neck to hips, with the complete front apron at its original length, including long front panels | yes |
| `head` | face, hair on the skull, and the exposed neck down to the collar, overlapping the torso's neck | yes |
| `weapon` | the whole weapon | no |
| `arm_near` | front arm: hand further right, with sleeve | yes |

`appendage_back` is an opt-in experimental extension for a user who explicitly requests preservation
of an unsupported rear appendage. It is not admitted by `basic-side-v1` and must not rescue a rejected
basic job. It shares the existing `rigid` renderer and the measured pelvis frame: its complete source
curve moves as one shape, without articulated or simulated tail bending. The binder requires alpha
overlap with hips/torso within one quarter of measured leg length of the pelvis; this proves a covered
source contact only. Review the full isolated appendage and its root contact in every delivered frame,
including both facings and floor clearance. No species-specific joints or pixel adjustments are used.
The garment-duplication alpha ratio is not applied to this slot: a rigid rear root must be hidden
under a different opaque garment, so their masks legitimately overlap. This matches the existing
arm-root ownership rule. Overlap alone is not proof of copied anatomy; inspect the exact registered
materials and all source/motion layers. The two-build synthetic regression includes a shorter
appendage with a large covered root; floating and non-pelvic contacts still fail the separate gate.
Use the same three-generation-per-stage budget, preserve failed attempts, and record the explicit
adaptation and user authorization separately from numerical acceptance. This extension does not
establish production support for arbitrary creatures or all 27 actions.

`hips` exists because the rest can't close the body. An image model stops the legs below the belt and
splits the robe into panels, so background shows through the figure below the belt, in a pose the
outline gives no sign of. It holds only hidden art, so it is judged by what it fills, not by matching
the reference, and it is required even for a character whose torso looks closed. `bind` cuts it to the
middle of the body and fades its lower end, so it never shows past the robe as a stiff block.

For a connected wraparound skirt whose front and rear panels cannot be separated
without repeatedly duplicating or omitting fabric, use the optional `robe` slot
instead. It retains the whole garment in one image, in front of both legs and
behind the torso and hands. Keep the torso to the upper garment, belt and short
belt ornaments in this route. Omit `cloth_back` unless there is a separate cape
or independent trailing garment. The robe has its own body-aligned hem joint;
its length never stretches the torso's shorter apron. It bends with the body
and average thigh direction, rather than simulating each loose panel separately.
Review its silhouette and mesh folds in motion; the walk is the first gate, and
this does not establish that flips, attacks or other clips will suit a wide robe.

Limbs are named by where they are in the picture, never "near" and "far" in a prompt: an image model
reads both as the same limb.

## Commands

```bash
python scripts/layer_parts.py plan --image hero.png --out hero/
```

Then, for each `hero/prompts/<slot>.txt`, edit the reference with that exact prompt and save the
result as `hero/layers/<slot>.png`. Use the image tool at hand; otherwise give the user the prompts.
Skip an optional slot the character doesn't have. Do not reword the prompts: a fix found for one
character belongs in `layer_slots.py`, for all of them.

For wide sleeves, also use the optional `hand_near_hint.txt` and `hand_far_hint.txt` prompts.
Edit the finished `arm_near.png` or `arm_far.png` respectively, keeping only the hand at its exact
canvas position, and save `layers/hand_near_hint.png` or `layers/hand_far_hint.png`. These images
are landmarks only and are never drawn. They prevent a hanging sleeve tip from being mistaken
for the wrist; the binder rejects hints that do not overlap their arm.

When two planted shoes are unambiguously visible, leg registration uses their sole positions
instead of matching pale trousers to a similarly coloured robe. Hidden hip art can be aligned
to the measured waist and crotch to correct modest redraw drift; this does not fill holes or
relax the solid-core check.

A tiny arch gap in one sole is treated as part of that footprint; separate shoes or ambiguous
extra footprints are not merged. For wraparound robes, `cloth_back` holds only the trailing rear
fabric. Short front panels, belts and front ornaments belong to `torso`, which also retains the
exposed neck above the collar. Keeping the whole skirt in both layers duplicates it in motion.

```bash
python scripts/layer_parts.py bind --image hero.png --layers hero/layers --reference-review hero/reference_review.json --name Hero --out hero/rig
python scripts/generate.py --character hero/rig/character.json --preset hd512 --clips walk --no-fx --out hero/build
python scripts/qa_motion.py hero/build
```

Numeric bind and motion QA do not certify complete art. Before approving the walk, inspect the
reference, all separate layers, `bind_joints.png`, every required review sheet and the running
preview. Trace both complete arms; reject short stumps, ghost limbs, broken clothing and extra
weapons as blockers. Record the versioned visual verdict described in `visual-review.md`.

After the walk is approved, drop `--clips walk --no-fx` for the full set of 27 clips. It takes about five
minutes per character at `hd512`.

`bind` finds each layer's scale, turn and position against the reference (image models redraw and
drift, so it never assumes they align), reads the joints from the layers' shapes, and writes the
puppet. `hero/rig/layers_check.png` must look like the reference.

## When bind refuses

The message names what to do. Remake the layer it names and run `bind` again.

| Message | Cause |
|---|---|
| `missing layers` | a required slot has no file |
| `X and Y show the same limb` | the image model drew one limb twice |
| `only N% of what it shows matches` | the model changed the art, or left something out |
| `the layers cover only N%` | some art is in no layer. Look at `layers_check.png` |
| `N% of the layers lies outside` | a layer holds extra art |
| `torso: it also holds the art of ...` | the torso took the tail or hair, so it would be drawn twice |
| `hips: N% of the body below the belt is see-through` | nothing fills the body between the belt and the crotch |
| `head/torso: no continuous neck overlap ...` | colour matching left an open neck or only one touching corner; redraw the complete bare neck at its reference position |

Never bypass a refusal by editing `bind`'s limits or the layer's pixels.

Layer prompts keep even small isolated parts at their original scale and position.
The head and torso share an exposed-neck overlap; registering their colours alone
does not prove that the jaw connects to the collar. After colour registration,
the binder seats the whole head by the smallest bounded translation that covers
95% of the central 60% of the torso's neck cross-section, sampled 2% into its
height. Vertical movement is limited to 8% of torso height, horizontal movement
to one quarter of that. Larger drift is refused. All colour, coverage and spill
checks run on the seated result. Internal attachment edges have no dark cap
outline, and the head's neck contains bare skin rather than a second collar.
This static cross-section does NOT detect an exposed triangular neck base, a cut painted over
the front of a collar, or stiff motion. Compare the registered composite with the source and
complete the mandatory head/neck motion review in `visual-review.md`. Preserve skull/face identity;
the base of the neck must follow the chest while the upper neck permits bounded independent
head motion. A whole bare neck rotating like a rigid cardboard tab is a failed result. The current
rigid-head renderer has no soft neck skinning; if that mechanism exposes a cut, report a failed
binding/motion stage, not a solved seam. Do not erase the source, inflate the collar or alter one
character's joints to hide it. A small harmonic head rotation is not evidence of natural motion.
The rear arm must reconstruct
its own hidden shoulder rather than copying the visible front shoulder plate.
Trailing fabric ends at the rear hip and excludes every front-facing skirt flap.
Keep long front panels in the torso at their original length: shortening every
apron loses silhouette coverage even when the rear cloth was separated correctly.

For repeated layer replacements, `bind --fit-cache path/to/cache` can reuse the
expensive registration search. The key covers the exact reference, layer, slot,
and registration source. Changed art is searched again, and every acceptance check runs
again even on a cache hit. Failed binds also keep completed search results.

## Binding reliability gates

The runtime shares near-side bone lengths with the far side. Before export, each
corresponding upper/lower arm and thigh/shin pair must have a longest/shortest
ratio at most 1.25. This is an input rejection limit, not a correction or a claim
that smaller differences are visually harmless. Redraw the mismatched limb.
Each segment must occupy at least 25% of its two-bone chain; at least 90% of
25 samples along each bone must have artwork within 2% of chain length (minimum
one pixel). These gates detect collapsed joints and unsupported centre lines;
they cannot recover anatomical landmarks hidden by a wide sleeve. Use the hand
hint when the inferred wrist is ambiguous. Synthetic fixtures of two body builds
and scale invariance tests exercise these gates; real-art acceptance still needs
visual review.

Rolled sleeves can expose a forearm while fingerless gloves dominate the hand
hint. Forearm landmark proposals preserve distinct colours actually present in
the hand instead of averaging glove and fingertip colours. Each material's
forearm area is compared with that same material's hand area. Supported shape
and material landmarks are compared as a pair; the 1.25 bone ratio, segment
support and joint-limit gates still apply unchanged. These are colour/geometry
proposals, not semantic skin or elbow recognition. Inspect the chosen joint
chains and the resulting bends; fully covered forearms supply no exposed-material
evidence. Tests cover two materials and scales plus covered-forearm rejection.

A weapon must intersect the near arm inside the inferred hand region (a disc at
the wrist with radius wrist-to-tip). With an inspected, registered near-hand hint,
the binder also intersects that exact hand mask and measures the palm pivot from
occupied contact pixels. It exports the measured along/across forearm offsets and
source-relative wrist angle to the existing runtime, so the hand and handle share
their pivot and turn. The binding report records this measurement. This is pixel
contact, not semantic handle detection: inspect the source, isolated sword and fist
to establish that it is the handle being held. Missing actual hand contact still
refuses binding. Without a near-hand hint the legacy grip remains 14% of the forearm
past the wrist and must be within 20% of the hand radius of weapon pixels (minimum
two pixels). Neither path supports two-hand constraints or validates arbitrary weapons.

Every attempted bind that reaches layer processing writes fresh `layers_check.png`,
`bind_joints.png` and `bind_report.json`, even on rejection. Early rejections have
only the available partial composition; joints appear once inference completes.
The report records accepted/rejected status, rejection reason, measured joint
chains and bone lengths when available. On rejection, previously exported character
files remain from their earlier successful run; do not treat them as a new bind.
Inspect the joint overlay along with the layer composition.

Idle arm spacing also rejects consecutive collapsed samples spanning at least
100ms (and at least two samples), reporting the first frame. This supplements the
median check, which can miss a short collapse. Moving clips retain their existing
checks because arm crossing during an attack or gait is intentional.

## What QA checks

These run in `qa_motion.py` under "broken parts", and any one fails the set:

| Check | Fault | Measure | Limit |
|---|---|---|---|
| `smear` | blurred patch in a layer | tiles with colour change but no step steeper than 16% of it | 3% of a layer's tiles |
| `hand` | hand lost its drawing | edge energy at the hand, frame against reference at the same size | 55% |
| `fold` | mesh creased at a joint | a layer's drawn mesh area turned inside out in any frame | 0.2% |
| `kink` | cloth reads as segments | angle between neighbouring chain segments | 42 degrees |
| `hole` | background shows through the body | see-through pixels on the line from waist to hip, as wide as 60% of the waist | 1% in any frame |
| `shoulder` | far arm drawn over the torso | layer order | far arm behind torso |
| `arm_chain` | an arm follows the other arm's joints | each arm layer's bone path | its own shoulder, elbow, wrist |
| `arm_spacing` | distinct reference arms collapse together at rest | median distal-upper-arm and wrist spacing relative to reference | at least 50% where reference spacing exceeds sleeve widths |
| `crouch` | walk on folded legs | mean knee bend in `walk` while the planted foot is ahead of or under the hip | 30 degrees |
| `garment_ground` | loose painted fabric penetrates the floor in a ground clip | lowest occupied cloth/robe mesh vertex below the canvas ground line | 0.5 px |

`smear` is a conservative local-gradient heuristic, not semantic proof of blur.
Deliberate smooth skin or leather shading can produce the same statistics as a
blurred patch. `smear_tile_report` exposes the exact source-layer tile coordinates,
colour span and maximum adjacent-pixel step used by the existing gate. Inspect
these regions at original resolution alongside the layer's contours and detail
before attributing a failure to damaged artwork. Evidence does not waive a FAIL
or grant visual approval; all thresholds and the fully opaque tile denominator
remain unchanged. A known-limit expected-failure test records the smooth-shading
ambiguity rather than pretending the detector can distinguish intent.

`crouch` skips the part of stance with the foot behind the hip, because a knee bends 40 to 50 degrees
to push off in any human walk. Counting it reported a false crouch on a correct leg. It judges `walk`
only: `crouch_walk` bends the knee on purpose, and a running stance flexes about 35 degrees.

`fold` is measured by area because the centre of a sharp bend crushes a few cells to nothing. Such a
cell shows no art whichever way it winds, while counting cells failed legs that looked right.

Framing a painted puppet also measures the occupied source mesh cells at 120 Hz,
including rigid rear appendages. For an intentionally limited clip trial, `generate.py` and
`contact_sheet.py` accept `--fit-selected-clips`: they keep the full registry for simulation and
handover dependencies but compute one common viewport from only the requested clips and their
cloth. Unexported actions have no framing guarantee. The default remains all available clips;
no source pixels, joints or crop thresholds change. The trace records `framing_scope` when selected.

The bounds include each layer's real width and any reach below the pivot; skeleton endpoints and
cloth centrelines alone do not bound a wide robe or hair fan. Mesh relaxation
averages neighbouring vertices, so the raw mapped bounds conservatively contain
the relaxed art. Frame size and QA thresholds are not widened to hide cropping.

Tight-cropped layers are filtered before warping. The mip records separate x/y
texture-coordinate scales after resizing: rounded width and height rarely have
exactly the same ratio. Sharing only the width ratio can shorten a narrow weapon
or stretch a wide layer even under rigid motion. Non-square strip regressions
check the visible extent on both axes, including one-pixel-wide source artwork.

In clips tagged `ground`, puppet cloth chains participate in floor contact even
when the same chain is free in air clips. The painted width of loose cloth and
the whole robe also has a continuous soft floor: it gathers in a thin layer
above the ground rather than moving the body upward or cutting source pixels.
Body, head, weapon and limb layers are not projected by this garment rule.
It is a two-dimensional contact approximation, not cloth volume simulation;
inspect the gathered hem during rolls. Air clips retain their free geometry.

A set that passes has passed these measures only. The art may still be wrong, so look before
reporting: open every frame of `review/` at full size and check each row of the table at the top of
this file by eye. Report it as needing human review in motion.

Arm binding is checked separately: the far arm must precede the torso in the layer stack and
each arm must follow its own joint chain. Preserve both measured shoulder seats; do not force
them to coincide. The complete idle carry comes from both arms and the weapon in the reference.
`arm_spacing` flags a formerly readable reference pose being compressed in idle; it does not
establish that every overlap looks natural. Review mandatory `shoulders_*.png` and `arms_*.png`
sheets as well as elbow/knee sheets before recording a verdict. Passing numerical limits does
not establish that an arm connection looks right. Rebind older rigs to get the complete carry.

## How the clips fit a character

The clip keys are written for one default body. These general rules fit them, and none is set per
character:

| Rule | Where | What goes wrong without it |
|---|---|---|
| Trailing chains stay in a fan behind the body, from straight down to level, measured from the art's own slant | `swing` from `bind`, `cloth.py` | cloth wraps round a flip; hair falls across the face |
| A chain on the floor lies where it fell | `cloth.py` | a turning body drags it through the ground |
| A chain heading for the next clip's shape turns each segment the short way | `cloth.py` `turn_to` | fading points crumples a chain still mid-flip |
| A sharper corner gets a longer arc | `puppet.py` `corner_run` | a wide limb pinches to a point at the knee |
| Cells still crossed are relaxed locally | `puppet.py` `untangle` | mirrored art at the tight side of a bend |
| A boot stays within 62 degrees of the shin's line as drawn | `puppet.py` `foot_turn` | boot and shin cross |
| Hanging panels stay within 40 degrees of the body's line | `puppet.py` `joint_at` | a crouch lifts the torso's panels into a fold |
| A spinning foot turns the short way round | `Body.foot_wrap` | the boot points backwards partway through a roll |
| Floor contact and spins use the character's own body | `build_clips(body=...)` | a big head goes through the floor |
| An attack key that covers the face takes the smallest turn of arm and weapon that clears it | `motions.py` `clear_face` | a shaft parked across a short-armed figure's face |
| A stance sinks until the knee stops short of its soft end | `motions.py` `STANCE_REACH` | planted feet creep as the hip moves |
| Idle keeps both reference arms and the weapon, with elbow-safe breathing; shared stance keys use that complete pose | `gait.idle`, `motions.py` | adapting only the free arm collapses it against the default weapon arm |
| Each arm keeps its measured attachment and own joint chain; the far arm remains behind the torso | `layer_parts.py`, `puppet_check.py` | coalesced attachments and upper-arm paths make a forearm look like a branch |
| A measured fist grip follows its forearm in rendering and weapon collision checks | `Body.weapon_grip_along/across`, `rig.py`, `art.py`, `puppet.py` | a fixed wrist offset moves an otherwise correctly bound sword out of the fist |
| Measured sole contacts drive ankle roll, ground checks and foot traces together | `Body.foot_n_heel/ball`, `foot_f_heel/ball`, `rig.py`, shared `constraints.py` | default-size feet report hovering even when larger painted boots touch the floor |
| Walking hips vault over the two measured rolling-foot targets with a smooth support change | `motions.py` `measured_walk_height`, measured soles only | a fixed default hip bob forces large boots into crouching or overstretches a planted leg |

`weapon_grip_along` and `weapon_grip_across` express the wrist-to-grip vector in the forearm's
local basis, divided by forearm length (perpendicular in rig y-up coordinates). Their defaults
are 0.14 and 0, preserving existing characters. An adapter with known grip art derives them
from its source joints; rendering and ground collision both use the solved `weapon_grip`.
This does not establish that the weapon remains visually unobscured throughout a clip.
Optional `foot_n_heel`, `foot_n_ball`, `foot_f_heel`, `foot_f_ball` are measured flat-sole
offsets from their ankle in rig units (y up). Omitted values retain the original foot
geometry. This aligns contact landmarks, not a claim that every resampled boot pixel
is continuously supported; painted soles and planted frames still require review.

A new fault belongs in this table, as a rule, not in one character's data.

## Stage gate

Build `walk` first and show the user the running preview. Build the full set only after they approve
the walk. The walk's carried pose, stride and hip height come from the reference, so a fault in them
shows here first and repeats in every clip after it.

## Verified so far

| Item | State |
|---|---|
| Walk on two characters of different build, same commands | generated, QA 0 FAIL, approved by the user |
| All 27 clips on the same two characters, same commands | generated with `hips`, QA 0 FAIL 0 WARN, the waist inspected in three frames of every clip, user review pending |
| Attacks and casts look right for a given weapon | needs human review: the same keys serve sword and spear, so a spear swings like a sword |
| Pixel presets | not tried |
| Godot, Phaser, PixiJS, Unity, Cocos import | not tried: the sprite exports are the usual ones, but no puppet set has been imported into an engine |
| Reference pose other than the contract's | refused or untested, not supported |
