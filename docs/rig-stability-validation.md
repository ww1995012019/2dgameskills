# Reusable humanoid rig stability

This development pass targets stable binding and reusable action data, not more built-in actions.
A single image does not contain hidden anatomy. Generated isolated layers are reconstructed artwork,
not a pixel-exact extraction of the identity image. The experimental atlas assembler still applies
an adult side-view proportion profile. Human, anthropomorphic and mechanical appearance must not be
confused with support for arbitrary anatomy or rigid segmented armour.

## Changes

- New known-joint bindings opt into source-frame mapping. The source and target use the same
  interpolated curve frame; compression responds to additional inward curvature, not the curve
  already drawn in the source. An unchanged bent source mesh previously drifted up to 8.863 pixels
  in a 180-pixel test part. Identity and uniform-transform tests now retain its vertices within
  1e-7 pixels, including cropped offsets. Existing bindings without the flag keep their old mapping.
- Body inputs reject nonfinite numbers, nonpositive bone lengths, invalid sole/attachment vectors,
  unknown fields and unsafe soft-IK fractions before sampling an action.
- Custom actions reject unknown/nonfinite pose channels, invalid timing, malformed events and
  unknown transition targets. Normalized `next_at` is now forwarded into exported handovers.
  Existing valid goblin action samples are unchanged; tests cover actual last-frame handover export.
- The experimental atlas adapter identifies a wrist from distal silhouette narrowing followed by
  palm widening before considering colour. The previous colour mask could include a bare forearm
  and attach the wrist close to the sleeve. A bounded compact-hand fallback remains for existing
  simple art. Ambiguous broad sleeves/competing narrowing are rejected, not guessed. Recolouring
  an accepted silhouette as skin, fur, glove or metal does not change its inferred joints.

## Actual art trials

Four new atlases were generated for this pass: male adventurer, female warrior, wolf ranger and
robot guardian. Original images and successive outputs are retained outside the repository under
`/workspace/shared/rig-fixtures`; generated art is not silently embedded in the public skill.
The male and female also have full identity images; the wolf and robot initially have atlas-only
inputs and cannot establish identity-reference fidelity.

The initial male `build-v1` has idle/walk, 97 frames at 256px/30fps. Motion measurements passed,
including foot slide 0.002px and hover 0.122px, but source-detail QA reported three failures.
Independent visual review found an apparent floating far fist in walk frames 0–4 and 22–24.
Isolated rendering establishes that the arm itself is continuous: foreground occlusion hides the
connecting forearm. This is a readability defect, not a proven mesh tear. Static assembly also
has a larger collar and heavier proportions than the identity. These findings are not waived.

Rebinding with the silhouette wrist detector produces versioned `rig-v2` and `build-v2` outputs.
Male v3 subsequently corrects the walking arm carriage. A separate male stress build exercises
idle, walk, run, crouch, attack, cast and a new keyed arm-raise action: 207 frames at 512px/24fps.
Motion, transitions and isolated attachment checks pass throughout. This does not establish
composite readability: early/late custom arm-raise frames expose a hand while hiding most of its
forearm. Independent enlarged review of all 64 visibility candidates and their adjacent sequences
found natural back-arm occlusion in this male output, including the initially suspicious custom
frames 3/21: a short visible wrist segment connects the hand at the torso edge. All candidates have
individual output-hash-bound decisions and concrete review evidence. The gate passes for these
decisions, not because visibility metrics automatically prove anatomy correct.

The current-code focused suite passes 81 tests. The 26-character legacy regression completes
with zero failures in every build; existing cutout-demo warnings remain (7 pixel, 8 HD).
Neither suite establishes identity fidelity or arbitrary-action visual acceptance. The initial
whole-repository baseline completes 378 tests with 7 failures, 2 skips and 4 expected failures.
Three failures are Chromium process-socket permission errors; four are Godot failing to create its
default user-data directory before playback. This is not an all-green or final-code baseline claim.
The four Godot tests subsequently pass with writable temporary XDG data/config directories.

## Verification boundaries

