# Layered puppets: the production route for AI art

Use this route for every AI-generated character that will ship. It takes one reference picture and
turns it into complete, separate layers that bend along the skeleton. Nothing is marked by hand and
nothing is set per character. A picture either meets the contract or is refused with what to remake.

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

**Reference picture.** All of these are required, and `plan` checks what it can measure:

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
| `hair_back` | long hair behind the head and back | no |
| `cloth_back` | robe tail, sashes, cape | no |
| `arm_far` | rear arm: hand further left, with sleeve | yes |
| `leg_far` | rear leg: foot further left | yes |
| `leg_near` | front leg: foot further right | yes |
| `hips` | solid under-layer from waist to crotch, mostly hidden by the torso | yes |
| `torso` | neck to hips, with what hangs in front of the thighs | yes |
| `head` | face and hair on the skull | yes |
| `weapon` | the whole weapon | no |
| `arm_near` | front arm: hand further right, with sleeve | yes |

`hips` exists because the rest can't close the body. An image model stops the legs below the belt and
splits the robe into panels, so background shows through the figure below the belt, in a pose the
outline gives no sign of. It holds only hidden art, so it is judged by what it fills, not by matching
the reference, and it is required even for a character whose torso looks closed. `bind` cuts it to the
middle of the body and fades its lower end, so it never shows past the robe as a stiff block.

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
python scripts/layer_parts.py bind --image hero.png --layers hero/layers --name Hero --out hero/rig
python scripts/generate.py --character hero/rig/character.json --preset hd512 --clips walk --no-fx --out hero/build
python scripts/qa_motion.py hero/build
```

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

Never bypass a refusal by editing `bind`'s limits or the layer's pixels.

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

`crouch` skips the part of stance with the foot behind the hip, because a knee bends 40 to 50 degrees
to push off in any human walk. Counting it reported a false crouch on a correct leg. It judges `walk`
only: `crouch_walk` bends the knee on purpose, and a running stance flexes about 35 degrees.

`fold` is measured by area because the centre of a sharp bend crushes a few cells to nothing. Such a
cell shows no art whichever way it winds, while counting cells failed legs that looked right.

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
