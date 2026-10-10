"""Draft appearance records for the characters that had none.

Read off three sources, in this order of authority:
  1. the game's structured `age` field in characters.js - Jeremy, 2026-10-04:
     "whatever the game says the age is, is the right age"
  2. an explicit ethnicity in her systemPrompt ("Latina", "Asian", "Indian")
  3. her own SHIPPED game assets - the 28 outfits already in the repo are what
     she actually looks like in the product, which beats any reference photo

Everything here is marked DRAFT. Jeremy corrects, and the record is the thing
every render prompt then carries.
"""

import json
from pathlib import Path

P = Path("../characters/appearance.json")
d = json.loads(P.read_text(encoding="utf-8"))

DRAFT = ("DRAFT 2026-10-04, read off her shipped game outfits and reference "
         "photos. Correct anything wrong - this clause goes into every render.")

NEW = {
    "ash": {
        "_note": DRAFT + " Ethnicity is not stated in the game; her renders read "
                         "white and deeply tanned. Waitress at Obsidian.",
        "ethnicity": "White, deeply tanned",
        "build": "slim and athletic with a flat stomach and a narrow waist",
        "bust": "medium-full",
        "figure": "slim athletic figure, narrow waist, medium-full bust",
        "features": ("very long loosely waved balayage hair - dark brown at the roots "
                     "melting to caramel-blonde at the ends - warm brown eyes, tanned "
                     "skin, freckles across her nose and cheeks"),
        "prompt": ("a 24-year-old deeply tanned white woman with a slim athletic figure, "
                   "a narrow waist and a medium-full bust, very long loosely waved "
                   "balayage hair that is dark brown at the roots and caramel-blonde at "
                   "the ends, warm brown eyes, and freckles across her nose and cheeks"),
        "age": 24,
    },
    "cindy": {
        "_note": DRAFT + " Black with a light caramel complexion; her blonde is dyed "
                         "and is a strong identity trait - it must be prompted, like "
                         "geena's magenta. Executive assistant, fashion is her thing.",
        "ethnicity": "Black",
        "build": "slim with a small waist",
        "bust": "medium",
        "figure": "slim figure with a small waist and a medium bust",
        "features": ("very long loosely waved honey-blonde dyed hair, warm brown eyes, "
                     "light caramel-brown skin, full lips"),
        "prompt": ("a 24-year-old Black woman with light caramel-brown skin, a slim "
                   "figure with a small waist and a medium bust, very long loosely waved "
                   "honey-blonde dyed hair, warm brown eyes and full lips"),
        "age": 24,
    },
    "gabi": {
        "_note": DRAFT + " Latina is stated in her systemPrompt. Her training set is "
                         "~90% loose hair, which is why prompted braids kept 20% - the "
                         "hair style is a dataset problem, not an appearance one.",
        "ethnicity": "Latina",
        "build": "slim and petite",
        "bust": "medium",
        "figure": "slim petite figure with a small waist and a medium bust",
        "features": ("very long straight jet-black hair, dark brown eyes, light olive "
                     "skin, full lips"),
        "prompt": ("a 20-year-old Latina woman with a slim petite figure, a small waist "
                   "and a medium bust, light olive skin, very long straight jet-black "
                   "hair, dark brown eyes and full lips"),
        "age": 20,
    },
    "jojo": {
        "_note": DRAFT + " Ethnicity is not stated in the game; her renders read East "
                         "Asian. Head bartender at Obsidian. Trained on the trigger "
                         "`jojo_ch`, not the bare name.",
        "ethnicity": "East Asian",
        "build": "slim with a defined waist",
        "bust": "full",
        "figure": "slim figure with a defined waist and a full bust",
        "features": ("very long dark brown hair with soft waves, dark brown eyes, warm "
                     "light skin"),
        "prompt": ("a 23-year-old East Asian woman with a slim figure, a defined waist "
                   "and a full bust, warm light skin, very long dark brown hair with "
                   "soft waves, and dark brown eyes"),
        "age": 23,
    },
    "keiko": {
        "_note": DRAFT + " Asian is stated in her systemPrompt and her mother Hotaru "
                         "owns Lumen Salon, so likely half Japanese - but her shipped "
                         "renders read MIXED, with sun-lightened brown hair rather than "
                         "black. Worth confirming which you want.",
        "ethnicity": "Asian (reads mixed in her renders)",
        "build": "slim and petite, youthful",
        "bust": "small-medium",
        "figure": "slim petite youthful figure with a small-medium bust",
        "features": ("very long wavy brown hair with sun-lightened caramel ends, warm "
                     "brown eyes, golden-tan skin, a soft round face"),
        "prompt": ("an 18-year-old Asian woman with a slim petite youthful figure, "
                   "golden-tan skin, very long wavy brown hair with sun-lightened "
                   "caramel ends, warm brown eyes and a soft round face"),
        "age": 18,
    },
    "kimmy": {
        "_note": DRAFT + " One of only two blue-eyed characters in the cast, so the "
                         "eye colour has to be prompted or the base model will give "
                         "her brown. Church on Sundays, The Chill Trap in the evenings.",
        "ethnicity": "White",
        "build": "slim with a small waist",
        "bust": "full",
        "figure": "slim figure with a small waist and a full bust",
        "features": ("very long straight light blonde hair, pale blue-grey eyes, fair "
                     "skin, soft features"),
        "prompt": ("a 24-year-old white woman with fair skin, a slim figure with a small "
                   "waist and a full bust, very long straight light blonde hair, pale "
                   "blue-grey eyes and soft features"),
        "age": 24,
    },
    "maya": {
        "_note": DRAFT + " HER HAIR HAS A TURQUOISE UNDERLAYER - clearly visible in "
                         "three of her four shipped outfits. Same shape as vivienne's "
                         "pink: an identity trait the LoRA will not volunteer, so it "
                         "must be named in the prompt or every render comes back plain "
                         "brown. The game says age 26; her systemPrompt prose says 24.",
        "ethnicity": "Latina",
        "build": "slim and athletic",
        "bust": "medium",
        "figure": "slim athletic figure with a narrow waist and a medium bust",
        "features": ("very long dark brown hair with a vivid turquoise dyed underlayer "
                     "showing at the ends beneath the top layer, dark brown eyes, "
                     "olive-tan skin, freckles across her nose, strong dark brows"),
        "prompt": ("a 26-year-old Latina woman with olive-tan skin, a slim athletic "
                   "figure with a narrow waist and a medium bust, very long dark brown "
                   "hair with a vivid turquoise dyed underlayer showing at the ends "
                   "beneath the top layer, dark brown eyes, strong dark brows and "
                   "freckles across her nose"),
        "age": 26,
    },
    "priya": {
        "_note": DRAFT + " The ONLY character with short hair and the ONLY one who "
                         "wears glasses - both in every shipped outfit. The glasses "
                         "belong in HER clause and nobody else's: a shared 'her "
                         "glasses' descriptor once corrupted three of four characters. "
                         "The game says age 22; her systemPrompt prose says late 20s.",
        "ethnicity": "Indian",
        "build": "slim with an hourglass shape",
        "bust": "full",
        "figure": "slim hourglass figure with a small waist and a full bust",
        "features": ("a chin-length dark brown bob parted to one side, black-framed "
                     "rectangular glasses she always wears, dark brown eyes, medium "
                     "brown skin, full lips"),
        "prompt": ("a 22-year-old Indian woman with medium brown skin, a slim hourglass "
                   "figure with a small waist and a full bust, a chin-length dark brown "
                   "bob parted to one side, black-framed rectangular glasses, dark brown "
                   "eyes and full lips"),
        "age": 22,
    },
    "priyanka": {
        "_note": DRAFT + " Indian is stated in her systemPrompt. Teaching assistant at "
                         "Chill Coast University. Her epoch-26 extension is the project "
                         "record for a rescued undertrained run: 21% -> 64%.",
        "ethnicity": "Indian",
        "build": "slim and petite",
        "bust": "small-medium",
        "figure": "slim petite figure with a small waist and a small-medium bust",
        "features": ("very long straight black hair, dark brown eyes, medium brown skin, "
                     "a warm open face"),
        "prompt": ("a 20-year-old Indian woman with medium brown skin, a slim petite "
                   "figure with a small waist, very long straight black hair, dark brown "
                   "eyes and a warm open face"),
        "age": 20,
    },
    "sandra": {
        "_note": DRAFT + " The only redhead in the cast, so the hair colour must be "
                         "prompted. 38 and a single mother; her shipped wardrobe is "
                         "noticeably more covered than anyone else's and should stay "
                         "that way.",
        "ethnicity": "White",
        "build": "slim",
        "bust": "modest",
        "figure": "slim figure with a modest bust",
        "features": ("long wavy copper-red hair, green eyes, fair freckled skin, warm "
                     "laugh lines"),
        "prompt": ("a 38-year-old white woman with fair freckled skin, a slim figure "
                   "with a modest bust, long wavy copper-red hair and green eyes"),
        "age": 38,
    },
    "trina": {
        "_note": DRAFT + " Green eyes and platinum hair, both of which the base model "
                         "will not volunteer. Works at Vale Contemporary in the Hill "
                         "district. The game says age 33; her systemPrompt prose says "
                         "29.",
        "ethnicity": "White",
        "build": "curvy with an hourglass shape",
        "bust": "full",
        "figure": "curvy hourglass figure with a small waist and a full bust",
        "features": ("very long loosely waved platinum-blonde hair, green eyes, light "
                     "tanned skin, strong defined brows, full lips"),
        "prompt": ("a 33-year-old white woman with light tanned skin, a curvy hourglass "
                   "figure with a small waist and a full bust, very long loosely waved "
                   "platinum-blonde hair, green eyes, strong defined brows and full lips"),
        "age": 33,
    },
}

for k, v in NEW.items():
    if k in d:
        print(f"SKIP {k} - already has a record")
        continue
    d[k] = v
    print(f"added {k}")

P.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"\n{len([k for k in d if not k.startswith('_')])} characters on record")
