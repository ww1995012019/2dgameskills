# Motion QA and timing

`qa_motion.py` prints PASS, WARN or FAIL per clip. It also works on any PNG sequence:
`python scripts/qa_motion.py path/to/frames --loop`.

## Checks

| Check | Measures | Usual cause | Fix |
|---|---|---|---|
| `hold` | Consecutive identical frames | Loop that repeats its first frame, or a static pose in a loop | Sample `[0, T)`. Add drift to a still loop, as `legs_drift` does for jumps |
| `seam` | Last-to-first change vs a typical step | Loop not closed | Integer cycle counts in every sine |
| `spike` | One step far bigger than both neighbours | A skipped in-between | Spread keys over 2-3 frames |
| `slide` | Stance foot travel vs `speed_px_s`, and foot height in stance | Stride and speed disagree, or foot past leg reach | Derive speed from `L / (duty * T)`; lower the hip |
| `jitter` | Movement of feet meant to be planted | Different stance values across poses | Share stance values. A lifted heel is fine, only both ends moving counts |
| `grip` | Distance between hands and their gun points | Target out of arm reach, so the gun floats free of a hand | Shorten `hold` or `fore`, or set `far_ik` to 0 and release that hand |
| `cadence` | Shots evenly spaced in frames, each with a flash | Shot period not on whole frames | Use `shot_frames`; snap clip length to whole shots |
| transitions | Pose jump where clips hand over | Clips that don't share a seam pose | Start the next clip from the pose the previous ends on |
| `limits` | Joints asked past their range, bones changing length, knees flipping direction | A pose beyond anatomy. The rig eases it into the limit, so a large excess means the pose isn't what was authored | Re-pose it. Limits are in `sprite_anim/constraints.py` |
| `clip` | Weapon held over the face, weapon or body through the ground | Reach or angle wrong for that pose | Move the pose. Crossing the face during a swing is fine; holding there isn't |
| `bounds` | Art cut off by the frame edge | Art wider than the frame | The generator auto-fits the character to its widest pose and prints `[fit]`. This fires only for what fit can't see, mainly dust or bake-time cloth |

Some clips are exempt where a check would be wrong: `fire` skips `spike`, `seam` and `hold`, because the
recoil snap at the wrap is the shot itself and cooldown frames are meant to hold. `subtle` loops
(slow breathing) skip `hold`, `seam` and `spike`, because pixel rounding decides which frame moves.
`drift` loops (air legs) skip `seam` only, since closed-form sines can only be opened by that rounding.
`action` clips allow a higher `spike`, and that includes `hurt`, which has no anticipation by design.

If QA passes and it still feels choppy, look at the game side: see `references/integration.md`.


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

A shot recorded at frame 0 intentionally resets recoil at the loop boundary. Its whole-pose
impulse uses the same 10%/20% height limits as transitions (`joint_seam_mode: shot_impulse`), rather
than comparing it with slow recovery steps. For full-body firing combos, ankles, knees and hip
still undergo the speed-relative gait seam check (`joint_gait_seam_ratio`). This does not exempt
firing from joint QA: an excessive recoil-boundary pose jump still fails. The existing `fire`,
`subtle` and `drift` exemptions above apply only to the pixel checks.

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
- **Aim clearance:** the gun moves forward as aim rises, so aiming straight up doesn't cover the face.

## Timing

| Action | Anticipation | Action | Recovery |
|---|---|---|---|
| Firing | none | first frame of the clip | until the next shot |
| Reload | 0.2 s gun lift | hands do the work | 0.2 s return |
| Throw | 0.3 s wind-up | release around 0.44 s | 0.35 s |
| Melee | 0.18 s | 0.07 s | 0.3 s |
| Hit reaction | none | 0.05 s | 0.35 s |

A shot has no anticipation, because any delay after the trigger reads as lag. Everything visible happens
on the first frame: flash at full size, gun at full recoil.

## What sells a gun

- **Recoil belongs to the whole upper body.** The gun slides back, the muzzle rises, and the torso rocks
  a little (`spine_up`), scaled by weapon. A pistol snap and a shotgun shove must feel different.
- **Flash lasts one or two frames.** Three layers of a spiked shape, with the seed changed per shot so
  consecutive flashes differ. A long flash looks like a torch.
- **Shells keep flying between shots.** Three shells are drawn at different ages so the stream looks
  continuous during automatic fire.
- **Reloads show their mechanics:** magazine out, falling, hand to pouch, new magazine in, slap, charging
  handle. Shotguns load shells one by one, and bolt rifles cycle the bolt after each shot.
- **The head tracks the aim at about three quarters of the angle.** Full tracking looks mechanical, and
  no tracking makes the gun seem detached from the soldier.

## Gait

`Gait(name, T, L, lift, duty, ...)`: `T` cycle time, `L` stride sweep in rig units, `lift` foot
clearance. `duty` is the fraction of the cycle each foot is down: above 0.5 is a walk, below 0.5 a run.
Ground speed is `L / (duty * T)` and is exported as `speed_px_s`. Change these rather than the game's
move speed. `Reversed` plays a gait backward for `backpedal`.
