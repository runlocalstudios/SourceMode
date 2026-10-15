"""Mix-and-match shoots and the submissive pose set (Jeremy, 2026-10-12).

A combo id `<scene>-<wardrobe>-<poses>` must behave exactly like a preset
everywhere a shoot id flows - resolve, lookup, total_shots - and a combo that
cannot render (a bed pose at the club, the work wardrobe for a character with
no job outfit) must be refused with the same words the tab greys it with.
"""

from __future__ import annotations

import pytest

from sourcemode.assets import shoots as S
from sourcemode.assets import wardrobe as W
from sourcemode.assets.render import shot_prompt


def test_combo_is_a_shoot_with_one_shot_per_pose():
    sh = S.combo("bedroom-lingerie-submissive")
    assert sh is not None
    assert sh.shots == len(S.SUBMISSIVE) == 21
    assert sh.setting == S.BEDROOM
    assert sh.outfits == S.LINGERIE
    assert S.lookup("bedroom-lingerie-submissive").id == sh.id
    assert S.total_shots(["club", "bedroom-lingerie-submissive"]) == 8 + 21
    # presets first in catalog order, then the combos as ticked
    assert [s.id for s in S.resolve(["bedroom-lingerie-submissive", "club"])] == [
        "club", "bedroom-lingerie-submissive"]


def test_component_ids_carry_no_hyphen_because_the_hyphen_is_the_separator():
    for x in S.SCENES + S.WARDROBES + S.POSE_PACKS:
        assert "-" not in x.id, x.id


@pytest.mark.parametrize("bad", ["club-lingerie", "mars-lingerie-submissive",
                                 "club-lingerie-submissive-extra", "boudoir"])
def test_a_non_combo_is_none_and_unknown_ids_still_raise(bad):
    if bad == "boudoir":
        assert S.combo(bad) is None and bad in S.BY_ID
        return
    assert S.combo(bad) is None
    with pytest.raises(KeyError):
        S.resolve([bad])


def test_a_bed_pose_at_the_club_is_refused_with_the_reason():
    why = S.combo_problem("club-lingerie-submissive", "ash")
    assert why and "need a bed" in why and "Club" in why
    assert S.combo_problem("bedroom-lingerie-submissive", "ash") is None
    # the standing pack needs only a floor, so it goes anywhere
    assert S.combo_problem("pool-swim-standing", "ash") is None


def test_the_work_wardrobe_is_her_job_outfit_and_blocks_without_one(monkeypatch):
    def fake(character):
        jobs = {"ash": [{"job": "waitress", "outfit": "a black shirt-dress uniform", "places": []},
                        {"job": "", "outfit": "", "places": []}]}
        return {"jobs": jobs.get(character, [{"job": "", "outfit": "", "places": []}])}
    monkeypatch.setattr(W, "editable", fake)
    from sourcemode.assets import appearance as A
    monkeypatch.setattr(A, "persona_job", lambda c: "")
    # her work week, not one outfit: five lines, all still the uniform
    work = S.wardrobe_outfits("work", "ash")
    assert len(work) == 5 and work[0] == "a black shirt-dress uniform"
    assert all(w.startswith("a black shirt-dress uniform") for w in work)
    assert S.wardrobe_outfits("work", "nobody") == ()
    assert S.combo_problem("club-work-standing", "nobody") == (
        "no job outfit in her record - add one under Jobs on the Characters tab")
    assert S.combo_problem("club-work-standing", "ash") is None
    slots = S.combo("club-work-standing").plan(character="ash")
    assert {s["outfit"] for s in slots} == set(work)
    assert len(slots) == len(S.POSES_BY_ID["standing"].poses)


def test_pose_slots_reach_the_prompt_and_keep_the_stockings():
    sh = S.BY_ID["submissive"]
    slots = sh.plan(character="nobody")
    assert len(slots) == 21 and len({s["id"] for s in slots}) == 21
    # pose 9: back to the camera, looking over her shoulder - the builder's
    # default "facing the camera, looking straight into the camera" must go
    p = shot_prompt("nobody", slots[8], backdrop=slots[8]["setting"])
    assert "her back to the camera" in p
    assert "looking back over her shoulder into the camera" in p
    assert "facing the camera" not in p and "looking straight into the camera" not in p
    assert slots[8]["stance"] in p
    # lingerie ends in stockings; drop_footwear would have eaten them
    assert "stockings" in p
    # pose 3: mouth open replaces the smile table entry
    p3 = shot_prompt("nobody", slots[2], backdrop=slots[2]["setting"])
    assert "her mouth open wide" in p3 and "smile" not in p3
    # a plain pose keeps the defaults
    p6 = shot_prompt("nobody", slots[5], backdrop=slots[5]["setting"])
    assert "facing the camera" in p6 or "toward her" in p6


