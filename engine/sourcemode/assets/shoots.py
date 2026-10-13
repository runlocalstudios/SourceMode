"""Named photo shoots: small, character-agnostic sets rendered from her LoRA.

Jeremy, 2026-10-04: a tab where he picks a character with an approved LoRA,
ticks as many small shot plans as he wants, and queues them as ONE GPU job.

Three things make this different from what was here before:

- **Data, not a script per character.** The six shoots this starts from lived in
  a one-off script (since deleted), hardcoded to Amanda and built on the local
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

import re
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
                             "her hair up in a messy bun", "her hair half-up",
                             "her hair worn down with high, tight pigtails")
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
    # A shoot whose slots depend on WHO she is (the influencer pack reads her
    # job and hobbies off the game) builds them with make(character, batch).
    make: object = None
    batch: int = 0
    # Jeremy, 2026-10-12: a shoot authored pose by pose. Each entry is a stance
    # plus whatever composition it needs (framing, facing, gaze, shot_type);
    # the outfits rotate under them. `()` keeps the outfit x pose rotation.
    pose_slots: tuple[dict, ...] = ()
    # A WARDROBES id. "work" is HER job outfit from characters/wardrobe.json,
    # which no fixed outfit tuple can carry, so it is resolved at plan time.
    wardrobe: str = ""

    def plan(self, seed: int = 0, character: str | None = None) -> list[dict]:
        """The shot list: outfit x pose walked in step, hair rotating under them.

        Deterministic, so re-running a shoot reproduces it and a judge verdict
        keyed to a shot id still means the same picture.

        `character` swaps in HER hair vocabulary where she has one. Tess wears
        box braids in every frame she was trained on, and the shared rotation
        would have asked her for loose hair on a quarter of every shoot.
        """
        from .wardrobe import hair_options  # noqa: PLC0415

        if self.make is not None:
            return self.make(character or "", self.batch or 1)
        if self.explicit:
            return [dict(x) for x in self.explicit] if not character else [
                {**x, "hair": hair_options(character)[i % len(hair_options(character))]}
                for i, x in enumerate(self.explicit)]
        hair = hair_options(character) if character else self.hair
        outfits = self.outfits
        if self.wardrobe:
            outfits = wardrobe_outfits(self.wardrobe, character or "") or self.outfits
        out = []
        if self.pose_slots:
            for i, p in enumerate(self.pose_slots):
                out.append({
                    "id": f"{self.id}_{i:02d}", "look": i + 1, "category": self.bucket,
                    "pose": "standing", "shoot": self.id,
                    # a pose may say what garment it needs ("panties|thong");
                    # the first outfit in the wardrobe that has it, else the rotation
                    "outfit": next((o for o in outfits if p.get("wants") and re.search(p["wants"], o)),
                                   outfits[i % len(outfits)]),
                    "hair": hair[i % len(hair)],
                    "stance": p["stance"],
                    "framing": p.get("framing", self.framing),
                    "setting": self.setting,
                    # full-length poses show her feet, and the lingerie sets
                    # end in stockings, which drop_footwear would strip
                    "shoes": True,
                    **{k: p[k] for k in ("facing", "gaze", "shot_type", "expression_natural")
                       if k in p},
                })
            return out
        for i in range(self.shots):
            out.append({
                "id": f"{self.id}_{i:02d}", "look": i + 1, "category": self.bucket,
                "pose": "standing", "shoot": self.id,
                "outfit": outfits[i % len(outfits)],
                "hair": hair[i % len(hair)],
                "stance": self.poses[i % len(self.poses)],
                "framing": self.framing,
                "setting": self.setting,
            })
        return out


BEDROOM = "warm soft lamplight, in a softly lit bedroom with white sheets"

# Jeremy, 2026-10-12: "lingerie + garter + stockings". Every set names all three
# so the stockings cannot drop out of a shot.
LINGERIE: tuple[str, ...] = (
    "a black lace bra and thong with a matching garter belt and sheer black stockings",
    "a red satin and lace bra and panties with a garter belt holding up sheer black stockings",
    "a white lace bralette and panties with a white garter belt and sheer white stockings",
    "a black strappy lingerie set with a garter belt and black fishnet stockings",
    "a burgundy lace bodysuit with garter straps clipped to sheer black stockings",
    "a sheer black mesh bra and panties with a garter belt and back-seamed black stockings",
)

# The submissive pose set, in Jeremy's order (2026-10-12), then the five added
# at his "any others you would add?". `needs` is what the scene must have for
# the pose to make sense; `facing` and `gaze` replace the builder's default
# "facing the camera, looking straight into the camera", which half of these
# are not. Side and from-behind shots keep less often than frontal ones - that
# is a known LoRA limit, not a prompt fault - so expect to re-roll them.
_FULL = "her whole body in frame"
_KNEEL = "from slightly above, her whole kneeling figure in frame"
SUBMISSIVE: tuple[dict, ...] = (
    {"stance": "kneeling on the floor, sitting back on her heels, hands resting on her thighs",
     "needs": ("floor",), "framing": _KNEEL, "shot_type": "full-length photo",
     "gaze": "her face tilted up toward the camera, looking up into the lens"},
    {"stance": "kneeling on the floor, sitting back on her heels, hands resting on her thighs",
     "needs": ("floor",), "framing": _KNEEL, "shot_type": "full-length photo",
     "gaze": "her face turned to the side, looking away from the camera"},
    {"stance": "kneeling on the floor, sitting back on her heels, hands resting on her thighs",
     "needs": ("floor",), "framing": _KNEEL, "shot_type": "full-length photo",
     "gaze": "her head tilted slightly back, eyes on the camera",
     "expression_natural": "her mouth open wide"},
    {"stance": "kneeling on the floor, sitting back on her heels, hands resting on her thighs",
     "needs": ("floor",), "framing": _KNEEL, "shot_type": "full-length photo",
     "facing": "her body in profile to the camera",
     "gaze": "her face in profile, looking straight ahead"},
    # Jeremy, 2026-10-12: viewed from the front - a straddle split, legs out to
    # either side, square to the camera, not a front split seen side-on
    {"stance": "doing a straddle split on the bed, legs stretched out to either side, torso upright, hands on the mattress between her thighs",
     "needs": ("bed",), "framing": _FULL, "shot_type": "full-length photo",
     "facing": "square to the camera, her whole body seen from the front"},
    {"stance": "sitting on the edge of the bed with her legs spread wide, hands on her knees",
     "needs": ("bed",), "framing": _FULL, "shot_type": "full-length photo"},
    {"stance": "lying on her side on the bed, propped on one elbow, legs together",
     "needs": ("bed",), "framing": _FULL, "shot_type": "full-length photo"},
    {"stance": "lying on her side on the bed with her legs spread, one hand resting between her thighs",
     "needs": ("bed",), "framing": _FULL, "shot_type": "full-length photo"},
    {"stance": "standing against the wall with her back to the camera, hips pushed back toward the viewer",
     "needs": ("wall",), "framing": "framed from the knees up", "shot_type": "photo",
     "facing": "her back to the camera",
     "gaze": "looking back over her shoulder into the camera"},
    {"stance": "standing against the wall with her back to the camera, hips pushed back toward the viewer",
     "needs": ("wall",), "framing": "framed from the knees up", "shot_type": "photo",
     "facing": "her back to the camera",
     "gaze": "her head turned to the side and tilted slightly down, her face seen in profile"},
    {"stance": "bent forward over the bed, hands flat on the mattress",
     "needs": ("bed",), "framing": _FULL, "shot_type": "photo from behind",
     "facing": "her back to the camera",
     "gaze": "looking back over her shoulder into the camera"},
    {"stance": "bent forward over the bed, hands flat on the mattress",
     "needs": ("bed",), "framing": _FULL, "shot_type": "photo from behind",
     "facing": "her back to the camera",
     "gaze": "her face turned to the side, seen in profile"},
    {"stance": "bent over at the waist in front of the camera, hands holding her ankles",
     "needs": ("floor",), "framing": _FULL, "shot_type": "full-length photo",
     "facing": "her back to the camera",
     "gaze": "looking back at the camera from between her legs"},
    {"stance": "bent over at the waist in front of the camera, hands holding her ankles",
     "needs": ("floor",), "framing": _FULL, "shot_type": "full-length photo",
     "facing": "her back to the camera",
     "gaze": "her face turned to the side"},
    # added
    {"stance": "on all fours on the bed, back arched",
     "needs": ("bed",), "framing": _FULL, "shot_type": "photo from behind",
     "facing": "her back to the camera",
     "gaze": "looking back over her shoulder into the camera"},
    {"stance": "crawling toward the camera on all fours across the bed",
     "needs": ("bed",), "framing": _FULL, "shot_type": "full-length photo",
     "gaze": "looking up into the camera from under her brows"},
    {"stance": "kneeling on the floor, sitting back on her heels, wrists crossed behind her back",
     "needs": ("floor",), "framing": _KNEEL, "shot_type": "full-length photo"},
    {"stance": "lying on her back on the bed with her head nearest the camera, arms above her head",
     "needs": ("bed",), "framing": "her face and upper body in frame",
     "shot_type": "photo from above the head of the bed",
     "gaze": "looking up into the camera, her face upside down to the viewer"},
    {"stance": "kneeling on the floor, sitting back on her heels, hands clasped behind her head",
     "needs": ("floor",), "framing": _KNEEL, "shot_type": "full-length photo"},
    # Jeremy, 2026-10-12: "her ass and crotch of her panties pointed towards
    # the viewer". `wants` picks a panties set from the wardrobe for this slot.
    {"stance": "face down on the bed with her knees tucked under her and her hips raised high, "
               "her ass and the crotch of her panties pointed straight at the camera",
     "needs": ("bed",), "framing": _FULL, "shot_type": "photo from behind, low, level with the bed",
     "facing": "her back to the camera", "gaze": "her face turned to the side against the sheets",
     "wants": r"panties|thong"},
    {"stance": "face down on the bed with her knees tucked under her and her hips raised high, "
               "her ass and the crotch of her panties pointed straight at the camera",
     "needs": ("bed",), "framing": _FULL, "shot_type": "photo from behind, low, level with the bed",
     "facing": "her back to the camera", "gaze": "looking back over her shoulder into the camera",
     "wants": r"panties|thong"},
)

# Jeremy, 2026-10-12: the toy shoot. "Default an open satin robe and panties
# but topless underneath"; she is in bed with a male-torso dildo. The toy is
# named the same way in every shot so the model has one thing to draw.
ROBE: tuple[str, ...] = (
    "an open black satin robe hanging loose off her shoulders over black panties, nothing else, her breasts bare",
    "an open champagne satin robe hanging loose off her shoulders over white lace panties, nothing else, her breasts bare",
    "an open burgundy satin robe hanging loose off her shoulders over black lace panties, nothing else, her breasts bare",
    "an open emerald satin robe hanging loose off her shoulders over black panties, nothing else, her breasts bare",
    "an open white satin robe hanging loose off her shoulders over pink panties, nothing else, her breasts bare",
)
_TOY = "a large flesh-toned male torso sex toy with a big dildo"
TOY: tuple[dict, ...] = (
    {"stance": f"kneeling on the bed beside {_TOY} standing upright on the mattress, both hands wrapped around the dildo, gripping it",
     "needs": ("bed",), "framing": _FULL, "shot_type": "full-length photo",
     "gaze": "looking into the camera"},
    {"stance": f"on all fours on the bed over {_TOY} lying on the mattress, her tongue out, licking the tip of the dildo",
     "needs": ("bed",), "framing": "her face and the toy in frame, from the waist up", "shot_type": "photo",
     "facing": "her body side-on to the camera", "gaze": "her eyes turned up to the camera",
     "expression_natural": "her mouth open, tongue out"},
    {"stance": f"straddling {_TOY} lying on the bed, the dildo pressed flat between her legs against the front of her panties, grinding on it, hands on its chest",
     "needs": ("bed",), "framing": _FULL, "shot_type": "full-length photo",
     "gaze": "looking down at the toy", "expression_natural": "lips parted, eyes heavy"},
    {"stance": f"kneeling astride {_TOY} lying on the bed, the dildo pressed up between her ass cheeks, her hands on her thighs",
     "needs": ("bed",), "framing": _FULL, "shot_type": "photo from behind",
     "facing": "her back to the camera", "gaze": "looking back over her shoulder into the camera"},
    {"stance": f"lying on her front on the bed over {_TOY}, the dildo squeezed between her breasts, her hands pressing them together around it",
     "needs": ("bed",), "framing": "her face, chest and the toy in frame", "shot_type": "photo from the foot of the bed",
     "gaze": "looking up into the camera"},
    {"stance": f"riding {_TOY} lying on the bed, cowgirl, the dildo inside her with her panties pulled to the side, hands on its chest, hips lifted",
     "needs": ("bed",), "framing": _FULL, "shot_type": "full-length photo",
     "gaze": "looking into the camera", "expression_natural": "her mouth open, eyes heavy"},
    {"stance": f"riding {_TOY} lying on the bed, reverse cowgirl, the dildo inside her with her panties pulled to the side, leaning forward with her hands on its thighs",
     "needs": ("bed",), "framing": _FULL, "shot_type": "photo from behind",
     "facing": "her back to the camera", "gaze": "looking back over her shoulder into the camera"},
)

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
    Shoot("submissive", "Submissive", "intimate", BEDROOM, LINGERIE, (),
          pose_slots=SUBMISSIVE, shots=len(SUBMISSIVE),
          note="Lingerie, garter and stockings. Kneeling, on the bed, against the wall, "
               "bent over. Side and from-behind shots keep less often - re-roll the rejects."),
    Shoot("toy", "Toy", "intimate", BEDROOM, ROBE, (),
          pose_slots=TOY, shots=len(TOY),
          note="Open satin robe, topless, panties. In bed with a male-torso dildo: gripping, "
               "licking, grinding, between her cheeks, between her breasts, cowgirl, reverse. "
               "The base model has never been measured on the toy - expect to re-roll."),

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

def _influencer() -> Shoot:
    from .influencer import TOTAL, slots  # noqa: PLC0415

    return Shoot("influencer", "Influencer pack", "social",
                 "her job and hobbies from the game, plus travel, pool, beach and boudoir",
                 (), (), shots=TOTAL, make=slots,
                 note="14 feed photos: 3 job, 3 hobbies, 2 lifestyle, 2 sightseeing, pool, "
                      "beach, 2 boudoir (no lingerie). Every tick is a NEW batch - different "
                      "scenes, outfits and hair - so a feed never repeats.")


CATALOG = GAME + (_influencer(),) + CATALOG
BY_ID = {s.id: s for s in CATALOG}
BUCKETS = ("game", "social", "intimate", "swim", "everyday", "night")
BUCKET_LABEL = {"game": "Game assets", "social": "Social", "intimate": "Intimate",
                "swim": "Swim", "everyday": "Everyday", "night": "Night out"}


# --- mix and match -----------------------------------------------------------
# Jeremy, 2026-10-12: "I want the ability to mix and match shoots - the shot
# type (club, boudoir) as one option, clothing as another option (club outfit,
# lingerie, casual)... So I want a picture of her at the club but wearing work
# outfit? No problem." A shoot above bundles setting + outfits + poses; here the
# three are separate lists and a combo id `<scene>-<wardrobe>-<poses>` builds
# the same Shoot on the fly. The presets above are untouched, and the lists
# below REUSE their settings and outfits rather than copying them, so a change
# to the club shoot's outfits is a change to the club wardrobe.
#
# Ids here carry no hyphen: the hyphen is the combo separator.

@dataclass(frozen=True)
class Scene:
    id: str
    label: str
    setting: str
    has: tuple[str, ...]      # what a pose may need: bed, wall, floor


@dataclass(frozen=True)
class Wardrobe:
    id: str
    label: str
    outfits: tuple[str, ...] = ()
    record: str = ""          # "job": her own job outfit(s) from characters/wardrobe.json


@dataclass(frozen=True)
class PosePack:
    id: str
    label: str
    poses: tuple[dict, ...]
    note: str = ""


def _poses(*shoot_ids: str, needs: tuple[str, ...] = ("floor",)) -> tuple[dict, ...]:
    """A preset's pose rotation as pose slots, so a pack can be mixed."""
    return tuple({"stance": p, "needs": needs}
                 for sid in shoot_ids for p in BY_ID[sid].poses)


