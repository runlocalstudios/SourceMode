"""The two game-asset packs on the shoots tab, and the one prompt builder.

The thing most worth protecting here is that adding the selfie pack did NOT
change what a wardrobe-pack slot renders. `shot_prompt` grew four optional
composition overrides so a selfie would not have to grow a second builder; if
any of them ever starts applying by default, a shipped pack silently changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sourcemode.assets import render, selfies
from sourcemode.assets.render import shot_prompt
from sourcemode.assets.shoots import (
    BY_ID, CATALOG, buckets, estimate_seconds, plan_path, resolve, total_shots)


def test_game_assets_group_is_first_and_holds_exactly_the_two_packs():
    bs = buckets()
    assert bs[0]["bucket"] == "game"
    assert bs[0]["label"] == "Game assets"
    assert [s["id"] for s in bs[0]["shoots"]] == ["pack28", "selfies"]


def test_the_wardrobe_pack_is_one_shot_per_look_not_four():
    # It used to render 4 candidates for every look and keep one: 112 shots to
    # ship 28, every time. Judge one and re-roll the rejects instead.
    assert BY_ID["pack28"].shots == 28
    assert BY_ID["selfies"].shots == 24 == selfies.TOTAL
    assert total_shots(["pack28", "selfies"]) == 52


def fake_plan(n_work: int = 5) -> dict:
    """A plan_28 shaped like the real ones: distinct outfit and hair per look."""
    hairs = ("her hair worn loose", "her hair pulled back in a high ponytail",
             "her hair up in a messy bun", "her hair half-up")
    cats = {"casual": 7, "workout": 4, "fancy_dining_gallery": 4, "fancy_town": 4,
            "casual_date": 4, "work": n_work}
    return {"categories": {cat: {"lookCount": n, "looks": [
        {"look": i + 1, "id": f"{cat}_{i + 1:02d}", "outfit": f"the {cat} outfit {i + 1}",
         "hair": hairs[(i + len(cat)) % len(hairs)]} for i in range(n)]}
        for cat, n in cats.items()}}


LOOKS = selfies.check_looks(fake_plan())
WORK = ("bright even light, in the lobby of a precinct, on a quick break",
        "bright even light, in the lobby of a precinct, in a quiet corner on her break")


@pytest.fixture
def planned(monkeypatch):
    """Every character has the fake plan and a job scene, so a shoot's plan can
    be built for anyone without the outputs folder or the game repo."""
    monkeypatch.setattr(selfies, "looks_for", lambda c: LOOKS)
    monkeypatch.setattr(selfies, "work_settings", lambda c: WORK)
    monkeypatch.setattr(selfies, "set_for", lambda c, path=None, mode=None: "A" * 24)


def test_selfie_pack_is_the_agreed_mix():
    # Jeremy, 2026-10-22: tied to her pack - 7 casual / 4 casual date / 4 fancy
    # dining / 4 fancy town / 2 work (looks 1 and 2) / 3 intimate, still 24.
    assert selfies.COUNTS == {"selfie_casual": 7, "selfie_casual_date": 4,
                              "selfie_fancy_dining_gallery": 4, "selfie_fancy_town": 4,
                              "selfie_work": 2, "selfie_intimate": 3}
    s = selfies.slots(LOOKS, WORK)
    assert len({x["id"] for x in s}) == 24 == selfies.TOTAL
    # `look` drives the expression table and the body yaw, so it must not repeat
    # or all 24 selfies come back with one face and one turn.
    assert sorted(x["look"] for x in s) == list(range(1, 25))
    assert all(x["setting"] and x["outfit"] and x["hair"] for x in s)


def test_a_tied_selfie_wears_the_same_numbered_look_and_is_named_after_it():
    """Jeremy, 2026-10-22: "if she texts you after a date, it's for the outfit
    she was just wearing ON the date ... the same hair style she had on the
    date." The id carries the look so the game maps by name, not position."""
    s = {x["id"]: x for x in selfies.slots(LOOKS, WORK)}
    for cat, n in selfies.GROUPS:
        for i in range(n):
            x = s[f"selfie_{cat}_{i + 1:02d}"]
            assert x["look_id"] == f"{cat}_{i + 1:02d}"
            assert x["outfit"] == LOOKS[cat][i]["outfit"] and x["hair"] == LOOKS[cat][i]["hair"]
    assert s["selfie_work_01"]["setting"] == WORK[0] and s["selfie_work_02"]["setting"] == WORK[1]
    # the intimate three are not tied to any look and still draw from the sets
    assert all(s[f"selfie_intimate_{r + 1:02d}"]["look_id"] is None for r in range(3))