The source-frame, body-data and custom-action tests are numerical/fault-injection evidence.
Existing 26-character regression does not exercise layered puppets, so the separate actual-art
trials and layered tests are required. Tests are never relaxed to make a trial pass.

Local Chromium could not create its process socket even after an authorized escalated launch.
A cloud-browser file URL was also refused. Neither is a successful interactive browser playback
check. Static frames and contact sheets remain useful but do not prove real-time playback.

Using writable temporary XDG data/config directories, the male seven-action, 207-frame stress
output subsequently imports and plays in Godot 4.6.3 at both 60 and 144 Hz. Every reconstructed frame
has maximum pixel error zero; animation timing, order and looping checks pass. This is actual
automated engine playback evidence, not human real-time aesthetic approval or a browser pass.
Reproduce with `XDG_DATA_HOME=/tmp/rig-godot-data XDG_CONFIG_HOME=/tmp/rig-godot-config python
dev/godot_smoke.py /workspace/shared/rig-fixtures/male-adventurer/stress-build-v1 --all-clips` after
creating those writable directories.

## Additional stability gates and observed corrections

New known-joint binds opt into frame-by-frame isolated alpha attachment checks. Fault injection
proves that a missing proximal arm strip is caught even when the opaque torso makes the final
composite pixel-identical. Integer-aligned ROI rasterization retains resolution; any local failure
falls back to full-canvas connectivity, since a valid painted path can leave a small region and
return. A real three-frame 512px SS2 comparison was 3.22 times faster with identical outcomes.

The male v3 walking profile centers its empty arm below its own shoulder using measured bone
lengths and the existing elbow bend. Independent review of all 20 frames found the previous
floating fist gone, with continuous visible forearm-to-hand when the far arm emerges behind the
body. This is a confirmed static-frame regression result, not interactive playback acceptance.

Female v2 was sent as work-in-progress, and the user reported a transparent-looking left hand.
The GIF has no transparent palette entry and decoded frames are opaque; source PNGs show the same
missing-looking forearm. The actual defect is occlusion/readability, not GIF alpha. Female v3
reduces forward floating-fist visibility, but its wider hem still hides the rear wrist in some
frames; this is an unresolved general garment-clearance case. The male is now the primary quality
target, with that female case retained as a regression rather than expanded further.

The male's flagged smear tiles were inspected enlarged with their coordinates retained in
`smear-diagnostics.png`. Independent review identifies natural skin/leather highlights and trouser
fold gradients, rather than texture erased into fog. Original numeric FAILs remain in reports;
thresholds were not loosened and no replacement art was generated merely to force a green score.

An explicitly reviewed `head_attachment=socket` mode adds a separate mechanical stem insertion
contract. Default cap-cover validation is unchanged. The robot static trial preserves head scale
and has 100% insertion support; painted socket interior depth and rigid armour deformation remain
unproven. This is not an automatic robot-recognition or rigid-limb feature.

## Alternatives actually rejected

The existing experimental whole-source skinning branch was tried in an isolated workspace with
automatic landmarks, retaining the original male reference. It produced 72 idle and 25 walk frames
and numerical QA of zero failures/one warning, but actual frames stretch the arm/chest into a flap
and distort legs/boots. Every frame has inverted triangles (idle 740–872, walk 242–1,131 of 15,162),
and the renderer omits their cells. An instrumented rerender matches all 97 output frames exactly;
a reduced-resolution trial also fails. This alternative is not merged or described as successful.

A source-guided proportion comparison also cannot be applied blindly: visible elbows/wrists/knees
are plausible, but the model's high-confidence hip is hidden under clothing. Whole-part scaling
cannot correct internal upper/lower limb ratios. Source estimates are diagnostics, not anatomical
ground truth or approval to distort the drawing.

A scratch distal-arm depth experiment reuses the identical mesh and original colour, lifting only
the far forearm in front of the torso. It reveals the hidden forearm in custom-action frames 3/21,
but exposes a cuff at the chest and adds an unwanted patch in the neutral control. Always-front
depth is rejected. Any future explicit depth policy needs safe switching and boundary review;
duplicating antialiased coverage also needs a coverage-preserving split rather than double drawing.

## Pelvic apparel ownership refinement

