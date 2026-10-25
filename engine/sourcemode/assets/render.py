"""Render every look in a plan through the native single-pass pipeline.

For each (category, look): N shots at the game's 2:3 grid, the character's LoRA
for identity, the plan's outfit + hair for the look, a solid mid-grey
background so light clothing keys cleanly. Each shot gets a sidecar with the
slot's identity and its score against the character's closeup reference, so
`assets cutout` and `assets place` never have to infer anything.

Layout:  <out>/<character>/renders/<category>_<NN>_<pose>/shot_<i>_s<seed>.png (+ .json)
Resumable: existing shots with a sidecar are skipped.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ..gates.identity import cosine, embed_image
from .adherence import check, measure
from ..pose.native import build_native_workflow
from ..pose.transfer import composite_on_plate
from .catalog import plan_slots, slot_dirname

W, H = 1024, 1536
# Jeremy, 2026-10-02: "I just want the level of consistency and prompt adherence"
# of the Codex game-asset-gen skill - its mid-thigh-up crop, separate body turn and
# head turn, and its closed expression table. Ported from
# ~/.codex/skills/game-asset-gen/scripts/scaffold.py (FRAMINGS, describe_yaw,
# pose_fields, EXPRESSIONS, the prompt order) rather than re-derived. Pose family
# rotates front / image-left / image-right by look number so every category carries
# all three; degrees come from a per-look seeded randomizer, exactly as the scaffold
# does. Full length is never asked for - it starved the face (122px kept 12%).
import random
import re

FRAMING_MID_THIGH = ("standing mid-thigh-up portrait; bottom edge cuts through the middle of the thighs; "
                     "knees, lower legs, and feet outside the frame; never full-body")
# Jeremy, 2026-10-02, on Amanda's first pack: "almost all a little too far away...
# shoot for framing to her upper thighs instead of what's basically at her knees".
FRAMING_UPPER_THIGH = ("standing upper-thigh portrait, close enough that her face is large in frame; bottom edge "
                       "cuts across the tops of her thighs just below the hips; knees, lower legs, and feet "
                       "outside the frame; never full-body, never a wide shot")
# Jeremy, 2026-10-15, on nisha's pack: "they are all supposed to be either front
# facing or NEARLY front facing with slight angles, from the mid-thigh up". The
# tiebreaker set (asset_scenes.TIEBREAKER, 2026-10-10) was written to that spec;
# the pack now asks for the same thing.
FRAMING = FRAMING_MID_THIGH
# Jeremy, 2026-10-18, on cici's pack coming back close up: "make sure the game
# asset prompts indicate something like 'portrait picture from the mid-thigh
# up'". His words, verbatim: the pack's shot type is a "portrait picture" and
# the framing is "from the mid-thigh up".
NATURAL_SHOT = "portrait picture"
# Jeremy, 2026-10-23, after maya's, marisol's and lizzie's packs read as less
# like her: MEASURED over ten packs, the grey-studio pack put her face at a
# median 285 px tall against 359 px in the sweep renders she was approved on
# (both asked "from the mid-thigh up") and ~350-440 px in her training set.
# "zoom in a little bit more to upper thigh so that the girls' face takes up
# more of the picture". The sweep keeps its own mid-thigh wording.
NATURAL_FRAMING = "from the upper thigh up"
# And on the body: "her body is just slightly angled, she looks directly at the
# camera". MEASURED on cici's pack (2026-10-18, 14 slight-turn looks under
# "turned slightly toward her right/left, looking into the camera"): the body
# came back near-profile (MediaPipe shoulder depth past 0.8) in 9 of 14, the
# eyes left the lens in 13 of 14, and the SIDE was ignored - all 7 "her left"
# asks rendered toward image-left. So the slight turn names no side, and the
# gaze is stated as his sentence says it.
NATURAL_FRONT = "her body faces the camera, she looks directly at the camera"
NATURAL_SLIGHT = "her body is just slightly angled, she looks directly at the camera"
# Jeremy, 2026-10-23: the 15 front / 13 slight pack "almost are TOO static now
# and TOO front facing ... go with up to 45 degree turns, just make sure the
# mix is as follows: 1/4 front facing, 1/4 body at a slight angle to the
# camera, 1/4 body at a 45 degree angle to the camera, 1/4 in a relaxed pose
# with (arms in her pockets / arms crossed / arms behind her back) - randomize
# the arm position". The 45 is written as a turn toward her side with her face
# on the camera, never "three-quarter view", which Qwen read as a profile 60
# times in 63 (2026-10-15).
NATURAL_QUARTER = "her body turned about 45 degrees toward {her}, her face turned to the camera, she looks directly at the camera"
ROTATION = ("front", "slight", "quarter", "relaxed")
ARMS = ("her hands in her pockets", "her arms crossed", "her hands behind her back")
#: two more for a casual or a work look only - the old sets' hands on hips and
#: one hand in a pocket read wrong on a date or a night out (Jeremy, 2026-10-25)
ARMS_EVERYDAY = ("her hands on her hips", "one hand in her pocket")
ARMS_EVERYDAY_CATEGORIES = ("casual", "work")
#: pockets only where the outfit has some - a dress or a bodysuit gets the other two
_POCKETS = re.compile(r"\b(?:jeans|trousers|pants|chinos|cargo\w*|shorts|joggers|sweatpants|overalls"
                      r"|jacket|blazer|coat|hoodie|cardigan)\b", re.I)
EXPRESSIONS = (
    "relaxed neutral: lips gently together, mouth corners level, cheeks soft, eyebrows resting, relaxed direct gaze; no smile",
    "warm closed-lip smile: both mouth corners lifted, cheeks slightly raised, lips gently together, brows relaxed, soft direct eye contact",
    "natural smile showing teeth: lips comfortably parted with upper teeth visible, cheeks raised, brows relaxed, eyes softly narrowed toward viewer",
    "subtle flirty smile: one mouth corner gently lifted, lips softly together, cheeks slightly raised, brows relaxed, inviting direct eye contact",
    "soft neutral: lips resting together without pressure, mouth corners level, cheeks relaxed, brows smooth, soft attentive eyes toward viewer; no smile",
    "gentle closed-lip smile: mouth corners subtly lifted, lips together without tension, cheeks lightly raised, brows resting, warm direct gaze",
    "bright natural smile showing teeth: both mouth corners lifted, lips parted in an easy smile with teeth visible, cheeks lifted, brows relaxed, eyes engaged with viewer",
    "warm flirty smile: lips slightly parted in a subtle smile, mouth corners gently lifted, cheeks softly raised, brows resting, softly lowered eyelids with direct inviting eye contact",
)
CATEGORY_ORDER = ("casual", "workout", "fancy_dining_gallery", "fancy_town", "casual_date", "work")
# expression type per EXPRESSIONS entry - the vocabulary adherence.measure() speaks
EXPRESSION_TYPES = ("neutral", "closed-lip", "teeth", "flirty", "neutral", "closed-lip", "teeth", "flirty")
# Jeremy, 2026-10-03: "the poses are just all over the place." The Codex skill this
# contract was ported from varies body turn, head turn, expression, outfit and hair -
# and NEVER the pose; the stance is simply a natural standing portrait every time.
# The rotating pose list here was mine, not theirs, and it is what made the pack read
# as inconsistent. One stance, stated the way they state it.
STANCE = ("relaxed standing weight shift, hands and arms resting naturally, "
          "shoulders level and open to the camera")
SITTING = "She sits on a plain wooden stool facing the camera, hands resting on her thighs, a soft natural smile."
# Jeremy, 2026-10-04, on zara's pack: "I think we should add beautiful and natural
# makeup to the prompts. It's another thing that I've found helpful in the past.
# Some of those Zara pictures just look frumpy." Stated once, here, so it reaches
# the wardrobe pack, every shoot, the selfie pack and the epoch eval alike - the
# whole point of there being one builder. A slot may override it: a gym shot or a
# just-woken selfie is allowed to ask for less.
MAKEUP = "beautiful, natural makeup"
# The keyable backdrop a shipping asset needs. The epoch EVAL passes a real setting
# instead - Jeremy, 2026-10-03: "it's easier to judge against a regular backdrop
# because it looks more real" - so the backdrop is the one part of the asset prompt
# that is a parameter, and everything else stays identical between the two uses.
KEY_BACKDROP = ("soft even studio lighting, a flat solid bright magenta #FF00FF background "
                "edge to edge with nothing else in frame, no shadows on it")


def appearance_clause(character: str) -> str:
    """Body/feature text for the prompt. Never for a caption - see appearance.py."""
    from .appearance import clause  # noqa: PLC0415
    return clause(character)


def is_up_style(hair_clause: str) -> bool:
    from .appearance import is_up_style as _f  # noqa: PLC0415
    return _f(hair_clause)


def drop_length(text: str) -> str:
    from .appearance import drop_length as _f  # noqa: PLC0415
    return _f(text)


def character_negative(character: str) -> str:
    """The character's own negative, from the same record as her appearance."""
    from .appearance import negative  # noqa: PLC0415
    return negative(character)


