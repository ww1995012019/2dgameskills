# Authoring motion

Read this before adding or re-timing clips. All durations below are at `style.speed` 1.

## Built-in clips

| Clip | Length | Loop | Next | Key events |
|---|---|---|---|---|
| `idle` | 2.4 s | yes | | |
| `idle_look` | 2.5 s | no | idle | |
| `walk` | 0.84 s | yes | | footstep ×2 |
| `run` | 0.56 s | yes | skid | footstep ×2 |
| `skid` | 0.46 s | no | idle | skid_dust |
| `jump_start` | 0.24 s | no | jump_rise | takeoff |
| `jump_rise` | 0.5 s | yes | jump_apex | |
| `jump_apex` | 0.34 s | no | fall | |
| `fall` | 0.48 s | yes | land | |
| `land` | 0.44 s | no | idle | land_dust |
| `double_jump` | 0.4 s | no | fall | air_puff |
| `crouch_enter`, `crouch_idle`, `crouch_exit`, `crouch_walk` | | | | footstep ×2 on walk |
| `roll` | 0.62 s | no | idle | invincible_on/off |
| `dash` | 0.42 s | no | idle | dash_burst |
| `wall_slide` | 0.5 s | yes | | |
| `attack_1`, `attack_2`, `attack_3` | 0.6, 0.56, 0.9 s | no | idle | hit_on, hit_off, screen_shake on 3 |
| `air_attack` | 0.5 s | no | fall | hit_on, hit_off |
| `cast` | 1.14 s | no | idle | projectile |
| `block`, `block_hit` | 0.14, 0.26 s | no | | block_spark |
| `hurt` | 0.42 s | no | idle | hit_flash |
| `death` | 1.3 s | no | hold last frame | body_thud |

Jump is split so physics controls height: play `jump_start`, fire the jump at `takeoff`, loop
`jump_rise` while moving up, play `jump_apex` near zero vertical speed, loop `fall`, then `land`
on contact.

`attack_*` have a `chain_frame`. If the next attack was pressed, jump to the next clip at that frame:
each attack starts from the previous one's follow-through pose, so the combo flows.

## Timing rules of thumb

| Action | Anticipation | Action | Recovery |
|---|---|---|---|
| Light attack | 0.15-0.2 s | 0.06-0.1 s | 0.25-0.35 s |
| Heavy attack | 0.25-0.35 s | 0.06-0.1 s | 0.5-0.6 s |
| Jump | 0.1-0.15 s | | 0.2-0.4 s on landing |
| Hit reaction | none | 0.05 s | 0.3-0.4 s |

Reactions have no anticipation, because the character didn't choose them. Player-triggered actions
need short anticipation, or input feels laggy: keep it under about 0.1 s for anything the player needs
to fire instantly, and let hit-frame `hit_on` come as early as the pose allows.

## What makes it read well

- **Contrast of speed.** Hold near a pose, then move very fast. Evenly paced motion looks floaty.
  Bunch keys around the extremes and leave one or two in the fast part.
- **Weight.** The hip drops after a foot lands, not at the moment of contact. `land` bottoms out
  about 0.1 s after touchdown.
- **Lean into motion.** Spine leans forward for run (about 13 degrees) and dash (24+), back for skid.
  The head counter-rotates, so the eyes stay level.
- **Arcs.** Hands, weapon tips and heads travel on curves. Keys that interpolate a joint in a straight
  line look robotic. Keep arm motion on the shoulder and elbow channels and it will arc by itself.
- **Silhouette.** Check a clip with the fill turned black, mentally: each key pose should read. Arms
  in front of the torso vanish, so swing them clear on the strong beats.
- **Squash and stretch.** 5-10% is plenty here: 0.9 at the deepest landing, 1.09 at launch. More starts to
  read as rubber, unless `style.bounce` is deliberately cartoonish.

## Gait parameters

`Gait(name, T, L, lift, duty, ...)` in `motions.py`:

- `T` cycle time, `L` stride sweep in rig units, `lift` foot clearance.
- `duty` is the fraction of the cycle each foot is on the ground. Above 0.5 means a walk (a double-support
  phase). Below 0.5 means a run (a flight phase).
- Ground speed is `L / (duty * T)` and is exported as `speed_px_s`. To change game speed, change these
  rather than the engine's move speed.
- `hip` lowers the body. If `slide` QA shows hover, the stride exceeds leg reach: lower the hip or
  shorten `L`.
- `bob_at` sets the phase of the highest point: mid-stance for a walk, mid-flight for a run.