The male atlas already contains its belt and split tunic in the hips image. Treating that image
only as a hidden pelvis erased those features behind the torso/legs. An explicit experimental
`pelvis_cover='front'` adapter option restores them, but placing the entire hips image in front
also reveals a blunt upper-trouser cut edge. That v4 trial is not final-polish acceptance.

One targeted generation supplied only a garment segmentation proposal. Its repainted RGB was
discarded. A registered binary mask partitions original RGBA pixels between the rear pelvis and
front belt/tunic; the original garment colour/detail is retained. Registration uncertainty at
the slit and hems remains subject to visual review, not an exact contour claim.

`dev/pelvic_overlay.py` requires explicit garment ownership, a binary registered mask and a new
destination. It preserves the source rig/reference, copies rigid geometry unchanged, and records
hashes plus pending semantic/motion review. The optional `--torso-under-pelvis` policy is necessary
when a long torso would otherwise show through garment openings. It rejects unknown interleaved
depth blocks rather than guessing. The collar adapter now preserves unrelated layer ordering.
Source-pixel conservation does not prove filtered runtime edge identity; dynamic boundaries must
be inspected separately. These remain development workflows, not automatic clothing recognition.

## 2026-11-04 resumed garment and dynamic review

The resumed run preserved the working tree and original fixture assets. Male v6
was already prepared but unrendered. It restores trousers behind the tunic slit.
Its 207-frame seven-clip build reconstructs exactly from exports and plays at
60/144 Hz in Godot with zero maximum pixel error. A rigid trouser-stub shelf
remained visible below the rear hem.

Removing that duplicate hips artwork alone removes the shelf but exposes a second
shirt hem. Waist/hip/mid-pelvis scalar torso cuts were all rejected: they trade
missing coverage for a protruding tab or a blunt front edge. A restricted original
hips underlay closes the slit, but does not repair the independently moving shirt
cutoff. No rejected cutoff became a default rule.

The experimental continuous-garment adapter (`dev/garment_ownership.py`) instead
accepts explicitly registered garment ownership and optional separate collar and
aperture backing images. It archives the original rig, preserves geometry, resets
approvals, reconstructs the current reference, and rejects overwritten destinations
or modified original leg pixels in optional completion inputs. Registration helpers
(`dev/garment_registration.py`) retain original upper torso pixels and fit only new
lower artwork to explicitly reviewed waist and hem anchors. This is not automatic
clothing detection or a two-character production acceptance.

Male v7 uses two targeted generated inputs: a continuous garment proposal and a
hidden brown-cloth completion whose interior supplies aperture backing. The failed
expanded-leg experiment was not adopted; original legs remain unchanged. All 20
frames of the sent `latest-male-walk-test.gif` match the v7 render before GIF
quantization. Independent review of 207 frames found the tested garment continuity
issues resolved. Five source-detail smear FAILs remain (the original four plus the
soft backing texture), and 65 occlusion candidates still need adjudication. The
backing is partly visible through the slit; its softness is not dismissed as wholly
hidden. v7 also passes export reconstruction and Godot 60/144 Hz playback.

**The user rejected the walking appearance.** This supersedes any implication of
complete dynamic acceptance: persistent bent knees, close foot crossing, rigid
upper-body carriage and uneven arm swing make it read as shuffling. Seam continuity
and engine reconstruction do not establish natural movement. A body-derived walk
profile is being tested separately; v7 is not a final animation pass.

The collar investigation also found that the old color-only neck heuristic deletes
brown/gold garment pixels, exposing too much neck. `remove_neck_stub` and
`install_collar_overlay` now require explicit `garment` ownership (preserve all
pixels) or `head_skin` with a registered binary mask. Color is no longer authority
to delete anatomy/clothing. Synthetic gold/brown collar fault tests cover this
ambiguity. Actual full-collar restoration is under visual review against identity.png,
not the already-defective derived v6 reference.

