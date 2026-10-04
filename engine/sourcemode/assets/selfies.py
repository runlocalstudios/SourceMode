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
FRAMING = ("close arm's-length phone selfie; her head and chest fill the frame and her face is "
           "large and sharp; the top of her head sits near the top edge; never a wide shot, "
           "never full-body")
MIRROR_FRAMING = ("mirror selfie: her reflection from the thighs up, her phone held at chest "
                  "height and visible in her hand, her face still large in the frame; "
                  "never a wide shot")

STANCE = ("she is taking the photo herself on her own phone, held a little above eye level and "
          "angled slightly down toward her")
STANCE_SEATED = ("she is sitting back comfortably and taking the photo herself on her own phone, "
                 "held a little above eye level")
STANCE_MIRROR = ("she stands in front of a full-length mirror photographing her own reflection, "
                 "phone held at chest height, her other hand relaxed at her side")

AVOID = ("No studio lighting, no professional photoshoot look, no third-person camera angle, "
         "no plain backdrop: this is a casual photo she took herself on her phone, in a real room.")

SHOT_TYPE = "phone selfie"

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
     "her hair half pinned back",
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
     "her hair half pinned back",
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
     "her hair half pinned back",
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
     "her hair half pinned back",
     "soft low light, standing in her dim bedroom", STANCE),
    ("a pale pink silk camisole and matching shorts",
     "her hair up in a messy bun",
     "warm light from a bedside lamp, kneeling on her bed", STANCE_SEATED),
    ("a burgundy satin slip with one strap off her shoulder",
     "her hair worn loose",
     "low warm light, in front of her bedroom mirror at night", STANCE_MIRROR),
)

_TONES = (("selfie_casual", _CASUAL), ("selfie_flirty", _FLIRTY),
          ("selfie_date", _DATE), ("selfie_intimate", _INTIMATE))


def slots() -> list[dict]:
    """The 24 shot slots, in tone order, shaped the way `shot_prompt` wants them.

    `look` walks 1..24 rather than restarting per tone, because it drives the
    expression table and the body/head yaw in `pose_fields` - so every selfie
    gets a different face and a different turn instead of twenty-four copies of
    one pose.
    """
    out: list[dict] = []
    for tone, rows in _TONES:
        for outfit, hair, setting, stance in rows:
            i = len(out)
            out.append({
                "id": f"selfie_{i + 1:02d}", "look": i + 1,
                "category": tone, "tone": tone, "pose": "standing",
                "outfit": outfit, "hair": hair, "setting": setting,
                "stance": stance,
                "framing": MIRROR_FRAMING if stance is STANCE_MIRROR else FRAMING,
                "shot_type": SHOT_TYPE, "avoid": AVOID,
            })
    return out


COUNTS = {tone: len(rows) for tone, rows in _TONES}
TOTAL = sum(COUNTS.values())
