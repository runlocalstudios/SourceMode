import json
import shutil

from sourcemode import video_templates as VT


def test_the_three_templates_load_with_a_script_and_his_sofa_legs():
    ids = {t["id"] for t in VT.all_templates()}
    assert {"velvet_lounge", "club_duo", "house_call"} <= ids
    for tid in ("velvet_lounge", "club_duo", "house_call"):
        t = VT.load(tid)
        assert t["script"].strip() and t["legs"]
        # 2026-10-28: every template keeps the Velvet Lounge legs - seated on a sofa
        assert "seated low on a sofa" in t["start"]["composition"]
    assert VT.load("club_duo")["cast"] == 2


def test_an_edited_script_is_saved_into_the_template(tmp_path, monkeypatch):
    shutil.copy(VT.path_for("house_call"), tmp_path / "house_call.json")
    monkeypatch.setattr(VT, "TEMPLATES_DIR", tmp_path)
    VT.save_script("house_call", "[0-5s] New words.\r\n[5-9s] More.")
    doc = json.loads((tmp_path / "house_call.json").read_text(encoding="utf-8"))
    assert doc["script"] == "[0-5s] New words.\n[5-9s] More."
    assert doc["legs"] and doc["start"]          # nothing else touched


def test_the_start_prompt_carries_her_the_outfit_and_the_partner(monkeypatch):
    import sourcemode.assets.render as R
    monkeypatch.setattr(R, "appearance_clause",
                        lambda c: {"nadia": "a young woman with long black hair",
                                   "kiki": "a young woman with shoulder-length brown hair"}.get(c, ""))
    p = VT.start_prompt(VT.load("velvet_lounge"), "nadia")
    assert p.startswith("nadia, a young woman with long black hair, a wide point-of-view photo")
    assert "lilac satin slip mini dress" in p and p.endswith("sharp focus.")
    duo = VT.start_prompt(VT.load("club_duo"), "nadia", "kiki")
    assert "a young woman with shoulder-length brown hair a few steps behind her" in duo


def test_a_start_frame_renders_at_its_sources_aspect():
    assert VT.size_for(VT.load("velvet_lounge")) == (1664, 928)
    assert VT.size_for(VT.load("desk_toy")) == (1024, 1536)
    assert VT.size_for(VT.load("harness_tease")) == (1024, 1536)


def test_an_outfit_still_is_a_regular_portrait_in_the_clips_outfit_and_setting():
    from sourcemode.assets.render import shot_prompt
    t = VT.load("house_call")
    slot = VT.outfit_slot(t, 0)
    p = shot_prompt("mei", slot, "mei", backdrop=slot["setting"])
    assert "white nurse mini dress with red trim" in p and "white modern open-plan home" in p
    assert "point-of-view" not in p and "boxer" not in p      # not the start frame's composition
    assert "a standing portrait picture" in p


def test_the_video_tab_shows_her_newest_120_keepers():
    import inspect
    from sourcemode import video as V
    assert inspect.signature(V.keepers).parameters["limit"].default == 120
