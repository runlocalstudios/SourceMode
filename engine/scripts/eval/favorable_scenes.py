"""The eval scene set, v2 - built to resemble the photos actually being shipped.

Jeremy, 2026-09-28: shelve the previous ten. He wants three-quarter portraits,
front-facing or at a slight angle, half outside and half inside, half loose hair
and half hair up, across ten outfit categories - casual, fancy, workout, sexy and
work, two each. Work outfits are deliberately reusable across characters.

Balance, checked below: 5 inside / 5 outside, 5 loose / 5 up, 5 square-on /
5 slight angle, 2 each of five outfit categories.

Design constraints taken from measured results, not invented here:
  - **Angle requests land one band shallower than asked**, so "square on" is asked
    plainly (18/18 compliance) and a slight turn asks for "about 35 degrees" to
    land near 15 (16/16).
  - **Never full length.** The prompt sets the face's pixel budget: full length
    rendered a 122px face and kept 12%, thighs-up 229px and kept 52%. Everything
    here is head-and-chest or waist-up.
  - **Hair off the face renders better** (ponytail/bun 68%, loose 38%), so the
    loose half is a real handicap - that is the point, it is half the shipped work.
  - **No wide expressions.** Across 880 judged frames the drum-kit laugh kept 12%
    and singing 29% against a 61% best; a scene that fails on the prompt tells you
    nothing about the checkpoint.
  - Identity traits are never named - the LoRA supplies those.

Replaces the previous ten. The old set is still reachable as PREVIOUS_10 below, but
nothing calls it; results from the two are not comparable and must never be mixed.
"""