SCENES: tuple[Scene, ...] = (
    Scene("bedroom", "Bedroom", BEDROOM, ("bed", "wall", "floor")),
    Scene("hotel", "Hotel room", BY_ID["silk"].setting, ("bed", "wall", "floor")),
    Scene("darkwall", "Dark wall", BY_ID["sheer"].setting, ("wall", "floor")),
    Scene("club", "Club", BY_ID["club"].setting, ("wall", "floor")),
    Scene("restaurant", "Restaurant", BY_ID["date_night"].setting, ("floor",)),
    Scene("livingroom", "Living room", BY_ID["loungewear"].setting, ("wall", "floor")),
    Scene("bathroom", "Bathroom mirror", BY_ID["mirror"].setting, ("wall", "floor")),
    Scene("gym", "Gym", BY_ID["gym"].setting, ("wall", "floor")),
    Scene("pool", "Poolside", BY_ID["pool"].setting, ("floor",)),
    Scene("beach", "Beach", BY_ID["beach_sunset"].setting, ("floor",)),
)

WARDROBES: tuple[Wardrobe, ...] = (
    Wardrobe("lingerie", "Lingerie, garter and stockings", LINGERIE),
    Wardrobe("robe", "Open satin robe, topless, panties", ROBE),
    Wardrobe("boudoir", "Boudoir", BY_ID["boudoir"].outfits),
    Wardrobe("silk", "Silk and satin", BY_ID["silk"].outfits),
    Wardrobe("sheer", "Sheer and lace", BY_ID["sheer"].outfits),
    Wardrobe("club", "Club", BY_ID["club"].outfits),
    Wardrobe("date", "Date night", BY_ID["date_night"].outfits),
    Wardrobe("casual", "Casual", BY_ID["mirror"].outfits + BY_ID["loungewear"].outfits),
    Wardrobe("gym", "Gym", BY_ID["gym"].outfits),
    Wardrobe("swim", "Swim", BY_ID["pool"].outfits + BY_ID["beach_sunset"].outfits),
    Wardrobe("work", "Work - her job outfit", record="job"),
)

