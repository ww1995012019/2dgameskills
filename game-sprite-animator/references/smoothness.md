# Smoothness: what stutter is and how to remove it

"卡顿" in sprite animation is rarely one thing. Find which of these it is before changing anything.

## QA checks

`qa_motion.py` prints PASS, WARN or FAIL per clip. It measures rendered frames, so it also works on
sprites from anywhere: `python scripts/qa_motion.py path/to/frames --loop`.

| Check | Measures | Usual cause | Fix |
|---|---|---|---|
| `hold` | Consecutive identical frames | Loop rendered with its end frame equal to its start, so one pose plays twice per cycle | Sample `[0, T)` with no endpoint. `render.frame_time` already does |
| `seam` | Last-to-first change vs a typical step | Loop not closed | Use integer cycle counts in every sine. Cloth loops are closed by `_close_loop` |
| `spike` | One step far bigger than both neighbours | A skipped in-between, keys too close, or a fast move with no bridge | Spread the keys over 2-3 frames, add `smear` |
| `slide` | Stance foot travel vs `speed_px_s`, and foot height during stance | Speed that doesn't match the stride, or a foot past leg reach | Derive speed from `L / (duty * T)`; shorten stride or lower hip |
| `jitter` | Movement of feet meant to be planted | Different `foot_*_x` between poses of a `hold_feet` clip | Share the stance values between those poses |
| transitions | Pose jump at a clip hand-over | Clips that don't share a seam pose | Start the next clip from the pose the previous ends on |

Attacks allow a higher `spike`: a strike is supposed to accelerate hard, and the smear carries it.

## Causes QA can't see

These live in the game, not the sprites. If QA passes and it still looks choppy, check here.

- **Advancing one frame per render tick.** Playback then depends on display rate and drops. Use an
  accumulator, as `sprite-player.js` does.
- **Timers instead of frame durations.** `setInterval` drifts and beats against the display.
- **Character position updated at a different rate than the animation.** Simulate at a fixed step
  and render from it. Round the draw position to whole pixels for pixel art, or the sprite shimmers
  against the background.
- **Bilinear filtering on pixel art.** Use nearest-neighbour and integer scales.
- **Trimmed sprites anchored by their own bounds.** Each frame's box differs, so the body vibrates.
  Anchor on the shared pivot from the manifest. All exports here preserve it.
- **Texture filtering halos.** Dark fringes appear when transparent pixels are black; `bleed()` in the
  atlas exporter prevents it. If you re-pack frames with another tool, enable its extrude or bleed option.
- **Late input.** Actions that swallow a press feel like lag even at a perfect frame rate. Buffer inputs
  for about 100-150 ms and let the recovery of `land`, attacks and rolls be cancelled after a few
  frames. The preview's demo shows the pattern.
- **Cutting between clips mid-step.** `walk` to `run` and `run` to `skid` are cuts. Keep the phase when
  switching gaits: start `run` at the same normalized time `walk` was at.

## How the generator avoids each

- Keyed curves are monotone cubic: velocity is continuous at keys and nothing overshoots between them.
- Gait feet use Hermite swing paths whose end tangents match the ground speed, so lift-off and
  touch-down have no velocity jump. Stance feet are computed, so they can't slide.
- Foot roll pivots on heel, then ball, around a shared flat reference, so the switch is continuous.
- Soft IK compresses the last few percent of leg reach. Hard IK snaps the knee straight at full
  extension, the classic knee pop.
- Cloth loops are closed by fading the last simulated cycle into the one before it. Waiting for the
  sim to become periodic doesn't work: a chain near force balance (wall slide) is chaotic and never
  repeats. One-shots start from the previous clip's end and ease into the next clip's start, so
  capes stay continuous across a jump.
- Extremities lag the body by a few milliseconds of curve time, which gives follow-through without
  extra keys.
- Shading comes from screen-space silhouette tests, so the light doesn't rotate with limbs and
  flicker frame to frame.

## Diagnosing existing animation

For a user's own sequence that stutters, run `qa_motion.py` on the frame folder, then read the output:

- `hold` FAIL on a loop: delete the last frame.
- `seam` FAIL: the loop doesn't close. Re-time or rebuild it.
- `spike`: find the frame with `contact_sheet`-style viewing and add an in-between.
- All PASS: it's a playback issue. Use the list above.

Generating in-betweens by optical flow gives ghosting on sprites, so re-rigging in cut-out mode is
usually the better route to more frames.
