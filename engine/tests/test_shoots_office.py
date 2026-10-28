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
