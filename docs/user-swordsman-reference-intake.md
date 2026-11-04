# New supplied swordsman reference intake (2026-11-04)

The supplied 1024 × 1536 image depicts a three-quarter/front swordsman in white,
teal and gold, with long hair, ribbons, broad sleeves, long robes, a jade pendant
and a one-handed straight sword. Preserve this identity; the visible geometry is
not the supported basic-side-v1 input and is not a top-down game view.

## Completed

- Inspected the actual image. Recorded source hash, identity features, occlusion,
  approximate visible sword-axis annotations and required supplemental layers in
  `out/user-swordsman-reference-20261104/intake.json`.
- Built a standalone `reference-review.html` with the unchanged embedded source,
  magnified hand region and optional reference markers. These are review annotations,
  not rig inputs, automatic detections or per-character motion tuning.
- Existing `test_weapon_hand_frame.py`: 8 tests passed, including two synthetic
  body proportions. These do not establish that this new image has been rigged.
- Source hash and JavaScript syntax verified. Chromium display verification was
  blocked before page load by `socket() Operation not permitted`, also after an
  approved escalation. No browser screenshot or visual pass exists.

## Boundaries and next stage

Zero animation frames. No new image generation was attempted, no hidden pixels
were painted, and no other engines were tested. No production script was changed.
The earlier supplemental-hand generation denial remains in effect; this new
reference is not a pretext to retry or route around it.

The source visibly shows fingers in front of the handle, with pommel above/right
and guard below/left, but cannot prove hidden palm/thumb contact. Correct attachment
needs one hand/weapon frame AND independent finger/handle occlusion review.

A useful next stage needs a camera-specific experimental layer contract and
complete aligned layers: back/front hair, torso, arms and sleeves, hand/sword,
hidden legs/boots, rear/front robe panels and ornaments. Hidden anatomy cannot be
recovered faithfully from this single image. Do not shorten the robe or hair or
convert its view silently. Do not feed this reference into the side-view basic
pipeline or imply that top-down supports custom PNGs. Web-first idle/carry and
then walking require actual suitable assets, a suitable rig and dynamic review.

## Visible-region prototype, continued

`dev/source_region_layers.py` now provides a reusable, deterministic source-pixel
candidate extraction experiment using RGB clustering and four-connected regions.
It is coordinate-free and has no character-specific masks or joints. The current
environment lacks the earlier SAM/YOLO dependencies and weights, so this is an
explicitly limited candidate method, not a replacement semantic model.

Run:

```sh
python dev/source_region_layers.py ../88C3417B-E082-41CF-AC1D-8069A98275B8.jpeg \
  --out out/user-swordsman-reference-20261104/visible-regions
python -m unittest discover -s dev/tests -p test_source_region_layers.py -v
```

The exported candidate bundle contains 25 PNGs with crop offsets, `layers.json`,
`layers-review.html`, a complete exact `static-recomposition.png`, and a visual
candidate sheet. Its HTML embeds all layer bytes and supports independent toggles
and show/hide all. Re-reading the exported PNGs and offsets independently proves
zero changed source pixels, zero overlap and zero unowned pixels. Four tests pass,
including two different synthetic canvas dimensions and injected overlap/hole
failures. JavaScript syntax passes. Browser playback remains unverified due to
Chromium startup restrictions; this stage does not invoke other engines.

Visual review of `candidate-sheet.jpg` finds fragmented robe shading/material
regions, a mostly connected background, and a large residual details layer.
**Anatomical layer gate: blocked.** Exact recomposition proves pixel preservation
only. It does not prove that candidate ownership matches a head, arm or leg, or
that those parts have complete hidden surfaces. Do not feed these candidates into
the known-joint binder. The profile restriction and previous image-generation
refusal remain untouched; no alternative image-generation route was used.
