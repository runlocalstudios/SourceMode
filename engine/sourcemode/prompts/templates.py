"""Per-leg prompt templates: pure functions (CharacterSource, ShotSpec) -> str.

Uses `re` for camera-vocabulary validation.

Design rules carried over from e2egen's measured findings (see INVENTORY.md):
- Framing and camera language are explicit, primary, directive prose — image
  and video models collapse to defaults when they're implicit.
- Keyframe prompts NEVER contain facial descriptors: identity comes from the
  trained LoRA + trigger token, and restating traits makes them compete with it.
- Video prompts are ordered blocks, most important first, ~80-120 words.
"""

from __future__ import annotations

import re

from ..source import CharacterSource
from .spec import ShotSpec

_SHOT_SIZE_WORDS = {
    "ECU": "extreme close-up",
    "CU": "close-up",
    "MCU": "medium close-up",
    "MS": "medium shot",
    "WS": "wide shot",
    "EWS": "extreme wide shot",
}

# Camera vocabulary that implies movement; "static" contradicts all of it.
_MOVING_RE = re.compile(
    r"\b(pan(?:s|ning)?|tilt(?:s|ing)?|dolly(?:ing)?|dollies|tracking|tracks|orbital|orbit(?:s|ing)?"
    r"|crane(?:s)?|push[- ]?in|pushes\s+in|whip[- ]?pan|handheld|zoom(?:s|ing)?)\b",
    re.IGNORECASE,
)
_STATIC_RE = re.compile(r"\b(static|locked[- ]off)\b", re.IGNORECASE)


class CameraContradictionError(ValueError):
    pass


def _camera_terms_in(text: str) -> set[str]:
    found = {m.group(1).lower() for m in _MOVING_RE.finditer(text)}
    if _STATIC_RE.search(text):
        found.add("static")
    return found


def validate_camera(spec: ShotSpec) -> None:
    """Reject contradictory camera terms across camera_move and motion text."""
    terms = _camera_terms_in(spec.camera_move) | _camera_terms_in(spec.motion)
    moving = terms - {"static"}
    if "static" in terms and moving:
        raise CameraContradictionError(
            f"shot {spec.idx}: contradictory camera terms — 'static' with {sorted(moving)}"
        )


def keyframe_prompt(source: CharacterSource, spec: ShotSpec) -> str:
    """Keyframe (image LoRA) prompt. NEVER includes facial descriptors —
    identity is carried entirely by the trigger token + LoRA.

    FRAMING LEADS, immediately after the trigger. Putting the environment
    first lets a strong compositional noun ("cafe window") become the subject
    and shrink the character to an incidental figure — measured on Bianca:
    all four candidates rendered a window with a tiny unrecognisable person
    (0.30-0.43). Framing-first matches e2egen's recorded finding (INVENTORY.md:
    "framing must be an explicit primary field or models collapse") and the
    hand-written prompts that scored 0.72 on the same character.
    """
    suffix = source.wardrobe_suffix(spec.wardrobe_state)
    trigger = f"{source.trigger_token}{suffix}"
    size = _SHOT_SIZE_WORDS[spec.shot_size]
    return (
        f"{trigger}, {size}, "
        f"{spec.lighting}, {spec.environment}, "
        f"{spec.emotion} expression, "
        f"{spec.lens}mm lens, {spec.grade}"
    )


def video_prompt(source: CharacterSource, spec: ShotSpec) -> str:
    """Wan 2.2 I2V prompt: ordered blocks, most important first, 80-120 words.

    [primary motion + explicit speed] [camera move, standard vocabulary]
    [environment/FX] [grade]. The character's negative_block is carried
    separately into the render's negative conditioning (Wan takes a distinct
    negative input) — see compile.compile_scene.
    """
    validate_camera(spec)
    camera = (
        "The camera is static, locked off on a tripod, holding the frame completely still"
        if spec.camera_move == "static"
        else f"The camera moves in a smooth {spec.camera_move} around the subject"
        if spec.camera_move == "orbital arc"
        else f"The camera performs a smooth {spec.camera_move}"
    )
    # The motion text comes from the brief, which usually names the character
    # ("Gwen walks…") or uses a pronoun ("she looks up…"); the sentence frame
    # already says "the character", so strip the leading subject.
    motion = re.sub(rf"^(?:{re.escape(source.name)}|she|he|they)\s+", "", spec.motion, flags=re.IGNORECASE)
    camera_pace = (
        "" if spec.camera_move == "static" else f", moving {spec.speed} and steady"
    )
    blocks = [
        # 1. primary motion, explicit speed word first
        f"{spec.speed.capitalize()}, the character {motion}, {spec.emotion} in expression and body "
        f"language, the movement continuous and natural from the first frame to the last.",
        # 2. camera move, standard vocabulary
        f"{camera}{camera_pace}, holding the {_SHOT_SIZE_WORDS[spec.shot_size]} framing "
        f"with a {spec.lens}mm field of view throughout the shot.",
        # 3. environment / FX
        f"Setting: {spec.environment}, with depth and atmosphere behind the subject. "
        f"{spec.lighting.capitalize()} shapes the scene consistently across every frame.",
        # 4. grade
        f"{spec.grade.capitalize()}, coherent motion, natural physics, stable identity, no morphing, no flicker.",
    ]
    return " ".join(blocks)


def video_negative(source: CharacterSource) -> str:
    return source.negative_block


# --- Character sheet (Qwen-Image-Edit) -------------------------------------

SHEET_VIEWS = (
    "front",
    "3/4 left",
    "3/4 right",
    "left profile",
    "right profile",
    "low angle front",
    "high angle front",
    "full body front",
    "full body 3/4",
)
SHEET_EXPRESSIONS = ("neutral", "slight smile")
SHEET_LIGHTINGS = ("soft even studio lighting", "directional window lighting")


def sheet_edit_prompts(source: CharacterSource) -> list[dict]:
    """One Qwen-Image-Edit instruction per (view x expression x lighting), plus
    the training caption for the resulting image."""
    jobs = []
    for view in SHEET_VIEWS:
        for expression in SHEET_EXPRESSIONS:
            for lighting in SHEET_LIGHTINGS:
                instruction = (
                    f"same person, {view}, {expression}, {lighting}, "
                    "plain grey background, preserve all facial features"
                )
                caption = (
                    f"{source.trigger_token}, {view}, {expression}, {lighting}, "
                    "plain grey background"
                )
                slug = (
                    f"{view}_{expression}_{lighting}".replace(" ", "-").replace("/", "")
                )
                jobs.append(
                    {"slug": slug, "view": view, "expression": expression,
                     "lighting": lighting, "instruction": instruction, "caption": caption}
                )
    return jobs


# --- Voice ------------------------------------------------------------------

def voice_prompt(source: CharacterSource, text: str, emotion: str = "neutral", pace: str = "normal") -> dict:
    """Build a Chatterbox/Higgs synthesis request dict."""
    return {
        "text": text,
        "emotion": emotion,
        "pace": pace,
        "reference_clip": source.voice.reference_clip,
        "character_id": source.character_id,
        "notes": source.voice.notes,
    }
