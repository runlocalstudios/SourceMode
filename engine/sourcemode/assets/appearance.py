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
    return {"character": c, "ok": not missing, "missing": missing, "warnings": warnings,
            "has_record": bool(rec)}


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
