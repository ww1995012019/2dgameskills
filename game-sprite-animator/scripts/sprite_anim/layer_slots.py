"""The fixed layer contract for layered puppets: which layers exist, back to front, and the prompt
that produces each one. Every character uses this same list, so nothing here may name a character."""

KEY_COLOR = (255, 0, 255)   # flat background of every layer picture

# Apply at reference/arm generation, before landmark-only hand hints. These are
# species-aware requirements, not an instruction to redraw an accepted layer.
NATURAL_HANDS = """Hands: anatomically coherent, proportionate palms and fingers appropriate to the
character's species. Empty hands rest in a relaxed semi-closed pose: gently curved fingers,
small uneven finger spacing, a readable thumb and a neutral wrist continuing the forearm.
Clawed hands keep their species' claws but relax the finger joints; claws alone do not require
a threatening grasp. Avoid rigid open palms, fan-splayed fingers, spider-leg fingers, excessive
hooking, hyperextended wrists, fused or extra digits and tiny substitute hands. Preserve the
visible digit count of the identity reference; do not force five human fingers onto a creature.
A weapon hand has a secure closed grip with the thumb opposing the fingers, wrist aligned
with the forearm. Do not relax or open a holding hand. An explicitly requested expressive hand
pose takes precedence, but must still have coherent anatomy."""

NATURAL_NECK = """Head and neck: the jaw, neck column and shoulders form one anatomically continuous
structure. Preserve the head's identity and proportions. The neck enters the collar naturally;
no pasted-on head, floating skull, flared triangular skin flap, shelf-shaped neck base, hard
horizontal/diagonal cut line or duplicated neck. An internal overlap is unoutlined and hidden
inside the matching torso neck, never laid over the outside/front of a collar or scarf.
Do not repaint a removed collar as skin or scales. If the source neck/hand pose is defective,
reject the source and repair that stage; do not change accepted registration to hide it.
When separating the head, COPY the VISIBLE neck contour from the registration plate. Its
bottom follows the existing skin/scales-to-collar boundary, including the original diagonal
or curved contour. Do not replace it with a straight rectangular stump or extend neck colour
over any fabric visible in the final composite. The torso already supplies hidden neck overlap.
Any hidden extension stays within the existing torso footprint and must be behind the original
source-verified front collar; its cut edge must never become visible. Do not enlarge a collar
or add a patch to conceal a detached or incorrectly skinned neck."""

REFERENCE_HAND_REPAIR = """Repair the EMPTY HAND gestures in this full-body registration plate.
Keep the same full canvas, side-view pose, scale, head, face, neck, torso, limbs, armour,
clothing, feet, accessories, colours and background. Keep each wrist in its original position
and keep both complete arm chains. Change only the finger curl of an empty hand into a
comfortable relaxed semi-closed resting gesture. The fingers settle close together with small
uneven bends; the thumb rests naturally beside the palm. Keep species-specific claws and
their original length without a threatening spread or a grasp around an invisible object.
Any hand actually holding a weapon keeps its original secure grip and weapon unchanged.
Do not make a new character illustration or change the body pose. Keep all empty canvas.
Output the complete corrected registration plate, not an enlarged hand or a contact sheet.
""" + NATURAL_HANDS

# Asks for a picture that passes the contract, from a description or from any earlier picture.
REFERENCE = """Full-body 2D game character: {who}. {style}.

Pose, fixed for every character: strict side view facing right, standing in a small walking stride, both feet flat on the same ground line, near arm reaching forward and slightly bent, far arm back and slightly bent, each arm clear of the torso and the legs, head level. Weapon, if any, held in the near hand, pointing forward and up. Long hair and loose cloth hang or trail behind the body and do not cross the legs or arms.

Framing: the whole figure in frame, about 85 percent of the canvas height, with margin on every side and nothing cropped.
Lighting: even flat lighting, no glow, no cast shadow, no ground, no text.
Background: one flat pure magenta #FF00FF. The character uses no magenta or pink-purple colours.
""" + "\n" + NATURAL_NECK + "\n" + NATURAL_HANDS

