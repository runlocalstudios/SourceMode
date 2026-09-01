"""Chatterbox TTS wrapper (MIT-licensed; optional extra `voice`).

Voice mirrors the face architecture: a character's canonical
`source.voice.reference_clip` is the audio equivalent of `reference_images`,
and Chatterbox clones from it zero-shot.

When a character has NO reference clip yet, Chatterbox's built-in voice is
used instead (verified in the installed tts.py: `generate(audio_prompt_path=
None)` falls back to the checkpoint's `conds.pt`). That is the bootstrap path
— generate with the built-in voice, pick a take, freeze it as the character's
reference clip — and it keeps the voice fully synthetic, with no third-party
likeness in the chain.

Device is auto-detected: the engine venv ships a CPU torch, so `device="cuda"`
would hard-fail here even though ComfyUI's own venv has a CUDA build.
"""

from __future__ import annotations

from pathlib import Path

from ..prompts.templates import voice_prompt
from ..source import CharacterSource

# Chatterbox knobs (names + defaults read from the installed chatterbox/tts.py).
# exaggeration drives emotional intensity; cfg_weight trades pacing against
# adherence — its docs note ~0.3 slows delivery for fast reference speakers.
DEFAULT_EXAGGERATION = 0.5
DEFAULT_CFG_WEIGHT = 0.5
EXAGGERATION_BY_EMOTION = {
    "neutral": 0.5, "calm": 0.35, "sad": 0.4, "tired": 0.35,
    "warm": 0.5, "curious": 0.55, "worried": 0.6, "tense": 0.65,
    "excited": 0.75, "angry": 0.8, "afraid": 0.75,
}
CFG_BY_PACE = {"slow": 0.3, "normal": 0.5, "fast": 0.7}


def build_request(source: CharacterSource, text: str, *, emotion: str = "neutral", pace: str = "normal") -> dict:
    return voice_prompt(source, text, emotion=emotion, pace=pace)


def chatterbox_available() -> bool:
    try:
        import chatterbox  # noqa: F401, PLC0415

        return True
    except Exception:
        return False


def pick_device(preferred: str | None = None) -> str:
    """cuda when this venv's torch actually has it, else cpu."""
    if preferred:
        return preferred
    try:
        import torch  # noqa: PLC0415

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def synthesize(
    source: CharacterSource,
    text: str,
    out_path: Path,
    characters_root: Path,
    *,
    emotion: str = "neutral",
    pace: str = "normal",
    dry_run: bool = False,
    device: str | None = None,
    exaggeration: float | None = None,
    cfg_weight: float | None = None,
    seed: int | None = None,
    log=print,
) -> dict:
    request = build_request(source, text, emotion=emotion, pace=pace)
    exaggeration = EXAGGERATION_BY_EMOTION.get(emotion, DEFAULT_EXAGGERATION) if exaggeration is None else exaggeration
    cfg_weight = CFG_BY_PACE.get(pace, DEFAULT_CFG_WEIGHT) if cfg_weight is None else cfg_weight
    reference = None
    if source.voice.reference_clip is not None:
        reference = characters_root / source.character_id / source.voice.reference_clip
        if not reference.exists():
            raise FileNotFoundError(f"{source.character_id} voice.reference_clip not found: {reference}")

    settings = {
        "exaggeration": exaggeration,
        "cfg_weight": cfg_weight,
        "reference_clip": str(reference) if reference else None,
        "builtin_voice": reference is None,
        "seed": seed,
    }
    if dry_run:
        log(f"[dry-run] chatterbox: {request} settings={settings}")
        return {"request": request, "settings": settings, "synthesized": False}

    if not chatterbox_available():
        raise RuntimeError("chatterbox not installed — uv sync --extra voice (or use --dry-run)")

    import torch  # noqa: PLC0415
    import torchaudio  # noqa: PLC0415
    from chatterbox.tts import ChatterboxTTS  # noqa: PLC0415

    device = pick_device(device)
    settings["device"] = device
    if seed is not None:
        torch.manual_seed(seed)
    if reference is None:
        log(f"[voice] {source.character_id} has no reference_clip — using Chatterbox's built-in voice (bootstrap)")
    log(f"[voice] loading Chatterbox on {device}")

    model = ChatterboxTTS.from_pretrained(device=device)
    wav = model.generate(
        text,
        audio_prompt_path=str(reference) if reference else None,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(out_path), wav, model.sr)
    duration_s = round(wav.shape[-1] / model.sr, 2)
    return {
        "request": request,
        "settings": settings,
        "synthesized": True,
        "path": str(out_path),
        "sample_rate": model.sr,
        "duration_s": duration_s,
    }
