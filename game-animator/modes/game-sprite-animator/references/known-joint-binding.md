# Reuse complete layers with known joints (side-view humanoids)

Use `scripts/bind_known_joints.py` when full aligned RGBA layers and measured or template joints
already exist. No image generation, registration search, hand-hint pictures or silhouette template
matching takes place. This is an additional numerical entry, not a way to approve incomplete art or
reopen a blocked generation job. Original source pixels are retained (output layers are cropped,
with offsets); coordinates always refer to the common input canvas.

Required layers: `head`, `torso`, `hips`, `arm_near`, `arm_far`, `leg_near`, `leg_far`.
Optional: `weapon` (one single-handed sword). Provide `order` with every layer once, back to front.
Each layer path is relative to the manifest. Cropped layers can instead use
`"canvas": [1024,1536]` and `"head": {"image":"head.png", "offset":[320,100]}`.
Padding preserves RGBA pixels exactly; source clipping and negative offsets are refused. Supply joints:

- each arm: `shoulder`, `elbow`, `wrist`;
- each leg: `hip`, `knee`, `ankle`;
- hips: `hip`, `waist`; head: `head_base` (neck attachment);
- weapon if present: `grip`, coinciding with the near hand and weapon art.

```json
{
  "name": "Character",
  "layers": {"head": "layers/head.png"},
  "joints": {"head": {"head_base": [350, 220]}},
  "order": ["head"]
}
```

The fragment illustrates syntax only; add all required layers and joints. Coordinates are finite
`[x,y]` pixels, origin top-left. Images must have a common canvas, alpha, and complete limb roots.
The skeleton adapts measured lengths and attachment positions; it does not require covering a
fixed silhouette. Structural checks (bone support, pair lengths, torso/neck continuity) remain.
Near/far limbs still share runtime lengths and must satisfy the existing 25% difference guard.

```bash
python scripts/bind_known_joints.py --manifest character/rig_input.json --out out/rig-v1
python scripts/generate.py --character out/rig-v1/character.json --clips idle,walk --preset hd --no-fx --out out/preview-v1
python scripts/qa_motion.py out/preview-v1
python scripts/visual_review.py out/preview-v1
```

Keep the manifest and layers to reuse on later motion changes. Binding writes provenance hashes
and explicitly leaves visual/user acceptance pending. Existing destinations are refused; export
into a new version. Export is staged so rejected inputs do not leave a partially accepted rig.
The input manifest is archived for provenance; its original relative paths are not rewritten.

Newly bound arm/leg roots are held to their skeleton attachments. Newly bound arms protect the hand beyond the wrist with a rigid distal region and a smooth
forearm blend (`tip_lock`). Older rigs retain their existing behaviour. Boots already have rigid
foot blending; heads and weapons remain rigid. Full armour material segmentation is not inferred.
Measured-foot idle derives standing support height from the soles, avoiding the default crouched stance on differently proportioned art. Measured-foot walking eases swing lift near contact to keep pelvis support smooth across loops.

For a rejected bind, first inspect joint coordinates, common-canvas alignment, layer completeness
and the grip. Fix numerical/geometry problems without repainting. A missing limb, extra limb,
incorrect face or absent hidden texture still requires an art correction. This entry neither
segments arbitrary illustrations nor invents hidden clothing. Review actual idle/walk before
expanding the motion range; synthetic validation is not real-art or engine-playback acceptance.
