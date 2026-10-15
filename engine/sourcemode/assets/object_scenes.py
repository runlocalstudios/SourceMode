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
