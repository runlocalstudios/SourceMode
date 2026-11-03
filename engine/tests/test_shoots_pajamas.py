import random

from sourcemode.assets import shoots as S


def test_the_pajama_pack_is_a_game_cutout_set_in_one_rolled_colour(tmp_path):
    # Jeremy, 2026-11-03: one garment, every detail fixed, only the colour rolled
    sh = S.BY_ID["pajamas"]
    assert sh.bucket == "game" and sh.setting == S.BY_ID["lingerie"].setting and sh.loose_hair
    assert S.rolls_one_outfit(sh)
    first = S.set_outfit(sh, tmp_path, "bianca", rng=random.Random(3))
    assert first in S.PAJAMAS
    assert S.set_outfit(sh, tmp_path, "bianca", rng=random.Random(9)) == first   # kept in set.json
    assert len(set(S.PAJAMAS)) == len(S.PAJAMA_COLOURS) >= 8
    for line in S.PAJAMAS:
        for fixed in ("short-sleeved", "notched collar", "small round white buttons", "every button done up",
                      "white piping", "pajama shorts", "barefoot"):
            assert fixed in line
    # white buttons and piping on a white or ivory set would vanish
    assert not {"white", "ivory", "champagne", "cream"} & set(S.PAJAMA_COLOURS)
    plan = sh.plan(character="bianca", outfit=first)
    assert {s["outfit"] for s in plan} == {first}
    assert all(s["shoes"] for s in plan)        # drop_footwear never touches "barefoot"
    assert {s["hair"] for s in plan} == {"her hair worn loose"}


def test_the_nine_poses_in_his_order_with_the_pack_negative_under_each():
    tags = [p["tag"] for p in S.PAJAMA_PACK]
    assert tags == ["standing", "standingside", "standingback", "sitting", "kneeling", "kneeling2",
                    "showfeet", "crawling", "after"]
    by = {p["tag"]: p for p in S.PAJAMA_PACK}
    lp = {p["tag"]: p for p in S.LINGERIE_PACK}
    for t in ("standing", "standingside", "standingback"):
        assert "mid-thighs" in by[t]["framing"] and "close" in by[t]["framing"], t
        assert "full-length" in by[t]["negative"], t
    assert "profile" in by["standingside"]["facing"] and "into the lens" in by["standingside"]["gaze"]
    assert "very close" in by["standingback"]["stance"] and "back to the camera" in by["standingback"]["facing"]
    assert "viewer" not in by["standingback"]["stance"] + by["standingback"]["shot_type"]  # never his body
    assert "a man" in by["standingback"]["negative"]
    for t in ("sitting", "kneeling", "kneeling2", "showfeet", "crawling"):
        assert by[t]["stance"] == lp[t]["stance"] and by[t]["framing"] == lp[t]["framing"], t
    # Jeremy, 2026-11-03: sitting grows buttons on the shorts; the side portrait
    # moves the button row onto the side of the shirt. Pajama copies only.
    assert "buttons on the shorts" in by["sitting"]["negative"]
    assert "buttons" not in lp["sitting"]["negative"]
    assert "buttons on the side of the shirt" in by["standingside"]["negative"]
    assert "smoothly to one side" in by["after"]["stance"] and "messy hair" in by["after"]["negative"]
    assert "naturally on the floor" not in by["after"]["stance"]
    for p in S.PAJAMA_PACK:
        assert p["needs"] == ("floor",)
        # Jeremy, 2026-11-03: a chest pocket grew on both kneeling poses in 13 of
        # 14 sets and on about half the sitting and crawling shots, never on the
        # standing front - so no pocket at all, on every pose
        for refuse in ("long pants", "robe", "print", "unbuttoned", "slippers", "chest pocket"):
            assert refuse in p["negative"], (p["tag"], refuse)
