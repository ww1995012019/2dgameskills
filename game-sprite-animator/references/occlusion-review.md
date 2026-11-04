# Output-bound humanoid occlusion review

New known-joint rigs with `puppet.attachment_checks: true` receive two separate checks:
physical attachment continuity and screen-space arm readability. Generation measures every
exported frame timestamp at its actual supersampling and render order, before motion blur/FX. `occlusion_review.json` records
review candidates, frame numbers, arm names, measured visibility, frontmost occluders and SHA256
hashes of every checked animation sheet plus `animations.json`.

A candidate is **review_required/WARN, not a physical FAIL**. Intentional depth overlap can be
correct. The hand and forearm must first be connected in the isolated arm layer. Selection then
requires all of:

- At least 20% of the wrist-distal hand region remains visible.
- Its visible alpha mass is at least 4 output pixels, and its isolated mass at least 8 pixels.
- At most 25% of the middle forearm region remains visible.
- At least 65% of that forearm's alpha mass is behind nearly opaque foreground layers
  (combined transmittance at most 5%).

These conservative review-selection thresholds exclude tiny antialiasing slivers, entirely hidden
hands and merely translucent coverings. They are not anatomical or aesthetic pass/fail limits.
A thin visible bridge can still produce a candidate. Visibility connectivity at alpha 0.1, 0.25 and
0.5 and per-layer occlusion attribution are recorded for inspection, not used to auto-reject poses.
A known legitimate candidate is a back hand naturally emerging at the torso edge while its
middle forearm remains behind the torso. In reviewed male stress frames `rig_probe` 3 and 21,
the severe occlusion measurements did not establish a floating fist: the visible distal skin path
was consistent with normal rear-arm depth. Keep such cases for explicit acceptance with frame-specific
rationale rather than changing motion/depth automatically or tuning away the candidate.

Attribution identifies frontmost covering pixels; removing a duplicate front torso may leave an
underlying torso covering the same arm.

The supported measurement is an ordinary humanoid wrist-distal region (within 65% of forearm
length), and the middle forearm between 30% and 65% proximal to the wrist. It does not semantically
recognize arbitrary sleeves, mechanical appendages or species. Those require separately verified
source-tagged regions. Other occlusion problems can be missed. `no_candidates` only means this
measurement found none; it is not visual approval.

From the skill directory:

```bash
python scripts/review_occlusion.py out/character
python scripts/review_occlusion.py out/character --check
python scripts/review_occlusion.py out/character --record reviewed_decisions.json
```

Inspect every listed frame in its named sheet. Copy `occlusion_decisions_template.json` to a review
file, supply a reviewer name and, for every candidate, `accepted` or `rejected` plus a concrete
visual rationale. Preserve its current report/output hash and each candidate's asset SHA256.
Accepted means this exact overlap is visually acceptable, not that an automated rule cleared it.
Rejected candidates remain pending for correction. Fixes must be regenerated and reviewed anew.

Missing decisions, rejected candidates, incomplete/duplicate decisions, stale sheets, changed
reports and mismatched hashes fail `--check`. Generation never creates acceptance decisions and
invalidates old acceptance when reusing an output directory. Generic visual acceptance must also
pass this gate. Physical motion/attachment QA remains independent.
