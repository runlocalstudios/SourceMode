import pytest

from sourcemode.voice.chatterbox import (
    CFG_BY_PACE,
    DEFAULT_CFG_WEIGHT,
    DEFAULT_EXAGGERATION,
    EXAGGERATION_BY_EMOTION,
    build_request,
    pick_device,
    synthesize,
)


def test_build_request_carries_character_and_text(sample_source):
    req = build_request(sample_source, "hello there", emotion="worried", pace="slow")
    assert req["text"] == "hello there"
    assert req["character_id"] == "testchar"
    assert req["emotion"] == "worried"
    assert req["pace"] == "slow"
    assert req["reference_clip"] is None


def test_dry_run_reports_settings_without_synthesizing(sample_source, tmp_path, chars_root):
    result = synthesize(
        sample_source, "a line", tmp_path / "out.wav", chars_root,
        emotion="excited", pace="slow", dry_run=True, log=lambda *_: None,
    )
    assert result["synthesized"] is False
    assert not (tmp_path / "out.wav").exists()
    s = result["settings"]
    assert s["exaggeration"] == EXAGGERATION_BY_EMOTION["excited"]
    assert s["cfg_weight"] == CFG_BY_PACE["slow"]
    # no reference clip on a fresh character -> chatterbox's built-in voice
    assert s["builtin_voice"] is True
    assert s["reference_clip"] is None


def test_unknown_emotion_and_pace_fall_back_to_defaults(sample_source, tmp_path, chars_root):
    result = synthesize(
        sample_source, "a line", tmp_path / "out.wav", chars_root,
        emotion="bewildered", pace="andante", dry_run=True, log=lambda *_: None,
    )
    assert result["settings"]["exaggeration"] == DEFAULT_EXAGGERATION
    assert result["settings"]["cfg_weight"] == DEFAULT_CFG_WEIGHT


def test_explicit_overrides_win(sample_source, tmp_path, chars_root):
    result = synthesize(
        sample_source, "a line", tmp_path / "out.wav", chars_root,
        emotion="angry", dry_run=True, exaggeration=0.1, cfg_weight=0.9, log=lambda *_: None,
    )
    assert result["settings"]["exaggeration"] == 0.1
    assert result["settings"]["cfg_weight"] == 0.9


def test_missing_reference_clip_file_fails_loudly(sample_source, tmp_path, chars_root):
    src = sample_source.model_copy(
        update={"voice": sample_source.voice.model_copy(update={"reference_clip": "voice/nope.wav"})}
    )
    with pytest.raises(FileNotFoundError) as err:
        synthesize(src, "a line", tmp_path / "out.wav", chars_root, dry_run=True, log=lambda *_: None)
    assert "nope.wav" in str(err.value)


def test_existing_reference_clip_is_used_over_builtin(sample_source, tmp_path, chars_root):
    clip = chars_root / sample_source.character_id / "voice" / "ref.wav"
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"RIFF")
    src = sample_source.model_copy(
        update={"voice": sample_source.voice.model_copy(update={"reference_clip": "voice/ref.wav"})}
    )
    result = synthesize(src, "a line", tmp_path / "out.wav", chars_root, dry_run=True, log=lambda *_: None)
    assert result["settings"]["builtin_voice"] is False
    assert result["settings"]["reference_clip"].endswith("ref.wav")


def test_pick_device_prefers_explicit_and_never_raises():
    assert pick_device("cpu") == "cpu"
    assert pick_device("cuda") == "cuda"
    # auto-detect must return something usable even on a CPU-only torch
    assert pick_device() in ("cuda", "cpu")
