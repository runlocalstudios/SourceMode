"""Named photo shoots: small, character-agnostic sets rendered from her LoRA.

Jeremy, 2026-10-04: a tab where he picks a character with an approved LoRA,
ticks as many small shot plans as he wants, and queues them as ONE GPU job.

Three things make this different from what was here before:

- **Data, not a script per character.** The six shoots this starts from lived in
  `scripts/eval/amanda_shoots.py`, hardcoded to Amanda and built on the local
  reference-seed recipe rather than her LoRA. They are now a catalog any
  character can be run through.
- **One prompt builder.** Every shot goes through `assets.render.shot_prompt`,
  the same function the wardrobe pack and the epoch eval use, so a shoot cannot
  describe a character differently from her pack. A shoot supplies the outfit,
  hair, stance, framing and setting; everything else - her age, appearance,
  frame, the expression table, the crop discipline, her negative - is shared.
- **Bite-sized.** 8-12 shots each, ~10-15 minutes, so ticking five boxes is an
  hour and the tab can state the cost before he commits.

Each shoot renders into its own judge set as it finishes, so a run that dies
part-way still leaves everything before it judgeable.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Shoot:
    id: str
    label: str
    bucket: str
    setting: str           # goes in the backdrop slot: light + place
    outfits: tuple[str, ...]
    poses: tuple[str, ...]
    hair: tuple[str, ...] = ("her hair worn loose", "her hair pulled back in a high ponytail",
                             "her hair up in a messy bun", "her hair half pinned back")
    framing: str = ""      # "" keeps shot_prompt's upper-thigh wardrobe crop
    shots: int = 12
    # "shoot" renders here, through shot_prompt and the t2i graph. "pack" means a
    # shipped game-asset pack with its own pipeline - a plate, a chroma backdrop,
    # cutout and place - which run_shoots delegates to rather than reimplements.
    kind: str = "shoot"
    # An explicit slot list beats the outfit x pose rotation when the set is
    # authored shot by shot, as the selfie pack is. `()` keeps the rotation.
    explicit: tuple[dict, ...] = ()
    # Which measured rate this renders at: the t2i sweep rate, or the slower
    # asset-pack rate (plate upload + adherence measurement per shot).
    rate: str = "render"
    # Only meaningful for kind="pack": the plan file, relative to outputs/.
    plan_file: str = ""
    note: str = ""

    def plan(self, seed: int = 0, character: str | None = None) -> list[dict]:
        """The shot list: outfit x pose walked in step, hair rotating under them.

        Deterministic, so re-running a shoot reproduces it and a judge verdict
        keyed to a shot id still means the same picture.

        `character` swaps in HER hair vocabulary where she has one. Tess wears
        box braids in every frame she was trained on, and the shared rotation
        would have asked her for loose hair on a quarter of every shoot.
        """
        from .wardrobe import hair_options  # noqa: PLC0415

        if self.explicit:
            return [dict(x) for x in self.explicit] if not character else [
                {**x, "hair": hair_options(character)[i % len(hair_options(character))]}
                for i, x in enumerate(self.explicit)]
        hair = hair_options(character) if character else self.hair
        out = []
        for i in range(self.shots):
            out.append({
                "id": f"{self.id}_{i:02d}", "look": i + 1, "category": self.bucket,
                "pose": "standing", "shoot": self.id,
                "outfit": self.outfits[i % len(self.outfits)],
                "hair": hair[i % len(hair)],
                "stance": self.poses[i % len(self.poses)],
                "framing": self.framing,
                "setting": self.setting,
            })
        return out


# Buckets group the tab's checkboxes. Keep each shoot small: the point is that
# ticking five is an hour, not an afternoon.
CATALOG: tuple[Shoot, ...] = (
    # --- intimate ------------------------------------------------------------
    Shoot("boudoir", "Boudoir", "intimate",
          "warm soft lamplight, in a softly lit bedroom with white sheets",
          ("a black lace bralette and matching panties",
           "a sheer white lace bodysuit",
           "a burgundy satin slip",
           "a black strappy lingerie set",
           "an oversized white shirt unbuttoned over black lace underwear",
           "a pale pink silk camisole and shorts"),
          ("sitting on the edge of the bed, one knee drawn up",
           "kneeling on the bed, back slightly arched",
           "lying on her side propped on one elbow",
           "standing by the bed, one strap slipped off her shoulder",
           "sitting back on her heels on the bed, hands on her thighs",
           "leaning forward toward the camera on the bed")),
    Shoot("silk", "Silk and satin", "intimate",
          "soft window daylight, in a quiet hotel room",
          ("a champagne silk slip dress",
           "a black satin robe loosely tied",
           "an ivory silk camisole and tap pants",
           "a deep red satin chemise"),
          ("standing at the window, half turned to the camera",
           "sitting on the end of the bed, ankles crossed",
           "leaning against the doorframe",
           "sitting in an armchair, one leg over the arm"), shots=8),
    Shoot("sheer", "Sheer and lace", "intimate",
          "low warm lamplight, against a plain dark wall",
          ("a sheer black mesh bodysuit",
           "a white lace teddy",
           "a black lace bra and high-waisted briefs",
           "a sheer wrap robe over matching underwear"),
          ("standing square to the camera, hands at her sides",
           "standing with one hip pushed out, hand on her waist",
           "sitting on a low stool, leaning forward",
           "standing turned away, looking back over her shoulder"), shots=8),

    # --- swim ---------------------------------------------------------------
    Shoot("pool", "Poolside", "swim",
          "soft open shade, beside a sunlit pool with a white lounger",
          ("a black string bikini", "a white one-piece cut high on the hip",
           "a red triangle bikini", "a tropical print bikini with tie sides"),
          ("standing at the pool edge, weight on one hip",
           "sitting on the lounger, leaning back on her hands",
           "kneeling on a towel beside the water",
           "standing in the shallows, water at her calves"), shots=8),
    Shoot("beach_sunset", "Beach at golden hour", "swim",
          "golden-hour backlight, on a quiet beach at the water's edge",
          ("a white crochet bikini", "a bronze metallic one-piece",
           "a sheer sarong over a black bikini", "a tie-dye triangle bikini"),
          ("walking toward the camera at the waterline",
           "standing with her back to the sea, looking at the camera",
           "sitting on the sand, knees drawn up",
           "standing with the sarong lifting in the wind"), shots=8),

    # --- everyday -----------------------------------------------------------
    Shoot("mirror", "Mirror selfies", "everyday",
          "soft even bathroom light, in a bright bathroom with a large mirror",
          ("a grey cropped hoodie and cotton shorts",
           "an oversized white tee and black briefs",
           "a matching ribbed bralette and leggings set",
           "a cropped tank and pyjama shorts"),
          ("standing square to the mirror, phone at chest height",
           "standing turned to show her side, phone raised",
           "leaning toward the mirror, free hand on the counter",
           "standing with her hip against the counter"), shots=8),
    Shoot("gym", "Gym", "everyday",
          "cool even gym lighting, in a modern gym with mirrors behind her",
          ("a black sports bra and high-waisted leggings",
           "a cropped white tank over a coloured sports bra, bike shorts",
           "a matching seamless set in sage green",
           "a loose cut-off tee over a sports bra and shorts"),
          ("standing facing the camera, towel over one shoulder",
           "sitting on a bench, forearms on her knees",
           "standing side-on, adjusting a glove",
           "leaning back against a rack, arms loose"), shots=8),
    Shoot("loungewear", "Loungewear at home", "everyday",
          "soft window daylight, in a warm living room",
          ("an oversized knit cardigan over a cami and shorts",
           "a matching ribbed lounge set",
           "a long-sleeve thermal top and thick socks",
           "an old band tee and sweatpants"),
          ("curled in the corner of the sofa",
           "sitting cross-legged on the rug, mug in both hands",
           "standing in the kitchen doorway",
           "lying on her front on the sofa, propped on her elbows"), shots=8),

    # --- night out ----------------------------------------------------------
    Shoot("club", "Club night", "night",
          "warm club lighting with coloured spill, in a dim nightclub",
          ("a black sequined mini dress",
           "a metallic halter top and leather mini skirt",
           "a red bodycon dress with a deep neckline",
           "a sheer mesh top over a bralette and black trousers"),
          ("standing against a lit wall, drink in hand",
           "sitting on a banquette, turned toward the camera",
           "standing at the bar, one elbow on it",
           "standing square on, hand through her hair"), shots=8),
    Shoot("date_night", "Date night", "night",
          "low warm restaurant light, in a dim dining room",
          ("a black slip dress with thin straps",
           "a wrap dress in deep green",
           "a fitted knit top and tailored trousers",
           "a satin cami under a cropped blazer"),
          ("sitting at the table, chin on her hand",
           "standing beside the table, coat over one arm",
           "sitting turned toward the camera, legs crossed",
           "leaning back in the chair, glass in hand"), shots=8),
)

# --- game assets ------------------------------------------------------------
# Jeremy, 2026-10-04: "the whole point of this thing is that as I complete the
# LoRAs, I want to be able to trigger the game asset generation from this page.
# So put that as two separate options in the top of that screen under game
# assets." These are not bite-sized and are not meant to be - they are the two
# things that actually ship into the game - so they sit in their own group,
# first, with their real cost on the label.
def _selfie_pack() -> Shoot:
    from .selfies import TOTAL, slots  # noqa: PLC0415

    return Shoot("selfies", "Selfie pack", "game",
                 "real rooms and streets, her own phone, backgrounds kept",
                 (), (), shots=TOTAL, explicit=tuple(slots()),
                 note="24 phone selfies - 8 casual, 6 flirty, 5 date, 5 intimate. "
                      "Ships as rendered: no chroma plate, no cutout.")


GAME: tuple[Shoot, ...] = (
    Shoot("pack28", "In-game asset pack (28 looks)", "game",
          "the shipped wardrobe pack: magenta plate, cut out and placed",
          (), (), shots=28, kind="pack", rate="shot",
          plan_file="game-assets/{character}/plan_28.json",
          note="One shot per look, judged like everything else - reject any and "
               "they are re-rolled in one job. Needs a wardrobe plan on disk "
               "first: the outfits are a decision, not a default."),
    _selfie_pack(),
)

CATALOG = GAME + CATALOG
BY_ID = {s.id: s for s in CATALOG}
BUCKETS = ("game", "intimate", "swim", "everyday", "night")
BUCKET_LABEL = {"game": "Game assets", "intimate": "Intimate", "swim": "Swim",
                "everyday": "Everyday", "night": "Night out"}


def buckets() -> list[dict]:
    """The catalog as the page wants it: grouped, with each shoot's cost."""
    out = []
    for b in BUCKETS:
        rows = [s for s in CATALOG if s.bucket == b]
        if rows:
            out.append({"bucket": b, "label": BUCKET_LABEL.get(b, b),
                        "shoots": [{"id": s.id, "label": s.label, "shots": s.shots,
                                    "setting": s.setting, "kind": s.kind,
                                    "note": s.note} for s in rows]})
    return out