#: There is no "fitted to her <frame>" clause any more. Jeremy, 2026-10-10:
#: "Get rid of the fit drop down. It's too confusing ... I already have the
#: description in there for pretty much every character, and there's no reason
#: to limit it to five types of frames." The appearance clause is the only
#: body text a prompt carries; vivienne's had been getting "tiny frame" from a
#: fallback her description never said.
#: Footwear in an outfit fights the upper-thigh crop. Jeremy, 2026-10-05: "none
#: of the game assets are ever supposed to have shoes unless I specifically ask.
#: they are always meant to be mid or high thigh up". zara casual_01 asked for
#: "white sneakers" under that crop and came back shot from overhead, full
#: length, feet in frame - the model obeyed the outfit and broke the crop.
_FOOTWEAR = re.compile(r"\b(?:sneakers?|shoes?|boots?|heels|sandals?|loafers?|pumps|flats"
                       r"|slippers?|trainers|stilettos?|mules|platforms|socks|stockings)\b", re.I)


def drop_footwear(outfit: str) -> str:
    """Remove footwear from an outfit, keeping every other garment.

    A comma-separated part that names footwear is dropped; if it joins the
    footwear on with "and"/"with", only that tail goes. A slot with
    `"shoes": true` skips this - that is how a look asks for them.
    """
    keep = []
    for part in (outfit or "").split(","):
        m = _FOOTWEAR.search(part)
        if not m:
            keep.append(part)
            continue
        joins = list(re.finditer(r"\s+(?:and|with)\s+", part[:m.start()]))
        if joins and part[:joins[-1].start()].strip():
            keep.append(part[:joins[-1].start()])
    return ",".join(keep).strip(" ,")


