"""The natural-register asset prompt: the caption's words, the caption's order,
the same facts as the contract prompt, no instructions.

Jeremy, 2026-10-09: "if you're being overly wordy or writing with AI slop, it's
a possibility that the issue is in the actual prompt itself".
"""

import re

import pytest

from sourcemode.assets import render as R

LOOKS = [
    {"id": "casual_01", "look": 1, "category": "casual", "pose": "standing",
     "outfit": "a soft oatmeal knit sweater and straight-leg jeans", "hair": "her hair worn loose"},
    {"id": "workout_02", "look": 2, "category": "workout", "pose": "standing",
     "outfit": "a sage green workout tank, dark joggers and white sneakers", "hair": "her hair up in a messy bun"},
    {"id": "work_01", "look": 3, "category": "work", "pose": "standing",
     "outfit": "a cream blouse tucked into a navy A-line skirt", "hair": "her hair in a low ponytail"},
]


@pytest.fixture
def zara(monkeypatch):
    monkeypatch.setattr(R, "appearance_clause",
                        lambda c, age=True: "a young woman with a petite figure, fair skin, very long dark brown hair and brown eyes")


def test_natural_is_short_and_in_the_captions_register(zara):
    for look in LOOKS:
        p = R.natural_prompt("zara", look, backdrop="soft window daylight, in a sunlit kitchen")
        assert p.startswith("zara, a young woman with")
        assert len(p.split()) < 90, p
        assert "image-left" not in p and "ALWAYS" not in p and ":" not in p.split(".")[0]
        assert "wearing " in p and "in a sunlit kitchen" in p and "beautiful, natural makeup" in p
        assert "Photorealistic, natural skin texture, sharp focus." in p


def test_natural_carries_the_same_turn_gaze_and_expression_as_the_contract(zara):
    for look in LOOKS:
        asked = R.pose_fields("zara", look)["asked"]
        p = R.natural_prompt("zara", look)
        body = p.split(", she looks directly at the camera")[0]
        if asked["body_side"] == "front":
            assert "her body faces the camera" in body
        elif asked["slight"]:
            assert "her body is just slightly angled" in body
        else:
            assert "her body turned about 45 degrees toward her " in body
        if asked["arms"]:
            assert f" with {asked['arms']}, " in p
        assert R._NATURAL_EXPRESSION[asked["expression"]] in p
    # a named turn still picks its family; the 45 never says "three-quarter view"
    her_right = R.natural_prompt("zara", {**LOOKS[0], "turn": "left"})
    assert "her body turned about 45 degrees toward her right, her face turned to the camera" in her_right
    assert "three-quarter" not in her_right


def test_a_pack_rotates_front_slight_45_and_relaxed_with_random_arms(zara):
    """Jeremy, 2026-10-23: "TOO static now and TOO front facing ... 1/4 front
    facing, 1/4 body at a slight angle, 1/4 body at a 45 degree angle, 1/4 in a
    relaxed pose with (arms in her pockets / arms crossed / arms behind her
    back) - randomize the arm position"."""
    fams, arms, sides = [], [], set()
    for look in range(1, 29):
        outfit = "a navy tee and dark jeans" if look % 2 else "a red slip dress"
        # the plan's own look numbers restart per category; `n` is the place in the plan
        asked = R.pose_fields("zara", {"id": f"casual_{look:02d}", "look": (look - 1) % 7 + 1, "n": look,
                                       "category": "casual", "pose": "standing", "outfit": outfit,
                                       "hair": "y"})["asked"]
        assert asked["crop"] == "upper-thigh-up"
        if asked["arms"]:
            fams.append("relaxed"); arms.append(asked["arms"])
            assert abs(asked["body_deg"]) <= 15
            if "pockets" in asked["arms"]:
                assert "jeans" in outfit          # no pockets on a slip dress
        elif asked["body_side"] == "front":
            fams.append("front")
        elif asked["slight"]:
            fams.append("slight"); sides.add(asked["body_side"])
            assert 10 <= abs(asked["body_deg"]) <= 15
        else:
            fams.append("quarter"); sides.add(asked["body_side"])
            assert 40 <= abs(asked["body_deg"]) <= 45 and asked["head_side"] == asked["body_side"]
    assert all(fams.count(f) == 7 for f in ("front", "slight", "quarter", "relaxed")), fams
    assert len(set(arms)) >= 2 and sides == {"image-left", "image-right"}
    for look in LOOKS:
        p = R.natural_prompt("zara", look)
        assert "three-quarter" not in p and "a standing portrait picture from the upper thigh up, " in p


