# Female free-arm readability experiment

This continuation reconstructs the recovered female eight-part atlas without new
art, landmark edits, painted fill, depth-order changes or joint-length changes.
It is not female identity acceptance or proof of arbitrary-image rigging. The
fixed-ratio atlas adapter still has the proportions/garment limitations described
in `visible-body-reference.md`. All new outputs are ignored development fixtures
under `out/recovered-fixtures-20261104/female/`.

## Reproduced failure

`assembly-baseline-v1/` and `rig-baseline-v1/` use the existing generic adapter and
known-joint binder. `preview-baseline-v1/` exports idle, walk and two settle banks.
The existing screen-space gate finds 11 candidates, including every frame of one
settle bank: roughly 38–42% of the far hand remains visible while middle-forearm
visibility is zero. Ordered review confirms the apparent detached-hand issue.
The male whole-idle-cycle reach transfer (`preview-carriage-v2/`) still yields 10
candidates here. Its successful male result does not generalize by itself.

## Reusable comparison method

`dev/free_arm_readability.py` enumerates seven bounded, dimensionless wrist reaches
from -0.45 to 0.45 arm lengths. It solves each candidate using the actual upper and
lower arm lengths, retains swing amplitude and source elbow by default, and enables
the existing reversible free-arm settle option. An explicit `--elbow relaxed` mode
uses the natural-walk profile's 20-degree elbow cap. It does not edit the original
spec, write joint overrides, repaint pixels, alter layer depth, or choose a winner.

The renderer uses one common fit for the alternatives. Reports keep walk frames
and final held poses separate and report actual hand/forearm fractions, hidden
regions and unchanged detached-hand review candidates. Zero candidates can mean
the arm is hidden, not good readability. Maximizing visibility can produce an
unnaturally extended arm. Human review of complete ordered frames remains required.
The helper only covers supported isolated-layer humanoid rigs and the measured
regions; it is not semantic arm recognition.

Example:

```sh
python dev/free_arm_readability.py \
  --character out/recovered-fixtures-20261104/female/rig-baseline-v1/character-natural.json \
  --out out/recovered-fixtures-20261104/female/carriage-source-comparison.json
```

Existing output paths are refused. Six unit tests cover normalized reach over two
proportions/two scales, scoped changes, source immutability, the relaxed elbow cap,
invalid profiles/regions and no automatic approval for a hidden limb.

## Versioned observations

- v3 (`preview-source-elbow-v3/`): normalized reach -0.45, source elbow. No detector
  candidates, but visually excessive rearward extension. Rejected as a preferred
  result despite numerically better visibility.
- v4 (`preview-source-elbow-v4/`): reach -0.30, source elbow. Both final holds expose
  connected forearm/hand regions (minimum paired fraction 73.5%). No detached-hand
  candidates across the actual 92 exported frames. Two sampled walk phases still
  hide either the hand or forearm almost entirely; zero flags is not all-frame
  visibility. All 20 walk and 14 settle frames were inspected in ordered sheets.
  The persistent floating-hand hold is improved, but source elbow posture looks
  quite bent during the backward swing. Idle still largely overlaps the far arm.
- v5 (`preview-relaxed-v5/`): an exploratory 8-degree elbow trial, reach -0.30, reads
  straighter but still produces two transient candidates. This is not the helper's
  relaxed preset, not a replacement default, and not promoted.

- v6 (`preview-relaxed-v6/`): the helper's 20-degree relaxed cap and reach -0.30.
  No candidates over 92 exported frames; final-hold paired visibility is at least
  87%. Ordered inspection of all 34 walk/settle frames shows a less kinked backward
  arm than v4 and a readable final forearm/hand. This is the preferred comparison
  for the next web review, not accepted artwork.

All candidates retain the original closed far fist, which differs from the identity's
relaxed hand. Source-smear QA still flags both arms and the near leg (three FAILs),
unchanged from baseline. Do not label v4 an accepted female animation or claim that
motion parameter changes repair defective source artwork.

## Web-only checkpoint

Following the user's requested platform priority, no Godot or other engine checks
were run in this continuation. For both v4 and the latest v6:

- All four clips pass numerical motion checks; overall QA is **3 FAIL, 0 WARN** due
  to the retained source-smear failures, not a clean pass.
- 92/92 reconstructed atlas frames match their source pixels.
- Both settle entry frames are pixel-identical to walk frames 1 and 11.
- `controller-proof-v6/proof.gif` and `trace.json` record an eight-second sequence
  from the actual exported JavaScript controller, including repeated/interrupted
  commands. This is not a browser recording or browser visual acceptance.
- Web demo schema/button/drawing-wiring test and four reversible settle tests pass.
- `preview-relaxed-v6/engine/web/grounded-walk.html` is the web demo entry.
- `review/all-locomotion-frames.png` contains every walk/settle frame in order.

Live browser verification remains blocked by the previously reported browser
socket permission failure; this task did not retry through another route. No
user approval, full-suite result, commit, push or publication is claimed.

## Source-smear evidence checkpoint

`dev/review_source_smear.py` now exports source hashes, half-open pixel bounds,
colour spans, maximum adjacent-pixel steps and marked source-layer images. It
uses the production detector directly, refuses to overwrite an evidence folder,
does not alter any artwork, and always leaves visual approval pending. The
production `smear_tiles` count interface and all thresholds are unchanged.

The eight-layer report is `smear-evidence-v2/report.json`. It reproduces all three
existing failures exactly: far arm 5/33, near arm 6/35, near leg 3/75. The far leg
has 1/83 candidate tiles and still passes the unchanged 3% gate. The other four
layers have zero candidates. These are source-art measurements, not failures
at a specific animation frame.

Inspection of the full-resolution marked source layers and v6 `joints_00.png`
finds that the arm candidates lie on smooth upper-arm/forearm skin shading; the
three near-leg candidates lie on boot leather. The near-arm tile at (24, 144)
has span 111 and maximum step 17 (15.32%), while the far-arm tile at (72, 312)
has span 94 and maximum step 9 (9.57%). Their neighboring contours, fingers,
fabric and boot seams retain detail. This makes intentional shaded material a
credible false-positive explanation, but does not establish that every source
region is sound or that the female animation is accepted. No repaint, sharpening,
threshold relaxation, automated waiver or visual pass has been applied.

The general limitation is now documented and tested: a deliberate smooth gradient
and blur can have identical local statistics. The known-limit test remains an
expected failure rather than making the detector pass it. The original blurred
patch fault-injection test still catches its defect.

Verification for this checkpoint:

- Exact old/new count parity on 105 recovered male/female source-layer PNGs.
- Seven source-evidence/smear tests: five passed and two explicitly documented
  expected failures (overblur and intentional smooth-shading ambiguity).
- Fifteen free-arm comparison, exported-JavaScript controller, mock-DOM web demo
  and reversible-settle tests passed. These are not live-browser validation.
- Fresh v6 QA: exit 1, unchanged **3 FAIL, 0 WARN**, four of 29 clips checked.
- Shared/unified synchronization, rebuilt package freshness and diff whitespace
  checks passed. No other engine, full regression baseline or publication run.
- Broader puppet, free-arm, web-controller/demo, settle and source-evidence batch:
  48 tests in 554.150 s, 46 passed and two documented expected failures, no
  unexpected failures or errors. This is a focused batch, not the full repository
  or 26-character regression suite.
