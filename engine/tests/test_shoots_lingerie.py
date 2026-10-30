import random

from sourcemode.assets import shoots as S


def test_the_lingerie_pack_sits_with_the_game_assets_and_wears_one_set():
    game = next(b for b in S.buckets() if b["bucket"] == "game")
    assert "lingerie" in [s["id"] for s in game["shoots"]]
    sh = S.BY_ID["lingerie"]
    assert sh.shots == len(S.LINGERIE_PACK) >= 12 and sh.kind == "shoot"
    assert S.rolls_one_outfit(sh)


def test_her_set_is_her_intimate_line_or_satin_in_her_colour_with_the_white_band(monkeypatch):
    import sourcemode.assets.wardrobe as W
    lines = {"sienna": "Black satin", "winnie": "Satin lingerie with garter sets, the colors vary",
             "ash": "patterns, silk, lace", "nadia": "",
             "mei": "a red satin bra and matching panties with a thin white band"}
    monkeypatch.setattr(W, "editable", lambda c: {"outfits": {"intimate": lines.get(c, "")}})
    assert S.lingerie_set("sienna") == S.LINGERIE_DEFAULT.format(c="black")
    assert S.lingerie_set("nadia") == S.LINGERIE_DEFAULT.format(c="black")
    assert S.lingerie_set("ash") == S.LINGERIE_DEFAULT.format(c="black")
    assert S.lingerie_set("winnie") == S.LINGERIE_DEFAULT.format(c="black")    # a brief, not an outfit
    assert S.lingerie_set("mei") == lines["mei"]                               # one garment, verbatim
    assert "lace" not in S.LINGERIE_DEFAULT and "white" in S.LINGERIE_DEFAULT


def test_every_pose_carries_a_tag_the_game_can_key_on_and_the_set_is_one_outfit(tmp_path, monkeypatch):
    import sourcemode.assets.wardrobe as W
    monkeypatch.setattr(W, "editable", lambda c: {"outfits": {"intimate": "Black satin"}})
    tags = [p["tag"] for p in S.LINGERIE_PACK]
    assert len(tags) == len(set(tags))
    for want in ("kneeling", "spreadwide", "bendingover", "crawling"):
        assert want in tags
    sh = S.BY_ID["lingerie"]
    first = S.set_outfit(sh, tmp_path, "sienna", rng=random.Random(1))
    assert first == S.LINGERIE_DEFAULT.format(c="black")
    plan = sh.plan(character="sienna", outfit=first)
    assert {s["outfit"] for s in plan} == {first}
    assert [s["tag"] for s in plan] == tags
    for s in plan:
        assert s["shoes"] and s["framing"]


def test_no_pose_puts_her_on_his_lap():
    # Jeremy, 2026-10-29: "kill the sitting on lap poses"
    assert not [p for p in S.LINGERIE_PACK if "lap" in p["tag"] or "the man" in p["stance"]]


def test_the_lingerie_poses_mix_into_any_scene_with_a_bed_and_floor():
    assert S.combo_problem("bedroom-intimatewear-lingeriepack", "nadia") is None
    assert S.combo_problem("hotel-intimatewear-lingeriepack", "nadia") is None
    assert "bed" in S.combo_problem("darkwall-intimatewear-lingeriepack", "nadia")
