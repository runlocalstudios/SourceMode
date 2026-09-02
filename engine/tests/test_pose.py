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


# --- footwear --------------------------------------------------------------
# Assets are cropped for the game UI, so feet are usually missing or half-cut.
# The model then copies whatever the reference did: barefoot references produced
# barefoot results, and zara's half-visible boots became detached brown blobs
# once the pose swung her feet behind her.


def test_footwear_is_deterministic_per_outfit():
    """Consistency is the whole point.

    An outfit that wears different shoes in different poses is worse than one
    wearing the wrong shoes, so the choice is a plain mapping, not a model call
    and not a random pick.
    """
    from sourcemode.pose.transfer import footwear_for

    a = Path("/c/zara/game-asset-gen/output/casual_date/casual_date_01_standing.png")
    b = Path("/c/zara/game-asset-gen/output/casual_date/casual_date_07_standing.png")
    c = Path("/c/bianca/game-asset-gen/output/casual_date/casual_date_01_standing.png")
    assert footwear_for(a) == footwear_for(b) == footwear_for(c)


def test_workout_is_not_swallowed_by_work():
    """'work' is a substring of 'workout' — trainers must not become court shoes."""
    from sourcemode.pose.transfer import footwear_for

    workout = footwear_for(Path("/c/x/output/workout/a_standing.png"))
    work = footwear_for(Path("/c/x/output/work/a_standing.png"))
    assert workout != work
    assert "trainer" in workout or "sneaker" in workout
    assert "heel" in work


def test_every_outfit_maps_into_the_agreed_vocabulary():
    """Sneakers, slippers, platforms, heels, flats — and never boots by default.

    Boots are only ever correct when the source already shows them, and that
    case is handled by the "keep what is visible" clause instead.
    """
    from sourcemode.pose.transfer import FOOTWEAR, FOOTWEAR_DEFAULT, FOOTWEAR_VOCAB

    for outfit, shoes in {**FOOTWEAR, "_default": FOOTWEAR_DEFAULT}.items():
        assert any(v in shoes.lower() for v in FOOTWEAR_VOCAB), f"{outfit}: {shoes!r} off-vocabulary"
        assert "boot" not in shoes.lower(), f"{outfit}: boots must never be the default"


def test_footwear_hint_keeps_visible_shoes_before_choosing_any():
    """Order matters: anything genuinely visible must win over the chosen pair.

    zara wears knee-high boots that the asset crops mid-calf; telling her to put
    on platforms would override real information the source does show.
    """
    from sourcemode.pose.transfer import FOOTWEAR_HINT

    filled = FOOTWEAR_HINT.format(shoes="black platform shoes")
    keep = filled.lower().index("kept exactly as it is")
    choose = filled.lower().index("black platform shoes")
    assert keep < choose, "the chosen pair is stated before the preservation clause"
    assert "only where" in filled.lower()


def test_footwear_hint_absent_by_default_in_the_static_instruction():
    """--no-shoes must leave the prompt exactly as it was before this feature."""
    assert "shoe" not in INSTRUCTION.lower()
    assert "{shoes}" not in INSTRUCTION


# --- refine pass -----------------------------------------------------------


def test_refine_workflow_never_loads_anypose():
    """AnyPose exists to MOVE a pose, which is what the refine pass must not do.

    The refine pass runs qwen_image_edit_ref, not the AnyPose graph: image1 is
    the posed result (pinning pose, body and wardrobe) and image2 is the source
    (supplying face and hair). If AnyPose leaked in it would re-pose the result
    against its own reference.
    """
    from sourcemode.config import load_config
    from sourcemode.pose.transfer import ANYPOSE_BASE, ANYPOSE_HELPER, build_refine_workflow

    nodes = build_refine_workflow(load_config(), "posed.png", "source.png", 1, "t/")
    loras = {n["inputs"].get("lora_name") for n in nodes.values()
             if n["class_type"] == "LoraLoaderModelOnly"}
    assert ANYPOSE_BASE not in loras and ANYPOSE_HELPER not in loras
    assert any(n["class_type"] == "LoadImage" for n in nodes.values())


def test_refine_instruction_names_no_hairstyle():
    """The reference image carries the style; naming one introduces it."""
    from sourcemode.pose.transfer import REFINE_INSTRUCTION, REFINE_NEGATIVE

    for style in ("pigtail", "ponytail", "braid", "bun", "updo"):
        assert style not in REFINE_INSTRUCTION.lower(), f"{style} named in REFINE_INSTRUCTION"
        assert style not in REFINE_NEGATIVE.lower(), f"{style} named in REFINE_NEGATIVE"


