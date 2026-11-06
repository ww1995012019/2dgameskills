# Repair loop: show the user the motion before full verification

When the user rejects something they saw (a waist that opens, a limp, a stiff neck), the slow part
used to be everything that happened before they saw the fix: full unit tests, all regression sets,
site publishing. Several rounds in a row were then rejected on sight. Order the work so the user's
eyes come first and the expensive proof comes once, after they approve.

## Loop

1. **Record the rejection.** Mark the earlier visual pass as revoked with the user's words and the
   affected clip/frames. Keep the failed history; do not reset attempt budgets.
2. **Fix the general cause** in the shared rules, never in one character's data
   (see `layered-art.md`, "How the clips fit a character").
3. **Render only what changed.** Regenerate just the affected clips for the characters involved
   (`generate.py --clips run ...` or `character_workflow.py preview --job ...`), run that build's
   `qa_motion.py`, and the unit tests for the modules you touched
   (`python3 -m unittest test_<module>` from `dev/tests`). Minutes, not hours.
4. **Make the comparison.**

   ```bash
   python scripts/compare_clips.py NEW_BUILD --before REJECTED_BUILD --clips run --out NEW_BUILD/compare
   ```

   Look at `<clip>.gif` and `<clip>_phases.png` yourself first, plus the close-up review sheets for
   the reported body part. Same scale, one fixed ground line, a dashed head line; old frames are
   picked by cycle phase. `compare.json` gives head-top range and the largest frame-to-frame step:
   measurements to mention, not a verdict.
5. **Send the GIFs to the user** with one line on what changed and what to watch. Do not publish a
   site version, update release notes or call it fixed yet. Wait for their verdict.
6. **Rejected again:** go back to step 1 with the new observation.
   **Approved:** only now run the full gate once: versioned visual review record and `--check`,
   the complete unit suite, all regression sets with `dev/baseline.py`, packaging, publishing the
   preview, and the commit/PR. A failure here goes back to step 2, and the user sees the result
   again if the visible motion changed.

## What this does not change

- Every existing numerical gate and visual-review requirement still applies before delivery; this
  only moves them after the user's look, so they run once instead of once per rejected attempt.
- A GIF the user liked is not a QA pass, and a QA pass is not the user's approval. Report both.
- Real-character fixtures in `dev/fixtures/characters/` lock approved frames. If a fix changes
  frames the user already approved for another character, show that character too.
