# Phase-preserving locomotion clock

The normal `preview.html` playable demo uses `GroundedWalkController` whenever
an idle and a supported walking loop are exported. Both the legacy Gait
(`phase_walk_v1`) and optional NaturalWalk (`natural_walk_v1`) export this policy.
Starting and stopping retain a single walking phase clock, and root movement uses
the controller's exact displacement while accelerating/braking. The stopped pose
is a two-foot walking hold, not the separate gallery idle animation; it has no
breathing. Other actions interrupt locomotion and return to a new held stance.
This does not smooth walk/run cuts or arbitrary action transitions.

`qa_motion.py` verifies the export clock and the actual displayed two-foot support
samples. This contract and the main-demo Node integration tests supplement the
continuous Python tests below; legacy walking still has its existing measured
soft-IK contact residuals and discrete sprites retain frame-sampling error.

Sparse odd frame counts can round the ideal second support centre backward into
a swing frame. Exported `locomotion.hold_phase` shifts both half-cycle-separated
centres forward to valid displayed support samples (for example, seven walk
frames at 8 FPS). The usual centre is retained when valid. QA, settle-bank
registration and the Canvas controller use this same phase. A frame set with no
two sampled support windows is rejected with an instruction to increase FPS.

`natural_walk_v1` can stop at any gait phase without crossfading foot targets.
The walk's phase clock slows smoothly until both soles support the body. That
pose becomes a **locomotion idle**. Resuming accelerates the same phase clock.
The authored `idle` Proc and legacy clips are unchanged; this is not a bridge
from that older idle pose. The hold has no breathing animation.

## Python sampler

```python
clips = build_clips(body=body, gait={'walk': {'profile': 'natural_walk_v1'}})
walk = clips['walk']
idle = walk.standing()             # initial double-support hold
start = idle.resume(duration=.3)
pose = start.sample(elapsed)
x = initial_x + start.displacement(elapsed)
# After start.duration, start keeps sampling the normal walk.
stop = walk.stop(start.phase_time(elapsed), min_duration=.3)
pose = stop.sample(stop_elapsed)
x = stop_initial_x + stop.displacement(stop_elapsed)
# After stop.duration, the pose and displacement remain fixed.
idle = stop.hold()
resume = stop.resume(duration=.3)
```

`GroundedGaitRamp.phase_time(t)` is the source walk clock in seconds;
`phase_rate(t)` is its rate, `vel(t)` is world velocity in rig units/second,
and `displacement(t)` is exact world displacement relative to ramp time zero.
Use displacement or exact clock differences, **not constant walk speed** or an
Euler integration of instantaneous velocity. No images are blended.

A stop rounds its duration upward so it ends in double support. Its duration is
at least `min_duration` and less than `min_duration + walk.duration`. The
requested minimum is therefore not a deadline for stopping. Both contact and
swing trajectories slow together, so the swing foot lands before the hold.
Keep the current world position as the next segment's origin.

Commands during a ramp must be queued until that ramp finishes. Constructing a
new full-speed stop midway through acceleration would change velocity abruptly.
This implementation does not promise immediate reversals or a turn animation.
`resume()` on a stop means resume **its final held stance**, not its current pose.
The ramp itself emits no events; a runtime can emit walk events as its source
clock crosses them.

## Why the feet stay planted

Let `q` be the source clock, `T` the cycle duration, and `v` the gait speed.
World travel is exactly `v * (q - q0)`. During contact the natural gait's sole
travels locally at `-v` per source second, so the two terms cancel, including
while slowing or accelerating. A quintic speed easing has zero slope and
curvature at its boundaries. No ankle target snapping, changed QA tolerance,
or support-foot teleport is involved.

For a ramp duration `D`, `u = clamp(t / D, 0, 1)` and
`I(u) = 2.5*u**4 - 3*u**5 + u**6`. Stopping uses
`q = q0 + D*(u-I(u))`; starting uses `q = q0 + D*I(u)`.
Past the end, stopping holds `q0+D/2`; starting continues at unit rate.
Stopping chooses the first double-support centre after `q0+min_duration/2`.