COMMON = """This is a production layer-separation task for a 2D game puppet. Output exactly one layer of this character.

KEEP ONLY: {keep}
REMOVE COMPLETELY: {remove}

Rules:
- If two images are supplied for a repair, the FIRST is the full original registration plate and controls all positions, sizes and pose. The SECOND is the previous failed isolated layer: correct it, but do not copy its wrong scale or extra content. Output only the requested layer.
- Treat the input as a full-canvas registration plate, not as an illustration to recompose. Keep all the empty canvas. An isolated small part must remain small in its original location; never enlarge it to fill the image.
- Same canvas size. Same pose. Same position and same scale as the input: every kept part stays where it is in the input, do not move, zoom, recenter or straighten it.
- Repaint what the removed parts were hiding with full sharp detail, matching the same fabric, pattern, line weight and cel shading. Never blur, smear or fade. Close exposed silhouette edges with the same dark outline. At an internal attachment cut (neck base or shoulder root), keep the overlapping material continuous and leave the cut edge UNOUTLINED; an outline across the overlapping neck would become a false seam.
- Same art style and colours as the input.
- Background: one flat pure magenta #FF00FF everywhere outside the kept layer. No shadow, no ground, no text, no other objects."""

# name: (what to keep, what to remove, required). Back to front, as the puppet draws them.
# An optional layer is left out for a character that has nothing of that kind.
SLOTS = {
    "appendage_back": ("ONE complete biological appendage attached behind the pelvis, from its narrow reconstructed hidden root through its complete original curved silhouette to its whole tip. Keep the appendage's own scales, spines, tip armour and painted details. Reconstruct only enough scaled root beneath the rear pelvis for a covered overlap, without retaining the body mass it emerges from. The pelvic body, buttock muscle and hip armour are NOT its root. No outlined cut edge. This is one whole rear appendage, not fabric, and will remain a rigid source shape following the pelvis",
                       "the head, hair, neck, chest, belt, the entire pelvis and buttocks, all hip and thigh armour belonging to the body, hips garment, both arms and hands, both whole legs and feet, every piece of cloth, every weapon and every other object. Keep no duplicate body mass, thigh-shaped branch or detached fragment", False),
    "hair_back": ("all the long hair that hangs behind the head and back, complete from the scalp down to its tips, plus any hair ribbons hanging behind the head",
                  "the face, the top of the head, every hair ornament, the whole body, all clothing, both arms, both legs and the weapon", False),
    "cloth_back": ("only the loose cloth trailing BEHIND the body: the rear robe tail, rear sash or cape, from its rear attachment seam to its tips. Keep only the REARMOST trailing fabric, behind the rear leg and rear hip, on the LEFT of the body. The central front apron is NOT part of this layer, even where a walking stride makes its lower hem extend left of the hip. Preserve the COMPLETE rear train silhouette, including ALL of its inner lining and underside fabric visible along the leftmost and bottommost rear hems. A pale or white lining sewn to the rear train is rear cloth, not trousers or a front apron: keep it in full with its original folds and colour. Reconstruct the hidden attachment, but exclude the separate central front apron. When a finished torso layer is supplied as an additional reference, it is an EXCLUSION GUIDE: remove every skirt panel and embroidered hem already present in that torso. Keep only the remaining rear train and its lining. Do not redraw the torso guide into this output. End the attachment at the back of the hip, not around the whole waist. Omit the entire wraparound skirt: no front-facing panel, no rightward-pointing flap and no white fabric between the thighs. Reconstruct only the hidden rear attachment as matching fabric",
                   "the head, hair, torso, the entire belt and waist ring, both arms, both legs, the weapon, every front thigh panel or apron, all front pendants, cords and tassels, and any fabric in front of or between the legs, including the central embroidered apron and its lower hem. Front skirt panels belong to the torso layer, never this layer", False),
    "arm_far": ("the rear arm only: the arm whose hand is further to the LEFT of the picture, which holds no weapon, complete from its OWN hidden shoulder attachment to the fingertips, with its whole sleeve and cuff. Reconstruct one continuous upper arm behind the torso, with a rounded shoulder root overlapping the torso. Do not copy the visible front shoulder plate or front sleeve onto this rear arm",
                "the head, hair, torso, the other arm that reaches to the right of the picture, both legs, the weapon and all other clothing", True),
    "leg_far": ("the rear leg only: the leg whose foot is further to the LEFT of the picture, complete from the hip to the sole with its trouser and boot. Show the upper thigh fully, as if nothing covered it. Preserve the sharp trouser seams and fabric fold contours; reconstruct the hidden thigh with the same crisp folds, not a broad airbrushed gradient",
                "the head, hair, torso, belt, robe, both arms, the other leg whose foot is further right, the weapon and every loose cloth, panel or sash", True),
    "leg_near": ("the front leg only: the leg whose foot is further to the RIGHT of the picture, complete from the hip to the sole with its trouser and boot. Show the upper thigh fully, as if nothing covered it. Preserve the sharp trouser seams and fabric fold contours; reconstruct the hidden thigh with the same crisp folds, not a broad airbrushed gradient",
                 "the head, hair, torso, belt, robe, both arms, the other leg whose foot is further left, the weapon and every loose cloth, panel or sash", True),
    "hips": ("the hips only: the garment worn under the outer clothing, from the waist down to the crotch, in the same material as the top of the legs, as one solid closed shape as wide as the waist. It fills the whole space behind the belt and behind every hanging panel, with no gap, and the bottom edge stops at the crotch",
             "the head, hair, chest, belt, every outer robe, panel, sash, tassel and ornament, both arms, both legs below the crotch, the weapon and every loose cloth", True),
    "robe": ("the complete connected outer skirt of a wraparound long robe, from its waist attachment seam to ALL its hems, as one continuous garment: front panels, rear train, side panels, inner lining and any attached trailing sash. Preserve the whole garment silhouette and embroidery, including all rear and front fabric",
             "the head, hair, chest, the belt and belt buckle, front belt pendants and tassels, both arms and hands, both trouser legs and boots, and the weapon. Keep the robe fabric, but no body parts", False),
    "torso": ("the torso layer: the entire neck including the exposed skin between the jaw and collar, full collar, chest, belly, waist belt and hips of the garment, plus only what hangs in front of the thighs: the complete front robe apron down to its original hem (including long or outward-flared front panels), belt ornaments, cords and tassels, as one complete closed shape. Do not leave an empty gap above the collar where the neck belongs",
              "the head, face, all hair, both arms, both shoulder plates, both sleeves, both hands, the weapon, both legs, and ALL rear skirt fabric below the belt, including short side panels as well as long robe tails. In the fixed RIGHT-facing pose, remove every below-belt flap extending toward the LEFT behind the thighs, even if it has embroidery. Keep the ENTIRE front apron on the RIGHT side of the thighs at its original length, width and flare, including its embroidered lower hem. Do not shorten it to a small tab or omit the rightmost front panel. The rear lower edge of this torso stops at the hip, not at a skirt hem", True),
    "head": ("the head: face, ear, the hair on the skull with its hair ornaments, AND the entire exposed neck down to the collar line, as one closed connected shape. The neck must overlap the neck in the torso layer so no gap opens as the head turns. The neck is BARE SKIN ONLY: preserve a natural narrow neck column down to the collar, with no collar, fabric stripe, collar rim, jewellery or clothing. Remove fabric completely; do NOT turn a wide collar flap into a triangular skin flap. The lower attachment ends in continuous neck colour with NO dark cap line across it, so it can overlap the torso neck seamlessly. Preserve the exact face and head size. Cut only long hair off at the jaw line, not the neck",
             "the body below the neck, every collar and collar rim, ALL clothing including any narrow diagonal fabric strip at the bottom of the neck, both arms, the weapon and the long hair below the jaw", True),
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
        remove="the ENTIRE FOREARM including bare skin, all fabric, the entire sleeve, cuff, bracelet, ribbons, the upper arm and shoulder, and everything except the hand and its fingers. End at the narrow wrist crease immediately behind the palm; NO long cylindrical forearm or forearm stump remains")


