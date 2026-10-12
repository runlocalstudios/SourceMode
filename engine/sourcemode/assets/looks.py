"""The 28-look wardrobe plan: drafted from her record, edited and approved on the
Characters tab, and the thing that unlocks the asset pack on the Shoots tab.

Jeremy, 2026-10-12, on Ash: "She has a job and is fully filled out, but I still
can't create it for her." The pack needs `game-assets/<char>/plan_28.json` - 28
concrete outfit+hair pairs - and until now the only way to make one was a
session writing the looks by hand and running `assets plan` from a terminal.
Her wardrobe record is style guidance, not 28 outfits, so a draft is made
from it here: each category takes garment templates coloured from her palette,
the work looks are built from her job line (see `work_outfits`), and the hair
rotates through her own options. The draft is a starting point for him to
edit, not a result.

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

# {c} is a colour from her palette. Each character SAMPLES her looks from these
# pools, so two characters do not wear the same garments on the same days.
# Jeremy, 2026-10-12, when the pools were eight deep and everyone drew all of
# them: "every single character will look exactly the same on the same days ...
# the same thing with just different colors." Keep every pool at least three
# times the count the pack asks for.
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
        "a {c} linen shirt knotted at the waist over cut-off denim shorts",
        "an oversized {c} graphic tee worn as a dress with a thin belt",
        "a {c} henley and distressed boyfriend jeans",
        "{c} overalls over a white cropped tee",
        "a {c} baby tee and low-rise cargo pants",
        "a {c} off-the-shoulder knit top and a denim skirt",
        "a {c} tube top under an open denim jacket with jeans",
        "a {c} tennis skirt and a white cropped polo",
        "a {c} romper with a drawstring waist",
        "a {c} plaid flannel tied at the waist over a white tank top and shorts",
        "a {c} crewneck sweatshirt and a pleated mini skirt",
        "a {c} satin cami tucked into high-waisted jeans",
        "a {c} corduroy mini skirt and a fitted white turtleneck",
        "a {c} knit cardigan buttoned up with nothing under it, and faded jeans",
        "a {c} racer-back jumpsuit",
        "a {c} crop top and a flowing white maxi skirt",
    ),
    "workout": (
        "a {c} sports bra and matching high-waisted leggings",
        "a {c} racerback tank over a black sports bra and bike shorts",
        "a {c} seamless crop top and leggings set",
        "a cropped {c} zip hoodie over a sports bra and running shorts",
        "a {c} longline sports bra and flared yoga pants",
        "a {c} one-piece athletic unitard",
        "a {c} tennis dress with built-in shorts",
        "a {c} mesh-panel sports bra and matching cycling shorts",
        "a {c} tank top and running shorts with a split hem",
        "a {c} crop top and high-waisted joggers",
        "a {c} sports bra under an open black mesh tank, with leggings",
        "a {c} ribbed workout onesie unzipped to the sternum",
        "a {c} halter sports bra and flared leggings",
        "a {c} baggy sweatshirt pulled off one shoulder over a sports bra and bike shorts",
        "a {c} scoop-neck bodysuit and wide-leg track pants",
        "a {c} strappy-back sports bra and a wrap skirt over leggings",
        "a {c} track jacket zipped halfway over a sports bra and leggings",
    ),
    "fancy_dining_gallery": (
        "a {c} satin midi dress with a cowl neckline",
        "a tailored {c} blazer dress",
        "a {c} silk slip dress with a draped neckline",
        "a fitted {c} knee-length sheath dress",
        "a {c} off-the-shoulder cocktail dress",
        "a {c} wrap midi dress with a slit",
        "a {c} one-shoulder jersey dress",
        "a {c} tailored jumpsuit with a plunging neckline",
        "a {c} lace midi dress over a nude lining",
        "a {c} velvet slip dress",
        "a {c} halter-neck midi dress with an open back",
        "a {c} pleated satin skirt and a fitted black bodysuit",
        "a {c} tuxedo-style blazer with nothing under it and wide-leg trousers",
        "a {c} square-neck fitted dress with puff sleeves",
        "a {c} silk shirt dress cinched with a belt",
        "a {c} strapless column dress",
        "a {c} ruched mesh midi dress",
        "a {c} high-neck sleeveless midi dress",
        "a {c} draped satin wrap top and a long bias-cut skirt",
        "a {c} fitted long-sleeve midi dress with a keyhole neckline",
    ),
    "fancy_town": (
        "a {c} sequined mini dress",
        "a {c} bodycon dress with a deep neckline",
        "a {c} corset top and a leather mini skirt",
        "a sheer {c} mesh top over a bralette and tailored black trousers",
        "a {c} cut-out halter mini dress",
        "a {c} latex-look mini dress",
        "a {c} chainmail halter top and black leather shorts",
        "a {c} bandage dress with a thigh-high slit",
        "a {c} bralette under a sheer black maxi dress",
        "a {c} satin mini slip dress with a cowl neck",
        "a {c} vinyl mini skirt and a black lace bodysuit",
        "a {c} backless halter jumpsuit",
        "a {c} rhinestone-strap mini dress",
        "a {c} ruched one-shoulder mini dress",
        "a {c} crop top and a high-slit satin maxi skirt",
        "a {c} bustier top and leather trousers",
        "a {c} micro mini dress with a lace-up front",
        "a {c} satin bustier and wide-leg black trousers",
        "a {c} fringe mini dress",
        "a {c} sheer mesh long-sleeve dress over a black bra and thong",
    ),
    "casual_date": (
        "a {c} wrap dress",
        "a {c} off-the-shoulder top and a denim skirt",
        "a fitted {c} knit top and a high-waisted midi skirt",
        "a {c} slip dress under a cropped denim jacket",
        "a {c} floral sundress with a sweetheart neckline",
        "a {c} smocked milkmaid top and a flowy midi skirt",
        "a {c} knit halter dress",
        "a {c} ruffled mini dress with flutter sleeves",
        "a {c} satin cami and a leather mini skirt",
        "a {c} tie-front crop top and wide-leg linen trousers",
        "a {c} square-neck mini dress with a cardigan over her shoulders",
        "a {c} fitted ribbed dress with a scoop neck",
        "a {c} blouse with balloon sleeves tucked into a denim mini skirt",
        "a {c} crochet top and a flowing skirt",
        "a {c} corset-waist midi dress",
        "a {c} bodysuit under high-waisted wide-leg trousers",
        "a {c} tiered sundress with a square neckline",
        "a {c} off-the-shoulder midi dress",
        "a {c} fitted turtleneck mini dress",
        "a {c} satin slip skirt and a cropped knit top",
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


# --- work looks ------------------------------------------------------------------
# Jeremy, 2026-10-12: "They're not going to wear the same fucking thing every
# day." One job line in her record becomes five work looks, and the KIND of job
# decides how. A uniform stays a uniform and varies in the small things - sleeves,
# an apron, a cardigan. A job she dresses herself for - the Chill Trap, a
# boutique, an office, a gallery - gets five different outfits in that job's
# register, coloured from her palette. Look 1 is always her own line.
#
# `{base}` is her job line with its "Obsidian waitress:" label stripped; `{c}`
# is a palette colour. First matching kind wins, so the specific ones go first.
WORK_KINDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("medical", r"nurse|hospital|scrubs|medical|clinic|doctor|dentist|vet\b", (
        "{base}",
        "{c} scrubs with a white long-sleeve tee underneath",
        "{c} scrubs with a fleece zip jacket over the top",
        "scrubs with a {c} printed top and plain trousers",
        "{c} scrubs with a stethoscope around her neck",
    )),
    ("dancer", r"dancer|stripper|chill trap|strip club|pole|burlesque|stage name|exotic", (
        "{base}",
        "a {c} satin bralette with matching micro shorts and a sheer wrap skirt",
        "a {c} lace bodysuit cut high on the hip with sheer black thigh-highs",
        "a {c} sequin two-piece - a tiny bra top and a thong-cut bottom",
        "a {c} mesh mini dress worn over a black bra and thong set",
    )),
    ("stage", r"\bband\b|stage|singer|musician|perform|\bdj\b|venue|show night", (
        "{base}",
        "a {c} satin bralette with high-waisted black trousers",
        "a {c} sequin crop top and a black micro skirt",
        "a {c} corset top with leather trousers",
        "a {c} mesh long-sleeve over a bralette and a mini skirt",
    )),
    ("boutique", r"boutique|clothing|fashion|threads|le chic|shop floor|stylist|retail", (
        "{base}",
        "a {c} satin blouse half-tucked into wide-leg trousers",
        "a fitted {c} turtleneck with a leather midi skirt",
        "a {c} blazer worn over a bralette with straight-leg jeans",
        "a {c} knit midi dress with a slim belt",
    )),
    ("gallery", r"gallery|curator|museum|art dealer", (
        "{base}",
        "a {c} column dress with a square neckline",
        "an oversized {c} blazer over a black turtleneck and slim trousers",
        "a {c} silk shirt with a black mini skirt and sheer tights",
        "a {c} asymmetric midi dress",
    )),
    ("fitness", r"yoga|trainer|\bgym\b|fitness|pilates|coach", (
        "{base}",
        "a {c} sports bra and matching high-waisted leggings",
        "a {c} racerback tank over a black sports bra and bike shorts",
        "a cropped {c} zip hoodie over a sports bra and leggings",
        "a {c} longline sports bra and flared yoga pants",
    )),
    ("academic", r"teach|professor|lecturer|university|tutor|school", (
        "{base}",
        "a {c} cardigan over a blouse with a pleated midi skirt",
        "a {c} tie-neck blouse with tailored trousers",
        "a {c} knit dress with a slim belt",
        "a {c} button-up shirt tucked into an A-line skirt",
    )),
    ("modest", r"church|volunteer|librar|charity|pastor|parish", (
        "{base}",
        "a {c} long-sleeve midi dress",
        "a {c} jumper with straight-leg jeans",
        "a {c} blouse with a knee-length skirt",
        "a {c} cardigan over a shirt dress",
    )),
    ("office", r"office|assistant|executive|professional|corporate|manager|real[- ]estate|agent|"
               r"\bsales\b|\brep\b|consultant|recruit|account|lawyer|paralegal|property", (
        "{base}",
        "a tailored {c} blazer over a silk cami with a pencil skirt",
        "a {c} sheath dress with a thin belt",
        "a {c} silk shirt tucked into high-waisted tailored trousers",
        "a fitted {c} knit top with wide-leg trousers and a long blazer",
    )),
)

# Everything else is a uniform - bar, cafe, counter, salon, grocery, or a job
# line nobody can place. It stays as written and changes in the small things;
# a variant whose key word is already in her line is skipped (keiko's record
# already has the apron).
UNIFORM_VARIANTS: tuple[tuple[str, str], ...] = (
    ("sleeve", "{base}, sleeves pushed up to the elbow"),
    ("apron", "{base}, a black apron tied at the waist"),
    ("cardigan", "{base}, a cropped black cardigan worn over it"),
    ("jacket", "{base}, a fitted black jacket worn open over it"),
    ("badge", "{base}, a thin black belt and a name badge"),
    ("necklace", "{base}, the top button undone and a thin pendant necklace"),
)

# Jobs that are a uniform whatever else their words say ("Lumen Salon assistant"
# is not an office job). Checked before WORK_KINDS.
UNIFORM_RE = re.compile(r"uniform|apron|salon|\bspa\b|waitress|server|bartender|barista|cafe|coffee|"
                        r"grocery|\btill\b|counter|burger|fast food|bakery|market stall|diner|tavern")

_LABEL_RE = re.compile(r"^[^:]{1,45}:\s+(?=\S)")


def job_base(outfit: str) -> str:
    """Her job line as prompt text: "Obsidian waitress: a short black
    shirt-dress" -> "a short black shirt-dress". A colon deeper in the line is
    left alone."""
    return _LABEL_RE.sub("", (outfit or "").strip()).strip()


def job_kind(text: str) -> str:
    """Which WORK_KINDS entry a job's words point at; "uniform" when none."""
    t = (text or "").lower()
    if UNIFORM_RE.search(t):
        return "uniform"
    for kind, pat, _ in WORK_KINDS:
        if re.search(pat, t):
            return kind
    return "uniform"