## Validation and limits

`dev/tests/test_walk_transitions.py` measures solved-joint boundary positions and
velocities, per-side support heights and world foot drift, multiple body
proportions, arbitrary starting phases, and different sampling rates. A
constant-speed-root fault injection proves the contact check catches a wrongly
integrated stop. These are numerical guarantees for the tested profile and
proportions, not a substitute for visual approval of new artwork.

`dev/render_walk_transitions.py --character character.json --out output`
renders a grounded idle/start/walk/stop/resume/stop sequence, with raw PNGs,
GIF, contact sheet, and per-frame JSON phase/root/contact measurements. The
near-ground proximity metric is deliberately separate from analytic planted
contacts: a just-airborne swing point is not a planted foot.

The optional `--mode blend` records the rejected skeletal-blend experiment.
Its development-only helper is `dev/walk_transition_diagnostic.py`; no blend
API is shipped in the skill. Its contact validation is explicitly not applicable. That experiment has smooth
pose seams but large foot drift, and is not the grounded locomotion solution.

The existing direct `play('idle')` / `play('walk')` switch still changes poses;
its expected-failure regression remains. Baked-sprite playback is discretized
and cannot inherit an exact continuous solved-skeleton guarantee. A compatible
player must retain the walk clock, advance by exact phase differences, freeze
on double support, and move its world pivot from the same displacement. Use the
actual frame clock (`frames.length / fps`), not a rounded duration string, when
mapping phase onto sprites. Runtime-specific verification is separate from
these Python tests and rendered proof.

## Canvas controller and export

Walking generation exports `locomotion.period_s = frames / fps`, duty fraction,
and unrounded movement speed retimed to that same baked clock. At 24/30 FPS the
default natural-walk period equals its authored 5/6 second; other rates or style
speeds may round differently. Settle-bank clock registration and endpoint duration
are retimed alongside the walk. `GroundedWalkController` in `sprite-player.js`
uses this clock for both sprite advance and returned world displacement:

```javascript
const control = new GroundedWalkController(animations, atlasImages);
control.setMoving(true); // false requests phase-aware braking
const result = control.update(dtMilliseconds);
worldX += result.dx;
control.draw(context, worldX, groundY);
```

Commands during a ramp are queued, with the latest requested state winning.
An interrupted start finishes its short ramp before braking. Braking may take
up to a stride longer than the minimum requested duration so the swing foot can
land. `result.state` is `hold`, `resume`, `walk`, or `stop`. Do not also call
`control.player.update` or switch its clip. The separate canonical idle is not
used; held stance can retain a raised rear heel and has no idle breathing.

The controller uses the exact export sampling period, not rounded `duration`.
It rejects low-FPS exports whose held frame misses the two-foot support window.
Low-level `SpritePlayer.play('idle')` still makes a direct clip cut. The normal
playable preview now wires the phase controller described above; other engine
controllers must integrate it explicitly and do not automatically inherit this
state machine.

`engine/web/grounded-walk.html` is included with natural-walk exports. Serve the
export folder over HTTP to try repeated start/stop commands. Node tests compare
the actual exported controller to Python phase timing, including 24/30/60/90/144
Hz updates, dropped-frame partitioning, repeated input, and queued reversals.
Browser visual playback remains a separate verification requirement. Continuous
world movement with discrete baked poses retains frame-sampling foot error;
the continuous Python sole-drift bound is not a pixel-perfect sprite guarantee.

## Optional flat-foot settling

The original hold retains a double-support walking pose with a raised rear heel.
`hold.settle(duration=.25)` now authors a finite `GroundedGaitSettle` clip that
smoothly flattens both feet around their existing heel/toe support pivots. The
hip-height envelope is recomputed throughout so the legs remain reachable.
Both positions and velocities meet the held poses continuously; world travel is
zero. The original gait hold/resume route remains available unchanged.

