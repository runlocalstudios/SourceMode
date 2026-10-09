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
                        lambda c: "a young woman with a petite figure, fair skin, very long dark brown hair and brown eyes")
    monkeypatch.setattr(R, "fitted_clause", lambda c: ", fitted to her tiny frame")


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
        if asked["body_side"] == "front":
            assert "facing the camera" in p and "looking straight into the camera" in p
        else:
            her = "her right" if asked["body_side"] == "image-left" else "her left"
            assert f"in a three-quarter view toward {her}" in p
            assert f"her face turned slightly toward {her}, looking into the camera" in p
        assert R._NATURAL_EXPRESSION[asked["expression"]] in p


def test_natural_keeps_the_hair_and_footwear_rules(zara):
    bun = R.natural_prompt("zara", LOOKS[1])
    assert "very long" not in bun and "dark brown hair" in bun          # length out when the hair is up
    assert "sneakers" not in bun                                         # no footwear under a thigh-up crop
    loose = R.natural_prompt("zara", LOOKS[0])
    assert "very long dark brown hair" in loose


def test_shot_prompt_switches_on_module_state_and_defaults_to_the_contract(zara, monkeypatch):
    contract = R.shot_prompt("zara", LOOKS[0])
    assert "Crop:" in contract and len(contract) > 1200
    monkeypatch.setattr(R, "PROMPT_STYLE", "natural")
    natural = R.shot_prompt("zara", LOOKS[0])
    assert natural == R.natural_prompt("zara", LOOKS[0])
    assert len(natural) < 600
    # the eval's slot mapping (asset_scenes) goes through shot_prompt, so one flag flips every scene
    assert re.match(r"^zara, a young woman", natural)
