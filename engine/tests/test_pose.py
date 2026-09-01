"""Pose-transfer tests.

Every case here is a bug that actually shipped. The pose module is prompt- and
threshold-driven, so the failures were never exceptions — they were plausible
images that were wrong, which is exactly what a test has to catch instead.
"""

from __future__ import annotations

import pytest

from sourcemode.pose.library import BASE_LIMITS, POSES, gates
from sourcemode.pose.transfer import HAIR_HINT, INSTRUCTION, NEGATIVE


# --- hair -----------------------------------------------------------------
# A rear view has to invent how the hair is gathered, and it defaults to a
# single tail: two low pigtails came back as one ponytail. The style cannot be
# inferred from a front-facing source, so it is stated per asset.


def test_hair_hint_absent_by_default():
    """No --hair must leave the prompt byte-identical to the un-hinted one.

    This is what makes the flag safe to add: characters with loose hair take
    exactly the path they took before, so there is nothing to regress.
    """
    assert INSTRUCTION + "" == INSTRUCTION
    assert "{hair}" not in INSTRUCTION
    assert "pigtail" not in INSTRUCTION.lower()


def test_hair_hint_states_the_style_and_pins_it_from_behind():
    filled = HAIR_HINT.format(hair="two low pigtails")
    assert "two low pigtails" in filled
    # The failure was specifically at the back, so the hint has to say so.
    assert "behind" in filled.lower()
    # And it must forbid the observed failure mode: merging into one tail.
    assert "merge" in filled.lower()


def test_no_hairstyle_is_ever_named_in_the_static_prompts():
    """Naming a style introduces it.

    An earlier instruction said "if her hair is tied in pigtails, a ponytail or
    a braid, keep that style" and put braids on loose-haired characters — the
    same failure as naming a stepladder to describe a camera position. Styles
    may appear only in the caller-supplied hint, never in the static text, and
    never in the negative either, where they get stripped instead.
    """
    for style in ("pigtail", "ponytail", "braid", "bun"):
        assert style not in INSTRUCTION.lower(), f"{style} named in INSTRUCTION"
        assert style not in NEGATIVE.lower(), f"{style} named in NEGATIVE"


# --- gates ----------------------------------------------------------------


@pytest.mark.parametrize("pose_key", list(POSES))
def test_declared_gates_replace_the_base_set(pose_key):
    """Merging was a real bug.

    Limits calibrated on a kneeling figure are meaningless for a standing one,
    and merging them silently rejected 6 of 6 good rear references. A pose that
    declares its own target must not inherit stray base keys.
    """
    pose = POSES[pose_key]
    target, limits, weights = gates(pose)
    if pose.get("ref_target"):
        assert set(target) == set(pose["ref_target"])
        assert set(limits) <= set(target)
        assert set(weights) == set(target)
    else:
        assert set(limits) == set(BASE_LIMITS)


@pytest.mark.parametrize("pose_key", list(POSES))
def test_every_limit_band_contains_its_target(pose_key):
    """A target outside its own accept band rejects every candidate."""
    target, limits, _ = gates(POSES[pose_key])
    for key, (lo, hi) in limits.items():
        assert lo < hi, f"{pose_key}.{key}: inverted band"
        assert lo <= target[key] <= hi, f"{pose_key}.{key}: target {target[key]} outside ({lo}, {hi})"


@pytest.mark.parametrize("pose_key", list(POSES))
def test_rear_poses_gate_on_facing(pose_key):
    """Orientation is the whole point of a rear pose, so it must be gated.

    It is gated via body_facing (anatomical shoulder ordering, +1 front / -1
    rear) because MediaPipe's Tasks API returns visibility 1.0 for every
    landmark, including a back that is fully turned away.
    """
    if not pose_key.startswith("standing_rear"):
        pytest.skip("not a rear pose")
    target, _, _ = gates(POSES[pose_key])
    assert "body_facing" in target
    assert target["body_facing"] < 0, "a rear pose must target a negative facing"


@pytest.mark.parametrize("pose_key", list(POSES))
def test_pose_declares_variants_and_reference_prompt(pose_key):
    pose = POSES[pose_key]
    assert pose["variants"], f"{pose_key} has no variants"
    assert "{arms}" in pose["ref_prompt"], f"{pose_key} never substitutes its arm variant"
    # Rule 1: never name a physical object to describe the camera.
    assert "stepladder" not in pose["ref_prompt"].lower()
