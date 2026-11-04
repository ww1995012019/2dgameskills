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
Padding preserves RGBA pixels exactly; source clipping and negative offsets are refused. Layers need
an alpha channel: RGBA, or grey/palette PNGs with alpha or a transparent index, which are converted to
RGBA without changing a pixel. Opaque RGB layers are refused. Supply joints:

- each arm: `shoulder`, `elbow`, `wrist`;
- each leg: `hip`, `knee`, `ankle`;
- hips: `hip`, `waist`; head: `head_base` (neck attachment);
- weapon if present: `grip`, coinciding with the near hand and weapon art (within 2% of the near
  arm's length, at least 2 px, of both).

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
Near and far limbs each keep their measured lengths at runtime (`thigh_f`, `shin_f`, `up_arm_f`,
`lo_arm_f`), so a far limb is no longer stretched to the near one's size; the 25% difference guard
remains. The far hip seat moves by the leg-length difference times the standing reach, so both legs
stand equally extended: no limp, both feet on the floor. Rigs without these fields keep shared lengths.
The head's size is measured along its own axis (neck to the art's centroid), so a tilted head counts
as upright. A backward-bent rest arm whose wrist nearly meets the shoulder (closer than 5% of the
arm) gives no line to mirror its elbow across and is refused.

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
New bindings also set `source_frame` on their deformable layers: binding and playback use the same
fractional curve frames, and only added inward bending compresses the image. An unchanged source
pose (including uniform rotation/translation/scale) therefore retains its source mesh, instead of
shifting vertices or compressing an already painted elbow again. Existing rigs without the flag
retain their previous output; rebind from the archived manifest to opt into the corrected mapping.
This preserves the supplied rest shape, not hidden anatomy or the appearance of arbitrary extreme poses.
Invalid finite/nonfinite body values, zero/negative bone lengths, malformed joint seats and unsafe
soft-IK settings are rejected when loading a body, before they can corrupt later actions.
Measured-foot idle derives standing support height from the soles, avoiding the default crouched stance on differently proportioned art. Measured-foot walking eases swing lift near contact to keep pelvis support smooth across loops.

For a rejected bind, first inspect joint coordinates, common-canvas alignment, layer completeness
and the grip. Fix numerical/geometry problems without repainting. A missing limb, extra limb,
incorrect face or absent hidden texture still requires an art correction. This entry neither
segments arbitrary illustrations nor invents hidden clothing. Review actual idle/walk before
expanding the motion range; synthetic validation is not real-art or engine-playback acceptance.

For explicitly reviewed mechanical head-stem artwork, an optional manifest
`"head_attachment": "socket"` selects an insertion contract instead of the default skin/collar
cap-cover contract. The supplied stem must be narrow, centered, connected and fully supported
inside the torso's upper core, with bounded insertion and substantial exposed head. This is never
auto-selected after normal binding fails. It does not infer front/rear painted socket surfaces or
make the limbs rigid; those still need material-specific artwork and dynamic visual review.

New bindings enable isolated attachment checks on every generated frame. Each arm/leg must retain
connected pixels from its own shoulder/hip through the proximal bone, and contact its separately
rendered parent. An opaque torso cannot conceal a missing arm strip from this check. Output
`attachment_scope.json` records the actual frames and parts checked. Pixel continuity is not a
promise that every occluded forearm reads clearly; inspect clothing and crossed limbs visually.

The unoccupied far arm in a new binding's walk is centered below its own shoulder using measured
upper/lower lengths and the source elbow bend. This avoids carrying an empty fist forward beside
the sword while its forearm is hidden behind the torso. Idle preserves the source carried pose,
and the near weapon hand is unchanged. Wide hems can still occlude a backward-swinging wrist.

### Optional hand-and-weapon frame

For reviewed held-weapon artwork, `weapon_hand_binding: true` records the source
blade-to-forearm angle in `body.weapon_hand_angle`. The hand pixels, palm offset
and blade then share wrist rotation rather than agreeing only on a grip point.
Authored wrist deviation is softly limited to ±35° and excess is reported by
joint QA. Ground correction moves the hand together with the blade. The default
is unchanged; this conservative contract is intended for bounded carry motion,
not automatic approval of attack clips or the source hand's anatomy.

Natural walk can additionally use `held_weapon_carry: "low"` to keep the loaded
arm beneath its own shoulder with reduced swing. This requires the measured
hand frame and cannot accompany `arm_n` or `wep_sway` overrides. It does not fix
an open/incorrect source fist: visually review thumb opposition, closed fingers,
handle enclosure, guard/pommel orientation and the full moving arm separately.