#: A hem detail below the knee pulls the frame down the same way shoes do.
#: Jeremy, 2026-10-24, on iris's workout_03, "a blush pink longline sports bra
#: and olive flared yoga pants", full length on both rolls: "flared yoga pants
#: ... would not be shown in an upper thigh-up picture". Measured over the
#: packs: prompts saying flared came back below mid-thigh 3 of 13, every other
#: prompt 3 in 100. The word goes at render, so his plan lines stay his.
_HEM_DETAIL = re.compile(r"\b(?:flared|flare-leg|bootcut|boot-cut|ankle-length|cuffed)\s+(?=\w)", re.I)


def drop_hem_detail(outfit: str) -> str:
    """"olive flared yoga pants" -> "olive yoga pants"."""
    return _HEM_DETAIL.sub("", outfit or "")


#: A graphic tee left to the model comes back with gibberish lettering, or her
#: own face printed on it. Jeremy, 2026-10-18, on a cici reject: "graphic ts
#: need to be without words or faces".
_GRAPHIC = re.compile(r"\bgraphics?\b(?:\s+(?:tee|t-shirt|shirt|top|sweatshirt|hoodie|crop top)s?\b)?", re.I)
PLAIN_GRAPHIC = "with a simple abstract design and no words, letters or faces"


def plain_graphics(outfit: str) -> str:
    """Every graphic in an outfit is a wordless, faceless abstract design."""
    s = outfit or ""
    if PLAIN_GRAPHIC in s:
        return s
    # a comma closes the clause when another garment follows it
    return _GRAPHIC.sub(lambda m: f"{m.group(0)} {PLAIN_GRAPHIC}"
                        + ("," if s[m.end():].strip() else ""), s)



def describe_yaw(degrees: int) -> str:
    if degrees == 0:
        return "FRONT: breastbone and pelvis face the lens; both shoulders equally near the camera, torso breadth balanced on both sides"
    side = "image-left" if degrees < 0 else "image-right"
    near = "image-right" if degrees < 0 else "image-left"
    if abs(degrees) < 20:
        return (f"SLIGHT turn toward {side} (about {abs(degrees)} degrees): breastbone and pelvis "
                f"angled just off the lens toward {side}; the shoulder on {near} a little nearer the camera")
    return (f"THREE-QUARTER toward {side} (about {abs(degrees)} degrees): "
            f"breastbone and pelvis point toward {side}; the shoulder on {near} is nearer the camera; "
            f"the shoulder on {side} recedes; chest and waist visibly foreshortened, "
            "far upper arm partly obscured by the torso. Rotate the whole torso, not just one shoulder")


