# AI-generated art

Use this when the user wants their own look and will make the character with an image generator
(GPT image, Midjourney, Stable Diffusion, Jimeng, Kling and the like). The image model draws the
character once; `scripts/cut_parts.py` cuts it into parts, and the rig, motion library, QA and
exports work unchanged. You cannot generate images yourself: write the prompt, the user runs it and
puts the picture in the working folder.

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
| `hip_n` `kn_n` `an_n` | near hip joint, knee, ankle |
| `heel_n` `toe_n` | where the near foot's heel and ball touch the ground |
| `*_f` | the same on the far side; leave out what you can't see |
| `weapon_grip` | the middle of the fist on the handle, on the weapon's centre line |
| `weapon_tip` | the far end of the weapon on that same line |

Required: `head_top head_base neck waist hip sh_n el_n wr_n hip_n kn_n an_n heel_n toe_n`. Without
`weapon_grip` and `weapon_tip` the character is unarmed.

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
- The motions are built for these proportions. A very different body (a giant head, very long arms)
  still animates but needs a careful look in the visual review.
- Side view only, one facing; mirror with the engine's flip.
