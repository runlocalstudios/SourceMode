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
SETTINGS = [
    "soft window daylight, in a sunlit kitchen",
    "warm late-afternoon sun, on a quiet residential street",
    "even overcast daylight, against a plain painted wall",
    "cool gym lighting, in a modern gym with mirrors behind her",
    "low warm restaurant light, in a dim dining room",
    "soft gallery lighting, in an art gallery with pale walls",
    "evening street light, outside a bar at night",
    "soft window daylight, in a coffee shop by the window",
    "even office lighting, in a bright open-plan office",
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


if __name__ == "__main__":
    for p in asset_prompts("amanda"):
        print(p[:160], "...")