#: A slot may name its turn and expression outright instead of taking the ones
#: the look number seeds. The tiebreaker eval set (asset_scenes.TIEBREAKER) is
#: what asks: Jeremy, 2026-10-10 - "either front facing or a very slight angle
#: looking at the camera with very simple expressions like a closed lip smile a
#: broad smile or a neutral expression". "slight" turns the body and head 10-15
#: degrees against the pack's 40-45 / 20-30. A pack slot sets neither and
#: takes ROTATION by look number.
TURNS = ("front", "left", "right", "slight-left", "slight-right")


def pose_fields(character: str, slot: dict) -> dict:
    """Screen-relative body geometry and an independent head pose, seeded per look.

    A pack slot rotates front / slight / 45 / relaxed by look number (seven of
    each over 28); the side of a turn, the degrees and the relaxed arms are
    drawn from the per-look rng. `turn` on the slot still picks a TURNS family
    outright, which is what the sweep and tiebreaker scenes do.
    """
    look = int(slot.get("look", 1))
    rng = random.Random(f"{character}-{slot.get('id', look)}")
    family = slot.get("turn")
    arms = None
    # a selfie, a shoot or an influencer slot brings its own framing or shot
    # type; its body stays front / slight as before - an arm's-length selfie
    # with "her hands in her pockets" holds no phone
    pack = not (slot.get("framing") or slot.get("shot_type") or slot.get("framing_natural"))
    if not family and not pack:
        family = ("front", "slight-left", "front", "slight-right")[(look - 1) % 4]
    if not family:
        # by place in the whole plan when the slot carries one (plan_slots
        # sets `n`), so a 28-look pack gets seven of each family
        fam = ROTATION[(int(slot.get("n", look)) - 1) % 4]
        side = rng.choice(("left", "right"))
        if fam == "front":
            family = "front"
        elif fam == "slight":
            family = f"slight-{side}"
        elif fam == "quarter":
            family = side
        else:
            # relaxed: front or a slight turn, and one of the arm positions.
            # Jeremy, 2026-10-25: "add hands on hips and hand in pocket rolls
            # only to casual and work outfits, do not add it to any of the date
            # or fancy/town/workout outfits where it probably doesn't fit well"
            family = rng.choice(("front", f"slight-{side}"))
            pockets = bool(_POCKETS.search(slot.get("outfit") or ""))
            pool = list(ARMS if pockets else ARMS[1:])
            if slot.get("category") in ARMS_EVERYDAY_CATEGORIES:
                pool += [a for a in ARMS_EVERYDAY if pockets or "pocket" not in a]
            arms = rng.choice(pool)
    if family not in TURNS:
        raise ValueError(f"turn must be one of {TURNS}, got {family!r}")
    slight = family.startswith("slight-")
    sign = {"front": 0, "left": -1, "right": 1}[family.removeprefix("slight-")]
    body = sign * (rng.randint(10, 15) if slight else rng.randint(40, 45))
    head = sign * (rng.randint(10, 15) if slight else rng.randint(20, 30))
    pitch = ("level", "slightly lowered", "slightly raised")[(look - 1) % 3]
    if sign:
        side = "image-left" if sign < 0 else "image-right"
        head_turn = (f"Nose points toward {side} (about {abs(head)} degrees); unequal visible cheek widths, "
                     "both eyes visible; her eyes locked on the lens, direct eye contact with the viewer")
    else:
        head_turn = "Nose faces the lens, both cheeks similarly visible; her eyes locked on the lens, direct eye contact with the viewer"
    cat_i = CATEGORY_ORDER.index(slot["category"]) if slot.get("category") in CATEGORY_ORDER else 0
    ex_i = (look - 1 + cat_i * 3) % len(EXPRESSIONS)
    if slot.get("expression"):
        if slot["expression"] not in EXPRESSION_TYPES:
            raise ValueError(f"expression must be one of {sorted(set(EXPRESSION_TYPES))}, got {slot['expression']!r}")
        ex_i = EXPRESSION_TYPES.index(slot["expression"])
    side = {"front": "front", "left": "image-left", "right": "image-right"}[family.removeprefix("slight-")]
    # A slight turn asks the HEAD for nothing but the lens ("she looks directly
    # at the camera"), and a 10-15 degree head turn sits under the measure's
    # own front threshold anyway - so the head ask is front, not a side.
    return {"body": describe_yaw(body) + (f"; {arms}" if arms else ""),
            "head": f"{head_turn}; chin {pitch}; no lateral head tilt",
            "expression": EXPRESSIONS[ex_i],
            # the structured ask, for adherence.check() against the measured render
            "asked": {"crop": "upper-thigh-up", "body_side": side, "body_deg": body,
                      "head_side": "front" if slight else side,
                      "head_deg": head, "pitch": pitch, "expression": EXPRESSION_TYPES[ex_i],
                      "slight": slight, "arms": arms}}


