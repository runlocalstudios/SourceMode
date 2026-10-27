"""The ten epoch-sweep prompts, and the tiebreaker set.

Jeremy, 2026-10-02: "The real test would be to generate 10 different examples that
look just like the asset generator prompts." Until 2026-10-19 the ten were the
pack's own `shot_prompt` text with a real setting swapped in for the backdrop.

Jeremy, 2026-10-19, rewrote them: "less prescriptive, more natural, get rid of
lighting, makeup, skin commentary, focus, the exact outfit, etc. i want it to be
as trimmed down as possible to limit the amount of things fucking up the
pictures", with this as the model:

    lena, portrait picture of a woman from the mid-thigh up, her body faces the
    camera, she looks directly at the camera and makes a neutral expression, her
    hair worn loose, standing in a kitchen wearing a casual outfit

So the sweep no longer renders the pack prompt verbatim. Each scene keeps the
place, hair, body turn and expression it had; the outfit is a kind, not a
garment. Rates judged before 2026-10-19 are not comparable to rates after it.
"""
from sourcemode.assets import render as _render
from sourcemode.assets.render import NATURAL_FRONT, NATURAL_SLIGHT, shot_prompt

# The ten keep his 2026-10-19 sentence as written. The pack moved to "from the
# upper thigh up" on 2026-10-23 (render.NATURAL_FRAMING); a sweep rate is only
# ever compared with another sweep, so the sweep's framing stays put.
NATURAL_FRAMING = "from the mid-thigh up"

BODY = {"front": NATURAL_FRONT.split(", ")[0], "slight-left": NATURAL_SLIGHT.split(", ")[0],
        "slight-right": NATURAL_SLIGHT.split(", ")[0]}

# category/look/outfit also let the hair tests build a pack prompt from each look
LOOKS = [
    {"id": "casual_01", "category": "casual", "look": 1, "turn": "front",
     "face": "makes a neutral expression", "hair": "her hair worn loose",
     "doing": "standing in a kitchen", "outfit": "a casual outfit"},
    {"id": "casual_02", "category": "casual", "look": 2, "turn": "slight-left",
     "face": "smiles with her mouth closed", "hair": "her hair in a high ponytail",
     "doing": "standing on a quiet residential street", "outfit": "a casual outfit"},
    {"id": "workout_01", "category": "workout", "look": 1, "turn": "front",
     "face": "smiles", "hair": "her hair in a high ponytail",
     "doing": "standing with her hands on her hips on an empty street", "outfit": "a running outfit"},
    {"id": "workout_02", "category": "workout", "look": 2, "turn": "front",
     "face": "makes a neutral expression", "hair": "her hair up in a messy bun",
     "doing": "sitting on a workout bench in a gym", "outfit": "a workout outfit"},
    {"id": "fancy_dining_gallery_01", "category": "fancy_dining_gallery", "look": 1, "turn": "front",
     "face": "smiles with her mouth closed", "hair": "her hair worn loose",
     "doing": "standing in an elegant restaurant", "outfit": "a dress"},
    {"id": "fancy_dining_gallery_02", "category": "fancy_dining_gallery", "look": 2, "turn": "slight-right",
     "face": "gives a soft flirty smile", "hair": "her hair worn loose",
     "doing": "standing in an art gallery", "outfit": "a dress"},
    {"id": "fancy_town_01", "category": "fancy_town", "look": 1, "turn": "front",
     "face": "smiles with her mouth closed", "hair": "her hair half pinned back",
     "doing": "standing outside a bar at night", "outfit": "a cocktail dress"},
    {"id": "casual_date_01", "category": "casual_date", "look": 1, "turn": "front",
     "face": "makes a neutral expression", "hair": "her hair worn loose",
     "doing": "standing in a coffee shop", "outfit": "a casual outfit"},
    {"id": "work_01", "category": "work", "look": 1, "turn": "front",
     "face": "gives a soft flirty smile", "hair": "her hair in a low ponytail",
     "doing": "standing in an office", "outfit": "a work outfit"},
    {"id": "work_02", "category": "work", "look": 2, "turn": "slight-left",
     "face": "makes a neutral expression", "hair": "her hair worn loose",
     "doing": "standing on a rooftop terrace", "outfit": "a smart casual outfit"},
]


def sweep_prompt(trigger: str, look: dict, character: str | None = None) -> str:
    """One trimmed sweep prompt. The subject is her appearance sentence, which
    the eval replaces with "a woman" unless --with-description; a look that puts
    the hair up drops its length words, and a canned up-style is swapped for a
    short-haired character, both exactly as the pack builder does."""
    from sourcemode.assets.wardrobe import short_hair  # noqa: PLC0415

    character = character or trigger
    hair = short_hair(character, look["hair"], look.get("look", 1))
    subject = _render.appearance_clause(character) or "a woman"
    if _render.is_up_style(hair):
        subject = _render.drop_length(subject)
    return (f"{trigger}, portrait picture of {subject} {NATURAL_FRAMING}, {BODY[look['turn']]}, "
            f"she looks directly at the camera and {look['face']}, {hair}, "
            f"{look['doing']} wearing {look['outfit']}")


