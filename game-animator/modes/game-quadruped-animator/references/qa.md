# Four-paw motion QA

`qa_motion.py <set>` writes `qa_report.json` and exits nonzero for a FAIL. Flags name the clip,
check, leg/joint and frame. Idle may hold rasterized breathing frames; locomotion duplicates fail.

- **structure / integrity:** frame counts, dimensions, finite coordinates, loop timing and decoded
  RGBA hashes must agree with the trace. Hashes bind pixels to a sample; they do not understand anatomy.
- **slide:** each planted paw has output-pixel displacement `[-speed_px_s/fps, 0]`, within 0.25px.
  Planted paw centres must stay at two rig units above the floor (the paw radius); raised contacts fail.
  All four paws are checked individually, including across the wrap. The separate foot and joint
  recordings must agree. Speed is derived from stride, stance fraction and cycle duration.
- **limits:** front and hind limbs each have three rigid segments. The upper/lower segments are
  18 and 20 units; pastern lengths follow their authored ankle-to-paw offsets. The front elbow bends
  backward and hind stifle forward; reflecting the bend while preserving bone lengths still fails.
  Spine, neck and head lengths are fixed. Targets beyond reach stop generation rather than stretch.
- **gait:** walk uses four sequential quarter-cycle footfalls; trot pairs diagonal legs; gallop
  staggers hind then fore contacts and contains suspension. Manifest phases, contact samples and
  named touchdown events must agree. This is one stylized canine gallop, not a model of every breed.
- **seam / spike:** RMS joint motion, including tail joints, is measured at the wrap and between
  frames. A wrap-to-mean-step ratio above 2.6 fails; a step exceeding both neighbours by 4× fails.
  A 0.2%-of-60-rig-unit floor prevents amplification of tiny idle/rounding movements.
- **tail:** root attachment, six-point segment lengths and the drawn tapered strip's floor clearance
  are checked. Segments are six units with 0.08-unit interpolation tolerance. At non-integral simulation
  samples the whole interpolated shape is translated to the exact frame anchor. Tail width is included
  in floor clearance. This does not prove absence of all tail/body intersections.
- **float, bones:** art cut off from the body, or a bone with nothing drawn along it. See
  `skeleton-qa.md`.
- **bounds:** visible alpha on the frame edge fails. All clips share one floor pivot.

Build `visual_review.py <set>` and inspect every row in all four sheets. Look for leg attachment,
wrong joint bends, believable chest/waist/head, four-foot ordering, paw contact, tail shape, clipping
and useful silhouettes. Contact dots are hn/hf/fn/ff. Record the reviewer, inspected sheets, concrete
findings and unresolved notes. A still image cannot demonstrate playing feel; use the preview too.

The checks do not provide a general mesh-collision solver, prove biological realism or validate
smooth contact-preserving blends between different gaits. Gait changes in the preview preserve
cycle phase; a game's acceleration, stopping and blend policy remain its controller's responsibility.

Combat additions: one-shots include their endpoint and are not tested as cyclic seams. Attack/hurt
body and tail end poses are checked separately against idle; both must be within 10% of body height.
Death holds its endpoint. Paw, jaw/chest floor and tail clearance checks remain enabled throughout.
Attack events must be exactly hit_on then hit_off at the authored window; death has one body_thud.
The bite is a ground-planted lunge, not an airborne pounce. Gait-to-reaction cuts are not blended.
