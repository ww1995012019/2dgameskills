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

## Custom clips

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
Add `ground` to `tags` for a clip on the floor, so clipping checks run on it. The rig's joint limits
apply automatically, so an extreme key may render less extreme than written: QA's `limits` reports it.

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
foot_n pelvis torso head weapon arm_n_up arm_n_lo hand_n`. Omit any you don't have.

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
- `px_per_unit` is source pixels per rig unit. Standing height is 100 units, so art 400 px tall is 4.0.
- Set `body` lengths (`thigh`, `shin`, `up_arm`, `lo_arm`, `pelvis_len`, `chest_len`, `neck_len`) to the
  art's own, in rig units, or parts hang off their neighbours. `cut_parts.py` measures them.
- `layers` (optional): `{"behind": [...], "front": [...]}` draws those parts behind or in front of
  everything else, for art layered differently from the default order, such as a weapon held in the
  far hand. `cut_parts.py` writes it from the joints file's `_behind` / `_front`.
- Paths are relative to the spec file.
- Limit: rotated bitmaps keep the source's baked shading and resolution. Supply art at or above output size.
