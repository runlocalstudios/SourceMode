"""The sweep scenes for an OBJECT LoRA - the torso toy first, 2026-10-15.

A character sweep asks "is this her" on the asset generator's own prompts; an
object sweep asks "is this the toy" in the settings the game will put it in.
Half the scenes show the toy alone, half with a woman who is nobody in
particular, and the tones the set was captioned with (light / tan / dark
brown) each get a turn, so a weak tone shows up as a weak scene and not as a
weak epoch. Written in the captions' register, trigger first.
"""

from __future__ import annotations

SCENES: tuple[str, ...] = (
    "a light-toned {t} standing on a white bed in a bright bedroom, seen from a front three-quarter angle, soft daylight from a window",
    "a tan {t} on a dark wooden table, seen from the side, a warm lamp behind it, a dim living room",
    "a dark brown {t} lying on its side on a grey fur rug, seen from the front, soft room light",
    "a light-toned {t} standing on a kitchen counter, seen from a side three-quarter angle, bright morning light",
    "a tan {t} standing against a grey plaster wall with ferns beside it, seen from behind, soft light",
    "a woman with long dark hair kneeling on a hotel bed holding a light-toned {t} that lies on the white sheets, seen from the front, soft daylight",
    "a woman in white stockings seen from behind, kneeling over a tan {t} on a bed, warm orange light",
    "a blonde woman in red stockings lying on a white bed beside a light-toned {t}, her hand around it, seen from the side, daylight",
    "a close view from behind of a woman in a red harness lowering onto a dark brown {t}, window blinds behind, daylight",
    "a woman in a black choker sitting on a light-toned {t} on the floor of a bright room, seen from the front, a plaid mini skirt, white thigh-highs",
)


def object_prompts(trigger: str) -> list[str]:
    """The ten sweep prompts for `trigger`, trigger first like every caption."""
    return [f"{trigger}, {s.format(t=trigger)}" for s in SCENES]


# The object tiebreaker - Jeremy, 2026-10-16, after the torso sweep read 7/7/8/7
# at epochs 17/19/20/22: "20 photos each ... all photos must have a girl in them,
# do 4 handjob, 4 blowjob, 2 footjob, 4 vaginal, 2 anal, 2 hovering above, 2 with
# it against her ass cheeks but not inside her. for each of these, split half and
# half between a random 20 year old woman description and ... the Amanda lora".
# Written in the captions' register, act tag right after the trigger, so the
# tiebreaker asks exactly what a game prompt will ask. `who` is "random" (the
# description below, no identity LoRA) or "character" (her trigger, her
# appearance sentence and her locked LoRA stacked on the toy's).
TIEBREAKER: tuple[dict, ...] = (
    {"tag": "POV handjob", "who": "random", "body": "lying on her side on a white bed, gripping the penis of a tan {t} in one hand and stroking it, looking up at the camera, seen from the toy's own viewpoint, soft daylight"},
    {"tag": "POV handjob", "who": "character", "body": "kneeling on a grey couch with both hands around the penis of a light-toned {t}, stroking it, smiling at the camera, seen from the toy's own viewpoint, warm lamp light"},
    {"tag": "handjob", "who": "random", "body": "in black lingerie kneeling beside a dark brown {t} lying on a bed, one hand wrapped around its penis, stroking it, seen from the side, a dim bedroom"},
    {"tag": "handjob", "who": "character", "body": "in a white tank top sitting on the floor beside a tan {t}, her hand around the base of its penis, seen from the side, a bright bedroom, daylight"},
    {"tag": "POV blowjob", "who": "random", "body": "in red lingerie kneeling on a bed with the tip of a tan {t} in her mouth, sucking it, one hand holding the base of its penis, seen from the toy's own viewpoint, warm light"},
    {"tag": "POV blowjob", "who": "character", "body": "kneeling on a white bed with the tip of a light-toned {t} in her mouth, sucking it, looking up at the camera, seen from the toy's own viewpoint, soft daylight"},
    {"tag": "blowjob", "who": "random", "body": "on all fours on a bed with the penis of a dark brown {t} in her mouth, sucking it, her hair pulled back, seen from the side, a hotel room, lamp light"},
    {"tag": "blowjob", "who": "character", "body": "in a black bra kneeling on a rug licking the shaft of a tan {t}, her tongue on the penis of the toy, gripping it with one hand, seen from the side, a living room, soft light"},
    {"tag": "POV footjob", "who": "random", "body": "in white knee socks lying back on a bed with her feet wrapped around the penis of a tan {t}, stroking it with her feet, seen from the toy's own viewpoint, framed prints behind, warm light"},
    {"tag": "footjob", "who": "character", "body": "in black stockings lying on a grey couch, stroking the penis of a dark brown {t} with both feet, seen from the side, a dim living room"},
    {"tag": "vaginal riding facing the viewer", "who": "random", "body": "facing the camera, riding a tan {t} on a white bed, the toy inside her vagina, her hands on her thighs, a cream headboard behind, soft daylight"},
    {"tag": "vaginal riding facing the viewer", "who": "character", "body": "in red stockings facing the camera, squatting on a light-toned {t} on a bed, the toy inside her vagina, looking into the camera, a grey headboard behind, warm light"},
    {"tag": "vaginal riding facing away", "who": "random", "body": "seen from behind, riding a tan {t} on a bed, the toy inside her vagina, looking back over her shoulder, a window with blinds behind, daylight"},
    {"tag": "vaginal riding facing away", "who": "character", "body": "in white thigh-highs seen from behind, kneeling over a dark brown {t} on a bed, the toy inside her vagina, a wooden headboard behind, soft lamp light"},
    {"tag": "anal riding facing the viewer", "who": "random", "body": "facing the camera, squatting on a tan {t}, the toy inside her anus, her vagina in view, seen from a low front angle, a plain white wall behind, flat indoor light"},
    {"tag": "anal riding facing away", "who": "character", "body": "seen from behind, on all fours riding a light-toned {t} on a pink bed, the toy inside her anus, looking back over her shoulder, bright room light"},
    {"tag": "hovering above", "who": "random", "body": "kneeling upright over a tan {t} on a grey bed, the tip of the toy just below her vagina, not inside her, her hands in her hair, seen from the front, warm room light"},
    {"tag": "hovering above", "who": "character", "body": "in a black choker squatting above a dark brown {t} on the floor of a bright room, the tip of the toy an inch below her vagina, not touching her, seen from the front, daylight"},
    {"tag": "pressed against her ass", "who": "random", "body": "seen from behind, kneeling with the penis of a tan {t} pressed between her ass cheeks, not inside her, looking back over her shoulder, a white bed, soft daylight"},
    {"tag": "pressed against her ass", "who": "character", "body": "in black stockings seen from behind, bending forward on a bed with the penis of a light-toned {t} resting against her ass cheeks, not inside her, a grey headboard, warm light"},
)

