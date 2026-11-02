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


def test_the_lingerie_pack_is_a_cutout_set_on_the_studio_floor_with_her_hair_loose():
    # Jeremy, 2026-11-01: "They are cutout sets so should not be placed in a
    # bedroom" and "The hair should just be loose for all these photos"
    from sourcemode.assets.pack import STUDIO_BACKDROP
    sh = S.BY_ID["lingerie"]
    assert sh.setting == STUDIO_BACKDROP
    for p in S.LINGERIE_PACK:
        assert p["needs"] == ("floor",), p["tag"]
        words = " ".join(str(v) for v in p.values()).lower()
        for prop in ("bed", "mattress", "pillow", "sheets", "wall", "chair"):
            assert prop not in words, (p["tag"], prop)
    assert {s["hair"] for s in sh.plan(character="nadia", outfit="x")} == {"her hair worn loose"}
    assert sh.plan(outfit="x")[0]["hair"] == "her hair worn loose"


def test_loose_hair_keeps_her_own_words_when_her_list_has_no_plain_loose(monkeypatch):
    import sourcemode.assets.wardrobe as W
    lists = {"tess": ("her hair in box braids up in a bun", "her hair hanging down her back"),
             "linda": ("her short hair neatly styled", "her short hair tousled and messy"),
             "zara": ("her hair worn down with high, tight pigtails", "her hair worn loose")}
    monkeypatch.setattr(W, "hair_options", lambda c: lists[c])
    assert W.loose_hair("tess") == "her hair hanging down her back"
    assert W.loose_hair("linda") == "her short hair neatly styled"
    assert W.loose_hair("zara") == "her hair worn loose"


def test_the_lingerie_poses_mix_into_any_scene_with_a_floor():
    assert S.combo_problem("bedroom-intimatewear-lingeriepack", "nadia") is None
    assert S.combo_problem("darkwall-intimatewear-lingeriepack", "nadia") is None


def test_the_kneeling_pair_looks_down_from_beside_her_and_differs_only_in_her_head():
    # Jeremy, 2026-11-01: standing right next to her as she kneels, looking
    # down; the same pose again with her head tilted back and her mouth open
    k1, k2 = (next(p for p in S.LINGERIE_PACK if p["tag"] == t) for t in ("kneeling", "kneeling2"))
    for k in (k1, k2):
        assert "straight down" in k["shot_type"] and "standing man" in k["shot_type"]
        assert "camera at her height" in k["negative"]
        assert "arms outstretched" in k["negative"] and "feet in the foreground" in k["negative"]
        assert "viewer" not in k["shot_type"] + k["stance"] + k["framing"]  # sienna: a man's feet
        assert "whole kneeling figure" not in k["framing"]
    assert {f: k1[f] for f in ("framing", "shot_type")} == {f: k2[f] for f in ("framing", "shot_type")}
    assert "behind her back" in k2["stance"] and "hands resting on her thighs" in k1["stance"]
    assert "tilted back" in k2["gaze"] and "tilted back" not in k1["gaze"]
    assert "mouth open" in k2["expression_natural"] and "closed-lip" in k1["expression_natural"]


def test_the_bend_over_and_spread_poses_turn_their_backs_and_name_the_torso_angle():
    # Jeremy, 2026-11-01: "The bend over and spread poses are supposed to be
    # with her back to the viewer"; bendingover2 sat back on her heels in 13 of
    # 13 while its stance said "kneeling"
    by = {p["tag"]: p for p in S.LINGERIE_PACK}
    for t in ("bendingover", "bendingover2", "spreadwide", "standingspread"):
        assert by[t]["facing"].startswith("her back to the camera"), t
    assert "slightly forward" in by["bendingover"]["shot_type"]
    assert "touching her toes" in by["bendingover"]["negative"]
    assert "touching the floor" in by["spreadwide"]["negative"]
    assert "leaning back on both hands" in by["lyingspread"]["stance"] and "lying flat" in by["lyingspread"]["negative"]
    assert "upside down" in by["lyingspread"]["negative"] and "upside down" in by["after"]["negative"]
    assert "toward the camera" in by["crawling"]["shot_type"] and "low-angle" not in by["crawling"]["shot_type"]
    assert "direct eye contact" in by["after"]["gaze"] and "eyes closed" in by["after"]["negative"]
    assert "elbows locked" in by["crawling"]["stance"] and "chest on the floor" in by["crawling"]["negative"]
    assert "on all fours" in by["crawling"]["stance"] and "both arms in view" in by["crawling"]["stance"]
    assert "upside-down V" in by["standingspread"]["stance"] and "feet" in by["standingspread"]["framing"]
    assert "kneel" not in by["bendingover2"]["stance"] and "propped up on her forearms" in by["bendingover2"]["shot_type"]
    assert "lying on her stomach" in by["bendingover2"]["stance"] and "on her heels" in by["bendingover2"]["negative"]
    assert "lying on her stomach" in by["showfeet"]["stance"] and "soles" in by["showfeet"]["stance"]
    assert "sitting" in by["showfeet"]["negative"]                # not lyingspread's pose
    for k in ("kneeling", "kneeling2"):
        assert "pointing straight down" in by[k]["framing"] and "horizon" in by[k]["negative"]
        assert "largest thing" not in by[k]["framing"]  # maya came out straight-on
    assert "open wide" in by["kneeling2"]["expression_natural"] and "teeth showing" in by["kneeling2"]["negative"]


def test_sitting_cannot_be_read_as_kneeling():
    # Jeremy, 2026-11-01: "The sitting prompt is also always the girl kneeling."
    sit = next(p for p in S.LINGERIE_PACK if p["tag"] == "sitting")
    # and "Crystal's is the perfect example": side-saddle, bottom on the floor
    assert "kneel" not in sit["stance"]
    assert "side-saddle" in sit["shot_type"] and "bottom resting on the floor" in sit["stance"]
    assert "kneeling" in sit["negative"]


def test_both_kneeling_poses_hold_eye_contact():
    # Jeremy, 2026-11-01: "it's important that the girl is looking directly at the viewer"
    for t in ("kneeling", "kneeling2"):
        g = next(p for p in S.LINGERIE_PACK if p["tag"] == t)["gaze"]
        assert "direct eye contact with the viewer" in g and "looking up into the lens" not in g


def test_after_places_both_arms():
    # Jeremy, 2026-11-01: "both missing a friggin' arm"
    st = next(p for p in S.LINGERIE_PACK if p["tag"] == "after")["stance"]
    assert "other arm" in st and "both arms in view" in st
