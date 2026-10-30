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
| `limits` | Joints asked past their range, bones changing length, knees flipping direction | A pose beyond anatomy. The rig eases it into the limit, so a large excess means the pose isn't what was authored | Re-pose it. Limits are in `sprite_anim/constraints.py` |
| `clip` | Weapon held over the face, weapon or body through the ground | Reach or angle wrong for that pose | Move the pose. Crossing the face during a swing is fine; holding there isn't |
| `bounds` | Art cut off by the frame edge | Art wider than the frame | The generator auto-fits the character to its widest pose and prints `[fit]`. This fires only for what fit can't see, mainly dust or bake-time cloth |

Attacks allow a higher `spike`: a strike is supposed to accelerate hard, and the smear carries it.


## Joint continuity checks

Generated sets with `rig_trace.json` also check the RMS displacement of the nine recorded joints
(wrists, ankles, knees, hip, neck and head base). Coordinates include root motion. Standing height
is 100 rig units, or `100 * unit_px` output pixels, so HD and pixel art use the same limits.

- Loops with more than two frames compare the last-to-first joint displacement with the mean
  interior displacement. Ratios above 1.7 WARN and above 2.6 FAIL. The denominator has a 0.2%-of-height
  floor for trace rounding and negligible movements. Zero joint displacement is valid for a still rig.
- Transitions compare the outgoing last pose with the declared incoming entry pose (`next_frame`,
  default 0) directly: RMS displacement
  above 10% of standing height WARNs and above 20% FAILs. It is not divided by animation speed.
- Pixel and joint statuses are combined using the worse result. `qa_report.json` includes
  `joint_seam_ratio`, `joint_seam_height`, transition `joint_distance_height`, endpoint frame indices
  and frame flags naming the loop or transition. The original pixel ratios remain available.
- PNG-only inputs and older traces without joints keep the original pixel checks. Missing joint
  fields do not mean joint continuity passed. Keep frames and their trace synchronized when editing.

## Skeleton constraints

These run inside the rig on every pose, so they apply to custom clips too. `sprite_anim/constraints.py`
holds the numbers.

- **Joint limits:** spine, head and elbow ease into their range along a smooth curve. A hard clamp would stop
  a joint dead on one frame, which is itself a hitch.
- **Heel lift:** an ankle only closes so far. Past that the heel rises and the ball stays planted, as in a
  real deep crouch, so feet don't slide and shins don't fold onto the foot.
- **Weapon ground clamp:** a held weapon rotates about the wrist rather than entering the floor.
- **Floor contact:** in a roll the lowest body part rests on the ground on every frame, because a tucked
  body changes shape as it turns and no fixed height works. A collapsing body is lifted rather than sinking.
- **Auto-fit:** before rendering, the generator measures every pose and scales the character just enough
  to fit, printing `[fit]`. A very long weapon means a slightly smaller character.
- **Cloth bend limit:** neighbouring cape or scarf segments can't fold past 62 degrees, which stops knots.

Clip tags adjust the checks: `ground` enables floor tests, and `tumble` relaxes the face and ankle rules
for spins and falls, where the body isn't posed. Use it only for those.

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