def prompt(slot):
    keep, remove, _ = SLOTS[slot]
    if slot != "appendage_back":
        remove += ", the complete separate rear biological appendage including its hidden root, scales, spikes and tip"
    result = COMMON.format(keep=keep, remove=remove)
    if slot in ('head', 'torso'):
        result += '\n' + NATURAL_NECK
    if slot in ('arm_near', 'arm_far'):
        result += '\n' + NATURAL_HANDS + '\nPreserve the accepted reference hand pose exactly; reconstruct only hidden anatomy. Do not re-pose fingers during separation.'
    return result

# The supported first production profile. The older SLOTS/prompts remain an
# experimental route; do not silently send a basic job through that route.
BASIC_PROFILE = 'basic-side-v1'
BASIC_SLOTS = ('arm_far', 'leg_far', 'leg_near', 'hips', 'torso', 'head', 'arm_near')
BASIC_SCOPE_CHECKS = ('short_fitted_clothing', 'short_hair', 'no_trailing_accessories',
                      'single_hand_simple_weapon', 'opaque_flat_art')
BASIC_REFERENCE = """Use the attached picture as CHARACTER IDENTITY reference, not as a pose to trace.
Preserve the face, species, build, palette, recognisable clothing motifs and drawing style.
Character: {who}. Style: {style}.

Create ONE full-body 2D humanoid game character in a strict right-facing SIDE VIEW.
Orthographic 90-degree SIDE ELEVATION, not a three-quarter illustration. Only one eye is visible;
show the chest and belt from their side edge, never a broad front-facing chest or belt buckle.
Two arms and two legs only. Small walking stride measured horizontally, not into picture depth. Both complete shoes flat on one horizontal
sole line. The two heel/sole bottoms must be at EXACTLY the same vertical height; no raised toes,
no slanted soles, no depth offset. Both boots point exactly right. Front/right-hand arm forward, rear/left-hand arm back, both slightly bent and visibly
clear of the torso below their attached shoulder roots. No gaps or floating arms at the shoulders.
Keep the rear shoulder behind the torso rather than drawing a second shoulder plate over the chest.
Show a readable shoulder -> upper arm -> elbow -> forearm -> wrist -> hand path for EACH arm. No stump arms, hidden forearms, tiny substitute hands or overlapping arm paths.
The FORWARD UPPER ARM must be visibly angled forward/down from its SHOULDER to an elbow
IN FRONT of the ribs. Then the complete forearm angles forward/up to the sword hand. The elbow
and wrist are outside the torso silhouette, with magenta space under the arm. Never start an arm
at the waist, belt or hip; never show only a forearm emerging from the torso.
{weapon}

Production adaptation: fitted or short sleeves with exposed hands, a short top ending at the
hips with NO front flaps extending onto the thighs, fitted trousers and simple shoes. Short hair ends above the shoulders. Simplify long robes,
wide sleeves, long hair, capes, dangling belts and tassels to this supported design while preserving
palette and motifs. If one of those features is essential to identity, stop and report that this
profile cannot preserve it; do not claim an exact reconstruction. No trailing cloth, floor-length
skirt, floating ornaments, second weapon, shield, holster, bow, gun or two-handed grip.

When a second image is supplied as a POSE GUIDE, it controls pose and attachment geometry only.
Follow both complete arm chains and the common sole baseline in that guide; the character identity,
materials and art style come from the character reference. Do not draw guide lines, circles, labels
or the guide's flat placeholder colours in the final art.

Use a portrait 1024 x 1536 canvas, figure about 85% of its height, all edges inside a generous margin.
Even flat/cel lighting and crisp opaque artwork, no blur or motion smear. No text, labels, guides,
shadow, glow, floor or scenery. Outside the figure is solid pure magenta #FF00FF. No magenta or
pink-purple in the character. Output a single static image, not a sheet or collage.
""" + "\n" + NATURAL_NECK + "\n" + NATURAL_HANDS