def test_date_selfie_timing_is_fixed_by_look_number_for_all_three_date_categories():
    """The game relies on it: looks 1, 2 and 4 are her just home afterwards,
    look 3 is her getting ready in the bathroom mirror. Never sent before the
    date - the "before" shot is sent after, explained."""
    s = {x["id"]: x for x in selfies.slots(LOOKS, WORK)}
    for cat in selfies.DATE_GROUPS:
        t = [s[f"selfie_{cat}_{i:02d}"]["timing"] for i in (1, 2, 3, 4)]
        assert t == ["after", "after", "before", "after"], cat
        assert "edge of her bed" in s[f"selfie_{cat}_01"]["setting"]
        assert "curled up on the sofa" in s[f"selfie_{cat}_02"]["setting"]
        assert s[f"selfie_{cat}_03"]["stance"] is selfies.STANCE_MIRROR
        assert "bathroom mirror" in s[f"selfie_{cat}_03"]["setting"]
        assert "walk-in closet" in s[f"selfie_{cat}_04"]["setting"]
        assert s[f"selfie_{cat}_04"]["framing"] == selfies.WAIST_FRAMING
        # the same four moments for every date category, by design
        assert [s[f"selfie_{cat}_{i:02d}"]["setting"] for i in (1, 2, 3, 4)] == \
            [s[f"selfie_casual_date_{i:02d}"]["setting"] for i in (1, 2, 3, 4)]
    for x in s.values():
        if x["timing"] is None:
            assert x["category"] not in {f"selfie_{c}" for c in selfies.DATE_GROUPS}
        assert "feet" not in x["setting"] and "full body" not in x["setting"]


def test_the_manifest_tells_the_game_the_look_and_the_timing_of_every_file():
    m = selfies.manifest(selfies.slots(LOOKS, WORK))
    assert len(m) == 24 and {x["file"] for x in m} == {f"{x['id']}.png" for x in selfies.slots(LOOKS, WORK)}
    d3 = next(x for x in m if x["file"] == "selfie_fancy_town_03.png")
    assert d3 == {"file": "selfie_fancy_town_03.png", "category": "fancy_town",
                  "look_id": "fancy_town_03", "timing": "before",
                  "outfit": LOOKS["fancy_town"][2]["outfit"], "hair": LOOKS["fancy_town"][2]["hair"]}
    assert next(x for x in m if x["file"] == "selfie_intimate_01.png")["look_id"] is None


def test_a_short_or_missing_plan_refuses_rather_than_inventing_an_outfit(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="1 work looks"):
        selfies.check_looks(fake_plan(n_work=1), "zara")
    from sourcemode import config as C
    monkeypatch.setattr(C, "load_config", lambda: {})
    monkeypatch.setattr(C, "outputs_dir", lambda cfg: tmp_path)
    with pytest.raises(ValueError, match="no approved wardrobe pack"):
        selfies.looks_for("zara")


def test_the_work_selfies_use_her_job_scene_from_the_game_schedule(monkeypatch):
    from sourcemode.assets import influencer as I
    monkeypatch.setattr(I, "_places", lambda c: (["policeStation"], []))
    a, b = selfies.work_settings("zara")
    assert a.startswith(I.PLACES["policeStation"]["job"][0][0]) and a.endswith("on a quick break")
    assert b.startswith(I.PLACES["policeStation"]["job"][0][0]) and "on her break" in b
    monkeypatch.setattr(I, "_places", lambda c: ([], []))
    assert selfies.work_settings("nobody") == (f"{selfies.WORK_FALLBACK}, on a quick break",
                                               f"{selfies.WORK_FALLBACK}, in a quiet corner on her break")


