"""The two game-asset packs on the shoots tab, and the one prompt builder.

The thing most worth protecting here is that adding the selfie pack did NOT
change what a wardrobe-pack slot renders. `shot_prompt` grew four optional
composition overrides so a selfie would not have to grow a second builder; if
any of them ever starts applying by default, a shipped pack silently changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sourcemode.assets import selfies
from sourcemode.assets.render import shot_prompt
from sourcemode.assets.shoots import (
    BY_ID, CATALOG, buckets, estimate_seconds, plan_path, resolve, total_shots)


def test_game_assets_group_is_first_and_holds_exactly_the_two_packs():
    bs = buckets()
    assert bs[0]["bucket"] == "game"
    assert bs[0]["label"] == "Game assets"
    assert [s["id"] for s in bs[0]["shoots"]] == ["pack28", "selfies"]


def test_the_wardrobe_pack_is_one_shot_per_look_not_four():
    # It used to render 4 candidates for every look and keep one: 112 shots to
    # ship 28, every time. Judge one and re-roll the rejects instead.
    assert BY_ID["pack28"].shots == 28
    assert BY_ID["selfies"].shots == 24 == selfies.TOTAL
    assert total_shots(["pack28", "selfies"]) == 52


def test_selfie_pack_is_the_agreed_mix():
    # Settled 2026-10-02: 8 casual / 6 flirty / 5 date / 5 intimate.
    assert selfies.COUNTS == {"selfie_casual": 8, "selfie_flirty": 6,
                              "selfie_date": 5, "selfie_intimate": 5}
    s = selfies.slots()
    assert len({x["id"] for x in s}) == 24
    # `look` drives the expression table and the body yaw, so it must not repeat
    # or all 24 selfies come back with one face and one turn.
    assert sorted(x["look"] for x in s) == list(range(1, 25))
    assert all(x["setting"] and x["outfit"] and x["hair"] for x in s)


def test_a_pack_slot_renders_exactly_what_it_did_before_the_selfie_overrides():
    slot = {"id": "casual_01", "look": 1, "category": "casual", "pose": "standing",
            "outfit": "a blue sundress", "hair": "her hair worn loose"}
    p = shot_prompt("nobody", slot)
    assert "New photorealistic standing portrait of" in p
    assert p.endswith("No profiles, rear views, seated poses, or off-camera gaze.")
    assert "phone selfie" not in p


def test_a_selfie_is_not_described_as_a_standing_portrait_that_forbids_sitting():
    # Half the pack is shot sitting on a bed or a sofa. The wardrobe pack's
    # closing line rules that out, so a selfie slot replaces it.
    sitting = [x for x in selfies.slots() if "sitting" in x["stance"]]
    assert sitting, "the pack should carry seated selfies"
    p = shot_prompt("nobody", sitting[0], backdrop=sitting[0]["setting"])
    assert "New photorealistic phone selfie of" in p
    assert "seated poses" not in p
    assert "this is a casual photo she took herself on her phone" in p
    # The backdrop is her real room - a selfie never gets the chroma plate.
    assert "#FF00FF" not in p


def test_the_selfie_prompt_never_names_the_outstretched_arm():
    # Measured at 1024x1536, n=4: bare 3/4 keep, geometric 3/4, "her arm
    # outstretched and visible in the frame" 1/4. It is the arm that lost.
    for slot in selfies.slots():
        p = shot_prompt("nobody", slot, backdrop=slot["setting"])
        assert "outstretched" not in p


def test_a_mixed_job_is_priced_at_two_rates_not_one():
    # 112 pack shots at the asset rate + 24 selfies at the sweep rate. Charging
    # the whole thing at the sweep rate understated it by over an hour.
    secs = estimate_seconds(["pack28", "selfies"], 75.0, 116.0)
    assert secs == pytest.approx(28 * 116.0 + 24 * 75.0)
    assert estimate_seconds(["boudoir"], 75.0, 116.0) == pytest.approx(12 * 75.0)


def test_only_the_wardrobe_pack_needs_a_plan_on_disk(tmp_path):
    assert plan_path(BY_ID["pack28"], "zara", tmp_path) == (
        tmp_path / "game-assets" / "zara" / "plan_28.json")
    for s in CATALOG:
        if s.id != "pack28":
            assert plan_path(s, "zara", tmp_path) is None


def test_a_character_with_no_wardrobe_plan_is_blocked_with_a_reason(tmp_path, monkeypatch):
    from sourcemode.assets import lora

    monkeypatch.setattr(lora, "outputs_dir", lambda cfg: tmp_path, raising=False)
    import sourcemode.config as config

    monkeypatch.setattr(config, "outputs_dir", lambda cfg: tmp_path)
    blocked = lora.blocked_shoots({}, "nobody")
    assert "pack28" in blocked
    assert "wardrobe plan" in blocked["pack28"]
    assert "selfies" not in blocked, "the selfie pack is fully specified, never blocked"

    # ...and present once the plan exists.
    p = tmp_path / "game-assets" / "nobody" / "plan_28.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"character": "nobody"}), encoding="utf-8")
    assert lora.blocked_shoots({}, "nobody") == {}


def test_resolve_still_refuses_a_typo():
    with pytest.raises(KeyError):
        resolve(["pack28", "pack_28"])


def test_the_queue_row_only_claims_training_and_sweep_for_a_training_job():
    # The shoots and asset jobs read "24m of GPU time once it starts - training
    # + sweep", with two blank durations, describing work they do not do.
    js = Path("sourcemode/monitor/queue_page.py").read_text(encoding="utf-8")
    i = js.index("of GPU time once it starts")
    window = js[i:i + 600]
    assert "j.estimate.train_s&&j.estimate.sweep_s" in window


# --- per-character hair -----------------------------------------------------

def test_a_box_braided_character_is_never_asked_for_loose_hair():
    """Jeremy, 2026-10-04: Tess's braid is a specific protective style, not the
    generic braid the shared vocabulary means.

    She wears long box braids in every training frame. The shared rotation
    opens with "her hair worn loose", which would have reached a quarter of
    every shoot and every selfie. That is the gabi collision in reverse - her
    set is ~90% loose hair and prompting a braid kept 20%.
    """
    from sourcemode.assets.wardrobe import DEFAULT_HAIR, hair_options

    tess = hair_options("tess")
    assert tess != DEFAULT_HAIR
    assert all("braid" in h for h in tess)
    assert not any("loose" in h for h in tess)

    for sid in ("boudoir", "selfies"):
        hairs = {s["hair"] for s in BY_ID[sid].plan(character="tess")}
        assert all("braid" in h for h in hairs), sid


def test_a_character_with_no_list_keeps_the_shared_rotation():
    from sourcemode.assets.wardrobe import DEFAULT_HAIR, hair_options

    assert hair_options("zara") == DEFAULT_HAIR
    assert hair_options("nobody-at-all") == DEFAULT_HAIR
    # and passing no character at all leaves a shoot exactly as it was
    assert BY_ID["boudoir"].plan()[0]["hair"] == DEFAULT_HAIR[0]


def test_the_braid_style_itself_is_identity_not_a_per_look_clause():
    # It is in every frame, so a clause that re-states it on some looks and not
    # others would make a constant accidentally variable. It lives in her
    # appearance record; the per-look clause only varies how it is WORN.
    from sourcemode.assets.appearance import clause

    assert "box braids" in clause("tess")
    assert "square grid" in clause("tess")
