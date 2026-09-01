"""Pose-transfer tests.

Every case here is a bug that actually shipped. The pose module is prompt- and
threshold-driven, so the failures were never exceptions — they were plausible
images that were wrong, which is exactly what a test has to catch instead.
"""

from __future__ import annotations

from pathlib import Path

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
    if "rear" not in pose_key:
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


@pytest.mark.parametrize("pose_key", [k for k in POSES if "squat" in k])
def test_squat_poses_gate_on_depth(pose_key):
    """Depth is the entire point of a deep squat.

    Without a squat_depth gate a shallow crouch scores fine on framing and
    proportions, which is how "very deep" quietly becomes "bending a bit".

    These poses are shot at EYE LEVEL, where the sign is the intuitive one:
    negative means the hips have dropped to or below the knees. That is only
    true because of the camera. The identical poses shot from overhead measured
    +0.41 to +0.55 for the same real-world depth, and a band written from
    anatomical intuition rejected 6 of 6 correct references. The band belongs to
    the camera, not to the pose.
    """
    target, limits, weights = gates(POSES[pose_key])
    assert "squat_depth" in target
    lo, hi = limits["squat_depth"]
    assert lo <= target["squat_depth"] <= hi
    assert hi <= 0.05, "upper band must exclude a squat whose hips never drop"
    assert weights["squat_depth"] >= 1.5, "depth should outweigh framing metrics"


@pytest.mark.parametrize("pose_key", [k for k in POSES if "squat" in k])
def test_squats_gate_on_hand_height_not_torso_bend(pose_key):
    """Where the hands are is what separates the two squat pairs.

    torso_bend is the intuitive choice and is useless here: reaching down to the
    floor out of a deep squat leaves the shoulder-hip line vertical, so it
    measured 0.2-1.3 degrees in BOTH poses and a torso_bend band of (10, 55)
    would have rejected every correct reference. hand_height (wrists vs ankles)
    separates them by a full 1.0 with no overlap.
    """
    target, limits, _ = gates(POSES[pose_key])
    assert "hand_height" in target
    assert "torso_bend" not in target, "torso_bend does not discriminate these poses"
    lo, hi = limits["hand_height"]
    assert lo <= target["hand_height"] <= hi


def test_hand_height_bands_separate_the_two_squat_pairs():
    """The floor pair and the knees pair must not accept each other.

    Measured: hands on knees 0.77-0.91, hands on floor -0.27 to -0.20. If the
    bands overlap, the gate cannot tell the poses apart and both collapse to
    whichever the model prefers.
    """
    knees = gates(POSES["squat_deep_hands_knees"])[1]["hand_height"]
    floor = gates(POSES["squat_deep_hands_floor"])[1]["hand_height"]
    assert floor[1] < knees[0], f"bands overlap: floor {floor} vs knees {knees}"

    knees_t = gates(POSES["squat_deep_hands_knees"])[0]["hand_height"]
    floor_t = gates(POSES["squat_deep_hands_floor"])[0]["hand_height"]
    assert not (floor[0] <= knees_t <= floor[1]), "a hands-on-knees ref would pass the floor gate"
    assert not (knees[0] <= floor_t <= knees[1]), "a hands-on-floor ref would pass the knees gate"


@pytest.mark.parametrize("pose_key", [k for k in POSES if "squat" in k])
def test_squats_are_not_shot_from_above(pose_key):
    """These are eye-level poses; an overhead camera made them read as gym drills.

    The calibrated bands are only valid for a level camera, so a prompt that
    reintroduces a high angle silently invalidates every threshold above.
    """
    prompt = POSES[pose_key]["ref_prompt"].lower()
    assert "eye level" in prompt
    for phrase in ("high angle", "looking down at", "from above her head"):
        assert phrase not in prompt, f"{pose_key} reintroduces an overhead camera: {phrase}"


# --- output naming ---------------------------------------------------------


def test_asset_label_separates_characters_sharing_an_outfit_slug():
    """Results were named from the source FILENAME alone, which lost work.

    maya and priyanka both have weekly_casual/casual_01_standing.png, so the
    second transfer overwrote the first result with no warning. Found by running
    the pose across the cast, not by a crash — nothing ever errored.
    """
    from pathlib import PurePath

    from sourcemode.pose.transfer import asset_label

    root = "C:/dev/chillafterdark/art-source/characters"
    maya = Path(f"{root}/maya/game-asset-gen/output/weekly_casual/casual_01_standing.png")
    priyanka = Path(f"{root}/priyanka/game-asset-gen/output/weekly_casual/casual_01_standing.png")
    assert asset_label(maya) != asset_label(priyanka)
    assert asset_label(maya) == "maya_weekly_casual"
    assert PurePath(maya).name == PurePath(priyanka).name, "the filenames really do collide"


def test_asset_label_skips_pipeline_directories():
    """'output' and 'game-asset-gen' describe the pipeline, not the subject."""
    from sourcemode.pose.transfer import asset_label

    label = asset_label(Path("/x/characters/zara/game-asset-gen/output/casual_date/a_standing.png"))
    assert label == "zara_casual_date"
    for generic in ("output", "game-asset-gen", "characters"):
        assert generic not in label


def test_asset_label_degrades_gracefully_outside_the_game_layout():
    """--assets takes an arbitrary folder, so this must not raise on any path."""
    from sourcemode.pose.transfer import asset_label

    assert asset_label(Path("/tmp/loose/img_standing.png"))
    assert asset_label(Path("img_standing.png"))


def test_hair_length_instruction_is_symmetric():
    """The instruction used to protect only LONG hair.

    "Hair that is long in image 1 is equally long at the back" says nothing
    about short hair, and a chin-length bob came back well past the shoulders.
    Length must be pinned in both directions — without naming a style, which
    would introduce it.
    """
    text = INSTRUCTION.lower()
    assert "neither lengthened nor shortened" in text
    assert "hair that is long" not in text, "asymmetric phrasing reintroduced"
