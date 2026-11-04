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

Check a QA flag the same way before acting on it. Open the frame enlarged and confirm the problem is
there: a flag is a measurement, and a measurement can be wrong.

The review narrows the risk, it doesn't remove it. Say which sheets you read, and that the set still
needs a person to watch it play before it counts as done.

## Checklist

Look at each clip for these, in this order. Name the clip and frame when something is wrong.

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
  are always blockers; never downgrade them to polish. Fix it before delivering.
- **polish:** a matter of taste or a small flaw. Record it, and fix it if it's cheap.

Fix the cause, not the frame. A roll that hovers needs a contact rule, not a nudged key. When a
visual issue slipped past QA and can be measured, consider adding a check for it.

## Record the verdict

Start from `review/verdict_template.json`, which is pending and cannot pass as generated.
Write a JSON file covering exactly every sheet. Copy `review_id` from `review/index.json`.
It hashes the current frames, sheets, animation metadata, rig trace, QA report and
delivery atlas images/JSON, including declared custom page filenames. A replaced,
missing or unreadable atlas invalidates the pass; declared pages cannot point
outside the export folder. Image recompression alone does not change decoded-pixel
hashes. Changes invalidate
the verdict; rebuild sheets and review again. Rebuilding or a rejected recording removes the old
current `visual_report.json`; archived reviews remain in `review/history/`.

Each sheet requires `verdict`, `checks` and `issues`. Every check requires `status` and concrete
`evidence` naming the observed poses/frames. Required checks are `complete_limbs`,
`continuous_garments`, `no_ghosting`, `expected_weapons`, `anatomy`, `readable_motion`.
Use `pass` or `fail`; only garments and weapons may be `not_applicable`, with a reason.
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

Categories are `missing_limb`, `broken_garment`, `ghosting`, `extra_weapon`, `anatomy`,
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

```bash
python scripts/visual_review.py out/c --record verdict.json
python scripts/visual_review.py out/c --check  # mandatory before delivery; stale passes fail
```

Legacy unversioned verdicts must be reviewed again; do not copy an old pass into the new schema.

Stop after three rounds and tell the user what's still open, rather than iterating on taste.

Report honestly: name what you reviewed and what you left out. The verdict is one reviewer's judgment of
still frames, so it can't assess how motion feels at speed. For that, the user should play `preview.html`.
