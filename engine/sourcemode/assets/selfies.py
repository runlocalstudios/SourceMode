"""The selfie pack: 24 in-character phone selfies per character, backgrounds kept.

Where this came from. Jeremy, 2026-10-02: "create the intimate selfies as
selfie_intimate... i'd also like you to create the selfies for bianca after
amanda so that i can compare and contrast with the ones created by codex... look
at the selfies in C:\\dev\\chillafterdark\\src\\assets\\characters\\bianca\\selfies
before you generate any because they are great examples of what i'm looking
for." The spec below was settled that day and then never written as a script -
the run was queued behind vivienne and zara and fell off. 2026-10-04 it becomes
a tickable pack on the shoots tab.

THE SHAPE, as agreed:
  24 shots - 8 casual / 6 flirty / 5 date / 5 intimate
  1024x1536, the TRAINING bucket
  backgrounds KEPT - a selfie has a room behind it, so no chroma plate and no
  cutout; these ship as rendered
  `selfie_intimate` is a FOURTH tone, still to be registered in the game's
  characterAppearance.js beside selfie_casual / selfie_flirty / selfie_date

THE STYLE, read off bianca's shipped twelve: arm's-length phone framing, head
and chest, real rooms - bed, sofa, kitchen, car, cafe, street - natural or warm
practical light, eyes on the lens, a couple of mirror shots with the phone
visible.

TWO MEASURED THINGS the prompts here obey:

1. **Render at 1024x1536, never at a video bucket.** The first jojo selfie test
   rendered 720x1280 and *all twelve* were rejected - 349-468px faces against a
   623px median in her working sweep. Re-rendered at 1024x1536 with nothing else
   changed, 7 of 12 were kept.

2. **Do not name the outstretched arm.** That was the suggested wording and it
   is the arm that LOST: at 1024x1536, bare "taking a selfie" kept 3/4, the long
   geometric description kept 3/4, and "her arm outstretched and visible in the
   frame" kept 1/4. n=4, so that is a direction and not a measurement - but
   there is no case for paying words for it.

Every slot goes through `assets.render.shot_prompt`, the one inference builder,
so a selfie cannot describe her differently from her wardrobe pack. A slot
supplies framing, stance, outfit, hair, setting and the avoid clause; her age,
appearance, frame, expression and negative are shared and cannot drift.
"""

from __future__ import annotations

# --- composition, held constant across the pack -------------------------------
# Jeremy, 2026-10-17: "You shouldn't see the phone in a selfie photo unless it's
# a mirror selfie." Gabi's pack (2026-10-14) named the phone in every slot -
# "on her own phone", "phone selfie", "on her phone" - and most of her twenty
# non-mirror selfies rendered a phone held up in her hand, a mirror selfie with
# no mirror. The phone IS the camera: outside the mirror slots it is never
# named, and the slot's negative asks for none. The mirror slots keep it, and
# they rendered right.
FRAMING = ("close arm's-length selfie; her head and chest fill the frame and her face is "
           "large and sharp; the top of her head sits near the top edge; never a wide shot, "
           "never full-body")
MIRROR_FRAMING = ("mirror selfie: her reflection from the thighs up, her phone held at chest "
                  "height and visible in her hand, her face still large in the frame; "
                  "never a wide shot")

STANCE = ("she is taking a selfie, the camera held a little above eye level and angled "
          "slightly down toward her")
STANCE_SEATED = ("she is sitting back comfortably and taking a selfie, the camera held a little "
                 "above eye level")
STANCE_MIRROR = ("she stands in front of a full-length mirror photographing her own reflection, "
                 "phone held at chest height, her other hand relaxed at her side")

AVOID = ("No studio lighting, no professional photoshoot look, no third-person camera angle, "
         "no plain backdrop: this is a casual selfie she took herself, in a real room.")
#: Appended to the run's negative on every non-mirror slot.
NEGATIVE = "phone, smartphone, phone in hand, phone screen, phone frame around the picture"

SHOT_TYPE = "selfie"

