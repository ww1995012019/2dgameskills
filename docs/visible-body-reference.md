# Experimental visible-body reference assembly

`dev/reference_body_assembly.py` is an opt-in development adapter, not a change to
the packaged/default binder. It replaces the atlas adapter's fixed adult layout
only when reviewed, hash-bound identity evidence exists. No generated source art
is edited, painted, cropped to a new silhouette, or stretched independently by axis.

## Contract

- Head, torso and hips each need three or more named noncollinear source/reference
  correspondences, reviewed for visible semantic meaning. The existing 5% similarity
  residual limit is unchanged. A passing residual is not identity approval.
- Collar endpoints must be explicit. Hip/waist joints and both limb reference chains
  are annotated evidence. Joint locations can be inferred under clothing, but they
  must never replace the separate review of visible garment anatomy.
- Limbs use one uniform scale from reference chain length. Segment-length mismatch
  above 5% of the full chain is rejected. The source's local elbow/knee bend is retained;
  root-to-wrist/ankle axes align to the reference. This is not a promise of matching
  all intermediate joint positions. Both original boot and hand pixels remain.
- The weapon retains its reviewed physical length ratio to the near arm chain,
  independent of source-image resolution. Its grip attaches to the hand; an
  optional reviewed grasp point and directed axis replace the palm-center default. The identity need not contain a weapon, so this
  is deliberately not a claim of identity-derived sword length.
- Source and identity file hashes are required. Output must be a new directory.
  Fits and canvas containment are checked before writing. Output is an unapproved
  known-joint binder manifest and static composite, never a promoted existing rig.

## Independent checks

`compare_visible_profile` is for separately reviewed, upright final composites of
the same pose, not invisible source landmarks or arbitrary animation frames. It
requires crown, chin, collar, belt/waist, pelvis, both knees and both soles. A hidden
or missing point blocks this diagnostic; do not mark it visible to obtain a pass.
Its 4% stature-level and 15% head/body-ratio limits are fixed development diagnostics,
not automated anatomy or identity recognition. Characters without a visible belt
must use an explicit visible waist feature and record what was actually observed;
if the garment hides every usable waist/pelvis anchor, this contract is unavailable.

`compare_extent` independently checks homologous visible endpoint spans after the
whole-part fit. A difference over 15% blocks the extent diagnostic. This prevents
leg-length agreement from silently certifying boot width. It never authorizes
anisotropic deformation or supplies missing width annotations.

## Recovered male experiment

Fixture evidence is in `out/recovered-fixtures-20261104/male/`:
`body-reference-annotations.json`, `body-reference-v1/reference_assembly.json`,
`body-reference-v1/assembled.png` and `body-reference-v1/visual_review.json`.
These ignored output fixtures are not packaged skill assets.

Independent full-resolution review found head/body, collar and belt substantially
closer to the identity than both previous versions. Knees and soles are distinct.
The candidate remains rejected: arms/hands are too bulky, shoulders/chest broad,
boots too heavy, and hands/sword conceal much of the central pelvis split. Reviewed
heel-to-toe spans after leg-length matching are approximately 47% and 21% larger
than their corresponding reference spans. These extent diagnostics agree with the
pixel review; simply rescaling the full legs would shorten their fitted length.
No new motion export or user static approval has occurred. A complete visible-profile
pass is deliberately absent because the central pelvis cannot be independently
assessed in this composite. No art-generation budget was reopened.

## Second-character boundary

The female source and identity were inspected. The separate hip art includes a
belt/waistband and upper side contours hidden beneath the identity's long jacket.
Its bottom crop boundary is not an anatomical landmark. There is not yet a reviewed
set of three distributed visible homologous hip features for this fixture. No
female reference assembly or two-character acceptance is claimed. Using hidden
waist points or arbitrary crop-edge correspondences would repeat the male error.
The next step requires an explicit visible/occluded garment ownership contract,
then two-character static acceptance, before advancing this experimental path.

## Initial checkpoint verification

17 focused tests cover two limb proportions/resolutions, rotation, pose retention,
segment faults, missing/hidden body landmarks, oversized heads and boots,
source-preserving raster output, hash changes, clipping and refusal to overwrite.
This is focused verification of an experimental adapter, not a full-suite,
strict-baseline, engine-playback, or user-acceptance claim.

## Supplemental-art continuation (same resumed task)

Later user authorization to test generated characters and use other methods when
one image is insufficient was received. This continuation used five built-in image
calls: two arm attempts, two leg attempts, and one garment-separation attempt. Each
initial arm/leg defect was recorded before one targeted edit. The prior generation
history was not reset. All raws and versioned candidates were retained in the
recovered fixture tree; `male/supplemental-generation-ledger.json` records hashes.

Latest static candidate: `male/body-reference-low-carry-v9/assembled.png`.
Its pixels are identical to v8; v9 corrects the metadata contract only.

- Supplemental arms remove the grossly bulky forearms/fists and supply a relaxed
  far hand. The original reference elbow pose and far-hand proportions are still
  not exact matches.
