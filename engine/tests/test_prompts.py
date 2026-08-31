import pytest
from pydantic import ValidationError

from sourcemode.prompts import (
    CameraContradictionError,
    ShotSpec,
    keyframe_prompt,
    sheet_edit_prompts,
    video_prompt,
    voice_prompt,
)
from sourcemode.prompts.templates import SHEET_EXPRESSIONS, SHEET_LIGHTINGS, SHEET_VIEWS, validate_camera


def spec(**overrides) -> ShotSpec:
    base = dict(
        idx=0, shot_size="MS", lens=35, camera_move="tracking",
        motion="walks through the market, glancing at stalls", speed="slowly",
        emotion="worried", environment="a rainy neon market at night",
        lighting="neon signs reflecting off wet pavement", grade="teal-orange cinematic grade",
        duration_s=6.0,
    )
    base.update(overrides)
    return ShotSpec(**base)


def test_keyframe_never_contains_invariants(sample_source):
    prompt = keyframe_prompt(sample_source, spec())
    for invariant in sample_source.invariants:
        # neither the full invariant line nor its descriptive tail may leak
        assert invariant not in prompt
        tail = invariant.split(":", 1)[1].strip()
        assert tail not in prompt
    assert sample_source.trigger_token in prompt
    assert "35mm" in prompt


def test_keyframe_wardrobe_suffix(sample_source):
    prompt = keyframe_prompt(sample_source, spec(wardrobe_state="armor"))
    assert "testchar_tk wearing scuffed armor" in prompt


def test_video_prompt_block_order_and_length(sample_source):
    prompt = video_prompt(sample_source, spec())
    words = prompt.split()
    assert 60 <= len(words) <= 140, f"got {len(words)} words"
    # ordered blocks: motion before camera before environment before grade
    motion_pos = prompt.index("walks through the market")
    camera_pos = prompt.index("tracking")
    env_pos = prompt.index("Setting:")
    grade_pos = prompt.index("Teal-orange")
    assert motion_pos < camera_pos < env_pos < grade_pos
    assert "slowly" in prompt  # explicit speed word


def test_video_prompt_strips_leading_subject(sample_source):
    # brief motion text names the character or uses a pronoun; the template
    # frame already says "the character"
    p1 = video_prompt(sample_source, spec(motion="Test Char walks through the market"))
    assert "the character walks through the market" in p1
    p2 = video_prompt(sample_source, spec(motion="she looks up from her phone and smiles"))
    assert "the character looks up from her phone" in p2
    assert "character she" not in p2


def test_video_prompt_static_camera_has_no_pace_clause(sample_source):
    p = video_prompt(sample_source, spec(camera_move="static", motion="stands quietly"))
    assert "completely still, holding" in p  # no ", moving steadily" contradiction


def test_video_prompt_rejects_contradictory_camera():
    s = spec(camera_move="static", motion="stands still as the camera pans across her shoulders")
    with pytest.raises(CameraContradictionError):
        validate_camera(s)


def test_video_prompt_static_is_fine():
    s = spec(camera_move="static", motion="stands still, breathing slowly")
    validate_camera(s)  # no raise


def test_duration_capped_at_8():
    with pytest.raises(ValidationError):
        spec(duration_s=9.0)


def test_shot_size_and_speed_enums():
    with pytest.raises(ValidationError):
        spec(shot_size="XXL")
    with pytest.raises(ValidationError):
        spec(speed="warp")


def test_sheet_edit_prompts_grid(sample_source):
    jobs = sheet_edit_prompts(sample_source)
    assert len(jobs) == len(SHEET_VIEWS) * len(SHEET_EXPRESSIONS) * len(SHEET_LIGHTINGS) == 36
    slugs = {j["slug"] for j in jobs}
    assert len(slugs) == 36  # unique
    for job in jobs:
        assert job["instruction"].startswith("same person, ")
        assert job["instruction"].endswith("preserve all facial features")
        assert "plain grey background" in job["instruction"]
        assert job["caption"].startswith(sample_source.trigger_token + ", ")
        assert "plain grey background" in job["caption"]


def test_voice_prompt(sample_source):
    req = voice_prompt(sample_source, "Hello there", emotion="calm", pace="slow")
    assert req == {
        "text": "Hello there",
        "emotion": "calm",
        "pace": "slow",
        "reference_clip": None,
        "character_id": "testchar",
        "notes": "",
    }