#: Jeremy, 2026-10-09: "review the prompts to ensure that they are optimized for
#: qwen generation. Because if you're being overly wordy or writing with AI slop,
#: it's a possibility that the issue is in the actual prompt itself, not being
#: written in sort of human natural language."
#:
#: The "contract" prompt below is the Codex game-asset-gen scaffold, ported
#: verbatim on 2026-10-02 - 1,900 characters of instruction prose ("Directions
#: mean image-left/image-right as seen by the viewer", "ALWAYS", "never full-body")
#: written for an instruction-following image API. Qwen-Image's encoder is a
#: Qwen2.5-VL and the LoRA was trained on 32-word captions in one register:
#: "gigi, a head-and-chest portrait, turned slightly toward her left, her hair in
#: a braid over one shoulder, wearing a grey crew-neck sweatshirt, a neutral
#: expression, natural sunlight, in a park pathway". The best asset numbers on
#: record came from prompts in that register (jojo_intimate 108/120, 494 chars).
#: "natural" says the same things - crop, body turn, head turn, gaze,
#: expression, makeup, hair, outfit, light, setting - in the caption's words and
#: order, about 70 words. PROMPT_STYLE is module state so the epoch eval can flip
#: it for an A/B without a second builder growing anywhere.
#:
#: 2026-10-09: "natural" became the default. Cassie epoch 18 kept 12/20 on it
#: against 5/10 on the contract prompt, judged stricter than the sweep - Jeremy:
#: "It was actually better than that ... It looks like we've solved our problems."
#: The contract prompt stays as the A/B arm (`--contract-prompt` on the eval).
PROMPT_STYLE = "natural"
_NATURAL_EXPRESSION = {
    "neutral": "a neutral expression", "closed-lip": "a soft closed-mouth smile",
    # "a broad smile showing her teeth" is the training captions' own phrase
    # (caption_from_vl); "a bright natural smile showing her teeth" came back
    # closed-lip 28 of 28 on crystal and on lizzie (Jeremy, 2026-10-25)
    "teeth": "a broad smile showing her teeth", "flirty": "a soft flirty smile",
}


def natural_prompt(character: str, slot: dict, trigger: str | None = None,
                   backdrop: str | None = None) -> str:
    """The asset prompt in the training caption's register. Same facts as the
    contract prompt, caption vocabulary, caption order, no instructions.

    The four composition overrides a shoot, the selfie pack or the influencer
    pack set (stance, framing, shot_type, avoid) are honoured here exactly as
    the contract honours them: a selfie stays a phone selfie held above eye
    level in her own room, a boudoir shot stays framed head to hips. A pack
    slot sets none of them and gets the upper-thigh standing portrait.
    """
    pf = pose_fields(character, slot)
    asked = pf["asked"]
    app = appearance_clause(character)
    if is_up_style(slot.get("hair", "")):
        app = drop_length(app)
    # captions say "her left"; the contract says image-left. image-left is her right.
    her = {"image-left": "her right", "image-right": "her left"}.get(asked["body_side"])
    if asked["body_side"] == "front":
        body, head = NATURAL_FRONT.split(", ")
    elif asked.get("slight"):
        body, head = NATURAL_SLIGHT.split(", ")
    else:
        body, head = NATURAL_QUARTER.format(her=her).split(", ", 1)
    if asked.get("arms"):
        body = f"{body} with {asked['arms']}"
    # Jeremy, 2026-10-12, the submissive pose set: half of it is not facing the
    # camera or looking into it, so a pose slot may say where her body and her
    # face actually are. Nothing else about the prompt changes.
    body = slot.get("facing") or body
    head = slot.get("gaze") or head
    shot = slot.get("shot_type") or NATURAL_SHOT
    outfit = drop_hem_detail(slot["outfit"] if slot.get("shoes") else drop_footwear(slot["outfit"]))
    # Jeremy, 2026-10-21: the pack prompt had lost the contract's "standing"
    # and daisy came back seated in 8 of 28; chest-up looks were dresses and
    # scrubs naming nothing below the waist. Done here, at render, so plans
    # approved before the fix (kasia's, nisha's scrubs) get it too.
    pack = not (slot.get("framing") or slot.get("shot_type") or slot.get("framing_natural"))
    if pack:
        from .looks import with_bottoms, with_legs  # noqa: PLC0415
        shot = f"standing {shot}"
        outfit = with_legs(with_bottoms(outfit))
    # a shoot's own framing sentence follows the shot type as its own clause;
    # the pack reads "a standing portrait picture from the upper thigh up"
    crop = f"a {shot}, {slot['framing']}" if slot.get("framing") else (
        f"a {shot} {slot.get('framing_natural') or NATURAL_FRAMING}")
    if pack:
        from .appearance import pack_camera  # noqa: PLC0415
        cam = pack_camera(character).get("prompt")
        crop = f"{crop}, {cam}" if cam else crop
    stance = f", {slot['stance']}" if slot.get("stance") else ""
    avoid = f" {slot['avoid']}" if slot.get("avoid") else ""
    expression = slot.get("expression_natural") or _NATURAL_EXPRESSION[asked["expression"]]
    from .appearance import hair_unsaid  # noqa: PLC0415
    hair = "" if slot["hair"].strip().lower() in hair_unsaid(character) else f"{slot['hair']}, "
    return (f"{trigger or character}, {app + ', ' if app else ''}{crop}, {body}, {head}{stance}, "
            f"{expression}, {slot.get('makeup') or MAKEUP}, "
            f"{hair}wearing {outfit}, "
            f"{backdrop or KEY_BACKDROP}. Photorealistic, natural skin texture, sharp focus.{avoid}")