POSE_PACKS: tuple[PosePack, ...] = (
    PosePack("standing", "Standing", _poses("sheer", "club")[:6],
             note="Square on, hip out, against the wall, looking back; drink in hand."),
    PosePack("bedroom", "On the bed", _poses("boudoir", needs=("bed",)),
             note="The boudoir poses: edge of the bed, kneeling, lying, leaning in."),
    PosePack("submissive", "Submissive", SUBMISSIVE,
             note=f"Kneeling, on the bed, against the wall, bent over. {len(SUBMISSIVE)} poses."),
    PosePack("toy", "Toy", TOY,
             note=f"In bed with a male-torso dildo. {len(TOY)} poses."),
)

SCENE_BY_ID = {s.id: s for s in SCENES}
WARDROBE_BY_ID = {w.id: w for w in WARDROBES}
POSES_BY_ID = {p.id: p for p in POSE_PACKS}


def wardrobe_outfits(wardrobe_id: str, character: str) -> tuple[str, ...]:
    """The outfits a wardrobe puts her in. The job wardrobe is HERS: the same
    five work looks the 28-look draft builds from her job line, so a shoot
    rotates through her work week rather than one outfit; `()` when she has no
    job outfit written down."""
    w = WARDROBE_BY_ID.get(wardrobe_id)
    if w is None:
        return ()
    if w.record == "job":
        from .looks import work_outfits  # noqa: PLC0415

        return work_outfits(character)
    return w.outfits


