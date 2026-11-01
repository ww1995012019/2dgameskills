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
For a strict side-view puppet, both shoulder hinges share a projected seat, the far arm stays
behind the torso, and the near arm stays in front. Check that the far sleeve is occluded at the
shoulder and reappears naturally below it as the arm moves. The verdict must cover these sheets.

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
  gun, a pose that doesn't read. Fix it before delivering.
- **polish:** a matter of taste or a small flaw. Record it, and fix it if it's cheap.

Fix the cause, not the frame. A roll that hovers needs a contact rule, not a nudged key. When a
visual issue slipped past QA and can be measured, consider adding a check for it.

## Record the verdict

Write a JSON file covering every sheet:

```json
{
  "reviewer": "claude",
  "sheets": {
    "sheet_00.png": {"verdict": "pass", "issues": []},
    "sheet_01.png": {"verdict": "fail", "issues": [
      {"clip": "roll", "frame": 8, "severity": "blocker", "what": "body hovers above the ground", "resolved": false}
    ]}
  }
}
```

```bash
python scripts/visual_review.py out/c --record verdict.json
```

This refuses a verdict that skips a sheet, and exits 1 while any blocker is unresolved. After fixing,
regenerate, re-run QA, rebuild the sheets and review the changed clips again. Set `resolved` only after
you have seen the fixed frames.

Stop after three rounds and tell the user what's still open, rather than iterating on taste.

Report honestly: name what you reviewed and what you left out. The verdict is one reviewer's judgment of
still frames, so it can't assess how motion feels at speed. For that, the user should play `preview.html`.
