# Experimental held-weapon frame and low carry

## Actual failure in the male v11 fixture

Full frames and the arm source were reviewed. The near hand is a loose, partly
open fist: the thumb does not convincingly close on a cylindrical handle. Its
annotated grip lies near the thumb opening. The handle consequently reads as
hanging beside the fist. The blade also had an independent angular channel while
the distal hand and palm offset followed only the forearm. Finally, the loaded
arm swung forward enough to overlap the free hand in the held walking pose.

These are separate defects. Coincident grip points and numeric attachment passes
cannot certify a closed, load-bearing grasp. The original source hand has NOT
been accepted or silently replaced.

## Reusable opt-in contract

A known-joint manifest may set `weapon_hand_binding: true`. The binder records
`body.weapon_hand_angle`, the source blade angle minus source forearm angle.
The source hand still needs semantic review: closed fingers, thumb opposition,
handle enclosed by the palm, correct guard/pommel side and plausible wrist.
This switch is a mechanical contract, not a declaration that those checks pass.

The rig rotates the distal hand pixels and wrist-to-grip offset with the blade.
The hand and weapon therefore share translation and orientation, including
weapon ground correction. Authored wrist deviation is softly limited to ±35°;
out-of-range requests or floor corrections beyond that envelope enter existing
joint-limit QA. This is a conservative low-carry envelope, not a universal
anatomical model for all weapon attacks. Existing rigs omit the optional angle
and retain their previous path.

For the natural walking profile, `gait.walk.held_weapon_carry: "low"` opts into
a quiet loaded arm, centred beneath its shoulder from its two bone lengths and
elbow bend. It uses 3° upper-arm swing, 1° elbow sway and 0.5° blade sway instead
of free-arm-like movement. It requires the measured hand frame and rejects
conflicting `arm_n` or `wep_sway` overrides. Other styles are not implied.

## Verification scope and remaining blocker

`dev/tests/test_weapon_hand_frame.py` covers two body proportions, distal pixel
transform equality, shared palm/blade orientation, ground correction, legacy
path, malformed data, two-profile binder opt-in and low-carry validation.
The v12 fixture exports only idle, walk and two grounded settle clips for
web-focused review. `dev/render_grounded_player.py` exercises the actual exported
JavaScript controller, but its GIF is not browser visual playback.

A single supplemental source-arm edit was requested through built-in image
generation on 2026-11-04. The service rejected the request with HTTP 400,
`moderation_blocked` / `violence`; no image was produced. No rewritten retry or
alternate route was attempted. The current hand-art defect remains unresolved.
Do not label v12 production-ready or approved merely because motion QA passes.
Godot and other engine testing are paused per the user's current instruction.