def test_a_selfie_or_shoot_slot_keeps_the_front_slight_body_and_never_gets_arms(zara):
    """The 45 and the relaxed arms are the pack's. An arm's-length selfie with
    "her hands in her pockets" holds no phone."""
    for look in range(1, 25):
        slot = {"id": f"selfie_{look:02d}", "look": look, "n": look, "category": "selfie_casual",
                "pose": "standing", "outfit": "a tee and jeans", "hair": "y",
                "shot_type": "phone selfie", "framing": "her head and chest fill the frame"}
        asked = R.pose_fields("zara", slot)["asked"]
        assert asked["arms"] is None and abs(asked["body_deg"]) <= 15
        p = R.natural_prompt("zara", slot, backdrop="in her bedroom")
        assert "45 degrees" not in p and " with her " not in p.split(", she looks directly")[0]


def test_the_sweep_scenes_keep_their_mid_thigh_sentence():
    """The pack moved to the upper thigh on 2026-10-23; a sweep rate is compared
    only with another sweep, so his 2026-10-19 sentence stays as written."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "asset_scenes", Path(__file__).resolve().parents[1] / "scripts" / "eval" / "asset_scenes.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert "portrait picture of a woman from the mid-thigh up, her body faces the camera" in \
        m.sweep_prompt("lena", m.LOOKS[0], "nobody_without_a_record")


def test_natural_keeps_the_hair_and_footwear_rules(zara):
    bun = R.natural_prompt("zara", LOOKS[1])
    assert "very long" not in bun and "dark brown hair" in bun          # length out when the hair is up
    assert "sneakers" not in bun                                         # no footwear under a thigh-up crop
    loose = R.natural_prompt("zara", LOOKS[0])
    assert "very long dark brown hair" in loose


def test_shot_prompt_defaults_to_natural_and_switches_to_the_contract_on_module_state(zara, monkeypatch):
    # 2026-10-09: natural is the default - cassie ep18 12/20 against 5/10, "we've solved our problems"
    natural = R.shot_prompt("zara", LOOKS[0])
    assert natural == R.natural_prompt("zara", LOOKS[0])
    assert len(natural) < 600
    # the eval's slot mapping (asset_scenes) goes through shot_prompt, so one flag flips every scene
    assert re.match(r"^zara, a young woman", natural)
    monkeypatch.setattr(R, "PROMPT_STYLE", "contract")
    contract = R.shot_prompt("zara", LOOKS[0])
    assert "Crop:" in contract and len(contract) > 1200


def test_natural_honours_a_shoots_composition_overrides(zara):
    """A selfie or an influencer shot is not an upper-thigh standing portrait.
    The four overrides the contract honours ride along in the natural register."""
    slot = {**LOOKS[0], "shot_type": "phone selfie", "stance": "she is holding the phone above eye level",
            "framing": "her head and chest fill the frame", "avoid": "No studio lighting."}
    p = R.natural_prompt("zara", slot, backdrop="soft daylight, in her bedroom")
    assert "a phone selfie, her head and chest fill the frame, " in p
    assert "portrait picture" not in p and "upper thigh" not in p
    assert ", she is holding the phone above eye level, " in p
    assert p.endswith("sharp focus. No studio lighting.")
    # a pack slot, which sets none of them, gets the pack's own framing
    assert "a standing portrait picture from the upper thigh up, " in R.natural_prompt("zara", LOOKS[0])


def test_a_pack_camera_reaches_only_her_pack_prompt(monkeypatch):
    from sourcemode.assets import appearance as A
    monkeypatch.setattr(A, "pack_camera", lambda c: {"prompt": "the camera at her eye level"} if c == "zara" else {})
    slot = {"id": "casual_01", "look": 1, "category": "casual", "pose": "standing",
            "outfit": "a white tee and jeans", "hair": "her hair worn loose"}
    assert "from the upper thigh up, the camera at her eye level, " in R.natural_prompt("zara", slot)
    assert "eye level" not in R.natural_prompt("zara", {**slot, "framing_natural": "framed from the chest up"})


def test_an_unsaid_hair_clause_leaves_her_hair_out_of_the_prompt(monkeypatch):
    from sourcemode.assets import appearance as A
    monkeypatch.setattr(A, "hair_unsaid", lambda c: {"her hair worn loose"} if c == "zara" else set())
    slot = {"id": "casual_01", "look": 1, "category": "casual", "pose": "standing",
            "outfit": "a white tee and jeans", "hair": "her hair worn loose"}
    p = R.natural_prompt("zara", slot)
    assert "hair worn loose" not in p and ", wearing a white tee" in p and ", ," not in p
    assert "her hair worn loose, wearing" in R.natural_prompt("mia", slot)
    assert "high ponytail, wearing" in R.natural_prompt("zara", {**slot, "hair": "her hair in a high ponytail"})
