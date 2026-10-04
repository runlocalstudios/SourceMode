"""Per-character wardrobe brief, and the hair a prompt is allowed to ask her for.

Jeremy, 2026-10-04: "when we describe Tessa's hair, we need to ensure that it
is accurate because her hair is sort of braided in a specific type of braid for
black hair... it's different from the kind of braid we use in the LoRA-Gen set."

He is right, and it is not only a wording problem. Tess wears **long box
braids** - many individual plaits parted in a square grid at the scalp - in
every single training frame. The shared hair vocabulary every shoot and every
wardrobe pack rotates through is:

    her hair worn loose / in a high ponytail / up in a messy bun / half pinned back

"Worn loose" means unbraided hair. Asking a LoRA trained entirely on box braids
for loose hair is the gabi failure in reverse: her set is ~90% loose hair and
prompting a braid kept 20%. For Tess the same collision points the other way,
and every pack and shoot would have hit it on every look.

So hair options are per character. Most characters have none and get the shared
list, which is correct for them. Tess gets a list that varies how the BRAIDS
are worn - the arrangement is the variable, the braids are not.

The braid style itself stays OUT of the per-look hair clause and lives in her
appearance record instead, because it is identity, not wardrobe: it is in every
frame, it is what she looks like, and a per-look clause that re-states it on
some looks and not others is how a constant becomes accidentally variable.
"""

from __future__ import annotations

import json
from pathlib import Path

#: The shared rotation, used by any character whose brief does not override it.
DEFAULT_HAIR: tuple[str, ...] = (
    "her hair worn loose",
    "her hair pulled back in a high ponytail",
    "her hair up in a messy bun",
    "her hair half pinned back",
)

_CACHE: dict[str, dict] = {}


def _load() -> dict:
    from ..config import ENGINE_ROOT  # noqa: PLC0415

    p = ENGINE_ROOT.parent / "characters" / "wardrobe.json"
    key = str(p)
    stamp = p.stat().st_mtime if p.is_file() else 0
    hit = _CACHE.get(key)
    if hit and hit["at"] == stamp:
        return hit["doc"]
    doc = {}
    if p.is_file():
        try:
            doc = {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items()
                   if not k.startswith("_")}
        except ValueError:
            doc = {}
    _CACHE[key] = {"at": stamp, "doc": doc}
    return doc


def brief(character: str) -> dict:
    """Her wardrobe brief, or `{}`. Never raises - a missing file must not take
    a render down, it just means nobody has written her style down yet."""
    return _load().get((character or "").lower()) or {}


def hair_options(character: str) -> tuple[str, ...]:
    """What a per-look hair clause may ask this character for.

    Falls back to the shared rotation, which is right for everyone whose hair
    the generic vocabulary actually describes.
    """
    h = brief(character).get("hair")
    if isinstance(h, list) and h:
        return tuple(str(x) for x in h if str(x).strip())
    return DEFAULT_HAIR


def avoid(character: str) -> str:
    """The line this character does not cross, in any category. Sandra wears no
    crop tops; a generated pack with no memory of that puts her in one."""
    return str(brief(character).get("avoid") or "").strip()
