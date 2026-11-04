# Rejected real-art trouser split

These are **failure fixtures**, retained after the user rejected the rendered
characters. They are not accepted character artwork, repaired rigs, or evidence
that the game has passed this skill's visual review.

The source is `ww1995012019/vsgame`, commit
`3640b6a988c770c886b04e05551bb3ff2c735594`. Its independent JavaScript renderer
split a complete painted trouser image down a vertical line between the hips,
then mapped each half with its own three leg bones. It supplied no independent
pelvis/crotch bridge. The shared painted boundary therefore separates during IK:
Hanfeng has a visible vertical gap even while idle, and Lieying's deep crouch
opens and overlaps the trouser fabric below the waist. Both WebGL and Canvas
reproduced the defect. The game and its original PNGs were not modified here.

Original atlas SHA-256:

- Lieying: `d3154848da72396cd0f79d7baaffc834def75070693f824808a806cb869d2a0c`
- Hanfeng: `aaa9ccfb58d9747de0ba54a163c50899be3062a062e388430eceea6ada9551ad`

Each `source.png` is the original atlas's first pose, normalized from its
443.5-pixel cell to the renderer's 448-unit source grid with bilinear resampling.
It is an audit reference, not repainted or completed character art. `idle.png`,
`crouch_half.png`, and `crouch_full.png` are clean RGBA crops from the actual
game's `OriginalSkin` WebGL renderer at `elapsed=0`, facing right, with crouch
blend 0, 0.5 and 1. The 320 × 180 crops retain the waist/hip defect and background
transparency. No diagnostic lines or painted repair pixels are baked in.

The matrices are the game's actual affine bone transforms. Their translation
and the solved skeleton receive the same original canvas offset and crop-origin
subtraction, so cropping preserves every numeric measurement. Landmark weights
come from the game's `partWeights` at the two hip roots; they map correctly to
the solved hip joints. Seam weights come from that same function at the shared
cut boundary, restricted to original source pixels with alpha greater than 96
at all four surrounding texels. Thus a correct landmark result must not clear
the discontinuous clothing seam.

`manifest.json` is input to `shared/scripts/audit_skin_binding.py`. Both fixtures
must fail its fixed seam gate, with faults located by clip and frame. The
regression in `dev/tests/test_split_pants_regression.py` verifies that the
correctly aligned hip landmarks do not override a broken seam. Those landmarks
use the game's declared joint positions, not independent anatomical ground
truth: their agreement cannot certify that the original joint placement is
correct on the painted character. A numeric seam fail is established here;
full character anatomy still requires visual review of source and moving art.

Large full-body comparison sheets and the isolated near/far-leg diagnostics
remain outside this development fixture. These files are not included in the
distributed skill packages.

## Meaning of the numeric samples

The manifest samples call the game's continuous `partWeights(point)` function
and apply its declared linear-blend skinning matrices directly. They measure
continuity of those declared source points, not exact final GPU pixel locations.
The renderer instead computes skinning at mesh vertices and interpolates inside
each triangle; texture filtering, alpha coverage and draw order then also affect
the visible raster.

A separate forward-mapping comparison evaluated the same retained landmarks
and seam samples on the actual 42-cell WebGL and 16-cell Canvas source meshes.
The maximum difference from direct point-wise LBS across the three poses was:

| Character | WebGL mesh, 42 cells | Canvas mesh, 16 cells |
|---|---:|---:|
| Lieying | 0.1225 px | 0.7287 px |
| Hanfeng | 0.0542 px | 0.3799 px |

These are differences between geometric mappings at the declared sample points,
not a bound on all pixels or a renderer-wide accuracy claim. The actual 42-cell
mesh's maximum shared-boundary separation remained 1.6651 / 33.6547 / 46.3002 px
for Lieying and 8.5143 / 63.1946 / 105.0088 px for Hanfeng (idle / half crouch /
full crouch). The negative result therefore remains unchanged, and the frozen
RGBA crops independently show transparent openings. Future audits of final mesh
continuity should export actual shared vertices or triangle/barycentric mapping;
direct point weights must not be advertised as final raster ground truth.
