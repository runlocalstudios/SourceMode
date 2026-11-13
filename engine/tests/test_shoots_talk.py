"""The talk shoot: Jeremy's own LoRA giving a talk (2026-11-12). One outfit, one
room, twelve poses, built in his pronouns through the one prompt builder."""
import re

from sourcemode.assets import shoots as S
from sourcemode.assets.render import shot_prompt


def _plan():
    sh = S.BY_ID["talk_office"]
    return sh, sh.plan(character="jeremy", outfit=sh.outfits[0])


def test_twelve_shots_one_outfit_one_room():
    sh, plan = _plan()
    assert sh.man and len(plan) == 12 and S.total_shots(["talk_office"]) == 12
    assert len(sh.outfits) == 1 and {s["outfit"] for s in plan} == {sh.outfits[0]}
    assert {s["setting"] for s in plan} == {S.TALK_OFFICE}
    assert len({s["tag"] for s in plan}) == 12


def test_every_prompt_is_his_and_never_names_hair_makeup_or_her():
    _, plan = _plan()
    for slot in plan:
        p = shot_prompt("jeremy", slot, "jeremy", backdrop=slot["setting"])
        assert p.startswith("jeremy, a portrait picture") and " of a man, " in p
        assert re.search(r"\b(?:his|he)\b", p) and not re.search(r"\b(?:her|she)\b", p)
        assert not re.search(r"hair", p) and "makeup" not in p     # "chair" is not hair
        assert "sport coat" in p and S.TALK_OFFICE in p
        assert p.endswith("Photorealistic, natural skin texture, sharp focus.")


def test_the_poses_vary_his_hands_turn_gaze_and_speech():
    _, plan = _plan()
    text = [shot_prompt("jeremy", s, "jeremy", backdrop=s["setting"]) for s in plan]
    assert sum("mid-sentence" in t for t in text) >= 4          # talking
    assert sum("looks off" in t for t in text) == 2              # at the audience
    assert sum("slightly" in t for t in text) >= 4               # turned, not all frontal
    assert any("pointing" in t for t in text) and any("walks" in t for t in text)
    assert all("from the " in t for t in text)                   # a crop on every shot
    assert all(s["negative"].startswith("other people") for s in plan)


def test_a_womans_slot_is_untouched_by_the_man_flag():
    slot = S.BY_ID["office_desk"].plan(character="nadia", outfit=S.OFFICE_SLUTTY[0])[0]
    assert "man" not in slot
    assert re.search(r"\b(?:her|she)\b", shot_prompt("nadia", slot, "nadia", backdrop=slot["setting"]))