- Supplemental legs bring reviewed heel-to-toe extent errors to approximately 7%
  near and 2% far, versus 47%/21% previously. No independent-axis squeeze was used.
- The old continuous torso and garment-only supplements were rejected by the
  unchanged 5% fit limit (6.0% and 7.3% residuals). They were not forced into place.
- A new garment-only layer was registered to the original hip garment with 2.27%
  residual, then composed into the torso's front artwork. The original complete
  hips remain behind both thighs as the crotch bridge. This is explicitly supplied
  replacement artwork, not a claim of source-pixel identity. No manual garment
  deletion or painted crotch fill was used.
- An explicitly measured thumb/index opening replaces the palm-centroid grip.
  Its directed axis determines a low-forward sword carry. The reverse direction
  trial intersected the forearm and was rejected. Independent static review finds
  the shorts boundary, oversized boots and obvious grip-placement defects resolved;
  no new obvious holes, doubled belt or exposed backing edge were found. The sword
  still occludes part of a thigh/knee, and residual arm differences remain.

Implementation changes: `head_attachment` is now explicit and required. These
sources inherit the original `cap_cover` contract, rather than being assigned a
new `socket` contract. The head anchor is measured on the final torso upper core.
The normal cap-contact check passes unchanged and the known-joint binder succeeds.
There was no fallback from an approved socket asset or relaxation of socket rules.

Arm/leg root-to-tip axes now align to the reference while preserving the original
local bend. Weapon size is based on its physical ratio to total arm chain length,
not the raw arm image's scale factor, so changing source resolution cannot shrink
it. Optional hand registration supplies a reviewed grip point and directed axis.
Optional front-garment input requires explicit torso ownership and the pelvis
behind both legs; output retains the existing eight-layer binder contract.

23 focused tests now pass, covering the earlier checks plus invalid hip metadata,
both knees below feet, missing name/head contract, atomic failure cleanup,
source-resolution-invariant weapon size, grip overrides and front ownership.
53 existing head/atlas/garment tests also passed before the latest opt-in additions.
No full-suite or strict-baseline result is claimed. Numerical idle/walk/settle tests
are in progress for the new bound fixture; static review does not certify motion.

## Motion readability continuation

The v9 bound fixture exports 92 frames / four clips with 0 FAIL and 0 WARN. Atlas
reconstruction matches all 92 source frames, both settle-entry PNGs are exactly
pixel-identical to their source walk frames, and the reduced-clip JS controls pass.
Independent ordered-frame review nevertheless found the far arm occluded across
much of the backward swing and indefinitely in one held bank. The passing numeric
occlusion detector did not establish a readable settled silhouette.

`derive_free_arm_carriage` now computes an opt-in `arm_f` override from the complete
idle cycle's body-relative wrist reach. It averages out breathing, normalizes by
arm length, and retains the natural walk's swing amplitude and relaxed elbow.
No character-specific angle is coded. Two body proportions at two scales verify
reach preservation. This improves the forward swing but does not by itself solve
a frozen backward-swing hold.

An additional explicit `gait.walk.settle_relax_free_arm` boolean returns only the
free arm to neutral carriage through the existing reversible settle weight. The
four new tests cover unchanged default/walk poses, exact entry and reversible
endpoints, unchanged feet/weapon arm and fixed bone lengths, and invalid options.
The opt-in v11 export is being reviewed; numerical quality and static hold
readability are separate results. The default profile and prior exports are not
silently altered.

## Latest verified checkpoint: v11

Independent review of all four review sheets and the final settled frame now finds
the persistent one-armed-looking hold resolved. The far forearm and relaxed hand
can both be followed in the final pose. Brief walk-phase overlap remains, and the
far hand/guard junction is somewhat crowded. No new attachment, garment or stepping
regression was seen. This remains sampled/ordered-frame judgment, not blanket
identity, aesthetic or timed-playback approval.

Final evidence for `male/body-reference-v11-preview`:
- Four clips, 92 frames, 0 numeric FAIL / 0 WARN.
- 92/92 atlas reconstructions exactly match source frame pixels.
- Both settle-bank entry frames have zero differing RGBA channels against their
  corresponding walk frames (1 and 11).
- Reduced-clip JS controller controls pass; an 8-second scripted-controller GIF is
  in `male/body-reference-v11-controller-proof/proof.gif`. It records actual
  exported JS frame selection, not browser screenshots.
- Godot headless import and all four clips pass at both 60 and 144 Hz: 92 frames
  checked per run, maximum pixel error zero. The first launch could not create its
  default home data directory; the successful test uses supported XDG application
  data/config/cache directories in the writable task temporary area.
- 25 reference-assembly tests, four opt-in settle tests, and the existing focused
  head/atlas/garment/natural-walk/transition/player groups pass. One existing expected
  failure still documents direct legacy idle/walk switching. Packaging line-ending,
  shared/mode sync and `git diff --check` pass. Skill archives were rebuilt.

The full aggregate suite and strict 26-set baseline were not rerun in this resumed
pass. Female full-body acceptance, live browser visual playback and user approval
are still pending. No commit or publication was performed.
