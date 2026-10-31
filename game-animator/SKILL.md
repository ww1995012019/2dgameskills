---
name: game-animator
description: Generate and inspect 2D game character sprite animations for side-view humanoids, side-view shooters, eight-direction top-down humanoids, and side-view wolves. Use for character sprites, animation sheets, custom humanoid actions, and supported engine exports; select the matching mode before generating.
---

# Game Animator

Choose a mode using the character, camera and movement. Read only that mode's `SKILL.md`, and run
its scripts from that mode's directory. Each mode is bundled here and requires Python with Pillow
and NumPy; no separate skill installation is needed.

| Request | Mode |
|---|---|
| Side-view humanoid, custom cut-out art, melee or spell | `modes/game-sprite-animator/` |
| Side-view shooter, gun aiming or layered firing | `modes/game-shooter-animator/` |
| 3/4 top-down eight-direction humanoid | `modes/game-topdown-animator/` |
| Side-view wolf with quadruped gait or combat | `modes/game-quadruped-animator/` |
| Experimental side-view flying creature with user-provided PNG parts | `references/creature-rig.md` |

Read the chosen mode's `SKILL.md` for its commands, supported character configuration, review and
export process. For side-view custom art and actions, use its `references/ai-art.md` and
`references/character-spec.md`; test custom actions in the preview and inspect joints visually.

These are independent existing implementations under one entry point. A character spec or PNG
parts from one mode do not automatically work in another. The experimental flight workflow can
generate rigid-part motion but is not a visually validated bird, bat or dragon product. Arbitrary
creature locomotion, full scene generation, and AI art for the top-down mode are not implemented.
Do not advertise an engine integration as verified beyond the mode's integration documentation.