# --- the twenty-four ----------------------------------------------------------
# (outfit, hair, setting, stance). Settings are real places with their own light,
# because that is what separates bianca's twelve from a studio render.
_CASUAL = (
    ("a sage green ribbed long-sleeve top",
     "her hair worn loose",
     "soft daylight, in her bedroom with a made bed and a doorway behind her", STANCE),
    ("an oversized cream knit sweater slipping off one shoulder",
     "her hair worn loose",
     "warm lamplight, on the sofa in her living room in the evening", STANCE_SEATED),
    ("a white cropped tank top and grey sweatpants",
     "her hair up in a messy bun",
     "bright morning light, in her kitchen with the counter behind her", STANCE),
    ("a dusty rose cropped sweatshirt",
     "her hair worn loose",
     "overcast daylight through the windshield, in the driver's seat of her car", STANCE_SEATED),
    ("a black fitted t-shirt and gold layered necklaces",
     "her hair pulled back in a high ponytail",
     "window light, at a table in a small coffee shop", STANCE_SEATED),
    ("a light blue denim jacket over a white top",
     "her hair worn loose",
     "golden-hour sunlight, on a city sidewalk with blurred shopfronts behind her", STANCE),
    ("a cropped white tee and high-waisted blue jeans",
     "her hair half-up",
     "bright open shade, on a hillside overlook with the valley blurred behind her", STANCE),
    ("a grey marl lounge set, the top cropped short",
     "her hair up in a messy bun",
     "soft daylight, in front of a full-length bedroom mirror", STANCE_MIRROR),
)
_FLIRTY = (
    ("a thin white ribbed tank top with no bra underneath",
     "her hair worn loose",
     "warm bedside lamplight, sitting on the edge of her bed at night", STANCE_SEATED),
    ("a black cropped halter top and low-rise jeans",
     "her hair pulled back in a high ponytail",
     "soft daylight, in front of a full-length bedroom mirror", STANCE_MIRROR),
    ("an oversized white shirt worn unbuttoned over a black bralette",
     "her hair worn loose",
     "late afternoon window light, in her bedroom", STANCE),
    ("a tiny pink cropped tee that ends above her navel",
     "her hair half-up",
     "warm practical light, leaning against the kitchen counter in the evening", STANCE),
    ("a soft black bodysuit with a deep scoop neck",
     "her hair worn loose",
     "dim warm lamplight, on the sofa late at night", STANCE_SEATED),
    ("a cropped grey hoodie zipped halfway with nothing underneath",
     "her hair up in a messy bun",
     "cool daylight, in her bathroom with a tiled wall behind her", STANCE),
)
_DATE = (
    ("a black satin slip dress with thin straps",
     "her hair worn loose",
     "warm restaurant light, at a candlelit table", STANCE_SEATED),
    ("a deep red wrap mini dress",
     "her hair half-up",
     "golden-hour light, on a city street at dusk with blurred lights behind her", STANCE),
    ("an emerald silk cowl-neck top and a short skirt",
     "her hair pulled back in a high ponytail",
     "warm lamplight, in her bedroom getting ready to go out", STANCE),
    ("a champagne sequined mini dress",
     "her hair worn loose",
     "dim bar lighting, in a booth with warm bokeh behind her", STANCE_SEATED),
    ("a little black dress with a square neckline",
     "her hair worn loose",
     "soft hallway light, in front of a full-length mirror before leaving", STANCE_MIRROR),
)
_INTIMATE = (
    ("a black lace bralette",
     "her hair worn loose",
     "low warm lamplight, lying back against her pillows at night", STANCE_SEATED),
    ("a short silky black cami pyjama set with thin straps",
     "her hair worn loose",
     "warm bedside lamplight, sitting cross-legged on her bed", STANCE_SEATED),
    ("a sheer white lace bodysuit",
     "her hair half-up",
     "soft low light, standing in her dim bedroom", STANCE),
    ("a pale pink silk camisole and matching shorts",
     "her hair up in a messy bun",
     "warm light from a bedside lamp, kneeling on her bed", STANCE_SEATED),
    ("a burgundy satin slip with one strap off her shoulder",
     "her hair worn loose",
     "low warm light, in front of her bedroom mirror at night", STANCE_MIRROR),
)

