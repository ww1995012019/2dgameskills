# Character spec

A character is one JSON file. Any field left out takes the default from `scripts/sprite_anim/art.py`.

```json
{
  "name": "hero",
  "head": "hair",
  "weapon": "sword",
  "cloth": ["cape", "hair"],
  "armor": false,
  "gloves": true,
  "body": { "head_size": 1.0, "bulk": 1.0 },
  "style": { "speed": 1.0, "bounce": 1.0 },
  "colors": { "skin": "#f2c7a0", "tunic": "#3f7fb5" },
  "custom_clips": {}
}
```

## Fields

| Field | Values | Effect |
|---|---|---|
| `head` | `hair`, `hood`, `helmet`, `wizard` | Headwear. `hood` adds a tassel, `wizard` a hat with a simulated tip |
| `weapon` | `sword`, `axe`, `staff`, `spear`, `none` | Held in the near hand. Smear length follows the weapon |
| `cloth` | any of `cape`, `scarf`, `hair`, `plume`, `tassel` | Simulated chains. Each adds visible follow-through |
| `armor` | bool | Chest plate, shoulder and knee guards |
| `gloves` | bool | Hands use `glove` instead of `skin` |
| `body` | see below | Proportions |
| `style.speed` | 0.8 to 1.3 | Multiplies playback speed of all clips, so > 1 is snappier |
| `style.bounce` | 0.7 to 1.3 | Scales bob and squash |

`body` fields, in rig units where standing height is 100: `thigh`, `shin`, `ankle_h`, `hip_h`,
`pelvis_len`, `chest_len`, `neck_len`, `up_arm`, `lo_arm`, `head_size`, `bulk`. Keep
`hip_h` about 1.5 below `ankle_h + thigh + shin`, or the legs lock straight. If legs change, set
`hip_h` to match.

Colour keys: `skin hair tunic tunic2 pants boots belt metal accent cape glove eye ink`, plus `dust` and
`dust2` for the effect sheets. Shadow and highlight tones are derived with a hue shift, so pick a mid
tone for each. `ink` is the outline. A dark, slightly saturated ink looks better than pure black.

## Carried arms at rest

An optional `gait.idle` sets `arm_n` and/or `arm_f` as
`[upper_arm_rest, upper_arm_sway, elbow_rest, elbow_sway]` in degrees. For example,
`"gait": {"idle": {"arm_f": [-20, 1.8, 8, 2.6]}}` leaves the free arm behind the body.
Optional `wep` and nonnegative `wep_sway` set the carried weapon angle and its sway. The rest
angles also update shared stance keys so attacks and casts recover to the same idle.
Breathing sway is scaled by `style.bounce` and bounded to keep the authored elbow inside its limits.
The layered-art binder writes the complete profile from both reference arms and the weapon.
Adapting only one arm can compress the two arm paths together. Omitting the profile retains the
existing default poses. Locomotion profiles such as `gait.walk` remain separate.

## Optional upright walk profile

`"gait": {"walk": {"profile": "natural_walk_v1"}}` opts into a body-derived
walking loop with sole-centered stride, later toe-off, bounded stance-leg reach,
and balanced arm swing based on the idle carry. Existing characters keep their
legacy walk unless they opt in. Replace a legacy walk override object when testing
this profile: explicit arm, stride and bob overrides still take precedence and can
undo its fit. Unknown profile names are rejected.

At default speed its period is 5/6 second (20 frames at 24 fps or 25 at 30 fps).
Review the actual silhouette and motion, not just contact/seam scores. This profile
only changes the walking loop and does not validate unrelated actions. The normal
playable preview now uses the phase-preserving walking controller for both the
legacy and natural profiles: releasing movement brakes into a two-foot support
hold, and moving again resumes the same phase. This hold is distinct from the
authored idle animation shown in the gallery. Direct low-level SpritePlayer
switches still cut between clips; use GroundedWalkController for this policy.

## Custom clips

### Skateboard glide for procedural art

Add the following to an empty-handed procedural character spec. This is an opt-in extra loop and
does not change the built-in idle, walk or run clips:

```json
"weapon": "none",
"gait": { "skateboard": {
  "profile": "glide_v1",
  "width": 64,
  "colors": { "deck": "#14378f", "grip": "#252b37", "accent": "#ffd000",
              "wheels": "#ffd41a", "metal": "#9ba7b7" }
}}
```

Width is 52–84 rig units; colors are optional `#RRGGBB`. Generate with
`python scripts/generate.py --character rider.json --clips idle,skateboard --fit-selected-clips --out out/rider`
and run `python scripts/qa_motion.py out/rider`. The `board` check measures both heel/ball proxies
against the deck on every exported frame, and the visual review must still check the actual shoes.
Select the action in the preview and press Q. The loop is stationary; the game controls world
movement. This profile has no mounting/dismounting transition and does not accept puppet/cut-out
characters or held weapons.

