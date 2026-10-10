"""The tiebreaker eval set: twenty simple portraits for sweeps too close to call.

Jeremy, 2026-10-10, after vivienne's natural sweep: "create 20 new prompts that
are all portraits from mid thigh up either front facing or a very slight angle
looking at the camera with very simple expressions like a closed lip smile a
broad smile or a neutral expression ... Make sure there's no age ... varied
outfits, varied backgrounds, some blurred backgrounds, some non-blurred
backgrounds, mostly indoors ... call it the tiebreaker set."
"""

from __future__ import annotations

import re
import sys

import pytest

from sourcemode.assets import render as R
from sourcemode.assets.appearance import clause
from sourcemode.config import ENGINE_ROOT

sys.path.insert(0, str(ENGINE_ROOT / "scripts" / "eval"))
from asset_scenes import TIEBREAKER, tiebreaker_prompts, tiebreaker_slot  # noqa: E402

AGE = re.compile(r"\b\d{2}-year-old\b")
FLAT = re.compile(r"\b(overcast|fluorescent|dim|cool|flat|harsh)\b", re.I)


@pytest.fixture
def zara(monkeypatch):
    monkeypatch.setattr(R, "appearance_clause",
                        lambda c, age=True: ("a 22-year-old, " if age else "") + "a young woman with very long dark brown hair")


def test_twenty_distinct_prompts_in_the_natural_register(zara):
    ps = tiebreaker_prompts("zara")
    assert len(ps) == 20 == len({p for p in ps})
    assert len({s["outfit"] for s in TIEBREAKER}) == 20
    assert len({s["setting"] for s in TIEBREAKER}) == 20
    for p in ps:
        assert p.startswith("zara, a young woman") and len(p.split()) < 100
        assert "a standing portrait framed from mid-thigh up, " in p
        assert "beautiful, natural makeup" in p and "Photorealistic, natural skin texture, sharp focus." in p


def test_no_age_whatever_the_record_says(zara):
    for p in tiebreaker_prompts("zara"):
        assert not AGE.search(p), p
    # and on the real record of a character whose age IS normally in the prompt
    assert AGE.search(clause("amanda"))
    assert not AGE.search(clause("amanda", age=False))
    assert not any(AGE.search(p) for p in tiebreaker_prompts("amanda"))


def test_front_or_slight_turn_only_and_simple_expressions(zara):
    turns = [s["turn"] for s in TIEBREAKER]
    assert turns.count("front") == 10 and turns.count("slight-left") == 5 and turns.count("slight-right") == 5
    assert {s["expression"] for s in TIEBREAKER} == {"neutral", "closed-lip", "teeth"}
    for s, p in zip(TIEBREAKER, tiebreaker_prompts("zara")):
        assert "three-quarter" not in p and "flirty" not in p
        asked = R.pose_fields("zara", tiebreaker_slot(s))["asked"]
        assert asked["expression"] == s["expression"]
        if s["turn"] == "front":
            assert asked["body_side"] == "front" and "facing the camera, looking straight into the camera" in p
        else:
            assert asked["slight"] and 10 <= abs(asked["body_deg"]) <= 15 and 10 <= abs(asked["head_deg"]) <= 15
            her = "her right" if s["turn"] == "slight-left" else "her left"
            assert f"turned slightly toward {her}, looking into the camera" in p


def test_the_settings_follow_the_lighting_and_place_rules():
    blurred = [s for s in TIEBREAKER if "softly blurred" in s["setting"]]
    outdoors = [s for s in TIEBREAKER if re.search(r"\b(on a|outside|in a park)\b", s["setting"])]
    assert len(blurred) == 8 and len(outdoors) == 5
    for s in TIEBREAKER:
        assert not FLAT.search(s["setting"]), s["setting"]
        assert re.search(r"\b(in|on|against|outside)\b", s["setting"]), s["setting"]


def test_hair_and_footwear_rules_still_apply(zara):
    for s, p in zip(TIEBREAKER, tiebreaker_prompts("zara")):
        if R.is_up_style(s["hair"]):
            assert "very long" not in p, p
        assert not re.search(r"\b(sneakers|boots|heels|shoes)\b", p)
    assert not any(h in {"her hair up in a messy bun", "her hair in a braid"} for h in (s["hair"] for s in TIEBREAKER))


def test_a_pack_slot_is_byte_for_byte_unchanged(zara):
    """The turn/expression/age picks only act when a slot sets them."""
    slot = {"id": "casual_01", "look": 1, "category": "casual", "pose": "standing",
            "outfit": "a white tee and jeans", "hair": "her hair worn loose"}
    p = R.shot_prompt("zara", slot)
    assert p.startswith("zara, a 22-year-old, a young woman")
    assert "a standing portrait framed from the upper thighs up, facing the camera, looking straight into the camera, " in p
    assert R.pose_fields("zara", slot)["asked"]["slight"] is False


def test_bad_picks_are_refused():
    with pytest.raises(ValueError):
        R.pose_fields("x", {"look": 1, "turn": "profile"})
    with pytest.raises(ValueError):
        R.pose_fields("x", {"look": 1, "expression": "smirk"})


def test_the_contract_arm_names_the_slight_turn():
    assert R.describe_yaw(12).startswith("SLIGHT turn toward image-right (about 12 degrees)")
    assert R.describe_yaw(-40).startswith("THREE-QUARTER toward image-left")


def test_the_eval_accepts_the_set_and_keeps_its_own_folder():
    src = (ENGINE_ROOT / "scripts" / "eval" / "dense_epoch_eval.py").read_text(encoding="utf-8")
    assert 'SCENE_SET not in ("asset", "tiebreaker")' in src
    assert 'OUT = Path(f"outputs/dense_{SUB}_{SCENE_SET}{_TAG}")' in src
    assert 'SET_ID = f"dense_{SUB}_{SCENE_SET}{_TAG}"' in src
