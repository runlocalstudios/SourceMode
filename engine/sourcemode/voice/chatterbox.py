"""Chatterbox TTS wrapper (MIT-licensed; optional extra `voice`).

The canonical reference clip comes from source.voice.reference_clip. Chatterbox
is imported lazily; without it (or with --dry-run) only the request is built.
"""

from __future__ import annotations

from pathlib import Path

from ..prompts.templates import voice_prompt
from ..source import CharacterSource


def build_request(source: CharacterSource, text: str, *, emotion: str = "neutral", pace: str = "normal") -> dict:
    return voice_prompt(source, text, emotion=emotion, pace=pace)


def chatterbox_available() -> bool:
    try:
        import chatterbox  # noqa: F401, PLC0415

        return True
    except Exception:
        return False


def synthesize(
    source: CharacterSource,
    text: str,
    out_path: Path,
    characters_root: Path,
    *,
    emotion: str = "neutral",
    pace: str = "normal",
    dry_run: bool = False,
    log=print,
) -> dict:
    request = build_request(source, text, emotion=emotion, pace=pace)
    if dry_run:
        log(f"[dry-run] chatterbox request: {request}")
        return {"request": request, "synthesized": False}
    if not chatterbox_available():
        raise RuntimeError("chatterbox not installed — uv sync --extra voice (or use --dry-run)")
    if source.voice.reference_clip is None:
        raise RuntimeError(f"{source.character_id} has no voice.reference_clip in its CharacterSource")

    from chatterbox.tts import ChatterboxTTS  # noqa: PLC0415
    import torchaudio  # noqa: PLC0415

    model = ChatterboxTTS.from_pretrained(device="cuda")
    ref = characters_root / source.character_id / source.voice.reference_clip
    wav = model.generate(text, audio_prompt_path=str(ref))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(out_path), wav, model.sr)
    return {"request": request, "synthesized": True, "path": str(out_path)}
