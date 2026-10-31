# Top-down QA and visual review

Run `python scripts/qa_motion.py out/c` on the actual exported set. Exit 1 means a failed check.
The tool writes `qa_report.json`, naming the clip, check and frame in `flags`. No check is enabled
by a zero-test run; missing required directions or trace data is an error.

- **structure:** PNG dimensions/counts agree with manifest and trace, events stay within the clip.
- **direction:** names, direction labels and velocity vectors agree. SHA-256 of decoded RGBA binds
  every rendered frame to its labelled direction/phase trace. Swapping front/back PNGs is detected.
  This is an integrity check, not an image understanding model: regenerating a wrong-facing drawing
  and its hashes together will not be caught. Visual review is required for semantic facing.
- **phase:** all eight directions have equal counts, fps, duration, events and scalar speed.
  Body height and foot-lift traces use the same gait phase. Turning in the preview keeps normalized
  animation phase, including sub-frame time; it does not restart the walk cycle.
- **hold:** repeated locomotion frames fail. Idle deliberately permits rasterized holds from slow
  breathing; one-shots may settle. This is not a universal detector for duplicates in every action.
- **seam:** RMS joint displacement across the loop, divided by mean interior displacement, fails
  above 2.6. A 0.2%-of-standing-height floor avoids amplifying trace rounding. A stationary rig is valid.
- **slide:** both components of a planted foot's ground-plane displacement must equal
  `-velocity_px_s / fps` within 0.25 output pixels. This checks vertical and diagonal movement as
  well as horizontal movement; feet are not tested against a side-view ground line.
- **limits:** legs remain 18+18 units, arms 14+14 units, the blade remains 23 units, and foot heights cannot penetrate the ground.
  IK fails generation for unreachable targets rather than stretching bones. This is not a general
  mesh/weapon collision solver; it does not prove that every limb overlap is visually correct.
- **float, bones:** art cut off from the body, or a bone with nothing drawn along it. Soft foot
  shadows are below the solid-art alpha. See `skeleton-qa.md`.
- **bounds:** nonzero alpha on the cell edge fails. All directions share the same feet pivot.
- **transitions:** attack/hurt end poses must meet idle within 10% of standing height. Death stays
  down until revived; gait switches preserve phase instead of using a fixed last-to-first handover.

`visual_review.py` produces six sheets, one per action: eight rows of directions, each with colour
and silhouette samples. Read all sheets for every character/style before delivery. Look for:

1. Face only on front/side views, distinct rear and oblique silhouettes; no rotated side-view art.
2. Feet follow the ground plane and remain attached; knees/elbows bend consistently; no stretched bones.
3. Weapon hand stays attached, foreground/background ordering matches facing, strike remains readable.
4. Death lowers the body and head onto the ground; hurt recovers; loops and direction changes feel smooth.
5. No clipping, inconsistent scale or pivot drift. Leftward art is a baked mirror, including handedness.

Record the reviewer, inspected files, concrete observations and unresolved issues in a local
`review/verdict.json`. Static sheets cannot establish playing feel; also play the preview.