def test_every_submissive_pose_names_what_it_needs_and_the_bedroom_has_it():
    bedroom = S.SCENE_BY_ID["bedroom"]
    for p in S.SUBMISSIVE:
        assert p["needs"], p["stance"]
        assert set(p["needs"]) <= set(bedroom.has), p["stance"]


def test_the_preset_is_in_the_intimate_bucket_and_the_tab_gets_the_three_lists():
    intimate = next(b for b in S.buckets() if b["bucket"] == "intimate")
    assert "submissive" in [s["id"] for s in intimate["shoots"]]
    m = S.mix()
    assert {x["id"] for x in m["poses"]} == {"standing", "bedroom", "submissive", "toy"}
    sub = next(x for x in m["poses"] if x["id"] == "submissive")
    assert sub["n"] == 21 and sub["needs"] == ["bed", "floor", "wall"]
    assert next(w for w in m["wardrobes"] if w["id"] == "work")["record"] == "job"


def test_a_pack_slot_is_untouched_by_the_new_overrides():
    slot = {"id": "casual_01", "look": 1, "category": "casual", "pose": "standing",
            "outfit": "a blue sundress", "hair": "her hair worn loose"}
    p = shot_prompt("nobody", slot)
    assert "a standing portrait framed from mid-thigh up" in p
    assert "looking straight into the camera" in p


def test_the_ass_up_shot_gets_a_panties_set_whatever_the_rotation_says():
    # Jeremy, 2026-10-12: "her ass and crotch of her panties pointed towards
    # the viewer" - the slot must not land on the bodysuit
    slots = S.BY_ID["submissive"].plan(character="nobody")
    last = slots[-2]
    assert "panties" in last["outfit"] or "thong" in last["outfit"]
    assert "bodysuit" not in last["outfit"]
    p = shot_prompt("nobody", last, backdrop=last["setting"])
    assert "the crotch of her panties pointed straight at the camera" in p
    assert "her back to the camera" in p and "stockings" in p
    # a wardrobe with nothing it wants falls back to the rotation
    sh = S.combo("bedroom-swim-submissive")
    assert sh is not None
    assert sh.plan(character="nobody")[-1]["outfit"] in S.WARDROBE_BY_ID["swim"].outfits


def test_the_toy_shoot_is_in_bed_in_the_robe_with_the_toy_named_in_every_shot():
    sh = S.BY_ID["toy"]
    assert sh.bucket == "intimate" and sh.shots == len(S.TOY) == 7
    slots = sh.plan(character="nobody")
    for s in slots:
        p = shot_prompt("nobody", s, backdrop=s["setting"])
        assert "male torso sex toy" in p and "dildo" in p
        assert "satin robe" in p and "her breasts bare" in p and "panties" in p
    cow = shot_prompt("nobody", slots[5], backdrop=slots[5]["setting"])
    assert "cowgirl" in cow and "panties pulled to the side" in cow and "looking into the camera" in cow
    rev = shot_prompt("nobody", slots[6], backdrop=slots[6]["setting"])
    assert "reverse cowgirl" in rev and "her back to the camera" in rev
    # mixable: the robe and the toy pack, bed scenes only
    assert S.combo("hotel-robe-toy") is not None
    assert S.combo_problem("hotel-robe-toy", "ash") is None
    assert "need a bed" in (S.combo_problem("club-robe-toy", "ash") or "")
    assert S.total_shots(["toy"]) == 7


def test_the_last_submissive_shot_is_the_ass_up_pose_looking_at_the_camera():
    last = S.BY_ID["submissive"].plan(character="nobody")[-1]
    p = shot_prompt("nobody", last, backdrop=last["setting"])
    assert "the crotch of her panties pointed straight at the camera" in p
    assert "looking back over her shoulder into the camera" in p
    assert "panties" in last["outfit"] or "thong" in last["outfit"]
