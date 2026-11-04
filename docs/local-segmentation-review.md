# Local segmentation review (experimental, web-only)

`dev/review_segmentation.py` adapts existing binary masks into an offline static review page. It does not run a model or upload images. Mask selection is explicit, separate from generic code. Candidate names and scores are supplied annotations, not proof of semantic ownership.

## Reuse

Create a JSON list with `name`, `mask` (path relative to the JSON file), `model_score` (optional finite 0–1 estimate), and `notes`. Masks must be binary 0/255 on the full source canvas. Cropped, resized, empty and soft masks fail validation; the tool never silently registers or rescales them.

```sh
python dev/review_segmentation.py source.jpeg selection.json --out review-output
python -m unittest discover -s dev/tests -p test_segmentation_review.py -v
node dev/test_segmentation_review.js review-output
```

Open `review-output/review.html` locally. It embeds all assets and has cutout, source and mask-overlay modes, per-candidate visibility, isolate, show-all and hide-all controls. A checkerboard exposes missing surfaces. `review.json` contains original image SHA-256, mask SHA-256 values, source canvas, zero offsets, exclusive-end bounds, model estimates, limitations and a binding gate. `candidate-*.png`, `mask-*.png` and `visible-composite.png` are independently inspectable source-coordinate outputs.

The report always says `needs_semantic_review_not_bindable` and `binding_gate.allowed=false`. There is no transition to binding or motion export. Semantic review, complete-part/hidden-area preparation, known joints and motion review remain separate work. A high model score cannot release any gate.

## Swordsman experiment, 2026-11-04

Input: 1024 × 1536 source JPEG. Existing local SlimSAM q8 masks were selected from the prior experiment's visual assessment, including deliberately overlapping fine-grained and composite candidates. No new inference was run by this adapter. Twelve masks retain **287,604 unique source pixels**, with **49,391 overlap pixels**. Selected pixels cover **18.285% of the full rectangular canvas**, not 18.285% of the character. No foreground silhouette is known, so anatomical coverage is not measured. The remaining 1,285,260 canvas pixels include both background and unselected character surfaces.

Independent Pillow compositing reproduces all selected source RGB pixels exactly and matches the exported RGBA composite. Hidden-surface pixels: 0. Animation frames: 0. Visual inspection shows substantial missing torso/robe regions, holes at shoulder boundaries, and stray head/ribbon fragments. Good exposed hand/face/boot fragments are not sufficient for a complete rig.

Three Python test methods pass, including two canvas sizes, exported-PNG round trips, overlap accounting, input fault injection, high-score gate preservation, and script-injection escaping. Source-region tests were also rerun separately. These synthetic two-size checks are NOT two-character semantic acceptance.

The Chromium smoke test is supplied but **blocked, not passed** in this executor: Chromium aborts before page load because its process-singleton socket creation returns `Operation not permitted`, including the escalation attempt. Browser rendering, interaction and mobile layout remain unverified here. No Godot or other engine tests were run. This adapter changes development review tools only; production skill code and packages are unchanged.

## Reversible visible-layer ownership

The page now supports explicit per-candidate assignment to named anatomy, garment, or accessory layers. This is an annotation of **all pixels of that candidate**, not a semantic split of a mixed candidate. Original masks and source pixels are never edited. Assigning the same target merges visible coverage only; it never makes a complete part.

Conflicting or partly unassigned overlaps remain magenta in the ownership view. “Claim overlapping pixels” explicitly gives a candidate priority at shared pixels; the latest claim wins. Release removes its priority. Changing its assignment clears its claim. Undo restores assignments and priorities, including Reset. Visibility and isolation are inspection controls only and cannot change ownership. The ownership view always includes all candidates.

Download ownership JSON to preserve assignments, claim order, reversible edit history, source and mask hashes, resolved/unassigned/conflict pixel counts, and the blocked binding gate. Changes otherwise live only in the current tab. The download is a review recipe, not a rig export or a complete-layer image. Reapply it only to the identified source and masks; automatic import is not implemented.

Run `node dev/test_segmentation_ownership.js` for pure logic checks without Chromium. These cover conflicting and unassigned overlaps, three-way last-claim precedence, release, reassignment, undo/reset, same-target visible union, provenance, and unchanged masks. Browser tests also include assignment controls but remain unrun under the previously reported socket restriction.

The local swordsman ownership build is `slimsam-local/web-ownership-review/review.html` alongside, not replacing, the earlier inspection export. Its additional actual-mask logic verification checks all 1,572,864 canvas pixels: initially 238,213 singly covered pixels remain unassigned and 49,391 shared pixels remain unresolved. An explicit test claim covers exactly the selected candidate's source mask, and undo restores the initial counts. This test does not save any semantic decisions into the page and does not constitute visual or anatomical validation.