def test_a_pack_slot_renders_exactly_what_it_did_before_the_selfie_overrides(monkeypatch):
    slot = {"id": "casual_01", "look": 1, "category": "casual", "pose": "standing",
            "outfit": "a blue sundress", "hair": "her hair worn loose"}
    p = shot_prompt("nobody", slot)
    assert "a standing portrait picture from the mid-thigh up" in p
    assert "phone selfie" not in p and "No studio lighting" not in p
    # and the contract arm, still selectable, is untouched by the selfie overrides
    monkeypatch.setattr(render, "PROMPT_STYLE", "contract")
    p = shot_prompt("nobody", slot)
    assert "New photorealistic standing portrait of" in p
    assert p.endswith("No profiles, rear views, seated poses, or off-camera gaze.")
    assert "phone selfie" not in p


def test_a_selfie_is_not_described_as_a_standing_portrait_that_forbids_sitting():
    # Half the pack is shot sitting on a bed or a sofa. The wardrobe pack's
    # closing line rules that out, so a selfie slot replaces it.
    sitting = [x for x in selfies.slots(LOOKS, WORK) if "sitting" in x["stance"]]
    assert sitting, "the pack should carry seated selfies"
    p = shot_prompt("nobody", sitting[0], backdrop=sitting[0]["setting"])
    assert "a selfie, " in p and "standing portrait" not in p
    assert "seated poses" not in p
    assert sitting[0]["stance"] in p and sitting[0]["framing"] in p
    assert "this is a casual selfie she took herself" in p
    # The backdrop is her real room - a selfie never gets the chroma plate.
    assert "#FF00FF" not in p


def test_the_phone_is_in_the_picture_only_in_a_mirror_selfie():
    """Jeremy, 2026-10-17: "She's holding a phone and then outstretching another
    phone. You shouldn't see the phone in a selfie photo unless it's a mirror
    selfie." Gabi's pack rendered a phone in hand on most of the non-mirror
    slots because every slot named it."""
    mirror = [x for x in selfies.slots(LOOKS, WORK) if x["stance"] is selfies.STANCE_MIRROR]
    plain = [x for x in selfies.slots(LOOKS, WORK) if x["stance"] is not selfies.STANCE_MIRROR]
    # look 3 of each date category is the bathroom mirror, getting ready
    assert len(mirror) == 3 and len(plain) == 21
    for slot in plain:
        p = shot_prompt("nobody", slot, backdrop=slot["setting"])
        assert "phone" not in p.lower(), slot["id"]
        # 2026-10-21, casey: "the camera held" drew a device too. The viewpoint
        # is described, never the thing taking the picture.
        assert "camera held" not in p.lower(), slot["id"]
        assert "a selfie, " in p
        assert "phone" in slot["negative"] and "phone frame" in slot["negative"]
        assert "camera" in slot["negative"]
    for slot in mirror:
        p = shot_prompt("nobody", slot, backdrop=slot["setting"])
        assert "a mirror selfie, " in p and "phone held at chest height" in p
        # The picture is the reflection; the mirror is never behind her.
        assert "her reflection" in p and "facing a full-length mirror" in p
        assert "mirror behind her" in slot["negative"] and "phone" not in slot["negative"]


def test_the_mirror_shoot_is_mirror_selfies_with_the_phone_in_every_shot():
    # Sienna's mirror shoot (2026-10-13) rendered the two phoneless poses as
    # plain bathroom portraits. Every pose holds the phone now and the shot
    # type says what the picture is.
    for slot in BY_ID["mirror"].plan(character="nobody"):
        p = shot_prompt("nobody", slot, backdrop=slot["setting"])
        assert "a mirror selfie, " in p and "phone" in slot["stance"]
        assert selfies.MIRROR_FRAMING in p and "standing portrait" not in p


def test_the_selfie_prompt_never_names_the_outstretched_arm():
    # Measured at 1024x1536, n=4: bare 3/4 keep, geometric 3/4, "her arm
    # outstretched and visible in the frame" 1/4. It is the arm that lost.
    for slot in selfies.slots(LOOKS, WORK):
        p = shot_prompt("nobody", slot, backdrop=slot["setting"])
        assert "outstretched" not in p