def asset_prompts(trigger: str) -> list[str]:
    return [sweep_prompt(trigger, l) for l in LOOKS]


# THE TIEBREAKER SET. Jeremy, 2026-10-10, after vivienne's natural sweep: "some of
# the pictures look exactly like her and some look horrible with weird lighting
# ... create 20 new prompts that are all portraits from mid thigh up either front
# facing or a very slight angle looking at the camera with very simple expressions
# like a closed lip smile a broad smile or a neutral expression ... no age ...
# varied outfits, varied backgrounds, some blurred backgrounds, some non-blurred
# backgrounds, mostly indoors ... separate from the normal one ... call it the
# tiebreaker set so I can just tell you to run the tiebreaker set."
#
# Twenty distinct prompts, so an n=20 run renders each once (the asset set
# renders its ten twice). Same builder, same appearance record, same makeup
# and footwear rules as the pack; what differs is held in the slot:
#   turn        front x10, slight-left x5, slight-right x5 - never three-quarter
#   expression  closed-lip x8, neutral x6, teeth x6 - never flirty
#   hair        loose x10, half pinned back x4, low ponytail x4, high ponytail x2
#               (up-styles cost ~9 points across 23 sweeps; no buns, no braids)
#   framing     mid-thigh up, his words
#   age         off, whatever the record says
#   light       warm or soft directional in every one - flat, cool, overcast and
#               dim light cost ~15 points and are what "weird lighting" looks like
#   setting     15 indoors, 5 out; 8 softly blurred behind her, 12 sharp
# Numbers from this set are not comparable to the asset set's; compare sweep to
# sweep within it only.
TIEBREAKER = [
    {"id": "tb_01", "look": 1, "turn": "front", "expression": "closed-lip", "hair": "her hair worn loose",
     "outfit": "a cream ribbed knit sweater and dark jeans",
     "setting": "soft window daylight, in a living room softly blurred behind her"},
    {"id": "tb_02", "look": 2, "turn": "slight-left", "expression": "neutral", "hair": "her hair in a low ponytail",
     "outfit": "a white button-down shirt tucked into high-waisted black trousers",
     "setting": "warm window light, in a bright open-plan office"},
    {"id": "tb_03", "look": 3, "turn": "front", "expression": "teeth", "hair": "her hair worn loose",
     "outfit": "a fitted black turtleneck and a camel wool skirt",
     "setting": "warm directional light, in a cafe with the counter softly blurred behind her"},
    {"id": "tb_04", "look": 4, "turn": "slight-right", "expression": "closed-lip", "hair": "her hair half pinned back",
     "outfit": "a navy silk blouse and tailored grey trousers",
     "setting": "warm afternoon sunlight, against a plain painted wall"},
    {"id": "tb_05", "look": 5, "turn": "front", "expression": "neutral", "hair": "her hair worn loose",
     "outfit": "a soft grey hoodie and black leggings",
     "setting": "soft window daylight, in a tidy bedroom"},
    {"id": "tb_06", "look": 6, "turn": "front", "expression": "teeth", "hair": "her hair in a high ponytail",
     "outfit": "a black sports bra and high-waisted leggings",
     "setting": "warm window light, in a home workout room softly blurred behind her"},
    {"id": "tb_07", "look": 7, "turn": "slight-left", "expression": "closed-lip", "hair": "her hair worn loose",
     "outfit": "a burgundy wrap dress",
     "setting": "warm directional restaurant light, in an elegant dining room"},
    {"id": "tb_08", "look": 8, "turn": "front", "expression": "neutral", "hair": "her hair in a low ponytail",
     "outfit": "a light blue denim jacket over a white tee",
     "setting": "warm late-afternoon sun, on a quiet residential street"},
    {"id": "tb_09", "look": 9, "turn": "slight-right", "expression": "teeth", "hair": "her hair worn loose",
     "outfit": "a sage green linen shirt dress",
     "setting": "golden-hour light, on a rooftop terrace with the city softly blurred behind her"},
    {"id": "tb_10", "look": 10, "turn": "front", "expression": "closed-lip", "hair": "her hair half pinned back",
     "outfit": "an emerald green satin blouse and black trousers",
     "setting": "soft gallery lighting, in an art gallery with pale walls"},
    {"id": "tb_11", "look": 11, "turn": "slight-right", "expression": "neutral", "hair": "her hair worn loose",
     "outfit": "a black fitted cocktail dress with thin straps",
     "setting": "warm evening light, in a hotel lobby with the lamps softly blurred behind her"},
    {"id": "tb_12", "look": 12, "turn": "slight-left", "expression": "teeth", "hair": "her hair in a low ponytail",
     "outfit": "a white cotton blouse and a pleated navy skirt",
     "setting": "soft window daylight, in a sunlit kitchen"},
    {"id": "tb_13", "look": 13, "turn": "front", "expression": "closed-lip", "hair": "her hair worn loose",
     "outfit": "an oversized oatmeal cardigan over a white camisole",
     "setting": "warm lamplight, in a cosy reading nook with bookshelves behind her"},
    {"id": "tb_14", "look": 14, "turn": "slight-left", "expression": "neutral", "hair": "her hair worn loose",
     "outfit": "a charcoal blazer over a white shirt",
     "setting": "warm window light, in a glass-walled meeting room"},
    {"id": "tb_15", "look": 15, "turn": "front", "expression": "teeth", "hair": "her hair in a high ponytail",
     "outfit": "a red zip-up track jacket and black joggers",
     "setting": "warm afternoon sunlight, in a park with the trees softly blurred behind her"},
    {"id": "tb_16", "look": 16, "turn": "front", "expression": "closed-lip", "hair": "her hair in a low ponytail",
     "outfit": "a dusty pink knit top and light-wash jeans",
     "setting": "soft window daylight, in a coffee shop by the window"},
    {"id": "tb_17", "look": 17, "turn": "slight-left", "expression": "closed-lip", "hair": "her hair worn loose",
     "outfit": "a black leather jacket over a grey tee",
     "setting": "warm evening street light, outside a bar at night with the street softly blurred behind her"},
    {"id": "tb_18", "look": 18, "turn": "front", "expression": "closed-lip", "hair": "her hair half pinned back",
     "outfit": "a lilac satin slip dress",
     "setting": "warm directional light, in a bedroom softly blurred behind her"},
    {"id": "tb_19", "look": 19, "turn": "slight-right", "expression": "teeth", "hair": "her hair worn loose",
     "outfit": "a navy-and-white striped long-sleeve top and dark jeans",
     "setting": "warm late-afternoon sun, on a balcony with a plain wall behind her"},
    {"id": "tb_20", "look": 20, "turn": "slight-right", "expression": "neutral", "hair": "her hair half pinned back",
     "outfit": "a cream blouse tucked into a navy A-line skirt",
     "setting": "warm window light, in a bright hallway with a plain white wall behind her"},
]
# the pack's own phrase (render.NATURAL_FRAMING): the eval renders what the pack
# renders. 2026-10-18 it became "from the mid-thigh up"; tiebreaker numbers
# judged before that date are not comparable to ones after it.
from sourcemode.assets.render import NATURAL_FRAMING as TIEBREAKER_FRAMING  # noqa: E402