BASIC_KEEP = {
    'torso': ('ONE complete torso-only portion of the ORIGINAL short upper garment: bare neck column, collar, closed chest, belly, waist belt and hip-length hem. Reconstruct continuous opaque BODY FABRIC beneath the removed sleeves, using the surrounding original outer-garment material, folds and shading. Removing an arm is layer separation, not a redesign into a sleeveless vest. The underarm and sleeve-root overlap must remain continuous garment fabric with no circular or oval hole, outlined socket, exposed undershirt disk or skin disk. Preserve genuine exposed skin/scales only where the original torso exposes them. The result has NO sleeve, NO shoulder shield/pauldron and NO upper-arm cap; its body fabric must still close the space underneath those removed parts. Preserve the original small whole-canvas placement',
              'head, face, hair, BOTH WHOLE ARMS including every sleeve and every shoulder plate/pauldron, hands, legs, weapons and all fabric below the hips. A rounded shoulder/upper-arm plate belongs to the ARM: remove that detached part while reconstructing the continuous original torso fabric beneath it. Do not outline an armhole or copy undershirt/skin colour into the hidden outer-garment body'),
    'hips': ('ONE solid hidden waist-to-crotch backing in the same fabric as the upper trousers. It is a continuous interior fabric bridge behind the torso and both thigh roots, with matching subtle fabric shading and no hole. ONE closed gently tapered shape only, with one uninterrupted rounded lower edge stopping AT the crotch. No shorts, Y-shape, leg opening, split lower edge or two thigh stumps. Keep its original full-canvas position and scale. This is reconstructed hidden fabric, not a duplicate of the visible trouser front: no pocket, fly, waistband, belt loops, exterior panel seam or outlined bottom hem. Internal overlap boundaries have continuous fabric colour and NO dark cut-edge outline',
             'head, hair, chest, belt, arms, BOTH COMPLETE LEGS and all thigh material below the crotch, weapons, loose cloth, external trouser pockets, fly, waistband, belt loops, shorts leg tubes and duplicate visible garment panels'),
    'leg_far': ('exactly ONE complete REAR LEG ending in the LEFTMOST boot, from its own hip root through its own thigh, knee and shin to the whole heel/sole/toe. One unbranched limb only. Reconstruct its hidden upper thigh, not a shared pelvis or a pair of shorts',
                'the other leg COMPLETELY, including its upper thigh and knee even if only a short cut-off stump is visible. No Y-shaped trouser branch, no second thigh, no shared waistband/crotch spanning both legs. Remove torso, belt, hips garment, arms, head and weapon'),
    'head': ('the exact small head and short hair from the full figure, with the complete bare neck down to collar level. One face only, continuous skin neck without collar or dark cut-edge cap. Keep its EXACT original pixel scale and upper-canvas location with all surrounding empty canvas',
             'all body and clothing, every collar or clothing stripe, shoulder plates, arms, legs, weapons and any background objects. NO PORTRAIT CLOSEUP, no recentering or enlarged face; this is the original full-size registration canvas with only the original small head left on it'),
}