def test_a_mixed_job_is_priced_at_two_rates_not_one():
    # 112 pack shots at the asset rate + 24 selfies at the sweep rate. Charging
    # the whole thing at the sweep rate understated it by over an hour.
    secs = estimate_seconds(["pack28", "selfies"], 75.0, 116.0)
    assert secs == pytest.approx(28 * 116.0 + 24 * 75.0)
    assert estimate_seconds(["boudoir"], 75.0, 116.0) == pytest.approx(12 * 75.0)


def test_only_the_wardrobe_pack_needs_a_plan_on_disk(tmp_path):
    assert plan_path(BY_ID["pack28"], "zara", tmp_path) == (
        tmp_path / "game-assets" / "zara" / "plan_28.json")
    for s in CATALOG:
        if s.id != "pack28":
            assert plan_path(s, "zara", tmp_path) is None


def test_a_character_with_no_wardrobe_plan_is_blocked_with_a_reason(tmp_path, monkeypatch):
    from sourcemode.assets import lora

    monkeypatch.setattr(lora, "outputs_dir", lambda cfg: tmp_path, raising=False)
    import sourcemode.config as config

    monkeypatch.setattr(config, "outputs_dir", lambda cfg: tmp_path)
    blocked = lora.blocked_shoots({}, "nobody")
    assert "pack28" in blocked
    assert "wardrobe plan" in blocked["pack28"]
    assert "selfies" not in blocked, "the selfie pack is fully specified, never blocked"

    # ...and present once the plan exists.
    p = tmp_path / "game-assets" / "nobody" / "plan_28.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"character": "nobody"}), encoding="utf-8")
    assert lora.blocked_shoots({}, "nobody") == {}


def test_resolve_still_refuses_a_typo():
    with pytest.raises(KeyError):
        resolve(["pack28", "pack_28"])


def test_the_queue_row_only_claims_training_and_sweep_for_a_training_job():
    # The shoots and asset jobs read "24m of GPU time once it starts - training
    # + sweep", with two blank durations, describing work they do not do.
    # Since 2026-10-05 the queue row shows no split at all - one duration and
    # what the job renders - so no row can describe work it is not doing.
    js = Path("sourcemode/monitor/queue_page.py").read_text(encoding="utf-8")
    i = js.index("function jobRow(")
    row = js[i:js.index("function acts(", i)]
    assert "training + " not in row and "sweep" not in row


# --- per-character hair -----------------------------------------------------

def test_a_box_braided_character_is_never_asked_for_loose_hair(monkeypatch):
    """Jeremy, 2026-10-04: Tess's braid is a specific protective style, not the
    generic braid the shared vocabulary means.

    She wears long box braids in every training frame. The shared rotation
    opens with "her hair worn loose", which would have reached a quarter of
    every shoot and every selfie. That is the gabi collision in reverse - her
    set is ~90% loose hair and prompting a braid kept 20%.
    """
    from sourcemode.assets.wardrobe import DEFAULT_HAIR, hair_options

    tess = hair_options("tess")
    assert tess != DEFAULT_HAIR
    # The braids are NOT named - Jeremy, 2026-10-04: "I don't want you to define
    # the box braids because that's part of the character... We want it to
    # recognize that that is just her." They are in all 62 training frames, so
    # an uncaptioned, unprompted constant binds to the trigger and she has them.
    # What this list does is keep the word "loose" out of her prompts.
    assert not any("braid" in h for h in tess)
    assert not any("loose" in h or "down and flowing" in h for h in tess)

    hairs = {s["hair"] for s in BY_ID["boudoir"].plan(character="tess")}
    assert not any("loose" in h for h in hairs)
    # the tied selfies wear the plan's hair, which was written from her own
    # vocabulary; the intimate three still rotate it
    monkeypatch.setattr(selfies, "looks_for", lambda c: LOOKS)
    monkeypatch.setattr(selfies, "work_settings", lambda c: WORK)
    monkeypatch.setattr(selfies, "set_for", lambda c, path=None, mode=None: "A" * 24)
    hairs = {s["hair"] for s in BY_ID["selfies"].plan(character="tess") if s["look_id"] is None}
    assert hairs and not any("loose" in h for h in hairs)