def shot_prompt(character: str, slot: dict, trigger: str | None = None,
                backdrop: str | None = None) -> str:
    """The trigger is the bare character name unless the plan overrides it; the rest
    follows the Codex prompt order: crop, body, head, expression, hair, outfit, finish.

    A slot may override four COMPOSITION fields, which is what lets a named shoot
    or the selfie pack share this builder instead of growing a second one:

      stance     a boudoir shot is not a standing weight shift
      framing    nor is it an upper-thigh crop
      shot_type  a selfie is not a "standing portrait"
      avoid      and the pack's "no seated poses" rules out half a selfie set

    Every one defaults to the wardrobe-pack value, so a pack slot is byte-for-byte
    unchanged. What is NOT overridable is everything that carries identity - her
    appearance clause, the expression table, the gaze rule - so it is
    shared and cannot drift between the uses. Two narrower picks exist for the
    tiebreaker eval set (2026-10-10): `turn` and `expression` choose from the
    same tables rather than replacing them.
    """
    # Hair too short to gather never gets a CANNED up-style - wardrobe plans and
    # the eval looks set hair per look, outside hair_options, and priya's
    # chin-length bob was asked for buns and rendered down AND up. A line from
    # her own wardrobe list is never touched: Jeremy, 2026-10-15, "If I put low
    # ponytail for a character, I want a low ponytail."
    from .wardrobe import SHORT_HAIR, is_own_hair, is_short_haired  # noqa: PLC0415
    if (is_short_haired(character) and is_up_style(slot.get("hair", ""))
            and not is_own_hair(character, slot.get("hair", ""))):
        slot = {**slot, "hair": SHORT_HAIR[int(slot.get("look", 1)) % len(SHORT_HAIR)]}
    slot = {**slot, "outfit": plain_graphics(slot["outfit"])}
    if slot["pose"] == "sitting":
        look = f"Photorealistic, natural skin texture, sharp focus, {backdrop or KEY_BACKDROP}. Natural realistic human proportions, correct anatomy."
        return (f"{trigger or character}. {SITTING} She is wearing {slot['outfit']}, "
                f"{slot['hair']}, {slot.get('makeup') or MAKEUP}. {look}")
    if PROMPT_STYLE == "natural":
        return natural_prompt(character, slot, trigger, backdrop)
    pf = pose_fields(character, slot)
    app = appearance_clause(character)
    # MEASURED 2026-10-04: a prompt that says her hair is long AND asks for it up
    # renders the full length hanging down with a bun perched on top - 10 of 10
    # bun-prompted shots across geena and cindy, 30% kept against 83% for every
    # other prompt in the same four sets. Jeremy had already said so: "you cannot
    # put long hair in the same prompt as a messy bun."
    # So the length words come out when the look puts the hair up. Colour and
    # texture stay - a platinum bun is still platinum, and the colour is the
    # identity trait the base model will not volunteer.
    if is_up_style(slot.get("hair", "")):
        app = drop_length(app)
    return (f"{trigger or character}. New photorealistic {slot.get('shot_type') or 'standing portrait'}"
            f" of {app + ', ' if app else ''}"
            f"her body shape and proportions exactly as described. "
            f"Crop: {slot.get('framing') or FRAMING_UPPER_THIGH}. Vertical 2:3, consistent headroom and scale; hair and lateral silhouette inside canvas. "
            f"Body: {pf['body']}. Directions mean image-left/image-right as seen by the viewer. "
            f"Head: {pf['head']}. Body direction and head direction are separate requirements. "
            f"Gaze: she is ALWAYS looking directly into the camera lens. "
            f"Expression: {pf['expression']}. "
            f"Makeup: {slot.get('makeup') or MAKEUP}. "
            f"Pose: {slot.get('stance') or STANCE}. "
            f"Hair: {slot['hair']}. "
            f"Outfit: {drop_hem_detail(slot['outfit'] if slot.get('shoes') else drop_footwear(slot['outfit']))}. "
            f"Photorealistic, natural skin texture, sharp focus, {backdrop or KEY_BACKDROP}. "
            f"Natural realistic human proportions, correct anatomy. "
            + (slot.get("avoid") or "No profiles, rear views, seated poses, or off-camera gaze."))


