"""The character's age and body/feature clause, for GENERATION prompts only.

Jeremy, 2026-10-03, on Kimmy's epoch eval: "kimmy's pictures also look plagued by
looking too old. moving forward as a rule I want you to put the model's age in all
generations. even if the lora is slightly older i have found this to help with my own
image generations."

So every generated image states her age. The age is the game's own, read from
`chillafterdark/src/data/characters.js` and cached in `characters/ages.json`; the
body/feature text, where one exists, comes from `characters/appearance.json`.

NEVER put any of this in a training caption. Age, build and colouring are identity
traits: a captioned trait stays variable and is never learned (assetgen rule b). It
goes in the prompt so the picture shows it, and nowhere near the .txt file.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AGES = ROOT / "characters" / "ages.json"
APPEARANCE = ROOT / "characters" / "appearance.json"
GAME_CHARACTERS = Path("C:/dev/chillafterdark/src/data/characters.js")

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        ages = {}
        if AGES.is_file():
            try:
                ages = {k: v for k, v in json.loads(AGES.read_text(encoding="utf-8")).items()
                        if not k.startswith("_")}
            except (OSError, ValueError):
                ages = {}
        look = {}
        if APPEARANCE.is_file():
            try:
                look = json.loads(APPEARANCE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                look = {}
        _cache = {"ages": ages, "look": look}
    return _cache


def refresh_ages() -> dict[str, int]:
    """Re-read every age out of the game data. Run after the cast changes."""
    src = GAME_CHARACTERS.read_text(encoding="utf-8", errors="replace")
    ages: dict[str, int] = {}
    for m in re.finditer(r"id:\s*'([a-z0-9_]+)'[^}]{0,400}?age:\s*(\d+)", src, re.S):
        ages.setdefault(m.group(1), int(m.group(2)))
    doc = {"_comment": ["Ages as the game states them, from chillafterdark/src/data/characters.js.",
                        "Stated in every GENERATION prompt (assets, eval scenes, local shot plans)",
                        "and NEVER in a training caption - age is an identity trait.",
                        "Regenerate with: sourcemode.assets.appearance.refresh_ages()"],
           **dict(sorted(ages.items()))}
    AGES.parent.mkdir(parents=True, exist_ok=True)
    AGES.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    global _cache
    _cache = None
    return ages


def _article(age: int) -> str:
    """"an 18-year-old", "an 11-year-old", "an 80-year-old" - but "a 19-year-old"."""
    return "an" if age in (8, 11, 18) or 80 <= age <= 89 else "a"


def age_of(character: str) -> int | None:
    """appearance.json wins: a character the game does not list yet (or one whose
    art age differs from her written age) is set there."""
    c = character.lower()
    own = (_load()["look"].get(c) or {}).get("age")
    return int(own) if own else _load()["ages"].get(c)


def frame(character: str) -> str:
    """How an outfit sits on THIS character - "tiny frame", "curvy frame".

    Empty when her record does not say, and an empty frame must produce no
    clause at all. `render.py` hardcoded "fitted to her tiny frame" for every
    character: true for amanda, who it was written for, and asserted for
    everyone else. cici's own record reads "curvy, hourglass, large bust, full
    hips" and the renderer was still telling the model she was tiny.

    That is the same defect as vivienne's "long black hair" - a prompt stating a
    trait the character's data contradicts - and it costs the same way, because
    explicit text beats a LoRA's learned association.

    `frame` is read first so the wording can be set deliberately; otherwise it
    is taken from `build`/`figure`, and anything that does not reduce to a short
    phrase is left out rather than guessed at.
    """
    rec = _load()["look"].get(character.lower()) or {}
    own = (rec.get("frame") or "").strip()
    if own:
        return own
    blob = " ".join(str(rec.get(k) or "") for k in ("build", "figure")).lower()
    if not blob.strip():
        return ""
    # Only the two shapes that actually change how clothing reads. A record that
    # says neither gets no clause, which is the safe answer.
    if any(w in blob for w in ("petite", "skinny", "slim", "slender", "tiny")):
        return "tiny frame"
    if any(w in blob for w in ("curvy", "hourglass", "full hips", "thick", "voluptuous")):
        return "curvy frame"
    return ""


# Words the game's own prose uses about how a character LOOKS. Deliberately
# narrow: the systemPrompt is mostly voice and behaviour, and matching loosely
# turns "building, frank and direct" into a physical description. Ethnicity and
# eye/hair/build words only.
_ETHNICITY = ("black", "latina", "asian", "vietnamese", "korean", "japanese", "chinese",
              "filipina", "indian", "white", "mixed", "hispanic", "middle eastern")
_PHYSICAL = ("hair", "eyes", "skin", "freckle", "tattoo", "curvy", "petite", "slim",
             "slender", "tall", "short", "build", "figure", "bust", "blonde",
             "brunette", "redhead")


def game_facts(character: str) -> dict:
    """What chillafterdark already states about her: age, role, and any
    appearance the writing commits to.

    Jeremy, 2026-10-04: "I want you to do a quick scan anytime we have a new
    character to check whether any of this is already described in Chill After
    Dark... most of these characters already have information that should be
    validated to ensure that it's the same, at least the first time."

    The game is the source of truth for age and for anything its dialogue
    asserts - a render that contradicts the writing is wrong even if it looks
    good. Returns `{}` when the game repo is not present, so nothing here
    depends on it being checked out.
    """
    import re as _re  # noqa: PLC0415

    if not GAME_CHARACTERS.is_file():
        return {}
    try:
        src = GAME_CHARACTERS.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    c = character.lower()
    m = _re.search(rf"^  {_re.escape(c)}:\s*\{{", src, _re.M)
    if not m:
        return {}
    nxt = _re.search(r"^  [a-z0-9_]+:\s*\{", src[m.end():], _re.M)
    rec = src[m.start(): m.end() + (nxt.start() if nxt else len(src))]

    out: dict = {"found": True}
    age = _re.search(r"age:\s*(\d+)", rec)
    if age:
        out["age"] = int(age.group(1))
    intro = _re.search(r"introImpression:\s*'([^']*)'", rec)
    if intro:
        out["intro"] = intro.group(1)
    sp = _re.search(r"systemPrompt:\s*`(.*?)`", rec, _re.S)
    text = sp.group(1) if sp else ""
    out["system_prompt"] = text
    # the opening line is where the writing states who she is and what she does
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    out["opening"] = first
    low = text.lower()
    out["ethnicity"] = sorted({w for w in _ETHNICITY if _re.search(rf"\b{w}\b", low)})
    out["physical"] = [l.strip() for l in text.splitlines()
                       if any(_re.search(rf"\b{w}", l.lower()) for w in _PHYSICAL)][:4]
    # where her week takes her, as (location, outfit) - the influencer pack
    # reads her job and hobbies off this rather than off prose
    out["schedule"] = [(m.group(1), m.group(2)) for m in _re.finditer(
        # keys appear both quoted and bare in the game file - priyanka's
        # library shift is `{ location: 'library', ... }`
        r"['\"]?location['\"]?:\s*'(\w+)'[^}]*?['\"]?outfit['\"]?:\s*'(\w+)'", rec)]
    return out


GAME_PERSONA = GAME_CHARACTERS.with_name("characterPersona.js")
GAME_LOCATIONS = GAME_CHARACTERS.with_name("locations.js")


def persona_job(character: str) -> str:
    """Her one-line job from characterPersona.js ("She runs the floor at
    Threads..."), or "" when the game does not have one."""
    import re as _re  # noqa: PLC0415

    try:
        src = GAME_PERSONA.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = _re.search(rf"^\s*{_re.escape(character.lower())}:\s*persona\(", src, _re.M)
    if not m:
        return ""
    j = _re.search(r"job:\s*'((?:[^'\\]|\\.)*)'", src[m.end(): m.end() + 1500])
    return j.group(1) if j else ""


def location_names() -> dict[str, str]:
    """Game location id -> display name ("threads" -> "Threads")."""
    import re as _re  # noqa: PLC0415

    try:
        src = GAME_LOCATIONS.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return dict(_re.findall(r"(?m)^\s{2}(\w+):\s*\{[^}]*?name:\s*'([^']+)'", src))


def validate(character: str) -> list[str]:
    """Where our record and the game's writing disagree. Checked when a record
    is created, not on every render - the game is authoritative, so a conflict
    means one of the two needs editing, by a person."""
    import re as _re  # noqa: PLC0415

    g = game_facts(character)
    if not g.get("found"):
        return []
    rec = _load()["look"].get(character.lower()) or {}
    ours = " ".join(str(rec.get(k) or "") for k in
                    ("prompt", "features", "ethnicity", "build", "figure")).lower()
    out = []
    if rec.get("age") and g.get("age") and int(rec["age"]) != g["age"]:
        out.append(f"age: record says {rec['age']}, the game says {g['age']} - the game wins, "
                   f"so remove the age field here")
    for e in g.get("ethnicity", []):
        if ours and e not in ours:
            out.append(f"ethnicity: the game's dialogue calls her {e!r}, our record does not")
    return out


def negative(character: str) -> str:
    """Per-character NEGATIVE text: what the base model reverts to without it.

    Raven has a full fringe in all five references and in her training frames;
    without a negative the renders came back with a centre part and a bare
    forehead - a visibly different person however well the LoRA learned her
    face. This used to live in a FEATURE_NEG dict inside dense_epoch_eval.py,
    so it reached the eval and never the asset pack. One source now, read by
    both.
    """
    return ((_load()["look"].get(character.lower()) or {}).get("negative") or "").strip()


# What a render from the LoRA needs documented BEFORE the first text-only
# inference - the epoch sweep - because that is the first time text alone has
# to carry identity. Training images come from reference photos and captions
# exclude identity by design, so neither needs this; the sweep and the pack do.
REQUIRED = ("age", "prompt")


def check(character: str) -> dict:
    """What is missing from her record, for the pre-flight before GPU time.

    `missing` are the fields the render prompt cannot do without: an age, and
    the appearance sentence. Without them the prompt is the trigger alone, and
    every trait the LoRA will not carry is lost - vivienne's sweep scored 0/90
    that way. `warnings` are the things worth having: a frame so an outfit sits
    on the right body, and a reference photo that embeds so the eval can score
    and the judge page can show her.
    """
    c = character.lower()
    rec = _load()["look"].get(c) or {}
    missing, warnings = [], []
    if not age_of(c):
        missing.append("age - not in the game's characters.js and not in appearance.json")
    if not (rec.get("prompt") or "").strip():
        missing.append("prompt - the appearance sentence every render carries "
                       "(ethnicity, build, hair colour and length, eyes, anything the "
                       "base model will not volunteer)")
    if not frame(c):
        warnings.append("frame - tiny / curvy / omit; without it no fitted clause is sent")
    refs = Path("C:/Epic Games/Files/cnc info/codex/references")
    if refs.is_dir() and not any(refs.glob(f"{c}_*")):
        warnings.append("no reference photo under codex/references - the eval cannot "
                        "score identity and the judge page has nothing to show")
    conflicts = validate(c)
    return {"character": c, "ok": not missing, "missing": missing, "warnings": warnings,
            "conflicts": conflicts, "has_record": bool(rec)}


#: Words that say the hair is HANGING. Measured 2026-10-04: a prompt carrying
#: one of these in the identity clause and an up-style per look renders the full
#: length down AND a bun perched on top of it - 10 of 10 bun-prompted shots
#: across geena and cindy, and he rejected 7 of them. Keep rate on those ten was
#: 30% against 83% for every other prompt in the same four sets.
#:
#: Jeremy had said this before it was measured: "you cannot put long hair in the
#: same prompt as a messy bun. Otherwise, you get those weird results."
# Only the words that mean LONG. "chin-length" and "shoulder-length" stay:
# short hair does not fight a bun, and dropping priya's "chin-length" would
# lose the one trait that makes her the only short-haired character in the cast.
_LENGTH = re.compile(
    r"\b(?:very long|waist-length|long)\s+"
    r"(?=(?:[\w-]+\s+){0,5}?(?:hair|bob|braids|curls|waves)\b)", re.I)
_FLOWING = re.compile(r",?\s*\b(?:hanging (?:free|loose|down)[^,.]*"
                      r"|worn (?:loose|down)|falling [^,.]*"
                      r"|down (?:her|the) back)", re.I)

#: An up-style in a per-look hair clause. Whole words, so "bunch" cannot trip it.
_UP = re.compile(r"\b(?:bun|ponytail|pinned back|pinned up|gathered|tied back"
                 r"|updo|piled|chignon|topknot|twisted up)\b", re.I)


def is_up_style(hair_clause: str) -> bool:
    """Does this per-look hair clause put the hair UP?"""
    return bool(_UP.search(hair_clause or ""))


def drop_length(text: str) -> str:
    """Remove hanging-hair wording from an identity clause.

    Only the words that assert the hair is DOWN go: length and flow. Colour and
    texture stay, because a platinum bun is still platinum and the colour is the
    identity trait the base model will not volunteer.
    """
    out = _FLOWING.sub("", _LENGTH.sub("", text or ""))
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",\s*,", ",", out)
    return out.strip(" ,")


def clause(character: str) -> str:
    """"an 18-year-old, extremely petite..." - age first, then the body text if any.

    Returns a bare age phrase for characters with no appearance entry, so the age rule
    holds for the whole cast and not only the three with written descriptions.
    """
    c = character.lower()
    age = age_of(c)
    text = (_load()["look"].get(c) or {}).get("prompt", "") or ""
    if age and text:
        # an entry that already opens with the age is left alone
        if re.match(rf"an?\s+{age}[- ]year[- ]old", text):
            return text
        return f"{_article(age)} {age}-year-old, " + re.sub(r"^an?\s+", "", text)
    if age:
        return f"{_article(age)} {age}-year-old woman"
    return text
