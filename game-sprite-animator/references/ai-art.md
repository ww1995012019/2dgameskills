# AI-generated art

Use this when the user wants their own look and will make the character with an image generator
(GPT image, Midjourney, Stable Diffusion, Jimeng, Kling and the like). The image model draws the
character once; `scripts/cut_parts.py` cuts it into parts, and the rig, motion library, QA and
exports work unchanged. Use an available image-generation tool when appropriate; otherwise provide
the prompt for the user to generate the picture. Save or place the resulting image in the working folder.

## 1. The reference pose

```bash
python scripts/cut_parts.py template --out tpl/
```

`tpl/template.png` shows the pose to ask for: side view facing right, near arm forward, far arm back,
a small stride, weapon held forward. Every limb is clear of the body, which is what makes a clean cut.
Show it to the user. `tpl/joints.json` is the joint list to fill in for the new picture, and
`tpl/template_joints.png` shows where each joint sits.

Prompt to adapt (keep the pose and framing lines, change the character and style):

```
Full-body 2D game character, [who: e.g. a young knight in silver armour with a red cape painted
close to the body], [style: e.g. hand-painted cartoon, thick dark outlines, soft cel shading].
Strict side view facing right. Standing, near arm reaching forward and slightly bent, far arm
back, legs apart in a small walking stride, both feet flat on the ground. Holding a [sword] in the
near hand, pointing forward and up. Whole body in frame with margin on every side, nothing
cropped. Even flat lighting, no cast shadow, no ground, no text. [Transparent background /
plain light grey background].
```

Tool notes:
- If the tool takes a pose or reference image (image-to-image, ControlNet OpenPose, "reference"),
  give it `template.png`. That fixes the pose far better than words.
- Ask for a transparent background where the tool supports it (GPT image does). Otherwise ask for a
  plain, flat background in a colour the character doesn't use; `cut_parts.py` removes it.
- The character should be at least as tall in pixels as the output frame (256 for `hd`, 512 for
  `hd512`). Larger is fine.
- Keep capes, long hair and scarves close to the body or leave them out: cut-out mode does not
  simulate cloth, and anything loose is cut into whichever part it overlaps.
- Ask for a neutral, open-eyed face. The head is one picture, so the face never changes expression.

## 2. Mark the joints

Copy `tpl/joints.json` and move every point onto the new picture, in its pixels (origin top left).
Look at the picture to do it, then check your marks on a drawn overlay and correct them before
cutting; marks within about 2% of the character's height are fine, past that joints start to open.

| Joint | Where |
|---|---|
| `head_top` | top of the skull (not the hair tip or hat) |
| `head_base` | where the head meets the neck |
| `neck` | base of the neck, on the shoulders' line |
| `waist` | narrowest point of the trunk |
| `hip` | centre of the hips |
| `sh_n` `el_n` `wr_n` | near shoulder, elbow, wrist: the centre of each joint, not its outline |
| `hand_n` | tip of the near hand (optional) |
| `hip_n` `kn_n` `an_n` | near hip joint, knee, ankle. The rig plants the sole 5 units under the ankle and the heel 4.5 behind it, so put `an_n` there, not at the boot's outline |
| `heel_n` `toe_n` | where the near foot's heel and ball (not the toe tip) touch the ground; read the sole's edge off the alpha if unsure |
| `*_f` | the same on the far side; leave out what you can't see |
| `weapon_grip` | the middle of the fist on the handle, on the weapon's centre line |
| `weapon_tip` | the far end of the weapon on that same line |

Required: `head_top head_base neck waist hip sh_n el_n wr_n hip_n kn_n an_n heel_n toe_n`. Without
`weapon_grip` and `weapon_tip` the character is unarmed.

The rig's near arm holds the weapon. If the picture has it in the far hand (common in side views:
the arm with the big shoulder plate is nearer the camera), mark the weapon arm as `*_n` anyway and
the other arm as `*_f`, and say how the picture is layered so both the cut and the animation follow
it:

```json
"_behind": ["arm_n_up"],
"_front": ["arm_f_up", "arm_f_lo", "hand_f"],
"_radius": {"pelvis": 11.5}
```

- `_behind` / `_front`: parts that sit behind / in front of the body in this picture. The cut gives
  overlapping pixels to the part really in front, and `character.json` gets a `layers` entry so the
  animation draws them the same way.
- `_radius`: a part's half-width in rig units where the art is much bulkier or slimmer than the
  defaults (an armoured skirt, a thin staff). Raise it when a wide part's edges end up on its
  neighbour in `bind_preview.png` (a skirt riding on the thigh).
- Mark the hidden shoulder where it would be: about level with the other one, so both upper arms
  come out the same length.

## 3. Cut and check

```bash
python scripts/cut_parts.py cut --image knight.png --joints knight_joints.json --base base.json --out knight/
```

`--base` carries over `name`, `weapon`, `style` and the rest from a spec you wrote; the cut adds
`parts`, `px_per_unit` and the measured `body`. Then look at two pictures:

- `bind_preview.png`: each part tinted, every joint marked. A tint spilling onto the wrong body part
  means a mark is off.
- `motion_check.png`: the character through the clips that bend it most. The command also reports
  any joint that opens while moving and exits 1; move that joint's mark onto the joint centre and cut
  again.

Warnings in the output and in `bind_report.json`:

| Warning | Meaning | Do |
|---|---|---|
| `only N% visible, rebuilt from …` | a far limb hidden behind the body; it was copied from the near one and darkened, as the procedural art does | usually fine; for better art, draw that part and replace `parts/<name>.png` |
| `hidden pixels filled from its own colours` | something in front covered part of it (an arm across the chest) and the gap was painted from its own colours | look at that area when it swings open in `motion_check.png` |
| `far side is N% of the near side` | near and far limb lengths disagree | one of the two sets of marks is wrong |
| `joint … is not on the character` | the mark is on the background | move it |
| `foot is N units` | heel and toe marks are far off | re-mark them on the sole |
| `an_n is N units above the sole` | the ankle mark is too low or too high for the rig's foot | move it as the message says, or the foot sinks or floats |
| `gap: clip: joint N%` | that joint shows through while moving | re-mark it on the joint centre |

## 4. Generate as usual

```bash
python scripts/generate.py --character knight/character.json --preset hd --out out/knight
python scripts/qa_motion.py out/knight
python scripts/visual_review.py out/knight
```

Then do the visual review as for any set (`references/visual-review.md`).

## Limits to tell the user

- The face never changes: no blinking or expressions. `idle_look` therefore holds a few identical
  frames, which QA reports as a hold WARN.
- Capes, hair and scarves don't move. Paint them close to the body.
- Light and shadow are painted into the parts and turn with them, so a part lit from the top left
  is lit from below when it swings over.
- The motions are built for these proportions. A very different body still animates but needs a
  careful look. A big head on low shoulders (heavy armour, chibi styles) is the usual case: overhead
  poses lift the fist only to face height, and QA's `clip` check reports the weapon over the face in
  `attack_3`'s wind-up.
- Detailed art shrinks badly to the pixel presets (64 px): for a pixel-art game, ask the image model
  for pixel art at a low resolution instead of downscaling a painted picture.
- Side view only, one facing; mirror with the engine's flip.