def _job_looks(job: dict, n: int, colours: list[str], rng: random.Random, game_job: str) -> list[str]:
    base = job_base(job["outfit"])
    # her record's words place the job; the game's one-line job is consulted
    # only when they do not (a legacy line like "a fitted knit top and
    # trousers" names clothes, not a job)
    words = " ".join((job.get("job", ""), job["outfit"]))
    kind = job_kind(words)
    if kind == "uniform" and game_job and not UNIFORM_RE.search(words.lower()):
        kind = job_kind(game_job)
    if kind == "uniform":
        tpl = ["{base}"] + [v for key, v in UNIFORM_VARIANTS if key not in base.lower()]
    else:
        tpl = list(next(t for k, _, t in WORK_KINDS if k == kind))
    cols = colours[:]
    rng.shuffle(cols)
    out = []
    for i, t in enumerate(tpl[:n]):
        out.append(t.format(base=base, c=cols[i % len(cols)]))
    while len(out) < n:                       # more looks asked than variants
        out.append(out[len(out) % len(tpl)])
    return out


def work_outfits(character: str, n: int = PACK_28["work"]) -> tuple[str, ...]:
    """Her `n` work outfits from her job line(s). Two jobs split them, the
    first job taking the larger share; no job outfit gives `()`.

    Deterministic per character, like the rest of the draft."""
    from .appearance import persona_job  # noqa: PLC0415
    from .wardrobe import editable  # noqa: PLC0415

    rec = editable(character)
    jobs = [j for j in rec["jobs"] if j["outfit"]]
    if not jobs:
        return ()
    colours = list(palette_colours(rec.get("palette", "")))
    rng = random.Random(f"{character}:work")
    game_job = persona_job(character) if len(jobs) == 1 else ""
    out: list[str] = []
    for i, job in enumerate(jobs):
        share = -(-(n - len(out)) // (len(jobs) - i))   # ceil of what is left
        out += _job_looks(job, share, colours, rng, game_job if i == 0 else "")
    return tuple(out[:n])


def draft_looks(character: str, seed: int = 0) -> dict[str, list[dict]]:
    """`{category: [{outfit, hair}, ...]}` for the standard 28, from her record.

    Deterministic per (character, seed): two drafts of the same character
    agree, two characters do not get the same lines, and "Start over" on the
    tab passes the next seed for a different roll.
    """
    from .wardrobe import editable, hair_options  # noqa: PLC0415

    rec = editable(character)
    colours = list(palette_colours(rec.get("palette", "")))
    hair = list(hair_options(character))
    rng = random.Random(f"{character}:{seed}" if seed else character)
    out: dict[str, list[dict]] = {}
    for ci, (cat, n) in enumerate(PACK_28.items()):
        looks = []
        off = rng.randrange(len(hair))          # her own hair rotation, not everyone's
        if cat == "work":
            # five different days at her job; blank lines when she has no job
            # outfit written down, for him to fill
            work = work_outfits(character, n)
            for i in range(n):
                looks.append({"outfit": work[i] if work else "",
                              "hair": hair[(i + ci + off) % len(hair)]})
        else:
            # a sample, not the whole pool: what she wears on day three is
            # not what the next character wears on day three
            tpl = rng.sample(TEMPLATES[cat], n)
            cols = colours[:]
            rng.shuffle(cols)
            for i in range(n):
                looks.append({"outfit": tpl[i].format(c=cols[i % len(cols)]),
                              "hair": hair[(i + ci + off) % len(hair)]})
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


def _first_render(folder: Path) -> Path | None:
    for name in ("scene_00.png", "scene_01.png"):
        if (folder / name).is_file():
            return folder / name
    hits = sorted(folder.glob("*.png")) if folder.is_dir() else []
    return hits[0] if hits else None


def source_asset(cfg: dict, character: str, epoch: int | None, lora: dict | None = None) -> Path | None:
    """A 2:3 render of her at her locked epoch for the pack to condition on:
    `scene_00.png` of her sweep in the library, else the old outputs/dense_* spot.

    A continued run numbers its epochs from 1 and sweeps into a folder tagged
    with its name - priyanka's lock is `priyanka_v2b-000006` = epoch 26, rendered
    in `*_sweep_v2b/ep06`. So after `ep<epoch>` anywhere, look in that run's own
    sweep folders for its file number, or its last epoch when the file is the
    unnumbered final one (vivienne: `vivienne_v2b.safetensors`, epoch 28, ep04)."""
    from ..library import library_dir  # noqa: PLC0415
    from ..config import outputs_dir  # noqa: PLC0415

    if epoch is None:
        return None
    roots = sorted((library_dir(cfg) / character).glob("*_sweep_*"), reverse=True)
    roots += sorted(outputs_dir(cfg).glob(f"dense_{character}*"), reverse=True)
    for r in roots:
        hit = _first_render(r / f"ep{int(epoch)}")
        if hit:
            return hit
    # the continued run's own folders
    name = Path((lora or {}).get("name") or (lora or {}).get("path") or "").name
    m = re.match(rf"{re.escape(character)}_(.+?)(?:-(\d+))?\.safetensors$", name)
    if not m:
        return None
    tag, num = m.group(1), m.group(2)
    own = [r for r in roots if re.search(rf"_sweep_{re.escape(tag)}(?:-|$)", r.name)]
    for r in own:
        if num:
            hit = _first_render(r / f"ep{int(num):02d}") or _first_render(r / f"ep{int(num)}")
        else:
            eps = sorted((d for d in r.glob("ep*") if d.is_dir()), key=lambda d: int(d.name[2:] or 0))
            hit = _first_render(eps[-1]) if eps else None
        if hit:
            return hit
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
    """Write a fresh draft from her record and return the state. Each draft
    after the first is a different roll (the seed counts up from the draft it
    replaces). Never touches an approved plan: a new draft sits beside it until
    approved, when it takes over."""
    from ..config import outputs_dir  # noqa: PLC0415
    from .lora import resolve_lora  # noqa: PLC0415

    c = character.lower()
    out = outputs_dir(cfg)
    prev = _read(draft_path(out, c)) or _read(approved_path(out, c)) or {}
    seed = int(prev.get("seed", -1)) + 1
    lora = resolve_lora(cfg, c)
    src = source_asset(cfg, c, (lora or {}).get("epoch"), lora)
    ref = reference(c)
    plan = make_plan(c, lora=(lora or {}).get("path"),
                     source_asset=str(src) if src else None,
                     reference=str(ref) if ref else None,
                     looks=draft_looks(c, seed), start_after=shipped(c))
    plan["seed"] = seed
    _write(draft_path(out, c), plan)
    return state(cfg, c)


def save(cfg: dict, character: str, categories: dict) -> dict:
    """Write his edits into whichever file is current - the open draft, or the
    approved plan if he is revising one. `categories` is {cat: [{id, outfit, hair}]}."""
    from ..config import outputs_dir  # noqa: PLC0415

    c = character.lower()
    out = outputs_dir(cfg)
    p = draft_path(out, c) if draft_path(out, c).is_file() else approved_path(out, c)
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
    src = source_asset(cfg, c, lora.get("epoch"), lora)
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
    # an open draft is what he is working on, even when a plan is approved
    doc = dr or ap
    st = "draft" if dr else ("approved" if ap else "none")
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
            "seed": (doc or {}).get("seed", 0),
            "categories": cats, "blank": blank, "shipped": shipped(c),
            "source_asset": (doc or {}).get("source_asset"), "lora": (doc or {}).get("lora")}
