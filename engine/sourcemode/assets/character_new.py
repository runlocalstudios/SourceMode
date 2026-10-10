"""Create a character once, completely, instead of discovering the gaps later.

Jeremy, 2026-10-04: "maybe what we need is a new form added to this as well
that creates a new character - name, age, body type, hair and eyes
descriptions, ethnicity, job, etc? that can then scaffold here for asset
generation, make sure we don't miss anything, and also pass along any needed
info to chillafterdark."

Every expensive mistake this project has recorded was a missing field found
too late:

  vivienne  swept 90 renders at 0/90 because her record said nothing about the
            pink underlayer, so the prompt said "long black hair"
  cici      had every outfit described as "fitted to her tiny frame" because
            `frame` was hardcoded and her record said curvy (the clause and
            the Fit field are gone since 2026-10-10; the prompt carries it)
  raven     had a bangs negative that lived in the eval and never reached her
            wardrobe pack
  maya      ships with a turquoise hair underlayer that no record mentioned
            until 2026-10-04, two LoRAs in
  four      characters whose structured `age` and systemPrompt prose disagree

None of those needed cleverness to prevent. They needed one form with the
field on it.

So this builds BOTH records from one submission - the appearance clause every
render carries, and the wardrobe brief a 28-look plan expands - and hands back
the chillafterdark snippet rather than writing into that repo, which is the
same contract `assets place` already follows.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: Every field the form collects. `need` is what `check()` will refuse without,
#: `want` is what something downstream silently defaults when it is absent -
#: which is how cici got a tiny frame and raven lost her negative.
FIELDS = (
    # key, label, need, hint
    ("character", "Id", "need", "lowercase, no spaces - the LoRA trigger and the game id"),
    ("name", "Display name", "need", "as the game shows it"),
    ("age", "Age", "need", "the number the game will carry; prose must agree with it"),
    ("ethnicity", "Ethnicity", "need", "Black, Latina, Indian, East Asian, White..."),
    ("skin", "Skin", "need", "fair / light olive / medium brown / light caramel-brown"),
    ("hair", "Hair", "need", "length, texture, colour - and any dyed layer, which the "
                             "model will NOT volunteer"),
    ("eyes", "Eyes", "need", "brown is the default the base model reaches for; anything "
                             "else has to be said"),
    ("build", "Build", "need", "petite / slim and athletic / curvy hourglass"),
    ("bust", "Bust", "want", "small / medium / full - it changes how every outfit sits"),
    ("features", "Other features", "want", "freckles, glasses, strong brows, full lips - "
                                           "anything you would notice first"),
    ("negative", "Never render", "want", "what the base model reverts to without being "
                                         "told - raven's centre part, a missing fringe"),
    ("job", "Job", "want", "fixes her `work` outfits - this is not a taste, the game "
                           "decides it"),
    ("style", "Wardrobe style", "want", "how she dresses, in one line"),
    ("palette", "Palette", "want", "the three or four colours she actually wears"),
    ("avoid", "Wardrobe avoid", "want", "the line she does not cross - sandra wears no "
                                        "crop tops in any category"),
)
NEED = tuple(k for k, _, kind, _ in FIELDS if kind == "need")
WANT = tuple(k for k, _, kind, _ in FIELDS if kind == "want")

ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def appearance_clause(d: dict) -> str:
    """Compose the one sentence every render prompt carries.

    Built in the order the shipped records use - age, ethnicity, skin, figure,
    hair, eyes, features - because that order is what `clause()` consumers
    already read and what the measured prompts were written in.
    """
    bits = []
    lead = f"a {d['age']}-year-old {d['ethnicity']}".strip()
    bits.append(f"{lead} woman" if not lead.endswith("woman") else lead)
    if d.get("skin"):
        bits.append(f"{d['skin']} skin")
    fig = d.get("build", "")
    if d.get("bust"):
        fig = f"{fig} with a {d['bust']} bust" if fig else f"a {d['bust']} bust"
    if fig:
        bits.append(f"a {fig}" if not fig.startswith(("a ", "an ")) else fig)
    if d.get("hair"):
        bits.append(d["hair"])
    if d.get("eyes"):
        bits.append(d["eyes"])
    if d.get("features"):
        bits.append(d["features"])
    return ", ".join(b for b in bits if b)


def appearance_record(d: dict) -> dict:
    """The appearance.json entry. `prompt` is composed unless one was typed."""
    rec = {
        "_note": f"Created on the new-character form, {d.get('created', '')}".strip(),
        "ethnicity": d["ethnicity"],
        "build": d["build"],
        "figure": d["build"] + (f" with a {d['bust']} bust" if d.get("bust") else ""),
        "features": ", ".join(x for x in (d.get("hair"), d.get("eyes"),
                                          f"{d['skin']} skin" if d.get("skin") else "",
                                          d.get("features")) if x),
        "prompt": (d.get("prompt") or "").strip() or appearance_clause(d),
        "age": int(d["age"]),
    }
    if d.get("bust"):
        rec["bust"] = d["bust"]
    if d.get("negative"):
        rec["negative"] = d["negative"]
    return rec


def wardrobe_record(d: dict) -> dict:
    """The wardrobe.json entry: the style brief a 28-look plan expands."""
    return {k: v for k, v in (
        ("_note", f"Created on the new-character form, {d.get('created', '')}".strip()),
        ("style", d.get("style", "")),
        ("palette", d.get("palette", "")),
        ("silhouettes", d.get("silhouettes", "")),
        ("work", d.get("job", "")),
        ("workout", d.get("workout", "")),
        ("avoid", d.get("avoid", "")),
    ) if v}


def missing(d: dict) -> list[str]:
    """Required fields that are blank. Collected here so the form can refuse
    before anything is written, rather than the pre-flight refusing an hour
    into a render."""
    out = []
    for key, label, kind, _ in FIELDS:
        if kind == "need" and not str(d.get(key, "")).strip():
            out.append(label)
    return out


def thin(d: dict) -> list[str]:
    """Fields that are not required but whose absence has cost real GPU time.
    Never blocking - this is a prompt to look, the way every gate here is."""
    out = []
    if not str(d.get("bust", "")).strip():
        out.append("Bust - it changes how every top and dress sits")
    if not str(d.get("style", "")).strip():
        out.append("Wardrobe style - her 28-look plan has nothing to expand from")
    if not str(d.get("job", "")).strip():
        out.append("Job - the five `work` looks have no context")
    return out


def game_snippet(d: dict) -> str:
    """What chillafterdark needs, for him to paste. Nothing writes into that
    repo from here - the same contract `assets place` follows, and the reason
    is that a generated edit to a hand-written data file is a merge conflict
    waiting to happen."""
    cid = d["character"]
    return (f"// src/data/characters.js\n"
            f"{cid}: {{\n"
            f"  id:              '{cid}',\n"
            f"  name:            '{d['name']}',\n"
            f"  age:             {int(d['age'])},\n"
            f"  sex:             'F',\n"
            f"  // Keep the prose age in systemPrompt EQUAL to the field above.\n"
            f"  // Four characters already disagree with themselves there.\n"
            f"  systemPrompt:    `You are {d['name']}, {d['age']}"
            + (f", {d['ethnicity']}." if d.get("ethnicity") else ".")
            + (f" {d['job']}." if d.get("job") else "") + "`,\n"
            f"}},\n\n"
            f"// src/data/characterAppearance.js - wardrobe pack registration\n"
            f"{cid}: {{ id: '{cid}', workLocations: [] }},\n")


def create(d: dict, *, characters_dir: Path) -> dict:
    """Write both records. Refuses to overwrite: an existing character is an
    edit, and an edit that arrives as a create silently discards whatever was
    already measured about her."""
    cid = str(d.get("character", "")).strip().lower()
    if not ID_RE.match(cid):
        raise ValueError("id must be lowercase letters, digits and underscores")
    gaps = missing(d)
    if gaps:
        raise ValueError("missing: " + ", ".join(gaps))
    d = {**d, "character": cid}

    written = {}
    for fname, build in (("appearance.json", appearance_record),
                         ("wardrobe.json", wardrobe_record)):
        p = characters_dir / fname
        doc = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        if cid in doc:
            raise ValueError(f"{cid} already has a record in {fname} - edit it, "
                             f"do not re-create her")
        rec = build(d)
        if rec:
            doc[cid] = rec
            p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                         encoding="utf-8")
            written[fname] = rec
    return {"character": cid, "written": sorted(written),
            "appearance": written.get("appearance.json", {}),
            "thin": thin(d), "snippet": game_snippet(d)}
