"""The influencer pack: a feed's worth of social photos per batch, from her LoRA.

Jeremy, 2026-10-05: a generic pack whose pictures still come out different per
character and per batch, so the feeds can be scheduled without looking cloned,
and one that injects "the character's in-game job and hobbies". The mix, as he
set it the same day:

    3 job        her work locations from the game schedule
    3 hobby      every other place her week takes her
    2 lifestyle  cafe, street, rooftop - nobody's location in particular
    2 sightseeing  one recognizable international landmark, one in the US,
                 asked generically on purpose - he wants to see whether the
                 model varies the landmark before we name a list
    1 pool       swimwear
    1 beach
    2 boudoir    suggestive, and NO lingerie to start

WHERE THE JOB AND HOBBIES COME FROM. Not prose: `characters.js` gives every
character a weekly schedule of (location, outfit), and the outfit already says
which is which - 'work', 'stripper' and 'server' are a shift, anything else is
her own time. `PLACES` turns each game location into a scene once, by hand, so
nothing per character needs a model or a guess. A test fails the day the game
schedules someone at a location that has no scene here.

VARIETY. Every pick - which of her places, which moment there, outfit, hair -
comes from one RNG seeded by (character, batch). Batch 3 for zara is always the
same 14 pictures, and is never zara's batch 2 or geena's batch 3.

Every slot renders through `assets.render.shot_prompt`, so her age, appearance,
frame, negative, the expression table and the no-footwear rule are shared with
the wardrobe pack and cannot drift.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

#: A schedule outfit that means she is at work rather than out.
WORK_OUTFITS = frozenset({"work", "stripper", "server", "uniform"})

# Wording from Qwen-Image-2512's own release material, which leads on reducing
# the AI look and demos it with "a casual iPhone snapshot: unpretentious
# composition" (qwen-image.net/blog/qwen-image-2512, researched 2026-10-05).
# Untested on our LoRAs - his keep rate on the first batch is the measurement.
SHOT_TYPE = "casual iPhone snapshot"
REAL = ("unpretentious, slightly off-centre composition; the scene's own real light, no staged "
        "studio light; visible skin texture and fine pores, a few flyaway hairs, no retouching")

# --- composition ----------------------------------------------------------------
# Head to mid-thigh with the face large: the measured rule for identity (a
# 122px full-length face kept 12%), and what an Instagram feed crop wants.
FRAMING = ("candid photo a friend took of her on a phone, framed from mid-thigh up; her face is "
           f"large, sharp and in focus; never a wide shot, never full-body; {REAL}")
SIGHT_FRAMING = ("travel photo a friend took of her on a phone, framed from the waist up and set "
                 "to one side of the frame so the landmark behind her is clearly visible and "
                 "recognizable; her face is still large, sharp and in focus; never full-body; "
                 f"{REAL}")
BOUDOIR_FRAMING = ("intimate candid photo from her partner's phone, framed from her head to her "
                   f"hips; her face is large, sharp and in focus; never a wide shot; {REAL}")

AVOID = ("No studio lighting, no plain backdrop, no catalogue posing, no legible text or "
         "signage, no other people in focus. No profiles, rear views or off-camera gaze.")

# --- her places: game location -> scenes ---------------------------------------
# Each moment is (setting, outfit, stance). "job" is used when the schedule has
# her working there, "hobby" otherwise; a location missing one falls back to the
# other. Settings follow the shoot convention - light first, then the place -
# and never hard midday sun or wet hair (both fail on this generator).
PLACES: dict[str, dict[str, list[tuple[str, str, str]]]] = {
    "adultStore": {
        # Never the shelves: a public feed sees a boutique counter.
        "job": [("soft pink boutique lighting, behind the counter of a small upscale boutique",
                 "a fitted black wrap top and high-waisted trousers", "leaning on the counter, smiling")],
        "hobby": [("soft pink boutique lighting, in a small upscale boutique",
                   "a satin camisole under an oversized blazer", "browsing a display, glancing back")]},
    "barbershop": {
        "hobby": [("warm vintage light, in a classic barbershop with leather chairs",
                   "a cropped denim jacket over a white tee", "sitting sideways in a barber chair")]},
    "central_street": {
        "hobby": [("soft morning light, on a wide civic boulevard with stone buildings",
                   "a matching running set", "jogging past, smiling at the camera"),
                  ("golden-hour light, on the steps of a grand civic building",
                   "a fitted ribbed dress and a cropped denim jacket", "sitting on the steps")]},
    "hill_street": {
        "job": [("soft morning light, on a quiet upscale street lined with townhouses",
                 "a tailored camel coat over a fitted knit dress", "walking, a leather tote on her arm")],
        "hobby": [("golden-hour light, on a quiet upscale street with flower boxes",
                   "a silk midi skirt and a fitted knit top", "strolling past a townhouse door"),
                  ("warm evening light, outside an elegant wine bar on a quiet hill street",
                   "a black satin slip dress and a light blazer", "standing by a bistro table")]},
    "officePark": {
        "job": [("bright even office light, in a modern open-plan office",
                 "a fitted blouse tucked into a pencil skirt", "sitting on the edge of a desk, laptop open"),
                ("soft window light, in a glass-walled meeting room",
                 "a tailored blazer over a silk camisole", "standing by the window, coffee in hand"),
                ("bright midday shade, on the lawn outside a glass office building",
                 "a crisp white shirt and wide-leg trousers", "walking with a laptop under her arm")]},
    "policeStation": {
        "job": [("bright even light, in the lobby of a city police precinct",
                 "a fitted navy police uniform", "standing at the front desk, hands resting on it")]},
    "aireSpa": {
        "job": [("soft warm candlelight, in a calm day-spa treatment room with folded white towels",
                 "a fitted black spa tunic", "standing beside the treatment table, hands folded")],
        "hobby": [("soft diffused light, in a quiet spa lounge with eucalyptus and stone",
                   "a plush white spa robe", "sitting on a cushioned lounger, legs tucked to one side")]},
    "artGallery": {
        "job": [("soft gallery lighting, in a white-walled contemporary art gallery",
                 "a black turtleneck and tailored black trousers",
                 "standing beside a large abstract canvas, holding a clipboard")],
        "hobby": [("soft gallery lighting, in a contemporary art gallery with pale walls",
                   "a cream knit dress", "standing in front of a large painting, glancing back")]},
    "beach": {
        "hobby": [("golden-hour light, on a wooden boardwalk by the sea",
                   "a white linen shirt tied at the waist over denim shorts",
                   "leaning on the boardwalk railing")]},
    "beachBar": {
        "job": [("warm late-afternoon light, behind the counter of a thatched-roof beach bar",
                 "a fitted white tank top and a short denim skirt with a black apron",
                 "leaning on the bar, a cocktail shaker in one hand")],
        "hobby": [("golden-hour light, at a thatched-roof beach bar with the sea behind",
                   "a flowing floral sundress", "sitting on a bar stool, a cocktail in hand")]},
    "bellaNotte": {
        "job": [("warm candlelight, in a cosy Italian trattoria between tables",
                 "a crisp white shirt and a black waist apron",
                 "standing with a tray of wine glasses balanced on one hand")],
        "hobby": [("warm candlelight, at a small table in a cosy Italian trattoria",
                   "a black off-shoulder top", "sitting at the table, twirling pasta")]},
    "belvedereGardens": {
        "hobby": [("soft golden-hour light, on a terraced garden path with the city below",
                   "a pale yellow sundress", "standing at a stone balustrade, hand on the rail"),
                  ("dappled shade, beside a flowering hedge in a formal garden",
                   "a white eyelet blouse and a long linen skirt", "sitting on a stone bench")]},
    "chillTrap": {
        # The club floor stays off a public feed: the job is getting ready.
        "job": [("warm vanity-bulb light, in a backstage dressing room with a lit mirror",
                 "a short black satin robe", "sitting at the vanity turned toward the camera, "
                 "a makeup brush in her hand"),
                ("neon light at night, outside a club entrance",
                 "a cropped black leather jacket over a sequined mini dress",
                 "leaning against the brick wall by the door")]},
    "church": {
        "hobby": [("soft morning light, on the steps outside a white clapboard church",
                   "a modest floral midi dress and a light cardigan", "standing on the steps")]},
    "coffeeShop": {
        "job": [("warm morning light, behind the counter of a cosy coffee shop",
                 "a black tee and a canvas barista apron",
                 "pouring latte art into a cup, glancing up at the camera")],
        "hobby": [("soft window light, at a window table in a warm coffee shop",
                   "an oversized cream knit sweater", "sitting with a latte held in both hands")]},
    "cupAndGo": {
        "job": [("bright morning light, behind the counter of a small takeaway coffee shop",
                 "a fitted green polo and a black apron", "handing a coffee cup across the counter")],
        "hobby": [("bright morning light, on the sidewalk outside a small coffee shop",
                   "a cropped hoodie and high-waisted jeans", "holding an iced coffee, mid-step")]},
    "fastFood": {
        "hobby": [("warm neon light at night, in a booth at a retro burger joint",
                   "a vintage graphic tee and a denim jacket",
                   "sitting in the booth, a milkshake in front of her")]},
    "fitness24": {
        "job": [("cool even gym lighting, on the floor of a modern gym",
                 "a fitted staff polo and black leggings", "standing with a clipboard by the racks")],
        "hobby": [("cool even gym lighting, in a modern gym with mirrors behind her",
                   "a matching seamless sports bra and leggings set",
                   "standing with a towel over one shoulder, water bottle in hand"),
                  ("soft morning light, in a calm yoga studio with wooden floors",
                   "a ribbed crop top and flared yoga pants", "sitting cross-legged on a mat")]},
    "grocery": {
        "hobby": [("soft natural light, in the produce section of a neighbourhood grocery",
                   "a striped tee and a denim skirt", "holding a bunch of fresh flowers")]},
    "hospital": {
        "job": [("bright even light, in a clean hospital corridor",
                 "light blue scrubs", "standing with a tablet held to her chest")],
        "hobby": [("bright even light, in a clean hospital corridor",
                   "light blue volunteer scrubs", "standing with a tablet held to her chest")]},
    "laMaison": {
        "job": [("low warm light, at the host stand of an elegant French restaurant",
                 "a sleek black sheath dress", "standing at the stand, menus in hand")],
        "hobby": [("low warm candlelight, at a white-tablecloth table in an elegant French restaurant",
                   "a satin slip dress in deep emerald", "sitting with a glass of champagne")]},
    "laundromat": {
        "hobby": [("cool fluorescent light at night, in a retro laundromat",
                   "an oversized hoodie and bike shorts", "sitting on top of a washing machine")]},
    "leChic": {
        "job": [("bright boutique lighting, in an upscale clothing boutique",
                 "a tailored blazer over a silk camisole", "arranging a rack of dresses")],
        "hobby": [("bright boutique lighting, in front of a fitting-room mirror in a chic boutique",
                   "a fitted designer mini dress with the tag still on", "turning to check the fit")]},
    "library": {
        "job": [("soft warm light, between tall shelves in a grand old library",
                 "a cardigan over a collared blouse", "shelving books from a cart")],
        "hobby": [("soft warm light, at a long reading table in a grand old library",
                   "an oversized knit sweater", "sitting with an open book, pen in hand")]},
    "lumenSalon": {
        "job": [("bright polished light, in a modern hair salon",
                 "a sleek black smock over a black top", "standing behind a salon chair, scissors in hand")]},
    "meridianResidential": {
        "job": [("bright afternoon light, in a sleek real-estate sales gallery",
                 "a tailored cream pantsuit", "standing beside a lit architectural model")]},
    "musicVenue": {
        "job": [("moody coloured stage light, behind the bar of a small live-music venue",
                 "a band tee knotted at the waist and black jeans", "leaning on the bar")],
        "hobby": [("moody coloured stage light, in the crowd at a small live-music venue",
                   "a band tee and a black leather jacket", "turning back toward the camera, smiling")]},
    "obsidian": {
        "job": [("low club lighting with coloured spill, in a black-walled nightclub",
                 "a short black waitress dress with white piping", "carrying a tray of drinks")],
        "hobby": [("low club lighting with coloured spill, in a dim nightclub",
                   "a metallic halter top and a leather mini skirt", "standing at the bar, drink in hand")]},
    "park": {
        "hobby": [("soft morning light, on a tree-lined jogging path in a green park",
                   "a cropped running tank and running shorts", "pausing mid-run, catching her breath"),
                  ("golden-hour light, on a picnic blanket in a green park",
                   "a gingham sundress", "sitting on the blanket with a paperback")]},
    "recordShop": {
        "hobby": [("warm light, between crates in a vintage record shop",
                   "a vintage band tee and a corduroy mini skirt", "holding up a vinyl record")]},
    "street": {
        "job": [("soft morning light, on a city sidewalk on her way to work",
                 "a trench coat over a fitted knit dress", "walking, a takeaway coffee in hand")],
        "hobby": [("golden-hour light, on a lively neighbourhood street with shopfronts",
                   "a slip skirt and an oversized denim jacket", "walking toward the camera, mid-laugh")]},
    "tavern": {
        "job": [("warm pub light with a game on the TVs, behind the bar of a sports pub",
                 "a fitted black tee and jeans", "pulling a pint from the tap")],
        "hobby": [("warm pub light, beside a pool table in a sports pub",
                   "a cropped flannel shirt and jeans", "leaning on a pool cue")]},
    "threads": {
        "job": [("bright store lighting, in a casual clothing store",
                 "a fitted tee and high-waisted jeans with a name tag", "folding sweaters at a table")],
        "hobby": [("bright store lighting, in front of a mirror in a casual clothing store",
                   "a cropped cardigan and a pleated skirt", "holding a dress up against herself")]},
    "unionMarket": {
        "job": [("warm market light, behind a food counter in a busy market hall",
                 "a striped apron over a white tee", "handing a paper boat of food across the counter")],
        "hobby": [("warm market light, at a flower stall in a busy market hall",
                   "a linen button-down and wide-leg trousers", "holding a bouquet of peonies")]},
    "university": {
        # The game's university staff are teaching assistants, not professors.
        "job": [("bright classroom light, at the whiteboard of a small seminar room",
                 "a fitted knit sweater and tailored trousers",
                 "standing by the whiteboard, a marker in her hand"),
                ("soft desk-lamp light, in a cramped office-hours room stacked with papers",
                 "a cardigan over a white blouse", "sitting at the desk, pen in hand, papers spread out")],
        "hobby": [("soft afternoon light, on a leafy university campus lawn",
                   "a cropped cardigan and a pleated mini skirt", "sitting on the grass with a laptop and books"),
                  ("soft warm light, at a cafe table on campus", "an oversized university sweatshirt",
                   "sitting with notes spread out, highlighter in hand")]},
}

# --- nobody's places -----------------------------------------------------------
LIFESTYLE = [
    ("warm morning light, at a sunny brunch table on a cafe terrace",
     "a white square-neck top and linen trousers", "sitting with a mimosa, chin on her hand"),
    ("golden-hour light, at a city crosswalk with blurred traffic behind her",
     "a fitted ribbed dress and a cropped denim jacket", "walking toward the camera"),
    ("blue-hour light, on a rooftop terrace with city lights behind her",
     "a black one-shoulder top and satin trousers", "leaning on the glass railing, drink in hand"),
    ("soft window light, in a cosy independent bookstore",
     "an oversized blazer over a white tee and jeans", "holding an open book, glancing up"),
    ("soft morning light, at a farmers market stall piled with fruit",
     "a linen sundress", "holding a paper bag of peaches"),
    ("soft window light, on a window seat in a bright apartment",
     "an oversized button-down shirt and bike shorts", "sitting with a mug in both hands"),
    ("golden-hour light, in the passenger seat of a car",
     "a cropped white tee and sunglasses pushed up on her head", "turned toward the camera, smiling"),
]

#: Generic on purpose (see the module docstring); one of each per batch.
SIGHT_INTL = ("{light}, in front of a famous, instantly recognizable international landmark "
              "abroad, a real place a traveller would photograph")
SIGHT_US = ("{light}, in front of a famous, instantly recognizable landmark in the United States, "
            "a real place a traveller would photograph")
SIGHT_LIGHT = ["golden-hour light", "soft morning light", "blue-hour light", "soft overcast daylight"]
SIGHT_OUTFIT = ["a flowy white sundress", "a fitted black tee and high-waisted wide-leg trousers",
                "a light trench coat over a striped top and jeans",
                "a linen co-ord set in sage green", "a cropped knit cardigan and a midi skirt"]
SIGHT_STANCE = ["standing with one hand holding her sunglasses",
                "turning back toward the camera mid-step", "standing with a coffee in hand, smiling"]

POOL = [("soft open shade, beside a rooftop hotel pool with loungers",
         "a black triangle bikini", "sitting on the pool edge, legs in the water"),
        ("golden-hour light, beside the infinity pool of a hillside villa",
         "a white one-piece swimsuit cut high on the hip", "standing at the pool edge, weight on one hip"),
        ("soft open shade, beside a resort pool lined with palms",
         "a red bikini with tie sides", "sitting on a white lounger, leaning back on her hands"),
        ("golden-hour light, beside a turquoise pool with white tiles",
         "a sage green ribbed bikini", "leaning on the pool ladder, smiling")]

BEACH = [("golden-hour light, on a quiet beach at the water's edge",
          "a crochet bikini top and a sheer sarong", "walking along the waterline toward the camera"),
         ("soft late-afternoon light, on white sand with dunes behind her",
          "an oversized linen shirt open over a bikini", "standing with the shirt lifting in the breeze"),
         ("golden-hour light, on a beach towel on the sand",
          "a bandeau bikini", "sitting with her knees drawn up, smiling over her shoulder"),
         ("soft overcast light, on a rocky beach path",
          "a flowing white beach cover-up dress", "standing with her hands in her hair")]

#: No lingerie (Jeremy, 2026-10-05). Poses keep her face upright - "on her
#: back" shoots from the feet and inverts the face (0/12 kept).
BOUDOIR = [("soft morning window light, in a bright bedroom with white sheets",
            "an oversized white button-down shirt, half buttoned", "sitting on the edge of the bed"),
           ("soft morning light, in a hotel bed with rumpled white sheets",
            "a white bedsheet wrapped loosely around her", "half-sitting against the headboard"),
           ("warm lamplight, in a softly lit bedroom",
            "a short silk robe loosely tied", "lying on her side propped on one elbow"),
           ("soft window light, in a cosy bedroom",
            "an oversized knit sweater slipping off one shoulder", "sitting cross-legged on the bed")]

#: (tone, how many) in render order.
MIX = (("job", 3), ("hobby", 3), ("lifestyle", 2), ("sightseeing", 2), ("pool", 1),
       ("beach", 1), ("boudoir", 2))
TOTAL = sum(n for _, n in MIX)


def _places(character: str) -> tuple[list[str], list[str]]:
    """(work locations, own-time locations) from her game schedule, deduped in order."""
    from .appearance import game_facts, location_names, persona_job  # noqa: PLC0415

    # The outfit is not the only signal: bianca works every Threads shift in
    # her 'default' clothes. A place her persona's job line names is her job.
    job_line = persona_job(character).lower()
    names = location_names()
    named = {loc for loc, nm in names.items() if nm.lower() in job_line} if job_line else set()
    work, play = [], []
    for loc, outfit in game_facts(character).get("schedule") or []:
        if loc not in PLACES:
            continue
        bucket = work if (outfit in WORK_OUTFITS or loc in named) else play
        if loc not in bucket:
            bucket.append(loc)
    return work, play


def _moments(locs: list[str], kind: str) -> list[tuple[str, tuple[str, str, str]]]:
    other = "hobby" if kind == "job" else "job"
    out = []
    for loc in locs:
        for m in PLACES[loc].get(kind) or PLACES[loc].get(other) or []:
            out.append((loc, m))
    return out


def _draw(rng: random.Random, pool: list, n: int) -> list:
    """n picks without repeats until the pool runs out, then it cycles."""
    order = rng.sample(pool, len(pool))
    return [order[i % len(order)] for i in range(n)]


def slots(character: str, batch: int) -> list[dict]:
    """The 14 slots of this character's batch. Deterministic in (character, batch)."""
    from .wardrobe import avoid, hair_options  # noqa: PLC0415

    c = (character or "").lower()
    rng = random.Random(f"{c}-influencer-{batch}")
    work, play = _places(c)
    hair = hair_options(c)
    life = [(None, m) for m in LIFESTYLE]

    # One shuffled lifestyle queue, shared: a job or hobby slot her places cannot
    # fill takes the next lifestyle scene instead of repeating one of hers -
    # priyanka has a single university scene, and drawing it three times gave
    # three near-identical photos.
    life_q = _draw(rng, life, 3 * len(life))
    picks: list[tuple[str, str | None, tuple[str, str, str]]] = []
    for tone, n in MIX:
        if tone in ("job", "hobby"):
            own = _moments(work if tone == "job" else play, tone)
            mine = rng.sample(own, min(n, len(own)))
            mine += [life_q.pop(0) for _ in range(n - len(mine))]
            picks += [(tone, loc, m) for loc, m in mine]
        elif tone == "lifestyle":
            picks += [(tone, None, life_q.pop(0)[1]) for _ in range(n)]
        elif tone == "sightseeing":
            for tmpl in (SIGHT_INTL, SIGHT_US):
                picks.append((tone, None, (tmpl.format(light=rng.choice(SIGHT_LIGHT)),
                                           rng.choice(SIGHT_OUTFIT), rng.choice(SIGHT_STANCE))))
        else:
            pool = {"pool": POOL, "beach": BEACH, "boudoir": BOUDOIR}[tone]
            picks += [(tone, None, m) for m in _draw(rng, pool, n)]

    extra = avoid(c)
    hairs = _draw(rng, list(hair), len(picks))
    out = []
    for i, (tone, loc, (setting, outfit, stance)) in enumerate(picks):
        framing = {"sightseeing": SIGHT_FRAMING, "boudoir": BOUDOIR_FRAMING}.get(tone, FRAMING)
        out.append({
            "id": f"influencer_b{batch:02d}_{i:02d}", "look": i + 1, "category": "influencer",
            "pose": "standing", "shoot": f"influencer_b{batch:02d}", "tone": tone,
            "place": loc, "setting": setting, "outfit": outfit, "stance": stance,
            "hair": hairs[i], "framing": framing,
            "shot_type": SHOT_TYPE, "avoid": AVOID + (f" {extra}" if extra else ""),
        })
    return out


_BATCH = re.compile(r"^influencer_b(\d+)$")


def batch_of(shoot_id: str) -> int | None:
    m = _BATCH.match(shoot_id or "")
    return int(m.group(1)) if m else None


def next_batch(char_dir: Path) -> int:
    """One past the highest batch already rendered for her - so ticking the box
    again is always a fresh batch, never a re-render of the last one."""
    # A batch folder with no image in it is a run that failed before rendering;
    # it does not use up a number (priyanka's first two attempts made b01, b02).
    seen = [batch_of(p.name) for p in Path(char_dir).glob("influencer_b*")
            if p.is_dir() and any(p.glob("*.png"))]
    return max([b for b in seen if b] or [0]) + 1