# Ten women who are nobody in particular, one per random slot, in slot order.
RANDOM_WOMEN: tuple[str, ...] = (
    "a 20-year-old woman with long blonde hair and fair skin",
    "a 20-year-old woman with a short black bob and tan skin",
    "a 20-year-old woman with long red curls and pale skin",
    "a 20-year-old woman with long straight black hair and brown skin",
    "a 20-year-old woman with shoulder-length light brown hair and olive skin",
    "a 20-year-old woman with a dark brown ponytail and freckled fair skin",
    "a 20-year-old woman with wavy honey-blonde hair and golden skin",
    "a 20-year-old woman with long dark hair in a braid and deep brown skin",
    "a 20-year-old woman with a platinum pixie cut and fair skin",
    "a 20-year-old woman with long auburn hair and light skin",
)


def object_tiebreaker_prompts(trigger: str, character: str, clause: str) -> list[dict]:
    """The twenty tiebreaker prompts. Each row: `prompt`, `tag`, `character`
    (True on the slots that stack her LoRA). A random slot reads
    `<trigger>, <tag>, <woman> <body>`; her slot leads with her own caption
    opening, `<name>, <clause>,` then the toy's `<trigger>, <tag>, <name> <body>`,
    because identity is the fragile half and her captions put her first."""
    out, women = [], iter(RANDOM_WOMEN)
    for s in TIEBREAKER:
        body = s["body"].format(t=trigger)
        if s["who"] == "character":
            p = f"{character}, {clause}, {trigger}, {s['tag']}, {character} {body}"
        else:
            p = f"{trigger}, {s['tag']}, {next(women)} {body}"
        out.append({"prompt": p, "tag": s["tag"], "character": s["who"] == "character"})
    return out


# Six handjobs with the placement spelled out - Jeremy, 2026-10-16, after her
# tiebreaker slots read 13/40 against the stranger's 24/40 and her POV handjob
# went 0/4: "clarify the location of the toy and her body relative to it in the
# picture so that we can just see how it goes with a little more clarity in the
# prompt". Every slot is hers; the eval renders them with her LoRA stacked.
HANDJOB_CLARITY: tuple[dict, ...] = (
    {"tag": "POV handjob", "body": "kneeling on a white bed at the right side of a tan {t} that lies on its back across the bottom of the frame, its penis standing upright in the centre, her right hand wrapped around the shaft, her body turned toward the toy, her face toward the camera, seen from the toy's own viewpoint, soft daylight"},
    {"tag": "POV handjob", "body": "lying on her stomach on a white bed beyond a light-toned {t} that lies on its back nearest the camera, the penis of the toy upright in the middle of the frame between her and the camera, both hands wrapped around the shaft, her chin level with the tip, looking into the camera, seen from the toy's own viewpoint, warm lamp light"},
    {"tag": "handjob", "body": "kneeling on the floor beside a grey couch, a tan {t} lying on its back along the couch in profile across the lower half of the frame, its penis upright, her right hand around the penis, her body side-on to the camera, her face turned to the camera, seen from the side at the height of the couch, a dim living room"},
    {"tag": "handjob", "body": "sitting cross-legged on a bed behind a dark brown {t} that lies on its back in front of her knees, the penis of the toy standing upright between her two hands, the whole toy and her body from the waist up in frame, seen from the front at eye level, a grey headboard behind, soft light"},
    {"tag": "handjob", "body": "kneeling at the right side of a tan {t} that stands upright on the edge of a bed with its penis pointing at the camera, her body side-on to the camera, one hand around the shaft near the tip, looking down at the toy, a bedside lamp behind, warm light"},
    {"tag": "POV handjob", "body": "close in, the stomach of a light-toned {t} lying on its back filling the bottom of the frame, her hand gripping the base of its upright penis, her face just behind the tip and looking into the camera, seen from the toy's own viewpoint, a white bedroom, soft daylight"},
)


def handjob_clarity_prompts(trigger: str, character: str, clause: str) -> list[dict]:
    """The six, in her caption opening then the toy's: `<name>, <clause>,
    <trigger>, <tag>, <name> <body>`. Same shape as the tiebreaker rows."""
    return [{"prompt": f"{character}, {clause}, {trigger}, {s['tag']}, {character} {s['body'].format(t=trigger)}",
             "tag": s["tag"], "character": True} for s in HANDJOB_CLARITY]
