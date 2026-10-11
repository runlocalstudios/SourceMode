"""Per-character wardrobe brief, and the hair a prompt is allowed to ask her for.

Jeremy, 2026-10-04: "when we describe Tessa's hair, we need to ensure that it
is accurate because her hair is sort of braided in a specific type of braid for
black hair... it's different from the kind of braid we use in the LoRA-Gen set."

He is right, and it is not only a wording problem. Tess wears **long box
braids** - many individual plaits parted in a square grid at the scalp - in
every single training frame. The shared hair vocabulary every shoot and every
wardrobe pack rotates through is:

    her hair worn loose / in a high ponytail / up in a messy bun / half-up /
    worn down with high, tight pigtails

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
import re
from pathlib import Path

#: The shared rotation, used by any character whose brief does not override it.
DEFAULT_HAIR: tuple[str, ...] = (
    "her hair worn loose",
    "her hair pulled back in a high ponytail",
    "her hair up in a messy bun",
    # Jeremy, 2026-10-11: "half-up" reads better than "half pinned back", and
    # pigtails over hair worn down are one of his favourites for long hair.
    "her hair half-up",
    "her hair worn down with high, tight pigtails",
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
    if is_short_haired(character):
        return SHORT_HAIR
    return DEFAULT_HAIR


#: What hair too short to gather can actually do. Jeremy, 2026-10-05, on priya's
#: influencer pack: "a bunch where her hair is down, but also in a bun at the same
#: time" - her record says "a chin-length dark brown bob" and the shared rotation
#: asked that bob for a messy bun and a high ponytail. The model drew both, or
#: lengthened her hair to obey (the skill's older lesson from her wardrobe pack).
#: No up-style here, so the collision cannot be asked for.
SHORT_HAIR: tuple[str, ...] = (
    "her hair worn loose",
    "her hair tucked behind her ears",
    "her hair swept to one side",
    "her hair held back on one side with a clip",
)
_SHORT = re.compile(r"\b(?:bob|pixie|chin-length|jaw-length|ear-length|shoulder-length|cropped|buzzed|short hair)\b", re.I)


def is_short_haired(character: str) -> bool:
    """Does her appearance record describe hair too short to put up?"""
    from .appearance import _load as _look  # noqa: PLC0415

    rec = _look()["look"].get((character or "").lower()) or {}
    return bool(_SHORT.search(" ".join(str(rec.get(k) or "") for k in ("prompt", "features"))))


def avoid(character: str) -> str:
    """The line this character does not cross, in any category. Sandra wears no
    crop tops; a generated pack with no memory of that puts her in one."""
    return str(brief(character).get("avoid") or "").strip()


# --- the Characters tab's wardrobe record ------------------------------------
# Jeremy, 2026-10-11: free-form style per outfit type ("chic, trendy, shabby,
# overdressed, underdressed, slutty, revealing, conservative, self-conscious"),
# and two jobs with their own outfits - "Marisol and Zara are both strippers and
# both work at the beach bar, I can't have them working at the beach bar in
# stripper outfits." The game's schedule labels every shift "work", so a job is
# tied to the game places where she does it.

#: (key, label, what it covers). Free text; nothing here is a dropdown.
OUTFIT_TYPES: tuple[tuple[str, str, str], ...] = (
    ("everyday", "Everyday / casual", "asset pack casual, casual selfies, influencer"),
    ("workout", "Workout / gym", "asset pack workout, gym shoot"),
    ("dressy", "Dressy - dinner, gallery", "asset pack fancy dining / gallery"),
    ("night_out", "Night out - town, club", "asset pack fancy town, club shoot"),
    ("date", "Date", "asset pack casual date, date selfies, date-night shoot"),
    ("home", "At home / loungewear", "loungewear shoot, at-home selfies"),
    ("swim", "Swim", "pool and beach shoots"),
    ("intimate", "Intimate", "boudoir, silk, sheer, intimate selfies"),
)
JOB_SLOTS = 2
TEXT_KEYS = ("style", "palette", "avoid")


def editable(character: str) -> dict:
    """Her wardrobe record in the Characters tab's shape. A brief written before
    the tab existed (`work`, `workout`, `silhouettes`) is carried into the new
    fields as a starting draft; nothing is written until he saves."""
    b = brief(character)
    outfits = {k: str((b.get("outfits") or {}).get(k) or "") for k, _, _ in OUTFIT_TYPES}
    if not outfits["workout"] and b.get("workout"):
        outfits["workout"] = str(b["workout"])
    style = str(b.get("style") or "")
    if b.get("silhouettes") and "outfits" not in b:
        style = (style + "; " if style else "") + "shapes: " + str(b["silhouettes"])
    jobs = [dict(job=str(j.get("job") or ""), outfit=str(j.get("outfit") or ""),
                 places=[str(p) for p in (j.get("places") or [])])
            for j in (b.get("jobs") or [])][:JOB_SLOTS]
    if not jobs and b.get("work"):
        jobs = [{"job": "", "outfit": str(b["work"]), "places": []}]
    while len(jobs) < JOB_SLOTS:
        jobs.append({"job": "", "outfit": "", "places": []})
    hair = b.get("hair") if isinstance(b.get("hair"), list) else []
    return {"style": style, "palette": str(b.get("palette") or ""),
            "avoid": str(b.get("avoid") or ""), "outfits": outfits, "jobs": jobs,
            "hair": [str(h) for h in hair], "note": str(b.get("_note") or ""),
            "draft": bool(b) and "outfits" not in b}


def save(character: str, data: dict, path: Path | None = None) -> dict:
    """Write her record from the tab. Every field is free text; blank fields
    are dropped. The legacy keys go once their content has a new home."""
    from ..config import ENGINE_ROOT  # noqa: PLC0415

    c = (character or "").strip().lower()
    if not re.match(r"^[a-z][a-z0-9_]{0,31}$", c):
        raise ValueError("a character id is required")
    p = path or (ENGINE_ROOT.parent / "characters" / "wardrobe.json")
    doc = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    old = doc.get(c) or {}
    rec: dict = {}
    if old.get("_note"):
        rec["_note"] = old["_note"]
    for k in TEXT_KEYS:
        v = str(data.get(k) or "").strip()
        if v:
            rec[k] = v
    outs = data.get("outfits") or {}
    rec["outfits"] = {k: str(outs.get(k) or "").strip() for k, _, _ in OUTFIT_TYPES
                      if str(outs.get(k) or "").strip()}
    jobs = []
    for j in (data.get("jobs") or [])[:JOB_SLOTS]:
        row = {"job": str(j.get("job") or "").strip(),
               "places": [str(x).strip() for x in (j.get("places") or []) if str(x).strip()],
               "outfit": str(j.get("outfit") or "").strip()}
        if row["job"] or row["outfit"] or row["places"]:
            jobs.append(row)
    if jobs:
        rec["jobs"] = jobs
    hair = [str(h).strip() for h in (data.get("hair") or []) if str(h).strip()]
    if hair:
        rec["hair"] = hair
    doc[c] = rec
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    _CACHE.clear()
    return rec


def job_for_place(character: str, place: str) -> dict | None:
    """Which of her jobs she is doing at a game place, or None."""
    for j in editable(character)["jobs"]:
        if place and place in j["places"]:
            return j
    return None
