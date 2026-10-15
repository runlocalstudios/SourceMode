"""The character's body/feature clause, for GENERATION prompts only.

The clause is her appearance text from `characters/appearance.json`, exactly as
written. The age is NOT added to it. Jeremy, 2026-10-10: "Let's get rid of the age
box. I'm gonna include it in the descriptions only when it's absolutely necessary."
(This replaces the 2026-10-03 rule that every generation states the game's age.)
The game's age, cached in `characters/ages.json`, is still read for the Looks tab
and the pre-flight.

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
_cache_stamp: tuple = ()


def _stamp() -> tuple:
    def mt(p: Path) -> int:
        try:
            return p.stat().st_mtime_ns
        except OSError:
            return 0
    return (mt(AGES), mt(APPEARANCE))


def _load() -> dict:
    """The records, re-read whenever either file changes on disk. The monitor
    is long-lived and used to read them ONCE: Vera, created on the new-character
    form, was refused for training with "age missing; prompt missing" because
    the training page's preflight ran against a cache from before she existed
    (2026-10-14). Nothing that writes these files should have to remember to
    clear a cache."""
    global _cache, _cache_stamp
    stamp = _stamp()
    if _cache is None or stamp != _cache_stamp:
        _cache_stamp = stamp
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


def key_characters() -> list[str]:
    """Every female key character the game declares, whether or not we have a
    record for her yet. Jeremy, 2026-10-08: Jordan, Eve and Aura were missing
    from the Looks tab - "they are key characters in the game - import all key
    characters not currently there". The page lists them from here; a record
    is written only when he confirms one, so nothing is invented for them."""
    try:
        src = GAME_CHARACTERS.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for m in re.finditer(r"^  ([a-z0-9_]+):\s*\{(.*?)^  \},?\s*$", src, re.S | re.M):
        body = m.group(2)
        if re.search(r"keyCharacter:\s*true", body) and re.search(r"\bsex:\s*'F'", body):
            out.append(m.group(1))
    return sorted(set(out))


def age_of(character: str) -> int | None:
    """appearance.json wins: a character the game does not list yet (or one whose
    art age differs from her written age) is set there."""
    c = character.lower()
    own = (_load()["look"].get(c) or {}).get("age")
    return int(own) if own else _load()["ages"].get(c)


# `frame` and the "fitted to her <frame>" clause are gone. Jeremy, 2026-10-10:
# "Get rid of the fit drop down. It's too confusing ... there's no reason to
# limit it to five types of frames when we can have somebody with a skinny
# frame but super wide hips." The prompt field carries the whole body; a
# fallback derived from `figure` had been sending vivienne "tiny frame".


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


# --- confirmation ---------------------------------------------------------------
# Jeremy, 2026-10-06: "they're so fucked up that I can't trust them." Bri's
# "lighter caramel ends" and Jaina's freckles were drafted from reference photos,
# marked "DRAFT - correct before her sweep", and rendered into both sweeps anyway:
# a note in a file stopped nothing. A record is now CONFIRMED when he approves its
# exact text on the Looks tab, bound to a fingerprint of the fields that reach a
# prompt - so any later edit, by hand or by a script, unconfirms it - and check()
# refuses an unconfirmed record like a missing one.
CONFIRM_FIELDS = ("prompt", "negative")


def record_fingerprint(rec: dict) -> str:
    import hashlib  # noqa: PLC0415

    blob = "\x1f".join(" ".join(str(rec.get(k) or "").split()) for k in CONFIRM_FIELDS)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def confirmed(character: str) -> bool:
    rec = _load()["look"].get((character or "").lower()) or {}
    c = rec.get("confirmed") or {}
    return bool(c.get("fingerprint")) and c["fingerprint"] == record_fingerprint(rec)


def confirm(character: str, fields: dict) -> dict:
    """Write his reviewed text and mark it confirmed. Only CONFIRM_FIELDS change;
    an empty string clears a field (an empty negative means none)."""
    import json as _json  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    global _cache
    c = (character or "").lower()
    doc = _json.loads(APPEARANCE.read_text(encoding="utf-8")) if APPEARANCE.is_file() else {}
    rec = doc.setdefault(c, {})
    for k in CONFIRM_FIELDS:
        if k in fields:
            v = " ".join(str(fields[k] or "").split())
            if v:
                rec[k] = v
            else:
                rec.pop(k, None)
    # Own age: overrides the game's age where age_of is read. Not in the
    # fingerprint. Prompts never state it - an age goes in the text itself.
    if "age" in fields:
        a = str(fields.get("age") or "").strip()
        if a:
            if not a.isdigit() or not 18 <= int(a) <= 80:
                raise ValueError("render age must be a whole number from 18 to 80")
            rec["age"] = int(a)
        else:
            rec.pop("age", None)
    if not (rec.get("prompt") or "").strip():
        raise ValueError("a confirmed record needs a prompt")
    rec["confirmed"] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "fingerprint": record_fingerprint(rec)}
    APPEARANCE.write_text(_json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    _cache = None
    return rec


def set_context(character: str, *, ethnicity: str) -> dict:
    """Context for the game's writing - never read by a prompt, and outside the
    confirm fingerprint, so changing it never un-confirms her description."""
    import json as _json  # noqa: PLC0415

    global _cache
    c = (character or "").lower()
    doc = _json.loads(APPEARANCE.read_text(encoding="utf-8")) if APPEARANCE.is_file() else {}
    rec = doc.setdefault(c, {})
    v = " ".join(str(ethnicity or "").split())
    if v:
        rec["ethnicity"] = v
    else:
        rec.pop("ethnicity", None)
    APPEARANCE.write_text(_json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    _cache = None
    return rec


def reload() -> None:
    """Forget the cached records - the monitor is long-lived and reads them once."""
    global _cache
    _cache = None


def check(character: str) -> dict:
    """What is missing from her record, for the pre-flight before GPU time.

    `missing` are the fields the render prompt cannot do without: an age, and
    the appearance sentence. Without them the prompt is the trigger alone, and
    every trait the LoRA will not carry is lost - vivienne's sweep scored 0/90
    that way. `warnings` are the things worth having: a reference photo that
    embeds so the eval can score and the judge page can show her.
    """
    c = character.lower()
    rec = _load()["look"].get(c) or {}
    missing, warnings = [], []
    if not age_of(c):
        missing.append("age - not in the game's characters.js and not in appearance.json")
    if not (rec.get("prompt") or "").strip():
        missing.append("prompt - the appearance sentence every render carries "
                       "(figure, waist and bust, skin tone, hair length, texture and "
                       "colour, eye colour - what drifts without body exposure; no age "
                       "numeral, no ethnicity word, nothing that strongly changes the face)")
    elif not confirmed(c):
        missing.append("confirmed - Jeremy has not confirmed this record; review it on "
                       "the Looks tab (drafts carried invented details into two sweeps)")
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
# "half-up" replaced "half pinned back" (2026-10-11) and is an up-style like it.
# Pigtails over hair worn DOWN are not: the length is the point of them.
_UP = re.compile(r"\b(?:bun|ponytail|pinned back|pinned up|half-up|gathered|tied back"
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
    """Her appearance text exactly as written - no age added, "" if she has none.

    Jeremy, 2026-10-10: an age goes in the description itself, and only when it
    is absolutely necessary.
    """
    rec = _load()["look"].get(character.lower()) or {}
    return rec.get("prompt", "") or ""
