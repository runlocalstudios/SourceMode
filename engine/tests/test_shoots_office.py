from sourcemode.assets import shoots as S


def test_the_office_group_has_its_three_shoots_revealing_by_default():
    office = next(b for b in S.buckets() if b["bucket"] == "office")
    assert [s["id"] for s in office["shoots"]] == ["office_door", "office_desk", "office_pov"]
    assert all(S.BY_ID[i].outfits == S.OFFICE_SLUTTY for i in ("office_door", "office_desk", "office_pov"))


def test_the_office_pieces_mix_and_their_poses_only_go_where_they_make_sense():
    assert S.combo_problem("officedoor-officechic-doorway", "nadia") is None
    assert S.combo_problem("office-officechic-desk", "nadia") is None
    assert "doorway" in S.combo_problem("bedroom-lingerie-doorway", "nadia")
    assert "desk" in S.combo_problem("bedroom-lingerie-desk", "nadia")
    # between his legs needs only a floor, so it goes anywhere with one
    for scene in ("bedroom", "hotel", "livingroom", "office", "beach"):
        assert S.combo_problem(f"{scene}-lingerie-betweenlegs", "nadia") is None


def test_between_his_legs_puts_his_legs_in_frame_and_her_between_them():
    for slot in S.BY_ID["office_pov"].plan(character="nadia"):
        assert "boxer shorts" in slot["framing"] and ("between his" in slot["stance"])


def test_his_shorts_are_named_as_his_and_hers_are_refused_without_naming_his():
    for slot in S.BY_ID["office_pov"].plan(character="nadia"):
        assert "the man wearing dark navy boxer shorts" in slot["framing"]
        assert "grey" not in slot["framing"] and "boxer" not in slot["negative"]
        assert "grey shorts" in slot["negative"] and "far away" in slot["negative"]
        assert "whole" not in slot["framing"]       # the camera stays close


def test_a_set_rolls_one_outfit_once_and_every_shot_wears_it(tmp_path):
    import random
    sh = S.BY_ID["office_pov"]
    first = S.set_outfit(sh, tmp_path, "nadia", rng=random.Random(3))
    assert first in S.OFFICE_SLUTTY
    # a re-run reads the roll back rather than rolling again
    assert S.set_outfit(sh, tmp_path, "nadia", rng=random.Random(99)) == first
    plan = sh.plan(character="nadia", outfit=first)
    assert {s["outfit"] for s in plan} == {first}


def test_a_redo_never_rolls_and_the_packs_never_roll(tmp_path):
    assert S.set_outfit(S.BY_ID["office_pov"], tmp_path, "nadia", roll=False) is None
    assert not (tmp_path / "set.json").exists()
    for sid in ("pack28", "selfies", "influencer"):
        assert not S.rolls_one_outfit(S.BY_ID[sid])
    assert S.rolls_one_outfit(S.combo("office-officechic-desk"))


def test_no_desk_shot_is_full_length_any_more():
    for p in S.DESK:
        assert "whole body" not in p["framing"] and "full-length" not in p.get("shot_type", "")


def test_no_pose_asks_for_a_lip_bite_or_puts_a_second_mouth_in_its_gaze():
    packs = (S.DOORWAY, S.DESK, S.BETWEEN_LEGS, S.SUBMISSIVE, S.TOY)
    for p in (x for pack in packs for x in pack):
        text = " ".join(str(p.get(k, "")) for k in ("stance", "gaze", "expression_natural"))
        assert "biting" not in text.lower(), p["stance"]
        assert "smile" not in p.get("gaze", ""), p["gaze"]