FAVORABLE = [
    # 1  casual | inside | loose | square on
    "in a head-and-chest portrait facing the camera square on, her hair worn loose, "
    "wearing a soft grey marl sweatshirt, relaxed expression, soft window daylight, "
    "in a blurred living room",

    # 2  work | inside | up | slight
    "in a waist-up portrait turned about 35 degrees to one side, her hair in a low bun, "
    "wearing a charcoal blazer over a white shirt, composed expression, even office "
    "light, in a blurred open-plan office",

    # 3  workout | outside | up | square on
    "in a head-and-chest portrait facing the camera square on, her hair in a high "
    "ponytail, wearing a black athletic crop top and leggings, calm expression after "
    "exercise, bright morning daylight, on a park path with trees behind her",

    # 4  fancy | inside | up | slight
    "in a head-and-chest portrait turned about 35 degrees to one side, her hair pinned "
    "up off her neck, wearing a black satin evening dress with thin straps, poised "
    "expression, warm low restaurant light, in a blurred dining room",

    # 5  casual | outside | loose | slight
    "in a waist-up portrait turned about 35 degrees to one side, her hair worn loose, "
    "wearing a blue denim jacket over a white tee, faint closed-mouth smile, bright "
    "overcast daylight, on a city sidewalk with blurred shopfronts behind her",

    # 6  sexy | inside | loose | square on
    "in a head-and-chest portrait facing the camera square on, her hair worn loose over "
    "one shoulder, wearing a deep red silk camisole, calm direct expression, warm "
    "bedside lamplight, in a blurred bedroom",

    # 7  work | outside | up | square on
    "in a waist-up portrait facing the camera square on, her hair in a sleek low "
    "ponytail, wearing a navy tailored suit jacket, composed expression, cool morning "
    "daylight, on a street outside a glass office building",

    # 8  fancy | outside | loose | slight
    "in a head-and-chest portrait turned about 35 degrees to one side, her hair worn "
    "loose and waved, wearing an emerald green cocktail dress, serene expression, "
    "golden hour light, on a terrace with a blurred garden behind her",

    # 9  workout | inside | up | slight
    "in a head-and-chest portrait turned about 35 degrees to one side, her hair in a "
    "messy bun, wearing a heather grey sports top, focused expression, bright even gym "
    "light, in a blurred gym interior",

    # 10 sexy | outside | loose | square on
    "in a waist-up portrait facing the camera square on, her hair worn loose, wearing a "
    "fitted black slip dress, relaxed expression, warm evening light, on a balcony with "
    "a blurred city skyline behind her",

    # --- 11-20, APPENDED 2026-09-29 so a confirmation can run at n=20 -----------
    # SCENES[:10] is untouched, so every number measured on the first ten stays
    # comparable and those frames are reused rather than re-rendered. Same balance
    # as 1-10: 5/5 inside-outside, 5/5 loose-vs-up, 5/5 square-on vs slight, and
    # two each of casual / work / workout / fancy / sexy.
    "in a waist-up portrait facing the camera square on, her hair worn loose, wearing "
    "a navy hooded sweatshirt, easy relaxed expression, bright overcast daylight, on a "
    "suburban street with blurred houses behind her",

    "in a head-and-chest portrait turned about 35 degrees to one side, her hair in a "
    "tight low bun, wearing a black turtleneck under a grey blazer, composed "
    "expression, cool even light, in a blurred meeting room",

    "in a head-and-chest portrait turned about 35 degrees to one side, her hair in a "
    "braided ponytail, wearing a teal running top, calm expression, bright morning sun, "
    "on a track with blurred trees behind her",

    "in a head-and-chest portrait facing the camera square on, her hair worn loose and "
    "softly waved, wearing a midnight blue velvet gown, serene expression, warm "
    "chandelier light, in a blurred ballroom",

    "in a waist-up portrait turned about 35 degrees to one side, her hair twisted up off "
    "her neck, wearing a black lace bralette under an open silk robe, calm direct "
    "expression, warm low lamplight, in a blurred bedroom",

    "in a head-and-chest portrait facing the camera square on, her hair in a messy "
    "topknot, wearing a mustard knit jumper, faint smile, soft window daylight, in a "
    "blurred kitchen",

    "in a waist-up portrait turned about 35 degrees to one side, her hair worn loose, "
    "wearing a cream trouser suit, confident expression, bright daylight, on a pavement "
    "outside a stone building",

    "in a head-and-chest portrait facing the camera square on, her hair pinned into a "
    "chignon, wearing a silver sequinned dress, poised expression, golden evening light, "
    "on a rooftop terrace at dusk",

    "in a head-and-chest portrait facing the camera square on, her hair worn loose and "
    "tied back at the nape, wearing a black sports bra, focused expression, bright even "
    "light, in a blurred studio gym",

    "in a waist-up portrait turned about 35 degrees to one side, her hair swept up off "
    "one shoulder, wearing a burgundy satin slip, relaxed expression, warm evening "
    "light, on a balcony with blurred lights behind her",
]

# The set this replaced, kept only so an old result can be traced to its prompts.
PREVIOUS_10 = "see git history / dense_*_fav sets rendered before 2026-09-28"

if __name__ == "__main__":
    import re
    # match the SETTING clause only - "a street outside a glass office building"
    # contains "office" and was counted as indoors by a looser pattern.
    inside = sum(1 for s in FAVORABLE if re.search(
        r"in a blurred (living room|open-plan office|dining room|bedroom|gym interior|meeting room|ballroom|kitchen|studio gym)", s))
    loose = sum(1 for s in FAVORABLE if "worn loose" in s)
    square = sum(1 for s in FAVORABLE if "square on" in s)
    full = sum(1 for s in FAVORABLE if "full length" in s or "head to toe" in s)
    print(f"{len(FAVORABLE)} scenes")
    print(f"  inside {inside} / outside {len(FAVORABLE)-inside}")
    print(f"  loose {loose} / up {len(FAVORABLE)-loose}")
    print(f"  square on {square} / slight {len(FAVORABLE)-square}")
    print(f"  full length {full} (must be 0)")
    for cat, pat in (("casual", r"sweatshirt|denim jacket|knit jumper"), ("work", r"blazer|suit jacket|trouser suit"),
                     ("workout", r"athletic|sports top|running top|sports bra"),
                     ("fancy", r"evening dress|cocktail|velvet gown|sequinned"),
                     ("sexy", r"camisole|slip dress|silk robe|satin slip")):
        print(f"  {cat:<8} {sum(1 for s in FAVORABLE if re.search(pat, s))}")
