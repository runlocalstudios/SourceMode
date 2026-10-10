"""Eval scenes that ARE the asset generator's prompts.

Jeremy, 2026-10-02: "The real test would be to generate 10 different examples that
look just like the asset generator prompts." So these are not scenes at all - each
is the exact text `sourcemode.assets.render.shot_prompt` emits for a wardrobe-pack
look (the ported Codex contract: mid-thigh-up crop, body turn, head turn, closed
expression table), for ten looks spread across the six categories and the four
seeded hairstyles. The eval renders the prompt verbatim through the LoRA; nothing
is prepended.
"""
from sourcemode.assets.render import shot_prompt

# ten looks: category coverage 2/2/2/1/1/2, hair loose x4 / up x6 the way the packs run
# Jeremy, 2026-10-03: the epoch evals came back on the magenta key backdrop, because
# they render the asset prompt verbatim and that is what a shipping asset needs. For
# judging he wants a real setting - "it looks more real" - so every look carries one.
# Everything else about the prompt stays byte-identical to what `assets render` emits.
#
# 2026-10-09: across 23 judged sweeps (1,720 verdicts) the four scenes lit flat or
# cool - overcast, gym, dim restaurant, office - filled four of the bottom five
# (28-35% keep) while every warm directional setting sat in the top half (41-49%).
# The packs render on the grey key, so flat light was an eval-only penalty. Jeremy:
# "We don't need to do a resweep, just change it to fix it." Those four now carry
# warm directional light; the places stay. Sweeps judged before this date used the
# old strings, so their scene_02/03/04/08 rates are not comparable to new ones.
SETTINGS = [
    "soft window daylight, in a sunlit kitchen",
    "warm late-afternoon sun, on a quiet residential street",
    "warm afternoon sunlight, against a plain painted wall",
    "warm late-afternoon window light, in a modern gym with mirrors behind her",
    "warm directional restaurant light, in an elegant dining room",
    "soft gallery lighting, in an art gallery with pale walls",
    "evening street light, outside a bar at night",
    "soft window daylight, in a coffee shop by the window",
    "warm window light, in a bright open-plan office",
    "golden-hour light, on a rooftop terrace at dusk",
]

LOOKS = [
    {"id": "casual_01", "category": "casual", "look": 1, "outfit": "a soft oatmeal knit sweater and straight-leg jeans", "hair": "her hair worn loose"},
    {"id": "casual_02", "category": "casual", "look": 2, "outfit": "a white cotton blouse and dark jeans", "hair": "her hair in a high ponytail"},
    {"id": "workout_01", "category": "workout", "look": 1, "outfit": "a black sports bra and high-waisted leggings", "hair": "her hair in a high ponytail"},
    {"id": "workout_02", "category": "workout", "look": 2, "outfit": "a sage green workout tank and dark joggers", "hair": "her hair up in a messy bun"},
    {"id": "fancy_dining_gallery_01", "category": "fancy_dining_gallery", "look": 1, "outfit": "a long-sleeved emerald green midi dress", "hair": "her hair in a low chignon"},
    {"id": "fancy_dining_gallery_02", "category": "fancy_dining_gallery", "look": 2, "outfit": "a black sheath dress with a high neckline", "hair": "her hair worn loose"},
    {"id": "fancy_town_01", "category": "fancy_town", "look": 1, "outfit": "a fitted black cocktail dress with three-quarter sleeves", "hair": "her hair half pinned back"},
    {"id": "casual_date_01", "category": "casual_date", "look": 1, "outfit": "a deep green wrap blouse and dark slim jeans", "hair": "her hair worn loose"},
    {"id": "work_01", "category": "work", "look": 1, "outfit": "a cream blouse tucked into a navy A-line skirt", "hair": "her hair in a low ponytail"},
    {"id": "work_02", "category": "work", "look": 2, "outfit": "a soft grey cardigan over a white shirt, charcoal trousers", "hair": "her hair worn loose"},
]


def asset_prompts(trigger: str) -> list[str]:
    return [shot_prompt(trigger, dict(l, pose="standing"), backdrop=SETTINGS[i % len(SETTINGS)])
            for i, l in enumerate(LOOKS)]


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
# renders its ten twice). Same builder, same appearance record, same makeup,
# fitted and footwear rules as the pack; what differs is held in the slot:
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
TIEBREAKER_FRAMING = "framed from mid-thigh up"


def tiebreaker_slot(s: dict) -> dict:
    return dict(s, pose="standing", age=False, framing_natural=TIEBREAKER_FRAMING)


def tiebreaker_prompts(trigger: str) -> list[str]:
    return [shot_prompt(trigger, tiebreaker_slot(s), backdrop=s["setting"]) for s in TIEBREAKER]


if __name__ == "__main__":
    for p in asset_prompts("amanda"):
        print(p[:160], "...")
    print()
    for p in tiebreaker_prompts("amanda"):
        print(p[:160], "...")
