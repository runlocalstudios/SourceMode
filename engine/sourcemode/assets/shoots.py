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

from .selfies import MIRROR_FRAMING


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
    # A fixed-size set whose slots still depend on who she is (the selfie
    # pack's set mix): per_character(character) -> slots. One folder, no batches.
    per_character: object = None
    # Jeremy, 2026-10-12: a shoot authored pose by pose. Each entry is a stance
    # plus whatever composition it needs (framing, facing, gaze, shot_type);
    # the outfits rotate under them. `()` keeps the outfit x pose rotation.
    pose_slots: tuple[dict, ...] = ()
    # A WARDROBES id. "work" is HER job outfit from characters/wardrobe.json,
    # which no fixed outfit tuple can carry, so it is resolved at plan time.
    wardrobe: str = ""
    # The shot type every rotation slot carries ("" keeps "standing portrait").
    # The mirror shoot is a mirror selfie, not a portrait of her near a mirror.
    shot_type: str = ""
    # LoRAs stacked under hers, as (lock id, strength): the toy shoot renders
    # with the torso toy's LoRA (Jeremy, 2026-10-17). A lock id, never a file
    # path - the lock is what survives a prune of the staging folders.
    loras: tuple[tuple[str, float], ...] = ()

    def plan(self, seed: int = 0, character: str | None = None,
             outfit: str | None = None) -> list[dict]:
        """The shot list: outfit x pose walked in step, hair rotating under them.

        Deterministic, so re-running a shoot reproduces it and a judge verdict
        keyed to a shot id still means the same picture.

        `outfit` puts every shot in that one outfit - the set's own roll
        (`set_outfit`), so the shoot reads as one shoot.

        `character` swaps in HER hair vocabulary where she has one. Tess wears
        box braids in every frame she was trained on, and the shared rotation
        would have asked her for loose hair on a quarter of every shoot.
        """
        from .wardrobe import hair_options  # noqa: PLC0415

        if self.make is not None:
            return self.make(character or "", self.batch or 1)
        if self.per_character is not None:
            return self.per_character(character or "")
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
                    "outfit": outfit or next((o for o in outfits if p.get("wants") and re.search(p["wants"], o)),
                                             outfits[i % len(outfits)]),
                    "hair": hair[i % len(hair)],
                    "stance": p["stance"],
                    "framing": p.get("framing", self.framing),
                    "setting": self.setting,
                    # full-length poses show her feet, and the lingerie sets
                    # end in stockings, which drop_footwear would strip
                    "shoes": True,
                    **{k: p[k] for k in ("facing", "gaze", "shot_type", "expression_natural",
                                         "negative") if k in p},
                })
            return out
        for i in range(self.shots):
            out.append({
                "id": f"{self.id}_{i:02d}", "look": i + 1, "category": self.bucket,
                "pose": "standing", "shoot": self.id,
                "outfit": outfit or outfits[i % len(outfits)],
                "hair": hair[i % len(hair)],
                "stance": self.poses[i % len(self.poses)],
                "framing": self.framing,
                "setting": self.setting,
                **({"shot_type": self.shot_type} if self.shot_type else {}),
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
# Jeremy, 2026-10-17: "add the torso toy LoRA to the instructions for the toy
# photo shoot." The toy is named by its trigger and the shoot stacks the locked
# torso LoRA (torso_v1 epoch 20 - 8/10 on the object sweep; epochs 17-22 were
# flat on the tiebreaker) at 0.6, the strength the tiebreaker and the handjob
# set rendered at. Her LoRA stays at 1.0 above it.
#
# Then, the same day, after Winnie's seven kept 7/7 with the LoRA: "update the
# images to 14 - 2 each of handjob, blowjob, foot job, vaginal, vaginal from
# behind, anal from the front, hovering just above it". Written the way the
# handjob clarity set's keepers were written (6/6 kept where the toy lies on
# its back across the bottom of the frame with her behind or beside it and her
# face to the camera; 0/4 for the side profile and the close-in POV): the toy's
# place in the frame first, then her body relative to it.
TOY_TRIGGER = "torsotoy"
TOY_LORA: tuple[tuple[str, float], ...] = (("torso", 0.6),)
_TOY = f"{TOY_TRIGGER}, a large flesh-toned male torso sex toy with a big dildo"
_TOY_DOWN = f"{_TOY}, lying on its back on the bed nearest the camera with the dildo standing upright"
_FOOT = "full-length photo from the foot of the bed"
_FOOT_LOW = "full-length photo from the foot of the bed, low, level with the mattress"
_BEHIND_LOW = "photo from behind, low, level with the bed"
_PULLED = "her panties pulled to the side"
TOY: tuple[dict, ...] = (
    # handjob
    {"stance": f"kneeling on the bed at the right side of {_TOY_DOWN} in the centre of the frame, her right hand wrapped around the dildo, stroking it, her body turned toward the toy",
     "needs": ("bed",), "framing": _FULL, "shot_type": _FOOT,
     "gaze": "looking into the camera"},
    {"stance": f"sitting cross-legged on the bed behind {_TOY_DOWN} in front of her knees, the dildo between her two hands, stroking it",
     "needs": ("bed",), "framing": "the whole toy and her body from the waist up in frame",
     "shot_type": "photo from the foot of the bed at eye level", "facing": "facing the camera",
     "gaze": "looking into the camera"},
    # blowjob
    {"stance": f"kneeling on the bed behind {_TOY_DOWN}, leaning down over it with the tip of the dildo in her mouth, sucking it, one hand holding the base of the dildo",
     "needs": ("bed",), "framing": "her face and the toy in frame, from the waist up",
     "shot_type": "photo from the foot of the bed", "facing": "facing the camera",
     "gaze": "her eyes turned up to the camera", "expression_natural": "her lips closed around the tip of the dildo"},
    {"stance": f"on all fours on the bed over {_TOY} lying on the mattress, her tongue out, licking the tip of the dildo",
     "needs": ("bed",), "framing": "her face and the toy in frame, from the waist up", "shot_type": "photo",
     "facing": "her body side-on to the camera", "gaze": "her eyes turned up to the camera",
     "expression_natural": "her mouth open, tongue out"},
    # footjob
    {"stance": f"sitting back on the bed leaning on her hands behind her, {_TOY_DOWN} between her and the camera, both her feet pressed around the dildo, stroking it with her feet",
     "needs": ("bed",), "framing": _FULL, "shot_type": _FOOT, "facing": "facing the camera",
     "gaze": "looking into the camera", "expression_natural": "a playful smile"},
    {"stance": f"lying back against the pillows with her legs stretched down the bed toward {_TOY_DOWN}, the dildo gripped between the soles of her feet, stroking it with her feet",
     "needs": ("bed",), "framing": _FULL, "shot_type": _FOOT_LOW, "facing": "facing the camera",
     "gaze": "looking down the bed into the camera", "expression_natural": "lips parted, eyes heavy"},
    # vaginal, facing the camera
    {"stance": f"riding {_TOY} lying on its back on the bed with its hips nearest the camera, cowgirl, the dildo inside her vagina with {_PULLED}, her hands on its chest, hips lifted",
     "needs": ("bed",), "framing": _FULL, "shot_type": _FOOT, "facing": "facing the camera",
     "gaze": "looking into the camera", "expression_natural": "her mouth open, eyes heavy"},
    {"stance": f"squatting on {_TOY} lying on its back on the bed with its hips nearest the camera, her feet flat on the mattress and her knees wide, the dildo inside her vagina with {_PULLED}, one hand on its stomach",
     "needs": ("bed",), "framing": _FULL, "shot_type": _FOOT_LOW, "facing": "facing the camera",
     "gaze": "looking into the camera", "expression_natural": "lips parted, eyes heavy"},
    # vaginal, from behind
    {"stance": f"riding {_TOY} lying on the bed, reverse cowgirl, the dildo inside her vagina with {_PULLED}, leaning forward with her hands on its thighs",
     "needs": ("bed",), "framing": _FULL, "shot_type": _BEHIND_LOW,
     "facing": "her back to the camera", "gaze": "looking back over her shoulder into the camera"},
    {"stance": f"kneeling astride {_TOY} lying on the bed, sitting upright on it with her back to the camera, the dildo inside her vagina with {_PULLED}, her hands on her hips",
     "needs": ("bed",), "framing": _FULL, "shot_type": _BEHIND_LOW,
     "facing": "her back to the camera", "gaze": "looking back over her shoulder into the camera",
     "expression_natural": "her mouth open, eyes heavy"},
    # anal, facing the camera
    {"stance": f"squatting on {_TOY} lying on its back on the bed with its hips nearest the camera, her feet flat on the mattress and her knees wide, the dildo inside her anus and her vagina in view above it, {_PULLED}, leaning back on her hands on its chest",
     "needs": ("bed",), "framing": _FULL, "shot_type": "full-length photo from a low front angle, level with the bed",
     "facing": "facing the camera", "gaze": "looking into the camera",
     "expression_natural": "her mouth open, eyes heavy"},
    {"stance": f"sitting back on {_TOY} lying on its back on the bed with its hips nearest the camera, her legs spread wide toward the camera, the dildo inside her anus and her vagina in view above it, {_PULLED}, her hands on her thighs",
     "needs": ("bed",), "framing": _FULL, "shot_type": "full-length photo from a low front angle, level with the bed",
     "facing": "facing the camera", "gaze": "looking into the camera",
     "expression_natural": "lips parted, eyes heavy"},
    # hovering just above it
    {"stance": f"kneeling upright astride {_TOY} lying on its back on the bed with its hips nearest the camera, hovering just above it with the tip of the dildo an inch below her vagina, not inside her, {_PULLED}, one hand holding the dildo upright beneath her",
     "needs": ("bed",), "framing": _FULL, "shot_type": _FOOT, "facing": "facing the camera",
     "gaze": "looking down at the dildo", "expression_natural": "lips parted, eyes heavy"},
    {"stance": f"squatting over {_TOY} lying on its back on the bed with its hips nearest the camera, her feet flat on the mattress and her knees wide, hovering with the tip of the dildo just below her vagina, not touching her, {_PULLED}, her hands on her knees",
     "needs": ("bed",), "framing": _FULL, "shot_type": _FOOT_LOW, "facing": "facing the camera",
     "gaze": "looking into the camera", "expression_natural": "biting her lower lip"},
)

# --- office ------------------------------------------------------------------
# Jeremy, 2026-10-28, from a photo of a private-office doorway: three office
# shoots in their own group - her at the open door leaning in toward him at his
# desk, the two of them inside with the door closed, and her on the floor
# between his legs (a pose pack, so it mixes into any scene with a floor). The
# office is "more luxurious" than his photo. Two wardrobes: conservative chic,
# and very revealing professional - the default for all three presets.
OFFICE_DOOR = ("warm afternoon light, seen from inside a luxurious private executive office: "
               "she is in its open doorway, a tall dark walnut door with a brushed brass handle "
               "swung open beside her, the plush carpeted hallway softly blurred behind her")
OFFICE_IN = ("warm lamplight, inside a luxurious private executive office with the door closed: "
             "a large dark walnut desk, a black leather executive chair, floor-to-ceiling windows "
             "with the city skyline at dusk, built-in walnut bookshelves and a cream wool rug")

OFFICE_SLUTTY: tuple[str, ...] = (
    "a white silk blouse unbuttoned to her navel over a black lace bra, a tight black pencil "
    "micro skirt and sheer black thigh-high stockings",
    "a fitted charcoal blazer worn open over a black lace bra, a matching high-waisted micro "
    "mini skirt and sheer black stockings",
    "a sheer white chiffon blouse over a black lace bra, a high-waisted black leather pencil "
    "skirt with a high slit and black stockings",
    "a tight black wrap dress with a plunging neckline and a thigh-high slit, sheer black stockings",
    "a cropped white button-up shirt tied under her breasts, a navy pinstripe micro mini skirt "
    "and sheer black thigh-high stockings",
    "a black tailored vest buttoned over a lace bralette, a tight red pencil mini skirt and "
    "sheer black stockings",
)
OFFICE_CHIC: tuple[str, ...] = (
    "a fitted navy blazer over a cream silk blouse, high-waisted navy tailored trousers, small "
    "gold stud earrings",
    "a black tailored sheath dress to the knee with cap sleeves, a thin gold necklace",
    "a camel wool blazer over a black fine-knit turtleneck and a black pencil skirt to the knee",
    "a white silk button-up blouse tucked into high-waisted charcoal wide-leg trousers, a slim "
    "gold watch",
    "a grey fitted knit dress with long sleeves and a belted waist, small pearl earrings",
    "an ivory tailored jumpsuit with a belted waist and a modest neckline, gold hoop earrings",
)

_THIGHS = "framed from the thighs up"
_EYES = "looking straight into the camera"
DOORWAY: tuple[dict, ...] = (
    {"stance": "leaning forward into the room with one hand braced on the door frame, her chest "
               "pushed toward the camera, her cleavage on display", "needs": ("doorway",),
     "framing": _THIGHS, "gaze": _EYES},
    {"stance": "leaning one shoulder against the door frame, one hip cocked, a fingertip at her lips",
     "needs": ("doorway",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "standing in the doorway with both hands high on the door frame above her, leaning "
               "forward slightly", "needs": ("doorway",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "peeking around the half-open door, one hand on its edge, leaning in toward the camera",
     "needs": ("doorway",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "leaning forward from the waist with one forearm resting on the door frame, her "
               "cleavage on display", "needs": ("doorway",), "framing": _THIGHS,
     "gaze": "looking up into the camera from under her brows"},
    {"stance": "turning to leave through the doorway, one hand on the door frame",
     "needs": ("doorway",), "framing": _THIGHS, "facing": "her back three-quarters to the camera",
     "gaze": "looking back over her shoulder into the camera with a playful smile"},
    {"stance": "leaning in the doorway with her arms folded under her breasts, pushing them up",
     "needs": ("doorway",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "one hand on the door frame, the other tugging her neckline down slightly as she "
               "leans in", "needs": ("doorway",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "pressed against the door frame, back arched and one hip pushed out",
     "needs": ("doorway",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "leaning in with one hand on the door frame, beckoning with one finger",
     "needs": ("doorway",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "standing in the doorway holding a folder against her hip, leaning in with a teasing "
               "smile", "needs": ("doorway",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "leaning forward with both hands on the door frame at waist height, her chest toward "
               "the camera", "needs": ("doorway",), "framing": _THIGHS,
     "gaze": "looking into the camera, biting her lower lip"},
)
# Jeremy, 2026-10-28, on Nadia's desk set: "a little too distant, and the facial
# identity is not rendering well because the face pixels are too small". The
# full-length desk shots put her face at a fraction of the frame; the closest
# framing that still shows the desk under her is knees up.
_CLOSE = "framed from the knees up, the camera close to her"
DESK: tuple[dict, ...] = (
    {"stance": "sitting on the edge of the desk facing the camera, legs crossed, leaning back on "
               "her hands", "needs": ("desk",), "framing": _CLOSE, "shot_type": "photo"},
    {"stance": "leaning forward across the desk on both hands toward the camera, her cleavage on "
               "display", "needs": ("desk",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "lying back across the desk, propped up on her elbows, one knee raised",
     "needs": ("desk",), "framing": _CLOSE, "shot_type": "photo"},
    {"stance": "standing beside the desk with one hip against it, slowly unbuttoning her top",
     "needs": ("desk",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "sitting in the leather executive chair with her legs crossed, leaning forward",
     "needs": ("desk",), "framing": _CLOSE, "shot_type": "photo"},
    {"stance": "bent forward over the desk, both forearms flat on it", "needs": ("desk",),
     "framing": _CLOSE, "shot_type": "photo from behind", "facing": "her back to the camera",
     "gaze": "looking back over her shoulder into the camera"},
    {"stance": "sitting on the desk with her knees apart, hands gripping the edge of the desk",
     "needs": ("desk",), "framing": _CLOSE, "shot_type": "photo"},
    {"stance": "crawling toward the camera on all fours across the desk", "needs": ("desk",),
     "framing": _CLOSE, "shot_type": "photo",
     "gaze": "looking up into the camera from under her brows"},
    {"stance": "standing with her back against the closed door, one hand behind her on the handle, "
               "biting her lip", "needs": ("door",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "perched on the arm of the leather chair, leaning toward the camera",
     "needs": ("desk",), "framing": _CLOSE, "shot_type": "photo"},
    {"stance": "standing at the window with the skyline behind her, one hand sliding her hem up "
               "her thigh", "needs": ("desk",), "framing": _THIGHS, "gaze": _EYES},
    {"stance": "standing in front of the desk, slowly pulling her top open", "needs": ("desk",),
     "framing": _THIGHS, "gaze": _EYES},
)
# The viewer is in the shot: seated, his bare thighs and boxer shorts at the
# bottom of the frame, the camera his eyes looking down at her.
# Nadia's first run, 2026-10-28: 13 of 28 shots put HIS grey boxer briefs on
# HER, under her skirt or lingerie - "his grey boxer briefs" sat next to her
# outfit and grey is a lingerie colour. And every shot had her kneeling upright
# a body-length away: the framing said "her kneeling figure in frame", so the
# camera backed off to fit all of her, and the close poses never happened.
# Now: his shorts are dark navy and named as the MAN's, said once, in the
# composition; the framing puts her head and upper body between his thighs,
# close; and each slot refuses shorts on her and the far, full-length shot.
_POV = "point-of-view photo from the eyes of a man sitting in a leather office chair, looking down at her"
_HIS = ("the man's own bare thighs spread wide along both sides of the bottom of the frame, the man "
        "wearing dark navy boxer shorts at the very bottom edge; she is close between his knees, her "
        "head and upper body filling the middle of the frame")
_UP = "looking up into the camera"
# No "boxer shorts" here, even as "on the woman": a negative is read as a bag of
# words and would take his shorts out too. His are navy; hers are refused by colour.
_NOT = "grey shorts, grey underwear, grey panties, far away, distant, her whole body in frame, standing"
BETWEEN_LEGS: tuple[dict, ...] = tuple({**x, "needs": ("floor",), "shot_type": _POV, "framing": _HIS,
                                        "negative": _NOT} for x in (
    {"stance": "kneeling right between his spread knees, close enough to touch, her hands resting on the "
               "tops of his thighs", "gaze": _UP},
    {"stance": "kneeling between his spread knees, leaning forward with her hands on his knees, lips parted",
     "gaze": _UP},
    {"stance": "kneeling between his knees, her hands sliding up the insides of his thighs toward the camera",
     "gaze": "looking up into the camera from under her brows"},
    {"stance": "kneeling up tall between his knees, her chest close to the camera, her hands on his thighs",
     "gaze": _UP},
    {"stance": "sitting back on her heels between his knees, her hands clasped behind her back", "gaze": _UP},
    {"stance": "kneeling between his knees, one hand on his thigh and the other tugging at the waistband "
               "of the man's boxer shorts", "gaze": _UP, "expression_natural": "biting her lower lip"},
    {"stance": "kneeling between his knees, resting her cheek on the inside of his thigh", "gaze": _UP},
    {"stance": "kneeling between his knees, both hands on his thighs", "gaze": _UP,
     "expression_natural": "her mouth open"},
    # Jeremy, 2026-10-28: "a few shots with her face near his crotch, a few with
    # her hands in the waistband of his underwear"
    {"stance": "leaning in between his thighs, her face just above the front of the man's boxer shorts at "
               "the bottom centre of the frame, her hands on his thighs", "gaze": _UP,
     "expression_natural": "lips parted"},
    {"stance": "leaning in between his thighs, her cheek almost touching the front of the man's boxer shorts",
     "gaze": "looking up into the camera from under her brows", "expression_natural": "a teasing smile"},
    {"stance": "leaning in low between his thighs, her face inches from his crotch at the bottom centre "
               "of the frame", "gaze": _UP, "expression_natural": "her mouth open"},
    {"stance": "kneeling between his knees, both of her thumbs hooked into the waistband of the man's "
               "boxer shorts", "gaze": _UP, "expression_natural": "biting her lower lip"},
    {"stance": "kneeling between his knees, her fingers slipped inside the waistband of the man's boxer "
               "shorts, starting to pull them down his thighs",
     "gaze": "looking up into the camera from under her brows", "expression_natural": "a sly smile"},
    {"stance": "kneeling up between his knees, one hand tugging at the waistband of the man's boxer "
               "shorts, her face close to his stomach", "gaze": _UP, "expression_natural": "lips parted"},
))

OFFICE: tuple[Shoot, ...] = (
    Shoot("office_door", "Office doorway", "office", OFFICE_DOOR, OFFICE_SLUTTY, (),
          pose_slots=DOORWAY, shots=len(DOORWAY),
          note="At the open door of a luxurious private office, leaning in toward him at his "
               "desk. Revealing professional by default; the Office scenes in Mix and match "
               "take the chic wardrobe."),
    Shoot("office_desk", "Private office, door closed", "office", OFFICE_IN, OFFICE_SLUTTY, (),
          pose_slots=DESK, shots=len(DESK),
          note="Inside with the door closed: on the desk, across it, in his chair, against the door."),
    Shoot("office_pov", "Between his legs (office)", "office", OFFICE_IN, OFFICE_SLUTTY, (),
          pose_slots=BETWEEN_LEGS, shots=len(BETWEEN_LEGS),
          note="His point of view from the chair, his legs and boxer briefs in frame, her on the "
               "floor between his knees. The pose pack mixes into any scene with a floor."),
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
    Shoot("toy", "Torso toy", "intimate", BEDROOM, ROBE, (),
          pose_slots=TOY, shots=len(TOY), loras=TOY_LORA,
          note="Open satin robe, topless, panties. In bed with the torso toy, two of each: "
               "handjob, blowjob, footjob, vaginal, vaginal from behind, anal from the front, "
               "hovering just above it. Renders with the locked torso LoRA at 0.6 under hers."),

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
    # Jeremy, 2026-10-17: a mirror selfie is the ONE kind of selfie where the
    # phone belongs in the picture. Sienna's set rendered the two phoneless
    # poses as plain bathroom portraits, so every pose now holds the phone and
    # the shot type and framing say "mirror selfie" the way the selfie pack's
    # mirror slots do - those rendered right.
    Shoot("mirror", "Mirror selfies", "everyday",
          "soft even bathroom light, in a bright bathroom with a large mirror",
          ("a grey cropped hoodie and cotton shorts",
           "an oversized white tee and black briefs",
           "a matching ribbed bralette and leggings set",
           "a cropped tank and pyjama shorts"),
          ("standing square to the mirror, phone held at chest height",
           "standing turned to show her side, phone raised beside her face",
           "leaning toward the mirror, phone up in one hand, free hand on the counter",
           "standing with her hip against the counter, phone held at her chest"),
          shots=8, shot_type="mirror selfie", framing=MIRROR_FRAMING),
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
    from .selfies import TOTAL, slots_for  # noqa: PLC0415

    # her approved looks under fixed moments; not `make`, which would turn
    # every tick into a new batch
    return Shoot("selfies", "Selfie pack", "game",
                 "real rooms and streets, her own phone, backgrounds kept",
                 (), (), shots=TOTAL, per_character=slots_for,
                 # the same plan the pack renders: the tab greys the box and the
                 # guard refuses until her 28 looks are approved
                 plan_file="game-assets/{character}/plan_28.json",
                 note="24 phone selfies wearing her approved pack: 7 casual, 4 casual date, "
                      "4 fancy dining, 4 fancy town, 2 work, 3 intimate. Needs plan_28. "
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


CATALOG = GAME + (_influencer(),) + CATALOG + OFFICE
BY_ID = {s.id: s for s in CATALOG}
BUCKETS = ("game", "social", "intimate", "swim", "everyday", "night", "office")
BUCKET_LABEL = {"game": "Game assets", "social": "Social", "intimate": "Intimate",
                "swim": "Swim", "everyday": "Everyday", "night": "Night out",
                "office": "Office"}


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
    Scene("officedoor", "Office doorway", OFFICE_DOOR, ("doorway", "wall", "floor")),
    Scene("office", "Private office", OFFICE_IN, ("desk", "door", "wall", "floor")),
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
    Wardrobe("officeslutty", "Office - very revealing professional", OFFICE_SLUTTY),
    Wardrobe("officechic", "Office - conservative chic", OFFICE_CHIC),
)

POSE_PACKS: tuple[PosePack, ...] = (
    PosePack("standing", "Standing", _poses("sheer", "club")[:6],
             note="Square on, hip out, against the wall, looking back; drink in hand."),
    PosePack("bedroom", "On the bed", _poses("boudoir", needs=("bed",)),
             note="The boudoir poses: edge of the bed, kneeling, lying, leaning in."),
    PosePack("submissive", "Submissive", SUBMISSIVE,
             note=f"Kneeling, on the bed, against the wall, bent over. {len(SUBMISSIVE)} poses."),
    PosePack("doorway", "Leaning in the doorway", DOORWAY,
             note=f"Leaning in at an open door toward him. Office doorway only. {len(DOORWAY)} poses."),
    PosePack("desk", "On his desk", DESK,
             note=f"On the desk, across it, in his chair, against the door. {len(DESK)} poses."),
    PosePack("betweenlegs", "Between his legs (his POV)", BETWEEN_LEGS,
             note=f"His legs and boxer briefs in frame, her kneeling between them. Any scene with "
                  f"a floor. {len(BETWEEN_LEGS)} poses."),
    PosePack("toy", "Torso toy", TOY,
             note=f"In bed with the torso toy, two of each act. {len(TOY)} poses."),
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
    """Where the plan a shoot renders from lives for this character, or None
    if it needs none - the pack, and since 2026-10-22 the selfies that wear
    its looks. Existence is the caller's question - the page greys the box,
    the runner refuses."""
    from pathlib import Path  # noqa: PLC0415

    if not shoot.plan_file:
        return None
    return Path(outputs_root) / shoot.plan_file.format(character=character)


def rolls_one_outfit(shoot: Shoot) -> bool:
    """Does this shoot wear one outfit across the set? Every authored shoot that
    rotates outfits does; the packs, the selfies and the influencer batches
    carry their own per-shot looks and do not."""
    return (shoot.kind == "shoot" and shoot.make is None and shoot.per_character is None
            and not shoot.explicit)


def set_outfit(shoot: Shoot, folder, character: str, *, roll: bool = True, rng=None) -> str | None:
    """The one outfit this set is shot in. Jeremy, 2026-10-28: "I'd like the
    outfits to sort of be randomly rolled, but once rolled, I'd like each of
    these sets to have the same outfit prompted ... so that there's more
    likelihood that these look like a coherent set and aren't just a bunch of
    one-off photos."

    Rolled once from the shoot's outfits and written into the set's set.json,
    so a re-run and a redo of one rejected shot wear the same thing. `roll`
    False only reads it (a redo never rolls). None for a shoot that does not
    roll, or when nothing is rolled yet and `roll` is False."""
    import json  # noqa: PLC0415
    import random  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    if not rolls_one_outfit(shoot):
        return None
    sj = Path(folder) / "set.json"
    doc = json.loads(sj.read_text(encoding="utf-8")) if sj.is_file() else {}
    if doc.get("outfit"):
        return str(doc["outfit"])
    if not roll:
        return None
    outfits = (wardrobe_outfits(shoot.wardrobe, character) if shoot.wardrobe else ()) or shoot.outfits
    if not outfits:
        return None
    pick = (rng or random.SystemRandom()).choice(list(outfits))
    doc["outfit"] = pick
    Path(folder).mkdir(parents=True, exist_ok=True)
    sj.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return pick


def set_aside_if_changed(dest, prompt: str) -> bool:
    """Move a shot (and its .txt) into `_superseded/` when it was rendered from
    a different prompt, so the run draws it again. Maya, 2026-10-26: her
    pack28+selfies run re-used all 24 selfies from 10-23 because the files
    existed - in her old outfits - and he had nothing new to judge. A shot with
    no .txt is left alone: nothing says it is stale."""
    from pathlib import Path  # noqa: PLC0415

    dest = Path(dest)
    txt = dest.with_suffix(".txt")
    if not dest.exists() or not txt.is_file() or txt.read_text(encoding="utf-8") == prompt:
        return False
    aside = dest.parent / "_superseded"
    aside.mkdir(exist_ok=True)
    for f in (dest, txt):
        f.replace(aside / f.name)
    return True


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
