"""Video templates: a reference clip turned into something any character can be run through.

Jeremy, 2026-10-28: "Let's start creating some video setup structure - name this
video and create the ability to create the starting frames for review before
implementing the video gen. Can you set the audio script to be the same as the
source, but something that I can edit, which would modify the future generations."

A template is one JSON file in /video-templates (tracked, so an edit to a script
is a diff he can see). It holds:

- the source clip it was modelled on (in devassets/video examples)
- the START FRAME: what she wears, where, and how the shot is composed - his
  point of view from a sofa, his knees and grey shorts fixed at the bottom of
  the frame (the 475895e9 clip's legs, which the club clip got wrong)
- the LEGS: one motion line per 5 s Wan leg, for when video generation lands
- the SCRIPT: what she says, started from the source's own words and edited on
  the Video tab; the voice track of every future render reads it from here

Start frames render landscape (the sources are 16:9) through her LoRA, four
seeds at a time, into a judge set - the still is the whole identity question,
so it is reviewed before any video time is spent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import ENGINE_ROOT

TEMPLATES_DIR = ENGINE_ROOT.parent / "video-templates"
ID_RE = re.compile(r"^[a-z0-9_]+$")
#: Qwen-Image's own 16:9 bucket - the sources are 1280x720
WIDTH, HEIGHT = 1664, 928
START_SEED = 5100


def path_for(template_id: str) -> Path:
    if not ID_RE.match(template_id or ""):
        raise ValueError("a template id is lowercase letters, digits and underscores")
    return TEMPLATES_DIR / f"{template_id}.json"


def load(template_id: str) -> dict:
    p = path_for(template_id)
    if not p.is_file():
        raise KeyError(f"no video template {template_id}")
    doc = json.loads(p.read_text(encoding="utf-8"))
    return {**doc, "id": template_id}


def all_templates() -> list[dict]:
    if not TEMPLATES_DIR.is_dir():
        return []
    return [load(p.stem) for p in sorted(TEMPLATES_DIR.glob("*.json"))]


def save_script(template_id: str, script: str) -> dict:
    """His edit of what she says. Written straight into the template, so the
    next render - and every one after it - speaks these lines."""
    p = path_for(template_id)
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["script"] = str(script or "").replace("\r\n", "\n").strip()
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return load(template_id)


def start_prompt(template: dict, character: str, partner: str | None = None,
                 trigger: str | None = None) -> str:
    """The start frame's prompt for her, in the caption register every other
    render uses: trigger, her appearance sentence, the composition, the outfit,
    her hair, the setting."""
    from .assets.render import appearance_clause  # noqa: PLC0415
    from .assets.wardrobe import short_hair  # noqa: PLC0415

    s = template["start"]
    who = appearance_clause(character) or "a woman"
    hair = short_hair(character, s.get("hair", "her hair worn loose"), 1)
    parts = [trigger or character, who, s["composition"], f"{hair}, wearing {s['outfit']}"]
    if int(template.get("cast", 1)) > 1:
        other = appearance_clause(partner) if partner else ""
        parts.append(s["partner"].format(partner=other or "another young woman"))
    parts.append(s["setting"])
    return ", ".join(p.strip().rstrip(",") for p in parts if p) + \
        ". Photorealistic, natural skin texture, sharp focus."


def start_negative(template: dict, base: str) -> str:
    extra = template["start"].get("negative", "")
    return f"{base}, {extra}" if extra else base
