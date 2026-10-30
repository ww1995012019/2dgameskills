# Character spec

A character is one JSON file. Any field left out takes the default from `scripts/sprite_anim/art.py`.

```json
{
  "name": "commando",
  "head": "headband",
  "weapons": ["rifle", "shotgun"],
  "cloth": ["headband"],
  "long_sleeves": false,
  "armor": false,
  "backpack": false,
  "goggles": false,
  "body": { "bulk": 1.1, "head_size": 1.0 },
  "style": { "speed": 1.0, "bounce": 1.0 },
  "colors": { "tunic": "#6a7a4d" }
}
```

| Field | Values | Effect |
|---|---|---|
| `head` | `helmet`, `beret`, `cap`, `headband`, `balaclava`, `hair` | Headgear. `headband` adds a simulated tail |
| `goggles` | bool | Goggles on a `helmet` |
| `weapons` | list of `pistol smg rifle shotgun sniper rocket` | The first is carried in full-body clips and combos. Each adds a full upper-body set |
| `cloth` | any of `scarf`, `hair`, `headband` | Simulated chains. A long scarf can read as a third arm on muted colours |
| `long_sleeves` | bool | Forearms use the shirt colour |
| `armor` | bool | Shoulder and knee guards |
| `backpack` | bool | Pack behind the torso |
| `body` | `thigh shin ankle_h hip_h pelvis_len chest_len neck_len up_arm lo_arm head_size bulk` | Proportions, standing height is 100 units. Keep `hip_h` about 1.5 below `ankle_h + thigh + shin` |
| `style.speed` | 0.8 to 1.3 | Playback speed of locomotion and actions. Fire rates don't change |
| `style.bounce` | 0.7 to 1.3 | Scales bob and squash |

Colour keys: `skin hair tunic tunic2 pants boots belt metal accent cape glove eye ink vest helmet gun
gun2 wood`, plus `dust` and `dust2` for effects. `cape` also colours the headband and scarf. Pick a
mid tone for each: shadows and highlights are derived with a hue shift.

## Weapons

`scripts/sprite_anim/weapons.py` holds the data. Gun frame: origin at the near-hand grip, +x along the
barrel, +y up.

| Weapon | Seconds per shot | Frames at 30 fps | Reload | Cycle |
|---|---|---|---|---|
| `pistol` | 0.2 | 6 | magazine, 1.1 s | slide kick |
| `smg` | 0.075 | 2 | magazine, 1.4 s | automatic |
| `rifle` | 0.1 | 3 | magazine + charging handle, 1.7 s | automatic |
| `shotgun` | 0.7 | 21 | three shells + pump, 1.9 s | pump after every shot |
| `sniper` | 1.15 | 34 | magazine + bolt, 2.0 s | bolt after every shot |
| `rocket` | 1.5 | 45 | loaded at the breech, 2.0 s | empty tube until reloaded |

To tune a weapon, change its `period`, `kick` (slide back), `climb` (muzzle rise) or `flash` (size).

To add a weapon:

1. Add an entry to `WEAPONS`. `hold` is the grip from the near shoulder, `fore` the far hand from the
   grip, `muzzle` the barrel tip, `port` the ejection point, `well` where ammunition goes in. `kind` picks
   the fire and reload behaviour: `mag`, `tube`, `bolt` or `rocket`.
2. Draw it in `SoldierArt.gun` in `scripts/sprite_anim/soldier.py`, using coordinates in the gun frame.
3. Add its name to a character's `weapons` and run QA. `grip` fails if `fore` is out of the far arm's
   reach: far shoulder to fore point must stay under about 27 units, so shorten `fore` or `hold`.

## Pose channels

Used when adding or adjusting clips in `motions.py`. Aim, look and spine_up belong to the upper body
and everything below the waist to the lower, which is what lets the two combine.

| Channel | Meaning |
|---|---|
| `aim` | World angle of the gun, 0 forward, +90 up |
| `look`, `look_w` | World angle of the head, and how strongly it overrides the body |
| `spine_up` | Extra torso lean owned by the upper body |
| `gun_ik`, `far_ik` | 1 hands locked on the gun, 0 free FK arms. Blend between them for throws |
| `recoil`, `climb` | Slide back along the barrel, muzzle rise in degrees. Negative `recoil` thrusts forward |
| `nh_x/y`, `fh_x/y` | Near and far hand offsets from grip and fore points, in the gun frame |
| `pump` | Slide, pump or bolt travel, 0 to 1 |
| `mag`, `mag_hand`, `mag_t` | Magazine in gun, in far hand, seconds since dropped (-1 = not dropped) |
| `flash`, `shot_t`, `shot_T` | Muzzle flash level, time since shot, shot period |
| `root_x/y`, `pelvis`, `foot_*` | Lower body, as in `game-sprite-animator` |
| `arm_*`, `wep` | FK arms and gun angle from the forearm, used when `gun_ik` is 0 |

The rig enforces joint limits on all of this, see `references/motion-qa.md`. Leg motion is IK: animate feet, not knees. World angles mean the upper body needs no compensation for
what the legs are doing.