```python
settle = stop.hold().settle(duration=.25)
flat_idle = settle.hold()       # SettledGaitHold, both foot pitches zero
unsettle = flat_idle.resume(duration=.25)
start = unsettle.resume(duration=.3)  # use only after unsettle finishes
```

The reverse-settle restores the exact gait pose before phase acceleration. Its
samples match the forward settle played backward. Commands during settle or
reverse-settle must be queued; do not skip directly from flat idle to the walk.
A settled hold does not add upper-body breathing. It still has the walking
stance's foot spacing, so it is not a feet-together rest pose.

For baking, construct `GroundedGaitSettle(walk, source_phase_time, duration)` at
the exact displayed walk frame, not an unsampled ideal phase. At 24 FPS the
support centres .05/.55 coincide with frames 1/11 of 20; at 30 FPS the held
sprites are frames 1/13 of 25, with sampled phases .04/.52. Keep bank sample
phase and continuous controller hold phase separate. Each finite bank includes
both endpoints using the normal `round(duration*fps)+1` frame count. Reversing
its saved frames avoids additional image synthesis. Runtime integration tests
must verify first/last pixels and world origin, not merely metadata names.

The proof command's `--mode settled` renders both settles, reverse-settles,
flat holds, and gait ramps with per-frame phase/root/contact measurements.
Tests cover support anchors, no ground penetration, endpoint joint velocities,
reverse equality, different body proportions, and scale. Visual approval of the
resulting stance remains distinct from these numerical checks.

### Flat-foot settle banks

Generate with `--grounded-settle` to include two small `walk_settle_0/1`
clips. The controller starts at their flat-foot endpoint, reverses a bank before
accelerating, and plays a bank after braking. Both banks preserve the existing
sole contact pivots and keep world displacement zero. The controller adds
`settle` and `unsettle` states, queues repeated input, and can reverse a pending
start back into standing without first taking an unnecessary walking stride.

Each bank is sampled from the actual displayed double-support walk frame,
not the continuous phase centre. This matters at 30 FPS, where a 25-frame loop
does not sample both half-cycle centres. Exported `source_frame`, `sample_time_s`
and `clock_phase_s` keep sprite endpoints and the world clock separate and
consistent. Settling lowers the pelvis and flattens the lifted heel; it does not
bring the feet together or create procedural breathing. This is a split stance,
not a claim to reproduce the independently authored idle pose.

Settle banks retain the source walk frame's cloth shape and carry it with each
cloth attachment as the body lowers. This prevents an independently initialized
cloth bake from popping at the walk/bank boundary. The finite settle uses
kinematic cloth, not simulated cloth relaxation; reversing the bank reuses the
same shapes. Export regression checks compare actual bank-entry PNGs to the
registered walk PNGs, in addition to checking skeletal continuity.
The endpoint pixel check currently covers unblurred exports. Kinematic carry is
not a floor-contact cloth solver: floor-length garments need separate contact
review as their attachment lowers. Do not assume those assets or motion-blurred
walk/bank handoffs inherit the tested short-cape pixel result.

### Optional empty-arm relaxation while settling

For `natural_walk_v1`, `gait.walk.settle_relax_free_arm: true` smoothly returns the
far/empty arm to the walk's neutral carriage during the existing heel-settle bank.
It leaves the carrying arm, weapon pose and both foot-contact paths unchanged.
The same quintic weight reverses on resume, so settle frame zero still matches its
source walk frame and the held pose matches the settle endpoint. The default is
false; ordinary walk frames and existing exports are unchanged unless opted in.

This can avoid freezing a fully occluded free-arm swing phase indefinitely. It
does not guarantee visible anatomy: review both final held silhouettes, shoulder
attachment and forward/backward hand overlaps. If neutral carriage itself is
hidden, correct its reviewed body-relative input or artwork rather than move the
whole far arm in front of the torso. Static frozen split stances are still not a
breathing, feet-together idle animation.
