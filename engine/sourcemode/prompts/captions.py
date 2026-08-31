"""Caption-cleaning grammar, ported from e2egen scripts/caption_florence.py:35-79.

Pure regex, torch-free. Strips generic subject phrases so identity binds to the
trigger token, and deletes invariant traits so they don't compete with it.
"""

from __future__ import annotations

import re

# Florence tends to open with a subject clause; we bind identity to the trigger instead, so strip
# these leading phrases and any generic re-mentions mid-caption.
SUBJECT_RE = re.compile(
    r"\b(the image (shows|is|depicts|captures|features)|this image (shows|is)|"
    r"in this image,?|the photo (shows|is)|a (photo|picture|portrait|close-?up|image) of)\b",
    re.IGNORECASE)
PERSON_RE = re.compile(
    r"\b(a|the|an)\s+(young\s+)?(woman|girl|lady|female|person|man|boy|male|model)\b",
    re.IGNORECASE)


def _strip_traits(c: str, terms: list[str]) -> str:
    """Remove invariant identity descriptors so they bind to the trigger, not the caption text.
    Drops the short clause/sentence that mentions each term rather than leaving dangling grammar."""
    for term in terms:
        # kill "She has freckles on her face." / "with green eyes," / ", green eyes"
        c = re.sub(rf"\b(she\s+has\s+|with\s+|having\s+)?[^.,]*\b{re.escape(term)}\b[^.,]*[.,]?",
                   " ", c, flags=re.IGNORECASE)
    return c


def clean_concept(caption: str, trigger: str) -> str:
    """Concept-LoRA captioning is the INVERSE of character captioning: the subjects must stay
    generic ("a woman") so identity does NOT bind to the trigger — only the shared action/concept
    should. So keep person phrases untouched and just anchor the trigger at the front."""
    c = caption.strip().replace("\n", " ")
    c = SUBJECT_RE.sub("", c).strip()
    c = re.sub(r"\s{2,}", " ", c).strip(" ,.")
    return f"{trigger}, {c}"


def clean(caption: str, trigger: str, strip_terms: list[str] | None = None) -> str:
    c = caption.strip().replace("\n", " ")
    if strip_terms:
        c = _strip_traits(c, strip_terms)
    c = SUBJECT_RE.sub("", c).strip()
    # first "a woman/the girl" -> the trigger; later ones -> "she/her" feel, just drop the article
    c = PERSON_RE.sub(trigger, c, count=1)
    c = PERSON_RE.sub("she", c)
    c = re.sub(r"\s{2,}", " ", c).strip(" ,.")
    if not c.lower().startswith(trigger.lower()):
        c = f"{trigger}, {c}"
    # collapse "trigger, trigger" if the substitution and prefix doubled up
    c = re.sub(rf"^{re.escape(trigger)},?\s+{re.escape(trigger)}\b", trigger, c, flags=re.IGNORECASE)
    return c