# --- sets B, C and D ------------------------------------------------------------
# Jeremy, 2026-10-21: "The selfie packs all look like the exact same prompts ...
# I don't want for example every girl to have a black shirt selfie sitting at a
# table with a bunch of gold chains." Three more sets of the same shape - 8/6/5/5,
# the mirror rows at the SAME positions so every mix keeps four mirror selfies -
# and each character draws her own mix of the four (see `set_for`).
_B = (
    (("a cobalt blue cropped cardigan buttoned up",
      "her hair worn loose",
      "soft daylight, on a park bench with trees blurred behind her", STANCE_SEATED),
     ("a striped navy and white boat-neck top",
      "her hair half-up",
      "bright midday light, on a boardwalk by the sea", STANCE),
     ("a mustard yellow hoodie with the hood down",
      "her hair up in a messy bun",
      "cool morning light, in her apartment hallway with coats on hooks behind her", STANCE),
     ("a white button-down shirt with the sleeves rolled up",
      "her hair pulled back in a high ponytail",
      "fluorescent office light, at her desk with a monitor blurred behind her", STANCE_SEATED),
     ("a lavender zip-up track jacket over a sports bra",
      "her hair pulled back in a high ponytail",
      "bright overhead light, in a gym with racks blurred behind her", STANCE),
     ("an olive utility shirt over a black tank top",
      "her hair worn loose",
      "dappled afternoon light, on a forest trail", STANCE),
     ("a soft peach crewneck sweatshirt",
      "her hair worn loose",
      "warm shop light, between the shelves of a bookstore", STANCE),
     ("a matching charcoal sweatshirt and biker shorts set",
      "her hair half-up",
      "warm hallway light, in front of a tall mirror by her front door", STANCE_MIRROR)),
    (("a lilac satin cami tucked into a short denim skirt",
      "her hair worn loose",
      "warm evening light, on her apartment balcony with the city behind her", STANCE),
     ("a white ribbed crop top and pale pink pyjama shorts",
      "her hair up in a messy bun",
      "morning daylight, in front of the mirrored wardrobe in her bedroom", STANCE_MIRROR),
     ("a red bandeau top under an open white linen shirt",
      "her hair worn loose",
      "bright afternoon sun, on a lounger by a pool", STANCE_SEATED),
     ("a fitted black tube top",
      "her hair pulled back in a high ponytail",
      "neon-tinted night light, in the back seat of a car", STANCE_SEATED),
     ("a baby blue knit cardigan worn with only a bralette under it",
      "her hair half-up",
      "warm lamplight, curled up in an armchair", STANCE_SEATED),
     ("an oversized boyfriend shirt slipping off one shoulder",
      "her hair worn loose",
      "early morning light through sheer curtains, in her bedroom", STANCE)),
    (("a cream corset top and black wide-leg trousers",
      "her hair worn loose",
      "golden light, on a rooftop terrace at sunset", STANCE),
     ("a sapphire blue velvet mini dress",
      "her hair pulled back in a high ponytail",
      "dim amber light, at a cocktail bar with bottles glowing behind her", STANCE_SEATED),
     ("a white halter top and a black leather mini skirt",
      "her hair half-up",
      "warm streetlight, outside a restaurant at night", STANCE),
     ("a dusty pink one-shoulder midi dress",
      "her hair worn loose",
      "soft candlelight, in a quiet wine bar", STANCE_SEATED),
     ("a fitted bronze satin mini dress",
      "her hair worn loose",
      "bright vanity bulbs, in front of a full-length mirror in a hotel room", STANCE_MIRROR)),
    (("a sheer black mesh top over a black bra",
      "her hair worn loose",
      "red-tinted low light, lying across her bed", STANCE_SEATED),
     ("an ivory satin robe tied loosely at the waist",
      "her hair up in a messy bun",
      "soft morning light, in a hotel bed with white sheets", STANCE_SEATED),
     ("a navy lace bralette and matching high-waisted briefs",
      "her hair worn loose",
      "cool moonlight from the window, standing by her bed", STANCE),
     ("an oversized grey t-shirt and nothing else",
      "her hair worn loose",
      "warm bedside light, under the covers at night", STANCE_SEATED),
     ("a deep plum lace teddy",
      "her hair half-up",
      "candlelight, in front of a tall bathroom mirror", STANCE_MIRROR)),
)
_C = (
    (("a forest green turtleneck sweater",
      "her hair worn loose",
      "crisp autumn daylight, on a street lined with orange trees", STANCE),
     ("a coral tank top and white shorts",
      "her hair pulled back in a high ponytail",
      "bright sun, at an outdoor market with fruit stalls behind her", STANCE),
     ("a heather grey zip hoodie, half unzipped",
      "her hair up in a messy bun",
      "soft window light, on the floor of her living room with a blanket", STANCE_SEATED),
     ("a powder blue polo shirt",
      "her hair half-up",
      "overcast daylight, on a train seat by the window", STANCE_SEATED),
     ("a black denim jacket over a burgundy top",
      "her hair worn loose",
      "night city lights, on a crosswalk with traffic blurred behind her", STANCE),
     ("a cream cable-knit cardigan",
      "her hair worn loose",
      "warm cafe light, in a window seat with a latte on the table", STANCE_SEATED),
     ("a bright red windbreaker",
      "her hair pulled back in a high ponytail",
      "windy daylight, on a beach with waves behind her", STANCE),
     ("a white tank top and light-wash mom jeans",
      "her hair worn loose",
      "bright daylight, in a store fitting room mirror", STANCE_MIRROR)),
    (("a cherry red ribbed cami",
      "her hair worn loose",
      "warm golden-hour light through blinds, on her bed", STANCE_SEATED),
     ("a cropped baby pink cardigan and a white mini skirt",
      "her hair half-up",
      "soft daylight, in front of a full-length mirror propped against her wall", STANCE_MIRROR),
     ("a black sports bra and grey joggers",
      "her hair up in a messy bun",
      "bright light, in her kitchen after a workout", STANCE),
     ("a sheer white blouse knotted at the waist",
      "her hair worn loose",
      "sunset light, on a sailboat deck", STANCE_SEATED),
     ("a teal satin pyjama shirt unbuttoned low",
      "her hair worn loose",
      "warm lamplight, on her sofa with a blanket over her legs", STANCE_SEATED),
     ("a strapless denim top",
      "her hair pulled back in a high ponytail",
      "late afternoon sun, leaning on a car outside", STANCE)),
    (("a silver metallic slip dress",
      "her hair worn loose",
      "colourful club lights, in a lounge with a blurred crowd behind her", STANCE),
     ("a white off-the-shoulder top and a pleated black skirt",
      "her hair half-up",
      "warm string lights, on a restaurant patio at night", STANCE_SEATED),
     ("a fuchsia bodycon mini dress",
      "her hair pulled back in a high ponytail",
      "soft car interior light, in the passenger seat on the way out", STANCE_SEATED),
     ("a black lace top and high-waisted cream trousers",
      "her hair worn loose",
      "warm theatre lobby light, under a chandelier", STANCE),
     ("a royal blue satin cowl-neck dress",
      "her hair worn loose",
      "soft bathroom light, in front of the vanity mirror getting ready", STANCE_MIRROR)),
    (("a red satin bralette and matching shorts",
      "her hair worn loose",
      "warm low light, sitting on the edge of a bathtub", STANCE_SEATED),
     ("a white cotton tank top and lace-trim panties",
      "her hair up in a messy bun",
      "soft morning sunlight, stretched out on rumpled sheets", STANCE_SEATED),
     ("a sheer black babydoll",
      "her hair worn loose",
      "dim purple lamplight, standing in her bedroom", STANCE),
     ("a soft sage green silk slip",
      "her hair half-up",
      "warm fairy lights above her bed at night", STANCE_SEATED),
     ("a black strappy lace bodysuit",
      "her hair worn loose",
      "low warm light, in front of a full-length mirror in a dark room", STANCE_MIRROR)),
)
_D = (
    (("a tan suede jacket over a white turtleneck",
      "her hair worn loose",
      "soft overcast light, outside a brick building downtown", STANCE),
     ("a sky blue sundress with thin straps",
      "her hair half-up",
      "bright sun, in a flower garden", STANCE),
     ("an oversized black band t-shirt",
      "her hair worn loose",
      "warm lamplight, sitting on her bedroom floor against the bed", STANCE_SEATED),
     ("a pastel green knit vest over a white t-shirt",
      "her hair pulled back in a high ponytail",
      "soft daylight, at a library table with shelves behind her", STANCE_SEATED),
     ("a fitted navy athletic zip top",
      "her hair pulled back in a high ponytail",
      "early morning light, on a running track", STANCE),
     ("a burnt orange off-the-shoulder top",
      "her hair worn loose",
      "warm patio light, at an outdoor brunch table", STANCE_SEATED),
     ("a white puffer jacket and a pink beanie",
      "her hair worn loose",
      "snowy daylight, on a winter street", STANCE),
     ("a black ribbed tank and grey sweat shorts",
      "her hair up in a messy bun",
      "bright bathroom light, in front of the bathroom mirror", STANCE_MIRROR)),
    (("a lemon yellow bikini top under a sheer cover-up",
      "her hair worn loose",
      "bright beach sun, on a towel on the sand", STANCE_SEATED),
     ("a black corset top and ripped jeans",
      "her hair pulled back in a high ponytail",
      "warm light, in front of a gold-framed mirror in her hallway", STANCE_MIRROR),
     ("a cropped white button-up tied under her chest",
      "her hair half-up",
      "soft afternoon light, at her vanity table", STANCE_SEATED),
     ("a pink satin bralette under an open denim shirt",
      "her hair worn loose",
      "warm sunset light, on a rooftop", STANCE),
     ("a grey cropped tank and cotton boy shorts",
      "her hair up in a messy bun",
      "lazy morning light, sitting up in bed with coffee", STANCE_SEATED),
     ("a fitted burgundy long-sleeve bodysuit",
      "her hair worn loose",
      "warm practical light, leaning in a doorway at home", STANCE)),
    (("an ivory satin midi skirt and a black fitted top",
      "her hair half-up",
      "warm gallery lighting, at an art exhibit", STANCE),
     ("a crimson halter mini dress",
      "her hair worn loose",
      "dim red booth lighting, in a jazz club", STANCE_SEATED),
     ("a black blazer dress with a plunging neckline",
      "her hair pulled back in a high ponytail",
      "city lights at night, in the back of a taxi", STANCE_SEATED),
     ("a gold shimmer cami and black satin trousers",
      "her hair worn loose",
      "warm light, on a hotel balcony overlooking the skyline at night", STANCE),
     ("a pale lilac tulle mini dress",
      "her hair worn loose",
      "soft bedroom light, in front of her mirror ready to leave", STANCE_MIRROR)),
    (("a white lace bralette and matching briefs",
      "her hair worn loose",
      "soft daylight through sheer curtains, kneeling on her bed", STANCE_SEATED),
     ("a black satin robe slipping off one shoulder",
      "her hair half-up",
      "warm low light, on a velvet chaise", STANCE_SEATED),
     ("a ruby red lace bodysuit",
      "her hair worn loose",
      "candlelight, standing beside her bed at night", STANCE),
     ("an unbuttoned men's dress shirt and lace panties",
      "her hair up in a messy bun",
      "warm morning light, sitting on the kitchen counter", STANCE_SEATED),
     ("an emerald green satin teddy",
      "her hair worn loose",
      "dim warm light, in front of a full-length mirror in her bedroom", STANCE_MIRROR)),
)