### Packaging an independently drawn frame sheet

If the complete character and prop have already been drawn in every frame, import an evenly spaced
grid of square transparent cells into a **new** output directory:

```bash
python scripts/import_frames.py --sheet artwork.png --columns 4 --rows 2 --count 8 \
  --fps 8 --clip skateboard --name rider --pivot 222,415 --pad 2 --out out/rider-frames
```

The pivot uses source-cell pixels; padding adds transparent pixels without altering the source.
Use an actual pivot appropriate for the source. The importer rejects empty, visibly cropped or
nontransparent frames and won't overwrite an existing output directory. It emits the standard
`preview.html`, frames, sheets, atlas and engine files, but no `rig_trace.json`: QA correctly
reports missing rig evidence, and import does not establish anatomy or foot contact. Inspect all
frames and playback. Do not use this to repackage material from an owned basic workflow or bypass
its review gates; the importer rejects sheets inside such a job.

### Other custom actions

For a character whose proportions make a built-in keyed action awkward, an optional
`clip_key_overrides` object can replace individual pose channels at existing zero-based key indices.
For example, `"clip_key_overrides": {"attack_3": {"1": {"arm_n_up": 120}}}` changes only that
channel at key 1. Other keys, timing, events, velocity and combo metadata remain unchanged. Indices
refer to the keys in `scripts/sprite_anim/motions.py`; inspect that clip before editing. Only
non-looping keyed clips are supported. Review the entire action and its combo transitions, and run
motion QA; corrections to a shared combo pose may need matching changes in both clips.

`assets/characters/goblin.json` has a working example. Add actions without touching the library. Times are in seconds, poses are sparse dicts layered on the
idle pose, and the first and last keys should stay close to idle so the clip joins the rest of the set.

```json
"custom_clips": {
  "wave": {
    "loop": false,
    "keys": [
      [0.00, {}],
      [0.18, {"arm_f_up": 96, "arm_f_lo": 40, "head": -10}],
      [0.34, {"arm_f_up": 96, "arm_f_lo": 84, "head": -10}],
      [0.50, {"arm_f_up": 96, "arm_f_lo": 40, "head": -10}],
      [0.66, {"arm_f_up": 96, "arm_f_lo": 84, "head": -10}],
      [1.00, {}]
    ],
    "events": [[0.18, "wave_sfx"]],
    "tags": ["ground", "hold_feet"]
  }
}
```

Optional keys: `prev` and `next` (cloth hand-over, default `idle`), `period` (loop length), `tags`.
Keys must start at zero with strictly increasing finite times and recognized finite pose channels.
Duration must be positive. A loop's last pose must match its first when the last key is at its period;
setting a longer period reserves an automatic return to the starting pose. `prev` and `next` must
name an available built-in/custom clip or be null. Non-looping clips with a `next` can use `next_at`
between 0 and 1 to enter at a normalized time in that target (1 selects its last frame).
Invalid keys, timing and references fail before rendering rather than silently disappearing or
breaking the skeleton. Valid data still needs motion QA and visual review for pose continuity.
Add `ground` to `tags` for a clip on the floor, so clipping checks run on it. The rig's joint limits
apply automatically, so an extreme key may render less extreme than written: QA's `limits` reports it.

Use `--clips all` or include the custom name when generating a subset. Non-built-in names appear in
the preview's custom-action selector when `idle` is also exported; select one and press Q to play it. A one-shot returns to idle
when finished; Q stops a loop or switches to another selected custom clip. Existing names such as
`cast` can be overridden, and retain their normal preview controls. Events are exported as timing
metadata: the target game must implement their effects and transitions. The preview only visualizes
its built-in event types, so a new event name alone will not create an effect.

### Pose channels

Angles are in degrees. Limbs: 0 hangs straight down, positive swings forward (toward +x), 90 is
horizontal forward, 180 is straight up. Arm angles are relative to the chest, so a torso leaning 30
degrees rotates the arm back 30; compensate on the arm when the world angle matters.

The far arm is drawn behind the torso and head. Raised past about 120 it disappears behind the head,
so for a gesture meant to be seen, hold the upper arm near 90-100 and lift the hand with the elbow.
The near arm carries the weapon, so gestures normally go on the far arm.