def test_a_character_with_no_list_keeps_the_shared_rotation():
    from sourcemode.assets.wardrobe import DEFAULT_HAIR, hair_options

    assert hair_options("zara") == DEFAULT_HAIR
    assert hair_options("nobody-at-all") == DEFAULT_HAIR
    # and passing no character at all leaves a shoot exactly as it was
    assert BY_ID["boudoir"].plan()[0]["hair"] == DEFAULT_HAIR[0]


def test_the_braid_style_is_named_nowhere_at_all():
    """Not in the per-look clause, and not in her appearance clause either.

    Jeremy, 2026-10-04: "I don't want you to define the box braids because
    that's part of the character. We don't want the LoRA to exclude that. We
    want it to recognize that that is just her." Naming a trait is exactly what
    keeps it variable (assetgen rule b); leaving a constant unnamed is what
    binds it to the trigger.
    """
    from sourcemode.assets.appearance import clause
    from sourcemode.assets.wardrobe import hair_options

    assert "braid" not in clause("tess").lower()
    assert not any("braid" in h.lower() for h in hair_options("tess"))


# --- long hair and a bun cannot share a prompt ------------------------------

def test_an_up_style_strips_the_length_from_the_identity_clause():
    """Jeremy, 2026-10-04: "you cannot put long hair in the same prompt as a
    messy bun. Otherwise, you get those weird results."

    Measured before fixing: every one of the 10 bun-prompted shots across
    geena's and cindy's four sets rendered the full length hanging down WITH a
    bun on top. He kept 3 of 10, against 25 of 30 for every other prompt in the
    same sets - 30% against 83%.
    """
    from sourcemode.assets.render import shot_prompt

    base = {"id": "x", "look": 1, "category": "casual", "pose": "standing",
            "outfit": "a black bralette"}
    down = shot_prompt("cindy", {**base, "hair": "her hair worn loose"})
    up = shot_prompt("cindy", {**base, "hair": "her hair up in a messy bun"})

    ident = lambda p: p.split("Crop:")[0]  # noqa: E731
    assert "very long" in ident(down), "a down style keeps her length"
    assert "very long" not in ident(up), "an up style must not also say long"
    # colour survives: it is the identity trait the base model will not volunteer
    assert "platinum-blonde" in ident(up)
    assert "her hair up in a messy bun" in up


def test_every_up_style_in_the_shared_rotation_is_detected():
    from sourcemode.assets.appearance import is_up_style
    from sourcemode.assets.wardrobe import DEFAULT_HAIR

    flags = [is_up_style(h) for h in DEFAULT_HAIR]
    assert flags == [False, True, True, True, False], DEFAULT_HAIR
    assert not is_up_style("a bunch of flowers behind her")


def test_short_hair_keeps_its_length_because_it_does_not_fight_a_bun():
    # priya is the only short-haired character; dropping "chin-length" would
    # lose the trait, and a bob was never the thing colliding with an updo.
    from sourcemode.assets.appearance import clause, drop_length

    assert "chin-length" in drop_length(clause("priya"))


def test_no_record_still_asserts_long_hair_under_an_up_style():
    import json
    import re
    from pathlib import Path

    from sourcemode.assets.appearance import clause, drop_length

    d = json.loads((Path("../characters/appearance.json")).read_text(encoding="utf-8"))
    for c in (k for k in d if not k.startswith("_")):
        assert not re.search(r"\b(very long|long)\b", drop_length(clause(c)), re.I), c