def combo(shoot_id: str) -> Shoot | None:
    """`<scene>-<wardrobe>-<poses>` as a Shoot, or None if it is not one."""
    parts = (shoot_id or "").split("-")
    if len(parts) != 3:
        return None
    sc, wd, pp = (SCENE_BY_ID.get(parts[0]), WARDROBE_BY_ID.get(parts[1]),
                  POSES_BY_ID.get(parts[2]))
    if not (sc and wd and pp):
        return None
    return Shoot(shoot_id, f"{sc.label} / {wd.label} / {pp.label}", "mix", sc.setting,
                 wd.outfits, (), pose_slots=pp.poses, shots=len(pp.poses),
                 wardrobe=wd.id)


def combo_problem(shoot_id: str, character: str) -> str | None:
    """Why this combo cannot render for her, or None. The page greys the
    option and the queue refuses it; the message is the same in both."""
    sh = combo(shoot_id)
    if sh is None:
        return None
    sc = SCENE_BY_ID[shoot_id.split("-")[0]]
    missing = sorted({n for p in sh.pose_slots for n in p.get("needs", ()) if n not in sc.has})
    if missing:
        return f"these poses need a {' and a '.join(missing)} - {sc.label} has none"
    if sh.wardrobe and not wardrobe_outfits(sh.wardrobe, character):
        return "no job outfit in her record - add one under Jobs on the Characters tab"
    return None


