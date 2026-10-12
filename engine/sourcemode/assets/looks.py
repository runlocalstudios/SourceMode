"""The 28-look wardrobe plan: drafted from her record, edited and approved on the
Characters tab, and the thing that unlocks the asset pack on the Shoots tab.

Jeremy, 2026-10-12, on Ash: "She has a job and is fully filled out, but I still
can't create it for her." The pack needs `game-assets/<char>/plan_28.json` - 28
concrete outfit+hair pairs - and until now the only way to make one was a
session writing the looks by hand and running `assets plan` from a terminal.
Her wardrobe record is style guidance, not 28 outfits, so a draft is made
from it here: each category takes garment templates coloured from her palette,
the work looks take her job outfit verbatim, and the hair rotates through her
own options. The draft is a starting point for him to edit, not a result.

    outputs/game-assets/<char>/plan_28.draft.json   his to edit
    outputs/game-assets/<char>/plan_28.json         approved; the pack renders this

Look numbers extend what the game already ships for her (`existing_looks`),
so a character with 28 outfits in the game drafts 29-56, not a collision.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .catalog import PACK_28, existing_looks, make_plan, plan_slots

GAME_ROOT = Path("C:/dev/chillafterdark")
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")

#: pack category -> the wardrobe record's outfit type that guides it
CATEGORY_TYPE = {"casual": "everyday", "workout": "workout", "fancy_dining_gallery": "dressy",
                 "fancy_town": "night_out", "casual_date": "date", "work": "job"}
CATEGORY_LABEL = {"casual": "Casual", "workout": "Workout", "fancy_dining_gallery": "Fancy - dining, gallery",
                  "fancy_town": "Fancy - town, club", "casual_date": "Casual date", "work": "Work"}

# {c} is a colour from her palette. Deliberately plain garments: the draft's job
# is to give him 28 editable lines in the right categories, not to guess taste.
TEMPLATES: dict[str, tuple[str, ...]] = {
    "casual": (
        "a fitted {c} t-shirt tucked into high-waisted light-wash jeans",
        "a {c} ribbed tank top and denim shorts",
        "a cropped {c} knit sweater over a short pleated skirt",
        "an oversized {c} button-up shirt worn open over a white cami and jeans",
        "a {c} sundress with thin straps",
        "a {c} cropped hoodie and bike shorts",
        "a {c} and white striped long-sleeve tee and a denim mini skirt",
        "a {c} bodysuit tucked into straight-leg jeans",
    ),
    "workout": (
        "a {c} sports bra and matching high-waisted leggings",
        "a {c} racerback tank over a black sports bra and bike shorts",
        "a {c} seamless crop top and leggings set",
        "a cropped {c} zip hoodie over a sports bra and running shorts",
        "a {c} longline sports bra and flared yoga pants",
    ),
    "fancy_dining_gallery": (
        "a {c} satin midi dress with a cowl neckline",
        "a tailored {c} blazer dress",
        "a {c} silk slip dress with a draped neckline",
        "a fitted {c} knee-length sheath dress",
        "a {c} off-the-shoulder cocktail dress",
    ),
    "fancy_town": (
        "a {c} sequined mini dress",
        "a {c} bodycon dress with a deep neckline",
        "a {c} corset top and a leather mini skirt",
        "a sheer {c} mesh top over a bralette and tailored black trousers",
        "a {c} cut-out halter mini dress",
    ),
    "casual_date": (
        "a {c} wrap dress",
        "a {c} off-the-shoulder top and a denim skirt",
        "a fitted {c} knit top and a high-waisted midi skirt",
        "a {c} slip dress under a cropped denim jacket",
        "a {c} floral sundress with a sweetheart neckline",
    ),
}

# Colour words a palette line may carry, longest first so "denim blue" wins
# over "blue". Anything else in the line is prose and is ignored.
_COLOURS = ("burnt orange", "denim blue", "navy blue", "baby blue", "sky blue", "royal blue",
            "hot pink", "blush pink", "dusty pink", "pale pink", "forest green", "sage green",
            "olive green", "emerald green", "deep red", "wine red", "cherry red", "off-white",
            "black", "white", "cream", "ivory", "beige", "tan", "camel", "brown", "chocolate",
            "grey", "gray", "charcoal", "silver", "gold", "navy", "cobalt", "blue", "teal",
            "turquoise", "green", "olive", "sage", "emerald", "mint", "yellow", "mustard",
            "orange", "coral", "peach", "red", "burgundy", "maroon", "wine", "pink", "rose",
            "fuchsia", "magenta", "purple", "lavender", "lilac", "plum", "violet", "denim")
_COLOUR_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in _COLOURS) + r")\b", re.I)
DEFAULT_COLOURS = ("black", "white", "navy", "red", "cream", "olive", "blush pink")


def palette_colours(palette: str) -> tuple[str, ...]:
    """The colours named in her palette line, in order, no repeats."""
    seen: list[str] = []
    for m in _COLOUR_RE.finditer(palette or ""):
        c = m.group(1).lower()
        if c not in seen:
            seen.append(c)
    return tuple(seen) or DEFAULT_COLOURS


def draft_looks(character: str) -> dict[str, list[dict]]:
    """`{category: [{outfit, hair}, ...]}` for the standard 28, from her record.

    Deterministic per character (seeded by her id), so two drafts of the same
    character agree and two characters do not get the same 28 lines.
    """
    from .wardrobe import editable, hair_options  # noqa: PLC0415

    rec = editable(character)
    colours = list(palette_colours(rec.get("palette", "")))
    hair = list(hair_options(character))
    rng = random.Random(character)
    jobs = [j["outfit"] for j in rec["jobs"] if j["outfit"]]
    out: dict[str, list[dict]] = {}
    for ci, (cat, n) in enumerate(PACK_28.items()):
        looks = []
        if cat == "work":
            # her job outfit, verbatim: a uniform is a uniform. Two jobs split
            # the five looks between them; none leaves the lines blank for him.
            for i in range(n):
                looks.append({"outfit": jobs[i % len(jobs)] if jobs else "",
                              "hair": hair[(i + ci) % len(hair)]})
        else:
            tpl = list(TEMPLATES[cat])
            rng.shuffle(tpl)
            cols = colours[:]
            rng.shuffle(cols)
            for i in range(n):
                looks.append({"outfit": tpl[i % len(tpl)].format(c=cols[i % len(cols)]),
                              "hair": hair[(i + ci) % len(hair)]})
        out[cat] = looks
    return out


# --- files -----------------------------------------------------------------------

def plan_dir(outputs: Path, character: str) -> Path:
    return Path(outputs) / "game-assets" / character


def approved_path(outputs: Path, character: str) -> Path:
    return plan_dir(outputs, character) / "plan_28.json"


def draft_path(outputs: Path, character: str) -> Path:
    return plan_dir(outputs, character) / "plan_28.draft.json"


def _read(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except ValueError:
        return None


def _write(p: Path, doc: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def source_asset(cfg: dict, character: str, epoch: int | None) -> Path | None:
    """A 2:3 render of her at her locked epoch for the pack to condition on:
    `scene_00.png` of her sweep in the library, else the old outputs/dense_* spot."""
    from ..library import library_dir  # noqa: PLC0415
    from ..config import outputs_dir  # noqa: PLC0415

    if epoch is None:
        return None
    ep = f"ep{int(epoch)}"
    roots = sorted((library_dir(cfg) / character).glob("*_sweep_*"), reverse=True)
    roots += sorted(outputs_dir(cfg).glob(f"dense_{character}*"), reverse=True)
    for r in roots:
        for name in ("scene_00.png", "scene_01.png"):
            p = r / ep / name
            if p.is_file():
                return p
        hits = sorted((r / ep).glob("*.png")) if (r / ep).is_dir() else []
        if hits:
            return hits[0]
    return None


def reference(character: str) -> Path | None:
    for pat in (f"{character}_face.*", f"{character}_portrait*.*"):
        hits = sorted(REFS.glob(pat)) if REFS.is_dir() else []
        if hits:
            return hits[0]
    return None


def shipped(character: str) -> dict[str, int]:
    return existing_looks(GAME_ROOT / "src" / "assets" / "characters" / character / "outfits")


def draft(cfg: dict, character: str) -> dict:
    """Write a fresh draft from her record and return the state. Overwrites an
    existing draft; never touches an approved plan."""
    from ..config import outputs_dir  # noqa: PLC0415
    from .lora import resolve_lora  # noqa: PLC0415

    c = character.lower()
    out = outputs_dir(cfg)
    lora = resolve_lora(cfg, c)
    src = source_asset(cfg, c, (lora or {}).get("epoch"))
    ref = reference(c)
    plan = make_plan(c, lora=(lora or {}).get("path"),
                     source_asset=str(src) if src else None,
                     reference=str(ref) if ref else None,
                     looks=draft_looks(c), start_after=shipped(c))
    _write(draft_path(out, c), plan)
    return state(cfg, c)


def save(cfg: dict, character: str, categories: dict) -> dict:
    """Write his edits into whichever file is current - the draft, or the
    approved plan if he is revising one. `categories` is {cat: [{id, outfit, hair}]}."""
    from ..config import outputs_dir  # noqa: PLC0415

    c = character.lower()
    out = outputs_dir(cfg)
    p = approved_path(out, c) if approved_path(out, c).is_file() else draft_path(out, c)
    doc = _read(p)
    if not doc:
        raise ValueError("nothing to save into - draft her looks first")
    edits = {e.get("id"): e for block in (categories or {}).values() for e in block}
    for block in doc["categories"].values():
        for entry in block["looks"]:
            e = edits.get(entry["id"])
            if e is not None:
                entry["outfit"] = str(e.get("outfit") or "").strip()
                entry["hair"] = str(e.get("hair") or "").strip()
    _write(p, doc)
    return state(cfg, c)


def approve(cfg: dict, character: str) -> dict:
    """Promote the draft to the plan the pack renders. Refuses blanks and a
    plan the renderer could not run (no LoRA, no source render)."""
    from ..config import outputs_dir  # noqa: PLC0415
    from .lora import resolve_lora  # noqa: PLC0415

    c = character.lower()
    out = outputs_dir(cfg)
    doc = _read(draft_path(out, c))
    if not doc:
        raise ValueError("no draft to approve")
    blank = [s["id"] for s in plan_slots(doc) if not s["outfit"] or not s["hair"]]
    if blank:
        raise ValueError(f"{len(blank)} look{'s' if len(blank) != 1 else ''} still blank: "
                         + ", ".join(blank[:6]) + ("..." if len(blank) > 6 else ""))
    # the LoRA and the source render are looked up again now, not trusted from
    # the draft: she may have been locked to a different epoch since
    lora = resolve_lora(cfg, c)
    if not lora:
        raise ValueError("no locked LoRA for her - the pack renders from her lock")
    src = source_asset(cfg, c, lora.get("epoch"))
    if not src:
        raise ValueError(f"no render of her at epoch {lora.get('epoch')} to condition on - "
                         "her sweep folder has no ep{} images".format(lora.get("epoch")))
    doc["lora"], doc["source_asset"] = lora["path"], str(src)
    if not doc.get("reference") and reference(c):
        doc["reference"] = str(reference(c))
    from datetime import datetime, timezone  # noqa: PLC0415
    doc["approved"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write(approved_path(out, c), doc)
    draft_path(out, c).unlink(missing_ok=True)
    return state(cfg, c)


def state(cfg: dict, character: str) -> dict:
    """What the Characters tab shows: none / draft / approved, and the looks."""
    from ..config import outputs_dir  # noqa: PLC0415
    from .wardrobe import editable  # noqa: PLC0415

    c = character.lower()
    out = outputs_dir(cfg)
    ap, dr = _read(approved_path(out, c)), _read(draft_path(out, c))
    doc = ap or dr
    st = "approved" if ap else ("draft" if dr else "none")
    rec = editable(c)
    cats = []
    if doc:
        for cat, block in doc["categories"].items():
            t = CATEGORY_TYPE.get(cat, "")
            guide = (" / ".join(j["outfit"] for j in rec["jobs"] if j["outfit"]) if t == "job"
                     else rec["outfits"].get(t, ""))
            cats.append({"key": cat, "label": CATEGORY_LABEL.get(cat, cat), "guide": guide,
                         "looks": [{"id": e["id"], "look": e["look"], "outfit": e["outfit"],
                                    "hair": e["hair"]} for e in block["looks"]]})
    blank = sum(1 for s in plan_slots(doc) if not s["outfit"] or not s["hair"]) if doc else 0
    return {"character": c, "state": st, "approved_at": (ap or {}).get("approved"),
            "categories": cats, "blank": blank, "shipped": shipped(c),
            "source_asset": (doc or {}).get("source_asset"), "lora": (doc or {}).get("lora")}
