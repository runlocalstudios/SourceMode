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
    # one sentence for the set; the side and back shots wear it minus the button row
    assert {s["outfit"] for s in plan if s["tag"] not in ("standingside", "standingback")} == {first}
    by_tag = {s["tag"]: s for s in plan}
    assert by_tag["standingback"]["outfit"] == first.replace(S._PJ_BUTTONS, "")
    # Jeremy, 2026-11-06: the side shot is knees-up, so it never says "barefoot"
    assert by_tag["standingside"]["outfit"] == first.replace(S._PJ_BUTTONS, "").replace(", barefoot", "")
    assert all(s["shoes"] for s in plan)        # drop_footwear never touches "barefoot"
    assert {s["hair"] for s in plan} == {"her hair worn loose"}


def test_the_nine_poses_in_his_order_with_the_pack_negative_under_each():
    tags = [p["tag"] for p in S.PAJAMA_PACK]
    assert tags == ["standing", "standingside", "standingback", "sitting", "kneeling", "kneeling2",
                    "showfeet", "crawling", "after"]
    by = {p["tag"]: p for p in S.PAJAMA_PACK}
    lp = {p["tag"]: p for p in S.LINGERIE_PACK}
    for t in ("standing", "standingback"):
        assert "mid-thighs" in by[t]["framing"] and "close" in by[t]["framing"], t
    for t in ("standing", "standingside", "standingback"):
        assert "full-length" in by[t]["negative"], t
    # Jeremy, 2026-11-06: "Keiko's side pajama shot keeps rendering full body
    # with her feet ... it should be like a knees up shot"
    side = by["standingside"]
    assert "knees-up" in side["shot_type"] and "above her knees" in side["framing"]
    assert "three-quarter" not in side["shot_type"] + side["framing"]
    assert "feet" in side["negative"] and "lower legs" in side["negative"]
    assert "profile" in by["standingside"]["facing"] and "into the lens" in by["standingside"]["gaze"]
    assert "very close" in by["standingback"]["stance"] and "back to the camera" in by["standingback"]["facing"]
    # Jeremy, 2026-11-03: three arms from behind - one countable action, not two one-handed ones
    assert "both hands resting on her hips" in by["standingback"]["stance"]
    assert "lifting her hair" not in by["standingback"]["stance"]
    assert "three arms" in by["standingback"]["negative"]
    assert "viewer" not in by["standingback"]["stance"] + by["standingback"]["shot_type"]  # never his body
    assert "a man" in by["standingback"]["negative"]
    assert "buttons down the back" in by["standingback"]["negative"]
    # Jeremy, 2026-11-03, after 21 of 28 rejects were the back shot with the
    # button row down her spine: "on the side and rear photos there should be
    # NO BUTTONS WHATSOEVER". The set's colour sentence is frozen in set.json,
    # so the strip happens per slot at plan time and reaches every redo.
    plan = {s["tag"]: s for s in S.BY_ID["pajamas"].plan(character="bianca", outfit=S.PAJAMAS[0])}
    for t in ("standingside", "standingback"):
        assert "button" not in plan[t]["outfit"], (t, plan[t]["outfit"])
        assert "satin pajama shirt with a notched collar" in plan[t]["outfit"]   # the rest survives
        assert "white piping" in plan[t]["outfit"]
        assert "smooth" in plan[t]["stance"], t                                   # what IS seen, said
        assert ", buttons," in "," + plan[t]["negative"] + "," or "buttons, " in plan[t]["negative"]
    assert "every button done up" in plan["standing"]["outfit"]                   # front poses keep them
    # casey's kneeling shot grew the photographer's camera and hands
    for t in ("kneeling", "kneeling2"):
        assert "camera in frame" in by[t]["negative"], t
    for t in ("sitting", "kneeling", "kneeling2", "showfeet", "crawling"):
        assert by[t]["stance"] == lp[t]["stance"] and by[t]["framing"] == lp[t]["framing"], t
    # Jeremy, 2026-11-03: sitting grows buttons on the shorts; the side portrait
    # moves the button row onto the side of the shirt. Pajama copies only.
    assert "buttons on the shorts" in by["sitting"]["negative"]
    assert "buttons" not in lp["sitting"]["negative"]
    assert by["standingside"]["negative"].startswith("buttons, ")
    assert "smoothly to one side" in by["after"]["stance"] and "messy hair" in by["after"]["negative"]
    assert "naturally on the floor" not in by["after"]["stance"]
    for p in S.PAJAMA_PACK:
        assert p["needs"] == ("floor",)
        # Jeremy, 2026-11-03: a chest pocket grew on both kneeling poses in 13 of
        # 14 sets and on about half the sitting and crawling shots, never on the
        # standing front - so no pocket at all, on every pose
        for refuse in ("long pants", "robe", "print", "unbuttoned", "slippers", "chest pocket"):
            assert refuse in p["negative"], (p["tag"], refuse)
