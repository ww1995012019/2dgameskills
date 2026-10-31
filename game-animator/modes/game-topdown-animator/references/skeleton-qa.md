# Skeleton integrity QA

Joint numbers can be perfect while the art is broken. The rig still solves a forearm whose image has
lost its middle, so length and limit checks stay green. These checks measure pixels instead. Code:
`scripts/sprite_anim/integrity.py`, and `part_check.py` for cut-out parts.

| Check | Where | Fails when | Usual cause | Fix |
|---|---|---|---|---|
| `float` | every clip, every frame | Art is cut off from the body by more than about one rig unit | A scrap of another part inside a part image; a broken part | Find the part in `bind_preview.png`, fix the marks and cut again |
| `bones` | every clip, every frame | A bone has a stretch with nothing drawn along it | A part missing or too short; a drawing bug | Same, or fix the drawing code |
| `parts` | cut-out and PNG creature sets, once per set | A part is missing, empty or not found, its bone has a hole, it has loose pieces, or its pivot isn't on the art. On cut-outs also: art outside the source picture's silhouette, or the head's pixels in the torso's image | Bad cut or hand-edited part | The message names the part |
| `bind` | cut-out sets, once per set | WARN: `bind_report.json` has warnings. FAIL: it recorded joints opening | Marks off the joint centres; the cut's warnings ignored | Fix the marks and cut again |

## Why `parts` is needed as well

A rendered frame can't see a limb lying over the body. On the case that prompted these checks, an
upper arm with 31% of its bone missing measured 100% coverage in every frame, because the torso
filled the hole. Only its image, checked alone in rest orientation, shows the break. A hole can also
be hidden in a clip that is never reviewed, so `parts` fails the whole set rather than one frame.

## Checking parts against the picture

A whole, connected part can still be wrong. On one real picture a knee's round cap was filled past the
silhouette with stretched outline, and half the face was copied into the torso. Nothing was loose, so
every other check passed. `cut_parts.py` now records where each part came from (`from` in
`character.json`) and keeps `source.png`, so each part can be turned back onto the picture. A rig cut
before this has no record and is not checked: cut it again.

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
| Art outside the picture | over 3% of the part, past 2 px of edge slack | The stretched cap measured 4-38%; a clean cut has none above the slack |
| Head in the torso | over 8% of the head | The face-copying cap measured 30-31%; a neck join stays well under it |
| Limb past its joint | over 2.5 rig units along the bone | A nub seen at a bent knee measured 3.7. `cut_parts.py` leaves the part behind a joint at most 2 units of cap, and marks a few pixels off add a little |

A blade may be split by the fist: the weapon's pieces are joined across 6 rig units around the grip.

## What is deliberately not checked

- **Sword smears:** smear frames skip `float`, as a smear can leave the blade behind. `bones` still runs.
- **Shooter fire and action clips:** report `float` as `n/a`. Casings and dropped magazines fly clear
  of the body on purpose, and the check can't tell them from a broken scrap. `bones` still runs.
- **Shooter layered clips:** `upper` clips are held to the arm and chest bones, `lower` clips to the leg
  and hip bones, because each draws half a body.
- **Rigs cut before a limb ended at its joint:** they fail `parts` with a nub on most limbs. That is a real fault in those rigs: cut them again.
- **Older sets:** a trace without `skeleton` reports `float` and `bones` as `n/a`. That is not a pass.
  Generate the set again. Cut-out rigs from before this check need cutting again too.

## What these checks can't see

- Foreign art attached to the right part, such as hair inside a forearm image: it is connected, so
  nothing is loose. Look at `bind_preview.png` and `motion_check.png`.
- A limb that is whole but the wrong shape or in the wrong place on the art.
- Hidden areas filled from a part's colours: they lie inside the silhouette, so they pass the picture
  check, and can show as streaks when the part in front moves away. `bind` reports the pixel count.
- Whether a face reads, or a body looks right. No check here looks at that: use the visual review.
- Hand and foot images have no single bone to walk, so only emptiness, pivot and loose pieces apply.
- A weapon's length is checked only when `parts.weapon.length` exists. `cut_parts.py` writes it.