IDENTITY_PROMPT = """Inspect the supplied character picture before generating anything. Describe its face,
build, palette, clothing motifs, equipment and art style. Separate visible facts from hidden or
uncertain anatomy. State every adaptation needed for basic-side-v1 (short hair, short/fitted
clothing, no trailing accessories, no weapon or one simple single-handed sword). If an essential
identity feature cannot be preserved in that scope, report the conflict rather than silently
removing it. Never infer that a photograph or illustration is already a bindable game reference.
Write this inspection in identity_notes.md; do not ask the user to write prompts or mark joints."""

REPAIR_RULES = {
    'incomplete': 'Reconstruct the COMPLETE requested part, including hidden attachment and every anatomical segment. Never substitute a stump, cuff, disconnected hand or silhouette fragment.',
    'extra_art': 'Remove every object outside KEEP ONLY, including copied limbs, stray fragments, duplicate clothing and every weapon in an arm/torso layer.',
    'blur': 'Repaint crisp matching seams, fingers, fabric folds and contours. No blur, translucent smear, stretched texture or ghost outline.',
    'registration': 'Restore the exact full canvas, original pose, position and scale. Never zoom or recenter an isolated small part.',
    'reference': 'Regenerate the complete standard reference following every pose, clothing, weapon-count and visibility requirement. Do not work around a failed reference by changing rig parameters.',
    'neck': NATURAL_NECK,
    'hand_pose': NATURAL_HANDS + '\nRepair the original reference if its hand pose is wrong. If separation alone damaged it, restore the accepted reference pose in the arm layer. Regenerate its hand hint only from the repaired finished arm, never use a hint to re-pose the hand.',
}


RIFLE_PROFILE = 'side-rifle-carry-v1'
RIFLE_SCOPE_CHECKS = ('short_fitted_clothing', 'no_trailing_accessories',
                      'two_hand_rifle_carry', 'opaque_crisp_art')


def rifle_reference_prompt(who, style):
    return f'''Use the supplied picture as character identity, not a pose to trace.
Character: {who}. Style: {style}.
Create one complete full-body 2D game registration image, strict orthographic RIGHT-facing
90-degree SIDE ELEVATION, on a portrait 1024 x 1536 canvas. Preserve recognisable face,
build, helmet/headgear, clothing, equipment, palette and the ONE rifle from the reference.
Head level, no front-facing chest or three-quarter perspective. Calm low-ready TWO-HAND
rifle carry in front of the chest/waist: camera-side hand on the pistol grip, far hand on
the fore-end. BOTH complete shoulder/elbow/forearm/wrist paths must be READABLE. Put the
supporting elbow forward and below the gun, outside the chest silhouette, so its full
forearm is visible below the gun. The near trigger elbow is lower/back, with visible
upper arm and forearm. No isolated palm emerging from the torso, no hidden stump arm.
Anatomical closed grips, neutral wrists, no extra hand or duplicate gun.
The complete rigid rifle points forward RIGHT and slightly down; stock, receiver,
magazine, barrel and muzzle remain inside the frame. No firing, flash or cartridge.
Small staggered standing stride, separate complete legs, both complete boot soles exactly
flat on ONE horizontal baseline, pointing RIGHT. Connected original trousers at waist
and crotch, short fitted upper garment ending at the hips. Secure equipment and straps
against their own body part; no loose glove, trailing strap, cape or long coat.
Figure about 85 percent of canvas height with generous margins. Crisp opaque material
detail, even illumination, no blur, floor, scenery, shadow, text or guide marks. Outside
the complete character and rifle use ONLY flat pure MAGENTA #FF00FF, no magenta on art.
Output one static registration image, not a sheet or a closeup.
''' + NATURAL_NECK + '\n' + NATURAL_HANDS