def t2i_workflow(cfg: dict, prompt: str, seed: int, prefix: str, *, lora_path: str,
                 negative: str, width: int = W, height: int = H,
                 render_pass: str = "medium",
                 extra_loras: tuple[tuple[str, float], ...] = (),
                 lora_strength: float = 1.0) -> dict:
    """The plain Qwen-Image text-to-image graph a shoot renders through.
    `lora_strength` exists for A/Bs only; every shoot renders hers at 1.0.

    Here rather than in a script because TWO things render shoots now - the
    first pass and the re-roll of whatever was rejected - and a second copy of
    the graph settings is exactly how one path quietly gets a different shift,
    a different step count or a different LoRA strength from the other.

    `extra_loras` stacks one more LoRA under hers - the toy shoot's torso LoRA
    (Jeremy, 2026-10-17). The template has one spare LoraLoader after hers, so
    one is the limit; its strength is capped at 0.6 by `validate_lora_stack`
    so it cannot fight her identity.
    """
    from ..render.workflow import (  # noqa: PLC0415
        load_template, prune_placeholder_loras, substitute, validate_lora_stack)
    from ..config import workflows_dir  # noqa: PLC0415

    if len(extra_loras) > 1:
        raise ValueError(f"the t2i graph has one spare LoRA slot, {len(extra_loras)} asked for")
    extra_path, extra_strength = extra_loras[0] if extra_loras else ("", 0.0)
    validate_lora_stack([{"path": lora_path, "strength": 1.0, "is_identity": True}]
                        + ([{"path": extra_path, "strength": extra_strength}] if extra_path else []))
    preset = cfg["render"][render_pass]
    return prune_placeholder_loras(substitute(
        load_template(workflows_dir(cfg), "qwen_image_t2i"), {
            "MODEL": cfg["models"]["qwen_image"],
            "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
            "VAE": cfg["models"]["qwen_vae"],
            "POSITIVE": prompt, "NEGATIVE": negative,
            "LORA_PATH": lora_path, "LORA_STRENGTH": float(lora_strength),
            "LIGHTNING": extra_path, "LIGHTNING_STRENGTH": float(extra_strength),
            "SHIFT": float(cfg["render"]["qwen_shift"]), "SEED": int(seed),
            "STEPS": int(preset["qwen_t2i_steps"]), "CFG": float(preset["qwen_t2i_cfg"]),
            "WIDTH": width, "HEIGHT": height, "FILENAME_PREFIX": prefix,
        }))


def needs_rerender(sidecar: dict, prompt: str) -> bool:
    """Is an existing shot still what the plan asks for?

    `render_plan` skips any shot whose file and sidecar exist, which is what
    makes a pack resumable after a crash - and also what made "I fixed the
    prompt, run it again" do nothing. Measured 2026-10-04: with the makeup
    clause added, re-running zara's pack would have re-rendered 3 of 28 looks
    and handed back 25 built from the superseded prompt.

    A sidecar with no prompt recorded predates this and is left alone rather
    than re-rendered on a guess.
    """
    prior = (sidecar or {}).get("prompt")
    return bool(prior) and prior != prompt