_TONE_IDS = ("selfie_casual", "selfie_flirty", "selfie_date", "selfie_intimate")
SETS = {"A": (_CASUAL, _FLIRTY, _DATE, _INTIMATE), "B": _B, "C": _C, "D": _D}
_TONES = tuple(zip(_TONE_IDS, SETS["A"]))


def slots(pick: str = "A") -> list[dict]:
    """The 24 shot slots, in tone order, shaped the way `shot_prompt` wants them.

    `pick` names the set each slot comes from: one letter for a whole set, or
    24 letters, one per slot. The mirror rows sit at the same positions in
    every set, so any mix keeps four mirror selfies.

    `look` walks 1..24 rather than restarting per tone, because it drives the
    expression table and the body/head yaw in `pose_fields` - so every selfie
    gets a different face and a different turn instead of twenty-four copies of
    one pose.
    """
    n = sum(len(rows) for rows in SETS["A"])
    pick = pick * n if len(pick) == 1 else pick
    out: list[dict] = []
    for t, tone in enumerate(_TONE_IDS):
        for r in range(len(SETS["A"][t])):
            i = len(out)
            outfit, hair, setting, stance = SETS[pick[i]][t][r]
            out.append({
                "id": f"selfie_{i + 1:02d}", "look": i + 1,
                "category": tone, "tone": tone, "pose": "standing",
                "outfit": outfit, "hair": hair, "setting": setting,
                "stance": stance,
                "framing": MIRROR_FRAMING if stance is STANCE_MIRROR else FRAMING,
                "shot_type": "mirror selfie" if stance is STANCE_MIRROR else SHOT_TYPE,
                "avoid": AVOID,
                **({} if stance is STANCE_MIRROR else {"negative": NEGATIVE}),
            })
    return out


