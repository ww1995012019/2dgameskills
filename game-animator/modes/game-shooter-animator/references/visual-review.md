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
silhouettes. The orange line is the ground. A red border means QA flagged that frame.

## Checklist

Look at each clip for these, in this order. Name the clip and frame when something is wrong.

**Contact**
- Feet on the orange line in ground clips, neither above nor below it
- Nothing hovering: a roll or lying body rests on the line
- Hands on the weapon, with no gap at the grip
- Weapon stops at the ground

**Anatomy**
- Limbs bend the right way, with no reversed knee or elbow
- Joints not folded past what a body can do
- Neck not twisted, head attached to the shoulders
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