def plan_path(shoot: Shoot, character: str, outputs_root) -> object | None:
    """Where a pack shoot's plan lives for this character, or None if it is not
    a pack. Existence is the caller's question - the page greys the box, the
    runner refuses."""
    from pathlib import Path  # noqa: PLC0415

    if shoot.kind != "pack" or not shoot.plan_file:
        return None
    return Path(outputs_root) / shoot.plan_file.format(character=character)


def estimate_seconds(ids: list[str], s_per_render: float, s_per_shot: float) -> float:
    """One job can mix a 75 s/shot sweep render with a 116 s/shot asset render.
    Charging the whole job at one rate was a 1h15m error on the 112-shot pack."""
    return sum(s.shots * (s_per_shot if s.rate == "shot" else s_per_render)
               for s in resolve(ids))


def resolve(ids: list[str]) -> list[Shoot]:
    """Named shoots, in catalog order. An unknown id is an error, not a skip -
    a typo must not quietly render four shoots when five were asked for."""
    unknown = [i for i in ids if i not in BY_ID]
    if unknown:
        raise KeyError(f"unknown shoot(s): {', '.join(unknown)}")
    want = set(ids)
    return [s for s in CATALOG if s.id in want]


def total_shots(ids: list[str]) -> int:
    return sum(s.shots for s in resolve(ids))