COUNTS = {tone: len(rows) for tone, rows in _TONES}
TOTAL = sum(COUNTS.values())

# --- which set each character gets ----------------------------------------------
# "random": every slot draws its own set, so no two characters share a pack and
# a given shot repeats across characters about one time in four. "rotate": the
# next character gets the next whole set, A B C D A... Either way the pick is
# written down the first time, because a re-roll rebuilds the slot from the
# plan and must get the same prompt the judged shot had.
MODE = "random"
LETTERS = "ABCD"


def _picks_file():
    from ..config import load_config, outputs_dir  # noqa: PLC0415
    return outputs_dir(load_config()) / "game-assets" / "selfie_sets.json"


def _had_selfies(character: str) -> bool:
    from ..config import ENGINE_ROOT  # noqa: PLC0415
    # rendered images, not the folder: run_shoots makes the folder before it
    # asks for the plan, so a folder alone would pin every new character to A
    return any(d.glob("selfie_*.png")
               for d in (ENGINE_ROOT.parent / "library" / character).glob("*_selfies_selfies"))


def set_for(character: str, path=None, mode: str | None = None) -> str:
    """Her 24-letter pick, assigned on first use and kept. A character who
    already has a selfie set stays on set A, the set she was shot with."""
    import json  # noqa: PLC0415
    import random  # noqa: PLC0415

    c = (character or "").lower()
    path = path or _picks_file()
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if c in doc:
        return doc[c]
    if _had_selfies(c):
        pick = "A" * TOTAL
    elif (mode or MODE) == "rotate":
        whole = sum(1 for v in doc.values() if len(set(v)) == 1)
        pick = LETTERS[whole % len(LETTERS)] * TOTAL
    else:
        rng = random.Random(f"{c}-selfies")
        pick = "".join(rng.choice(LETTERS) for _ in range(TOTAL))
    doc[c] = pick
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return pick


def slots_for(character: str, batch: int = 1) -> list[dict]:
    """Her selfie pack: her set mix, with her own hair vocabulary rotating
    under it, exactly as the fixed pack applied it."""
    from .wardrobe import hair_options  # noqa: PLC0415

    out = slots(set_for(character)) if character else slots()
    hair = hair_options(character) if character else ()
    return [{**x, "hair": hair[i % len(hair)]} for i, x in enumerate(out)] if hair else out