Resumed verification before these final additions: 460 tests ran, with 3 failures,
2 skips and 4 expected failures. All three failures were CSS browser tests: the
bundled Chromium was absent; retry with the installed `/usr/bin/chromium` failed
at process socket creation (`Operation not permitted`). No successful browser
playback claim is made. All 26 regression sets finish with zero QA status
regressions against baseline; strict comparison still reports 116 changed clips
and 102 numeric drifts, so this is not a strict pixel-baseline pass. The focused
final garment/registration/collar/pelvic set passes 41 tests.


The opt-in `natural_walk_v1` now centers stride on the sole, delays toe-off, fits
stance reach, and derives balanced arm carriage from idle. The final measured
idle/walk build has 58 idle and 20 walk frames; all ten per-clip metric columns pass.
Independent ordered-frame review finds the persistent crouched shuffle and doubled
fist resolved, with plausible far-arm occlusion at frames 14–16. It is still not a
user approval or a realtime visual-playback pass. The exact 5/6-second period avoids
rounding 0.84 seconds into a faster 20-frame/24fps playback. Nine focused tests pass;
one expected failure explicitly records missing phase-aware idle/walk transitions.
Direct idle0→walk0 shifts the near wrist by 9.157 rig units (about 29 px at this fit),
and arbitrary-phase stop can shift the near ankle by 24.20 units. These are real
remaining transition defects, not loop failures. Five source-smear FAILs and one
visibility WARN are unchanged. The profile leaves all legacy/default clips intact.

## Resumed settle-bank pixel continuity check

The resumed workspace retained the implementation but not the previous rig fixture
folders. The old `/tmp/male-keyframes.png` is the rejected crouched-walk example,
not evidence for the current motion profile. Original generated source images
were later located separately; rebuilding rig metadata from them is not an exact
restore of the previous rig revision.

A new 128px, 30 FPS procedural-hero export exposed a genuine secondary-motion
handoff bug: both settle banks began with different cloth pixels than their
registered walk frames (1103 and 1191 differing RGBA channels). Skeleton endpoint
tests alone had missed this. Settle and held clips now carry the source walk's
cloth shape in each cloth attachment frame. Both 30 FPS entry comparisons are
now pixel-identical. Both 24 and 30 FPS export regressions compare the real PNGs;
standalone-source dependency, hold continuity, and reversible cloth shapes have
focused regression coverage. This is kinematic carry during settling, not a new
cloth relaxation simulator. Motion-blurred exports and floor-length cloth need
separate validation; do not generalize the short-cape result to every garment.

The ordinary legacy-rendering path remains unchanged. Current Chromium launch
still fails at process socket creation (`Operation not permitted`), so Node
controller frame-selection proofs are not browser visual playback.

The reconstructed male puppet also passes exact entry-pixel comparisons for both
settle banks (walk frames 1 and 11 at 24 FPS), recorded in its preview folder.
This does not resolve the reconstructed art's head/collar/waist defects or its
four retained source-smear failures.

## Recovered reference-candidate rejection and focused verification

The recovered male head-only registration was retained as an explicitly rejected
experiment: local collar/chin continuity improves, but independent full-body review
finds the head too large relative to the assembled body. The source torso fit uses
lower artwork hidden by the pelvis garment. The next reference correction must
reconcile visible collar, waist/belt, pelvis, knee and sole anchors before deriving
head placement. The continuous torso source is useful art, but naively registering
its waist to the original torso bottom lowers the belt by roughly 160 source pixels.
Removing the garment-bearing hips also removes the only explicit crotch bridge;
separate leg tubes do not establish hidden pelvis coverage. Neither substitution
was silently adopted.

Focused resumed checks: 39 head/garment/ownership/pelvis tests passed; 27 natural
walk/transition/player tests ran with 26 passes and one existing expected failure
for direct legacy idle/walk switching. Five new canvas-padding tests plus the nine
original head-registration tests pass. Real-fixture whole-frame translation yields
identical rendered arrays at three idle/walk samples and identical fit scale.
The rejected candidate generates four clips / 92 frames at 256px, 24 FPS. All
per-clip motion measurements pass; the same four arm/leg source-smear failures
remain. No full-suite, strict-baseline, realtime-browser, or user visual pass is
claimed by these focused checks. Grounded holds remain frozen split stances rather
than animated breathing or a return to feet-together idle.