def test_makeup_reaches_every_path_from_the_one_builder(planned):
    """Jeremy, 2026-10-04, on zara's pack: "I think we should add beautiful and
    natural makeup to the prompts... Some of those Zara pictures just look
    frumpy." Stated once so the pack, the shoots, the selfies and the eval all
    get it - that is what the single builder is for.
    """
    from sourcemode.assets.render import MAKEUP, shot_prompt

    pack = {"id": "casual_01", "look": 1, "category": "casual", "pose": "standing",
            "outfit": "a sundress", "hair": "her hair worn loose"}
    assert f", {MAKEUP}, " in shot_prompt("nobody", pack)
    sit = {**pack, "pose": "sitting"}
    assert MAKEUP in shot_prompt("nobody", sit)
    for sid in ("boudoir", "selfies"):
        slot = BY_ID[sid].plan(character="nobody")[0]
        assert MAKEUP in shot_prompt("nobody", slot, backdrop=slot["setting"])
    # and a slot may ask for less - a gym shot or a just-woken selfie
    assert ", none, bare skin, " in shot_prompt(
        "nobody", {**pack, "makeup": "none, bare skin"})


def test_a_pack_resumes_but_re_renders_when_the_prompt_changed():
    """Resumability must not mean "a prompt fix does nothing".

    `render_plan` skips any shot whose file and sidecar exist, which is what
    lets a pack survive a crash. Measured 2026-10-04: with the makeup clause
    added, re-running zara's pack would have re-rendered 3 of 28 looks and
    handed back 25 built from the superseded prompt.
    """
    from sourcemode.assets.render import needs_rerender

    assert needs_rerender({"prompt": "old words"}, "new words")
    assert not needs_rerender({"prompt": "same words"}, "same words")
    # a sidecar from before prompts were recorded is left alone, not re-rolled
    assert not needs_rerender({}, "anything")
    assert not needs_rerender({"prompt": ""}, "anything")


def test_the_intimate_three_differ_by_set_and_the_rest_ignore_the_pick():
    """Jeremy, 2026-10-21: every girl had the same black-shirt, gold-chains
    cafe selfie. The tied 21 now differ by her pack; the intimate three still
    draw from four sets by her pick, and no set names the phone."""
    tied = lambda s: [(x["outfit"], x["setting"]) for x in s if x["look_id"] is None]  # noqa: E731
    seen = set()
    for letter in "ABCD":
        s = selfies.slots(LOOKS, WORK, letter)
        assert [x["id"] for x in s] == [x["id"] for x in selfies.slots(LOOKS, WORK, "A")]
        assert [x for x in s if x["look_id"]] == [x for x in selfies.slots(LOOKS, WORK, "A") if x["look_id"]]
        for x in s:
            if x["stance"] is not selfies.STANCE_MIRROR:
                assert "phone" not in (x["outfit"] + x["setting"]).lower()
        seen |= set(tied(s))
    assert len(seen) == 4 * 3
    # a 24-letter mix reads the intimate letters at the intimate positions
    mix = "A" * 21 + "BCD"
    assert tied(selfies.slots(LOOKS, WORK, mix)) == [
        tied(selfies.slots(LOOKS, WORK, l))[r] for r, l in enumerate("BCD")]


def test_had_selfies_means_rendered_images_not_a_folder(tmp_path, monkeypatch):
    # 2026-10-22: `any(d.glob(...) for d in ...)` was true for the generator
    # itself, so every character shot on 10-21 was pinned to set A.
    from sourcemode import config as C
    monkeypatch.setattr(C, "ENGINE_ROOT", tmp_path / "engine")
    d = tmp_path / "library" / "zara" / "2026-10-22_selfies_selfies"
    d.mkdir(parents=True)
    assert selfies._had_selfies("zara") is False
    (d / "selfie_casual_01.png").write_bytes(b"")
    assert selfies._had_selfies("zara") is True


def test_a_character_keeps_her_selfie_mix_and_old_packs_stay_on_set_a(tmp_path, monkeypatch):
    f = tmp_path / "picks.json"
    monkeypatch.setattr(selfies, "_had_selfies", lambda c: c == "bianca")
    a = selfies.set_for("newgirl", path=f)
    assert len(a) == 24 and set(a) <= set("ABCD") and len(set(a)) > 1
    assert selfies.set_for("newgirl", path=f) == a          # a re-roll gets the same prompts
    assert selfies.set_for("bianca", path=f) == "A" * 24
    r1 = selfies.set_for("r1", path=f, mode="rotate")
    r2 = selfies.set_for("r2", path=f, mode="rotate")
    assert len(set(r1)) == len(set(r2)) == 1 and r1 != r2