def rifle_prompt(slot):
    if slot in HAND_HINTS:
        return basic_prompt(slot)
    if slot not in BASIC_SLOTS:
        raise ValueError('unsupported rifle carry layer: ' + slot)
    keep, remove = BASIC_KEEP.get(slot, SLOTS[slot][:2])
    if slot == 'arm_near':
        keep = ('the CAMERA-SIDE arm on the PISTOL GRIP, complete from its real shoulder '
                'through upper arm, elbow, forearm, wrist and closed trigger-hand fingers; '
                'preserve the sleeve, elbow and exact grip pose in the reference')
        remove = 'the other supporting arm/hand, head, torso, legs, ALL rifle parts and every other object'
    elif slot == 'arm_far':
        keep = ('the FAR-SIDE SUPPORTING arm whose hand is under the rifle FORE-END, complete '
                'from its own shoulder through upper arm, elbow, forearm, wrist and curled '
                'supporting fingers; reconstruct hidden segments with matching sleeve/skin detail '
                'without moving the visible supporting palm')
        remove = 'the camera-side trigger arm/hand, head, torso, legs, ALL rifle parts and every other object'
    anatomy = ('\n'+NATURAL_NECK if slot in ('head', 'torso') else
               '\n'+NATURAL_HANDS if slot in ('arm_near', 'arm_far') else '')
    return COMMON.format(keep=keep, remove=remove)+anatomy+'''
RIFLE-CARRY contract: one complete connected requested layer on the unchanged full
registration canvas. Do not re-pose, recenter, zoom, simplify details or copy the other limb.
Arm layers NEVER contain any part of the rifle, handle or magazine. The trigger hand and
supporting hand have different roles and must not be selected merely by screen-left/right.
Preserve each accepted hand gesture while removing the rifle. The torso has no arms or
detached shoulder pieces; the hips contain only complete hidden internal trouser material,
no duplicate visible waistband or outer pocket. Each leg includes its own whole thigh,
knee and boot, with tightly attached equipment belonging to that leg alone.
'''


def basic_reference_prompt(who, style, weapon):
    if weapon not in ('none', 'sword'):
        raise ValueError('basic-side-v1 supports none or one single-handed sword only')
    equipment = ('Both hands empty. No weapon, scabbard, shield or equipment held in either hand.' if weapon == 'none'
                 else 'Exactly ONE simple straight sword in the front/right hand, pointing forward and up. Blade, guard and pommel clearly visible; the fingers close around the grip. Rear hand empty. One-handed grip only; no scabbard or spare weapon.')
    return BASIC_REFERENCE.format(who=who, style=style, weapon=equipment)


def basic_prompt(slot):
    if slot not in (*BASIC_SLOTS, 'weapon', *HAND_HINTS):
        raise ValueError('unsupported basic layer: ' + slot)
    if slot in HAND_HINTS:
        return hand_prompt() + '\nThe source is the FINISHED ' + HAND_HINTS[slot] + ' layer, not the full character. Keep the exact wrist and fingers; never invent a different hand.\n'
    keep, remove = BASIC_KEEP.get(slot, SLOTS[slot][:2])
    anatomy = ('\n' + NATURAL_NECK if slot in ('head', 'torso') else
               '\n' + NATURAL_HANDS + '\nPreserve the accepted reference hand pose exactly; do not re-pose during separation.'
               if slot in ('arm_near', 'arm_far') else '')
    return COMMON.format(keep=keep, remove=remove) + anatomy + """

BASIC-SIDE-V1 acceptance: one complete connected requested part only. Preserve sharp drawn detail;
no stump limbs, detached fragments, ghost art, duplicate garment pieces or extra equipment.
Both arm layers must include their own complete upper arm, elbow, forearm, wrist and hand.
An arm layer NEVER contains any weapon, handle, blade or scabbard. Remove the weapon while keeping
all fingers intact. Do not fix ambiguity by copying the other arm. The torso is short, ends at the
hips and has no skirt/apron/tassel. Hair is short; no separate rear hair or cloth layer.
"""
