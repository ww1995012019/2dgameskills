# Skeleton integrity QA

Joint numbers can be perfect while the art is broken. The rig still solves a forearm whose image has
lost its middle, so length and limit checks stay green. These checks measure pixels instead. Code:
`scripts/sprite_anim/integrity.py`, and `part_check.py` for cut-out parts.

| Check | Where | Fails when | Usual cause | Fix |
|---|---|---|---|---|
| `float` | every clip, every frame | Art is cut off from the body by more than about one rig unit | A scrap of another part inside a part image; a broken part | Find the part in `bind_preview.png`, fix the marks and cut again |
| `bones` | every clip, every frame | A bone has a stretch with nothing drawn along it | A part missing or too short; a drawing bug | Same, or fix the drawing code |
| `parts` | cut-out and PNG creature sets, once per set | A part is missing, empty or not found, its bone has a hole, it has loose pieces, or its pivot isn't on the art | Bad cut or hand-edited part | The message names the part |

## Why `parts` is needed as well

A rendered frame can't see a limb lying over the body. On the case that prompted these checks, an
upper arm with 31% of its bone missing measured 100% coverage in every frame, because the torso
filled the hole. Only its image, checked alone in rest orientation, shows the break. A hole can also
be hidden in a clip that is never reviewed, so `parts` fails the whole set rather than one frame.

## Thresholds

Measured on five real cut-out rigs, the demo and the procedural sets. Broken limbs had 31-46% of the
bone empty and loose pieces of 4-49% of the part; whole parts had under 5% and none.

| Value | Setting | Why |
|---|---|---|
| Solid art | alpha above 96 | Glows, soft edges and contact shadows (alpha 65 in the top-down art) are not body |
| Floating piece | at least 0.5% of the body and 4 px | A visible scrap measured 0.8%. Specks of 0.1-0.2% are antialiasing |
| Bridged gap | about one rig unit | Two parts a hairline apart read as touching |
| Empty bone in a frame | over 20% of the bone and 3 rig units, with one unit of tolerance | The rig's line isn't the art's centre |
| Hole in a part's own bone | over 12% of the bone | Fits tighter than a frame: the strip searched is the part's own image |
| Loose piece in a part | at least 1% of the part's art | Whole parts have none above 0.5% |

A blade may be split by the fist: the weapon's pieces are joined across 6 rig units around the grip.

## What is deliberately not checked

- **Sword smears:** smear frames skip `float`, as a smear can leave the blade behind. `bones` still runs.
- **Shooter fire and action clips:** report `float` as `n/a`. Casings and dropped magazines fly clear
  of the body on purpose, and the check can't tell them from a broken scrap. `bones` still runs.
- **Shooter layered clips:** `upper` clips are held to the arm and chest bones, `lower` clips to the leg
  and hip bones, because each draws half a body.
- **Older sets:** a trace without `skeleton` reports `float` and `bones` as `n/a`. That is not a pass.
  Generate the set again. Cut-out rigs from before this check need cutting again too.

## What these checks can't see

- Foreign art attached to the right part, such as hair inside a forearm image: it is connected, so
  nothing is loose. Look at `bind_preview.png` and `motion_check.png`.
- A limb that is whole but the wrong shape or in the wrong place on the art.
- Hand and foot images have no single bone to walk, so only emptiness, pivot and loose pieces apply.
- A weapon's length is checked only when `parts.weapon.length` exists. `cut_parts.py` writes it.