def render_plan(cfg: dict, client, plan: dict, out: Path, *, shots: int = 4, seed: int = 7100,
                lora_strength: float = 0.85, render_pass: str = "medium", log=print,
                only: set[str] | None = None) -> list[dict]:
    character = plan["character"]
    if not plan.get("lora") or not plan.get("source_asset"):
        raise ValueError("plan needs `lora` and `source_asset` to render")
    slots = [s for s in plan_slots(plan) if not only or s["id"] in only]
    blank = [s["id"] for s in slots if not s["outfit"] or not s["hair"]]
    if blank:
        raise ValueError(f"plan has looks with no outfit/hair: {', '.join(blank)}")

    root = out / character / "renders"
    root.mkdir(parents=True, exist_ok=True)
    plate = root / "_plate.png"
    if not plate.exists():
        # The PLATE sets the framing, not the words. Measured 2026-10-03: the prompt
        # said "upper-thigh, bottom edge just below the hips" and the renders came
        # back with the hips at 0.74 of frame height, exactly where the older
        # "mid-thigh" wording put them - while the plate was a full standing shot.
        # The same thing happened with head turn, where the plate's direction beat
        # the text 5 times in 6. So the plate is cropped to the target framing first
        # and the prompt only has to agree with it. Cropping the plate costs no
        # detail; upscaling the output afterwards would add none.
        from .framing import crop_to_hips  # noqa: PLC0415
        src_img = Image.open(plan["source_asset"]).convert("RGBA")
        framed, note = crop_to_hips(src_img)
        log(f"  plate: {note}")
        tmp = root / "_plate_src.png"
        framed.save(tmp)
        composite_on_plate(tmp, plate, colour=(255, 0, 255))
    image_name = client.upload_image(plate)
    ref = embed_image(Path(plan["reference"])) if plan.get("reference") else None

    results = []
    for si, slot in enumerate(slots):
        sdir = root / slot_dirname(slot)
        sdir.mkdir(exist_ok=True)
        prompt = shot_prompt(character, slot, plan.get("trigger"))
        (sdir / "prompt.txt").write_text(prompt, encoding="utf-8")
        for k in range(shots):
            s = seed + si * 1000 + k * 137
            dest = sdir / f"shot_{k:02d}_s{s}.png"
            side = dest.with_suffix(".json")
            if dest.exists() and side.exists():
                prior = json.loads(side.read_text(encoding="utf-8"))
                if not needs_rerender(prior, prompt):
                    results.append(prior)
                    continue
                log(f"  {slot['id']} shot {k}: prompt changed, re-rendering")
            nodes = build_native_workflow(cfg, image_name, prompt, s, f"assets/{character}/{slot['id']}",
                                          lora=plan["lora"], lora_strength=lora_strength,
                                          render_pass=render_pass, width=W, height=H,
                                          negative_extra=character_negative(character))
            files = client.outputs(client.wait(client.submit(nodes), timeout_s=3600))
            if not files:
                log(f"  {slot['id']} shot {k}: no output")
                continue
            client.fetch(files[0], dest)
            score = None
            if ref is not None:
                e = embed_image(dest)
                score = round(cosine(ref, e), 4) if e is not None else 0.0
            # Jeremy, 2026-10-02: a full-body render (bare feet) was placed over a
            # correct mid-thigh one because place ranked by identity alone. The ask
            # is recorded and the render is measured against it; place ranks by the
            # number of asks broken, then identity. Relative to the ask, so a
            # full-body look passes when full body was asked for.
            asked = pose_fields(character, slot)["asked"] if slot["pose"] != "sitting" else {}
            try:
                adherence = check(asked, measure(dest)) if asked else {"failed": [], "soft": [], "got": {}}
            except Exception as exc:  # noqa: BLE001 - a measurement, never a blocker
                adherence = {"failed": [], "soft": [], "got": {}, "error": str(exc)}
            meta = {"source": str(dest), "asset": {"character": character, "category": slot["category"],
                                                   "look": slot["look"], "pose": slot["pose"], "shot": k},
                    "score": score, "asked": asked, "adherence": adherence,
                    "seed": s, "prompt": prompt, "lora": plan["lora"],
                    "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            side.write_text(json.dumps(meta, indent=1), encoding="utf-8")
            results.append(meta)
            log(f"  {slot['id']} shot {k}: " + (f"{score:.3f}" if score is not None else "rendered"))
    return results
