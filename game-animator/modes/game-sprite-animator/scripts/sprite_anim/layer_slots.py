"""The fixed layer contract for layered puppets: which layers exist, back to front, and the prompt
that produces each one. Every character uses this same list, so nothing here may name a character."""

KEY_COLOR = (255, 0, 255)   # flat background of every layer picture

# Asks for a picture that passes the contract, from a description or from any earlier picture.
REFERENCE = """Full-body 2D game character: {who}. {style}.

Pose, fixed for every character: strict side view facing right, standing in a small walking stride, both feet flat on the same ground line, near arm reaching forward and slightly bent, far arm back and slightly bent, each arm clear of the torso and the legs, head level. Weapon, if any, held in the near hand, pointing forward and up. Long hair and loose cloth hang or trail behind the body and do not cross the legs or arms.

Framing: the whole figure in frame, about 85 percent of the canvas height, with margin on every side and nothing cropped.
Lighting: even flat lighting, no glow, no cast shadow, no ground, no text.
Background: one flat pure magenta #FF00FF. The character uses no magenta or pink-purple colours."""

COMMON = """This is a production layer-separation task for a 2D game puppet. Output exactly one layer of this character.

KEEP ONLY: {keep}
REMOVE COMPLETELY: {remove}

Rules:
- Same canvas size. Same pose. Same position and same scale as the input: every kept part stays where it is in the input, do not move, zoom, recenter or straighten it.
- Repaint what the removed parts were hiding with full sharp detail, matching the same fabric, pattern, line weight and cel shading. Never blur, smear or fade. Close the shape with the same dark outline where it was cut.
- Same art style and colours as the input.
- Background: one flat pure magenta #FF00FF everywhere outside the kept layer. No shadow, no ground, no text, no other objects."""

# name: (what to keep, what to remove, required). Back to front, as the puppet draws them.
# An optional layer is left out for a character that has nothing of that kind.
SLOTS = {
    "hair_back": ("all the long hair that hangs behind the head and back, complete from the scalp down to its tips, plus any hair ribbons hanging behind the head",
                  "the face, the top of the head, every hair ornament, the whole body, all clothing, both arms, both legs and the weapon", False),
    "cloth_back": ("only the loose cloth trailing BEHIND the body: the rear robe tail, rear sash or cape, from its rear attachment seam to its tips. Keep only the trailing rear portion even if it was sewn to a wraparound skirt; reconstruct the hidden attachment as matching fabric",
                   "the head, hair, torso, the entire belt and waist ring, both arms, both legs, the weapon, every short front thigh panel or apron, all front pendants, cords and tassels, and any fabric in front of or between the legs. Front skirt panels belong to the torso layer, never this layer", False),
    "arm_far": ("the rear arm only: the arm whose hand is further to the LEFT of the picture, which holds no weapon, complete from the shoulder to the fingertips, with its whole sleeve and cuff",
                "the head, hair, torso, the other arm that reaches to the right of the picture, both legs, the weapon and all other clothing", True),
    "leg_far": ("the rear leg only: the leg whose foot is further to the LEFT of the picture, complete from the hip to the sole with its trouser and boot. Show the upper thigh fully, as if nothing covered it. Preserve the sharp trouser seams and fabric fold contours; reconstruct the hidden thigh with the same crisp folds, not a broad airbrushed gradient",
                "the head, hair, torso, belt, robe, both arms, the other leg whose foot is further right, the weapon and every loose cloth, panel or sash", True),
    "leg_near": ("the front leg only: the leg whose foot is further to the RIGHT of the picture, complete from the hip to the sole with its trouser and boot. Show the upper thigh fully, as if nothing covered it. Preserve the sharp trouser seams and fabric fold contours; reconstruct the hidden thigh with the same crisp folds, not a broad airbrushed gradient",
                 "the head, hair, torso, belt, robe, both arms, the other leg whose foot is further left, the weapon and every loose cloth, panel or sash", True),
    "hips": ("the hips only: the garment worn under the outer clothing, from the waist down to the crotch, in the same material as the top of the legs, as one solid closed shape as wide as the waist. It fills the whole space behind the belt and behind every hanging panel, with no gap, and the bottom edge stops at the crotch",
             "the head, hair, chest, belt, every outer robe, panel, sash, tassel and ornament, both arms, both legs below the crotch, the weapon and every loose cloth", True),
    "torso": ("the torso layer: the entire neck including the exposed skin between the jaw and collar, full collar, chest, belly, waist belt and hips of the garment, plus only what hangs in front of the thighs: short front panels, belt ornaments, cords and tassels, as one complete closed shape. Do not leave an empty gap above the collar where the neck belongs",
              "the head, face, all hair, both arms, both shoulder plates, both sleeves, both hands, the weapon, both legs, and ALL rear skirt fabric below the belt, including short side panels as well as long robe tails. In the fixed RIGHT-facing pose, remove every below-belt flap extending toward the LEFT behind the thighs, even if it has embroidery. Only the front apron on the RIGHT side of the thighs stays. The rear lower edge of this torso stops at the hip, not at a skirt hem", True),
    "head": ("the head: face, ear, the hair on the skull with its hair ornaments, down to the jaw, as one closed shape. Cut long hair off cleanly at the jaw line",
             "the neck, the whole body, all clothing, both arms, the weapon and the long hair below the jaw", True),
    "weapon": ("the weapon held in the hand, complete from pommel to tip, with the hilt fully visible as if no hand held it",
               "the whole character: head, hair, body, clothing, both arms and both hands", False),
    "arm_near": ("the front arm only: the arm whose hand is further to the RIGHT of the picture, the one holding the weapon if there is one, complete from the shoulder to the fingertips, with its whole sleeve, cuff and hand. If the hand grips something, the fingers stay closed around nothing",
                 "the head, hair, torso, the other arm whose hand is further left, both legs, the weapon and all other clothing", True),
}

# Optional landmark-only images, extracted from each finished arm layer. They
# are never drawn: loose sleeves can extend farther than the fingers, so their
# silhouette alone cannot locate a wrist reliably.
HAND_HINTS = {
    "hand_near_hint": "arm_near",
    "hand_far_hint": "arm_far",
}


def hand_prompt():
    return COMMON.format(
        keep="only the exposed hand and all its fingers at the end of this arm, from the wrist to the fingertips, in their exact original position",
        remove="all fabric, the entire sleeve, cuff, bracelet, ribbons, the upper arm and shoulder, and everything except the hand and its fingers")


def prompt(slot):
    keep, remove, _ = SLOTS[slot]
    return COMMON.format(keep=keep, remove=remove)