def test_refine_instruction_pins_the_body_and_only_edits_the_head():
    from sourcemode.pose.transfer import REFINE_INSTRUCTION

    low = REFINE_INSTRUCTION.lower()
    assert "same pose" in low and "only her head" in low
    assert "do not move her" in low


def test_refine_declines_without_insightface(monkeypatch, tmp_path):
    """No scorer means no way to tell better from worse, so it must not guess.

    A second pass that cannot be evaluated is not free — it would ship whatever
    the model produced. Returning the first-pass image is the correct answer.
    """
    import sourcemode.gates.identity as ident
    from sourcemode.pose.transfer import refine_head

    monkeypatch.setattr(ident, "insightface_available", lambda: False)
    posed = tmp_path / "posed.png"
    posed.write_bytes(b"x")
    best, note = refine_head(None, None, posed, tmp_path / "s.png", tmp_path / "a.png",
                             tmp_path, "model.task", log=lambda *a: None)
    assert best == posed
    assert "skipped" in note


def test_refine_pose_tolerance_is_tight():
    """A refine that fixes the face but straightens the pose is a regression."""
    from sourcemode.pose.transfer import REFINE_MIN_GAIN, REFINE_POSE_TOLERANCE

    assert 0 < REFINE_POSE_TOLERANCE <= 0.1
    assert REFINE_MIN_GAIN > 0, "must require a real gain, not a tie, to replace the first pass"


# --- face identity ---------------------------------------------------------
# The pose reference is a photograph of a DIFFERENT woman, handed to the model
# as image2 on every render, so her identity competes with the character's.
# Masking her face is worth ~+0.07 face similarity on both characters tested.


def test_identity_points_exclude_the_ears():
    """Ears carry head ANGLE, not identity.

    The prompt asks the model to copy the reference's head tilt and gaze, and
    those cues live in the head outline. Masking the ears too would remove the
    identity and take the head angle with it.
    """
    from sourcemode.pose.face import EARS, IDENTITY_POINTS

    assert not set(EARS) & set(IDENTITY_POINTS)
    for i in EARS:
        assert i not in IDENTITY_POINTS


def test_face_box_returns_none_when_no_person(tmp_path):
    """A reference that cannot be measured is still a usable reference."""
    from PIL import Image

    from sourcemode.pose.face import face_box

    p = tmp_path / "flat.png"
    Image.new("RGB", (256, 256), (128, 128, 128)).save(p)
    assert face_box(p, "models/pose_landmarker_heavy.task") is None


def test_mask_reference_face_still_writes_when_no_face(tmp_path):
    """Never drop the reference just because no face was found.

    Returning False must still leave a usable file at dest, otherwise the
    transfer would upload nothing and fail far from the cause.
    """
    from PIL import Image

    from sourcemode.pose.face import mask_reference_face

    src, dest = tmp_path / "s.png", tmp_path / "d.png"
    Image.new("RGB", (256, 256), (128, 128, 128)).save(src)
    assert mask_reference_face(src, dest, "models/pose_landmarker_heavy.task") is False
    assert dest.exists()
    assert Image.open(dest).size == (256, 256)


def test_paste_face_preserves_canvas_and_changes_only_the_box(tmp_path):
    """Compositing must not move or resize the image it is patching."""
    from PIL import Image

    from sourcemode.pose.face import paste_face

    base = tmp_path / "base.png"
    Image.new("RGB", (400, 600), (10, 200, 10)).save(base)
    patch = Image.new("RGB", (128, 128), (200, 10, 10))
    out = tmp_path / "out.png"
    paste_face(base, patch, (100, 100, 228, 228), out, feather=12)

    res = Image.open(out).convert("RGB")
    assert res.size == (400, 600)
    assert res.getpixel((10, 10)) == (10, 200, 10), "outside the box must be untouched"
    r, g, _ = res.getpixel((164, 164))
    assert r > g, "centre of the box should be the patch"


def test_face_module_uses_no_insightface():
    """Identity generation must stay commercially clean.

    InstantID, PuLID and IP-Adapter FaceID are all built on InsightFace, whose
    weights are non-commercial, and this output ships in the game. InsightFace
    is allowed only for scoring candidates in QC tooling.
    """
    import ast
    from pathlib import Path as P

    # Parse imports rather than grep the text: the module docstring names these
    # deliberately, to record WHY they are not used.
    src = P(__file__).parent.parent / "sourcemode" / "pose" / "face.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for banned in ("insightface", "instantid", "pulid", "ip_adapter", "ipadapter"):
        assert banned not in {m.lower() for m in imported}, \
            f"{banned} must not be used to generate pixels"