| Channel | Meaning |
|---|---|
| `root_x`, `root_y` | Hip offset from rest. `root_y` -15 is a deep crouch |
| `root_rot` | Whole-body spin about the hip |
| `pelvis`, `spine`, `neck`, `head` | Lean, positive forward. `head` is usually the negative of the lean so the eyes stay level |
| `arm_n_up`, `arm_n_lo` | Near arm shoulder and elbow. Elbow only bends forward (positive) |
| `arm_f_up`, `arm_f_lo` | Far arm |
| `foot_n_x`, `foot_n_y`, `foot_n_p` | Near foot: offset from the hip's vertical line, lift, pitch (positive = toes up) |
| `foot_f_x`, `foot_f_y`, `foot_f_p` | Far foot. Idle stance is `foot_n_x` 8, `foot_f_x` -9 |
| `ik_body` | 0 feet stay in ground space, 1 feet travel with the body. Use 1 for flips and lying down |
| `wep` | Blade angle from the forearm. World blade angle = arm_up + arm_lo - chest_lean + wep |
| `squash` | Vertical scale about the ground; width takes the inverse |
| `eye` 0-1, `brow` 0-1, `mouth` 0-1 | Expression |
| `smear` 0-1 | Blade trail strength. Put it on the strike keys |
| `glow` | Orb at the far hand |

Legs are IK: animate feet, not knees. To plant a foot, keep its `foot_*_x` constant across keys
(that is what the `hold_feet` tag has QA verify) and move the body with `root_x`.

## Cut-out mode: the user's own art

To animate existing art, split it into PNG layers and map them in `parts`. The motion library, QA and
exports work unchanged; the procedural drawing is replaced. Cloth is not drawn in this mode, so paint
capes and hair into the parts and leave `cloth` empty.

From a single full-body picture, such as one made with an image generator, `scripts/cut_parts.py`
cuts the parts and writes this file for you: see `references/ai-art.md`. A worked example is
`assets/characters/cutout_demo/` (the hero's reference pose, cut).

```json
{
  "name": "my_char",
  "weapon": "sword",
  "cloth": [],
  "px_per_unit": 4.0,
  "parts": {
    "head":  {"image": "head.png",  "pivot": [55, 112]},
    "torso": {"image": "torso.png", "pivot": [44, 112]}
  }
}
```

Part names, drawn back to front: `arm_f_up arm_f_lo hand_f leg_f_up leg_f_lo foot_f leg_n_up leg_n_lo
foot_n pelvis torso head weapon arm_n_up arm_n_lo hand_n`. Supply all of them, except `weapon` with
`"weapon": "none"`: the rig draws nothing on a bone with no part, so QA fails a missing one.

Rules for the layers:

- Draw limbs hanging straight down, torso and head upright, the weapon pointing up, the foot flat
  and facing right. The rig rotates parts from this rest orientation.
- `pivot` is the pixel in that image that sits on the joint: the shoulder for an upper arm, the elbow
  for a forearm, the neck base for the head, the waist for the torso, and for the weapon the middle of
  the fist on its handle (the rig holds it just past the wrist, along the forearm).
- Optionally set `rest_angle` in degrees for a part drawn away from its standard orientation.
  It is clockwise in image coordinates (right and down are positive), measured from the
  standard orientation for that part. For example, an arm pointing right instead of down has
  `rest_angle: -90`. The renderer subtracts this angle from the rig angle. It defaults to 0.
- Let parts overlap generously at joints so bending doesn't open a gap.
- On the `weapon` part, `length` is grip to tip in rig units. Framing, the ground clamp and clipping use
  it instead of the drawn weapon's reach, and QA checks the art really reaches that far. `cut_parts.py`
  writes it.
- Optionally set `scale` on a part to draw it larger or smaller than `px_per_unit` says, such as a
  swapped-in weapon drawn at another size. It defaults to 1.
- `px_per_unit` is source pixels per rig unit. Standing height is 100 units, so art 400 px tall is 4.0.
- Set `body` lengths (`thigh`, `shin`, `up_arm`, `lo_arm`, `pelvis_len`, `chest_len`, `neck_len`) to the
  art's own, in rig units, or parts hang off their neighbours. `cut_parts.py` measures them.
- `layers` (optional): `{"behind": [...], "front": [...]}` draws those parts behind or in front of
  everything else, for art layered differently from the default order, such as a weapon held in the
  far hand. `cut_parts.py` writes it from the joints file's `_behind` / `_front`.
- Paths are relative to the spec file.
- Limit: rotated bitmaps keep the source's baked shading and resolution. Supply art at or above output size.

For a `gait.walk.profile` of `natural_walk_v1`, the optional boolean
`settle_relax_free_arm` relaxes only the far/empty arm toward its neutral carriage
during grounded settling. It defaults to false and rejects non-boolean values or
other gait profiles. See `walk-transitions.md`; this does not authorize a visual
pass or alter foot contacts, the weapon hand, or the walk cycle itself.