def mix() -> dict:
    """The three lists as the shoots tab wants them."""
    return {"scenes": [{"id": s.id, "label": s.label, "has": list(s.has)} for s in SCENES],
            "wardrobes": [{"id": w.id, "label": w.label, "record": w.record} for w in WARDROBES],
            "poses": [{"id": p.id, "label": p.label, "n": len(p.poses), "note": p.note,
                       "needs": sorted({n for x in p.poses for n in x.get("needs", ())})}
                      for p in POSE_PACKS]}


def lookup(source: str) -> Shoot | None:
    """A shoot by the id its renders were filed under - including one batch of
    a batched pack ("influencer_b03"), which is what a redo has to rebuild, and
    a mix-and-match combo."""
    from dataclasses import replace  # noqa: PLC0415

    from .influencer import batch_of  # noqa: PLC0415

    if source in BY_ID:
        return BY_ID[source]
    b = batch_of(source)
    if b:
        return replace(BY_ID["influencer"], id=source, batch=b)
    return combo(source)


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
    unknown = [i for i in ids if i not in BY_ID and combo(i) is None]
    if unknown:
        raise KeyError(f"unknown shoot(s): {', '.join(unknown)}")
    want = set(ids)
    # presets in catalog order, then the combos in the order they were ticked
    return ([s for s in CATALOG if s.id in want]
            + [combo(i) for i in ids if i not in BY_ID])


def total_shots(ids: list[str]) -> int:
    return sum(s.shots for s in resolve(ids))