def tiebreaker_slot(s: dict) -> dict:
    return dict(s, pose="standing", framing_natural=TIEBREAKER_FRAMING)


def tiebreaker_prompts(trigger: str) -> list[str]:
    return [shot_prompt(trigger, tiebreaker_slot(s), backdrop=s["setting"]) for s in TIEBREAKER]


# THE SWEEP SEED. Until 2026-10-11 every sweep used SEED = 8800 + scene, for every
# character, forever. Sharing a seed across a sweep's epochs is right - the epochs
# are then compared on identical noise - but one fixed draw per scene meant an
# unlucky draw failed at every epoch for everyone: vivienne's kitchen and coffee
# shop kept 1 of 20 in her 24-28 sweep and 5 of 8 on fresh seeds with the SAME
# prompt and checkpoint. Jeremy: "randomize the seed at the beginning of a sweep,
# but then keep the seed across each lora epoch". The seed is stored in the
# sweep's folder, so a resumed or re-run sweep renders the same draws.
LEGACY_SEED = 8800


def sweep_seed(out_dir, given: int | None = None) -> int:
    import json  # noqa: PLC0415
    import random  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    out_dir = Path(out_dir)
    f = out_dir / "seed.json"
    if f.is_file():
        return int(json.loads(f.read_text(encoding="utf-8"))["seed"])
    if given is not None:
        seed = int(given)
    elif any(out_dir.glob("ep*/scene_*.png")):
        # renders from before this change are on disk: finishing them on new
        # seeds would mix two sets of draws in one sweep
        seed = LEGACY_SEED
    else:
        seed = random.SystemRandom().randrange(1, 2**31 - 10_000)
    out_dir.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"seed": seed}), encoding="utf-8")
    return seed


if __name__ == "__main__":
    for p in asset_prompts("amanda"):
        print(p[:160], "...")
    print()
    for p in tiebreaker_prompts("amanda"):
        print(p[:160], "...")
