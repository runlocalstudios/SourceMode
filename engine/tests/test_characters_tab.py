"""The Characters tab: two jobs tied to game places, free-form style per
outfit type, and context that never reaches a prompt.

Jeremy, 2026-10-11: "Marisol and Zara are both strippers and both work at the
beach bar, I can't have them working at the beach bar in stripper outfits."
"""

from __future__ import annotations

import json

from sourcemode.assets import wardrobe as W


def _doc(tmp_path, rec):
    p = tmp_path / "wardrobe.json"
    p.write_text(json.dumps({"_comment": ["x"], "zara": rec}), encoding="utf-8")
    return p


def test_two_jobs_keep_their_own_places_and_outfits(tmp_path, monkeypatch):
    p = _doc(tmp_path, {})
    rec = W.save("zara", {"jobs": [
        {"job": "dancer", "places": ["chillTrap"], "outfit": "a sequinned two-piece"},
        {"job": "server", "places": ["beachBar"], "outfit": "a fitted black tee and denim shorts"},
        {"job": "", "places": [], "outfit": ""}]}, path=p)
    assert [j["job"] for j in rec["jobs"]] == ["dancer", "server"]
    monkeypatch.setattr(W, "brief", lambda c: json.loads(p.read_text(encoding="utf-8"))[c])
    assert W.job_for_place("zara", "beachBar")["outfit"].startswith("a fitted black tee")
    assert W.job_for_place("zara", "chillTrap")["job"] == "dancer"
    assert W.job_for_place("zara", "park") is None


def test_save_keeps_the_note_and_the_rest_of_the_file(tmp_path):
    p = _doc(tmp_path, {"_note": "DRAFT", "style": "old", "work": "old uniform"})
    W.save("zara", {"style": "trendy, a little underdressed", "outfits": {"swim": "tiny bikinis"},
                    "hair": ["her hair worn loose", " "]}, path=p)
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["_comment"] == ["x"]
    z = doc["zara"]
    assert z["_note"] == "DRAFT" and z["style"] == "trendy, a little underdressed"
    assert z["outfits"] == {"swim": "tiny bikinis"} and z["hair"] == ["her hair worn loose"]
    assert "work" not in z           # the legacy key's content now lives in jobs


def test_a_legacy_brief_is_carried_into_the_new_fields(monkeypatch):
    monkeypatch.setattr(W, "brief", lambda c: {
        "style": "covered", "silhouettes": "midi dresses", "work": "church volunteer dress",
        "workout": "full leggings", "avoid": "crop tops"})
    e = W.editable("sandra")
    assert e["draft"] is True
    assert e["jobs"][0]["outfit"] == "church volunteer dress" and len(e["jobs"]) == W.JOB_SLOTS
    assert e["outfits"]["workout"] == "full leggings"
    assert "midi dresses" in e["style"] and e["avoid"] == "crop tops"


def test_avoid_and_hair_still_reach_the_renderers(tmp_path, monkeypatch):
    p = _doc(tmp_path, {})
    W.save("zara", {"avoid": "nothing pastel", "hair": ["box braids up", "box braids down"]}, path=p)
    monkeypatch.setattr(W, "brief", lambda c: json.loads(p.read_text(encoding="utf-8"))[c])
    assert W.avoid("zara") == "nothing pastel"
    assert W.hair_options("zara") == ("box braids up", "box braids down")


def test_ethnicity_is_context_and_never_unconfirms_her(tmp_path, monkeypatch):
    from sourcemode.assets import appearance as A
    f = tmp_path / "appearance.json"
    f.write_text(json.dumps({"zara": {"prompt": "a young woman with long dark hair"}}), encoding="utf-8")
    monkeypatch.setattr(A, "APPEARANCE", f)
    A.reload()
    A.confirm("zara", {"prompt": "a young woman with long dark hair", "negative": ""})
    A.set_context("zara", ethnicity="Latina")
    A.reload()
    assert A.confirmed("zara")
    assert "Latina" not in A.clause("zara")
    A.reload()


def test_an_age_typed_on_the_tab_satisfies_the_shoot_preflight(tmp_path, monkeypatch):
    """Jeremy, 2026-10-17: "I cannot add the character's age anywhere, which
    means that from your characters, I'm unable to generate a photo shoot".
    Winnie is not in the game's characters.js, so the game lends her no age;
    the tab showed age read-only and the pre-flight refused her."""
    from sourcemode.assets import appearance as A
    f = tmp_path / "appearance.json"
    f.write_text(json.dumps({"winnie": {"prompt": "a young woman with long black hair"}}), encoding="utf-8")
    monkeypatch.setattr(A, "APPEARANCE", f)
    monkeypatch.setattr(A, "AGES", tmp_path / "ages.json")   # not in the game
    A.reload()
    A.confirm("winnie", {"prompt": "a young woman with long black hair", "negative": ""})
    assert "age" in "; ".join(A.check("winnie")["missing"])

    A.set_context("winnie", ethnicity="", age="22")
    assert A.check("winnie")["ok"]
    assert A.age_of("winnie") == 22
    assert A.confirmed("winnie")            # age is outside the fingerprint

    # blank clears her own; with no game age she is incomplete again
    A.set_context("winnie", ethnicity="", age="")
    assert A.age_of("winnie") is None
    assert not A.check("winnie")["ok"]
    import pytest
    with pytest.raises(ValueError):
        A.set_context("winnie", ethnicity="", age="twenty")
    A.reload()
