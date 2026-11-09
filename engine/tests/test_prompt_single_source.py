"""One prompt builder, one appearance record, one negative - for inference.

Three jobs describe a character and they are MEANT to differ: training images
take identity from reference photos and must not describe her in text; captions
must leave identity out so it binds to the trigger; inference from the LoRA
must state every trait the LoRA will not carry. Vivienne's pink had to be absent
from the first two and present in the third.

Within the inference job there is exactly one builder. These tests pin that,
because the second one - a FEATURE dict inside dense_epoch_eval.py with its own
"a woman" subject and no age - is how vivienne was fixed in appearance.json and
still rendered black-haired, and how raven's bangs negative reached the eval and
never her pack.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from sourcemode.assets.appearance import check, clause, negative
from sourcemode.assets.render import character_negative, shot_prompt
from sourcemode.config import ENGINE_ROOT

sys.path.insert(0, str(ENGINE_ROOT / "scripts" / "eval"))

EVAL = ENGINE_ROOT / "scripts" / "eval" / "dense_epoch_eval.py"


def test_the_sweep_prompt_is_his_trimmed_sentence():
    """Jeremy, 2026-10-19: no lighting, makeup, skin, focus or exact outfit. His
    model sentence is scene 00 word for word once her sentence is "a woman"."""
    import sourcemode.assets.render as R
    from asset_scenes import LOOKS, asset_prompts

    real = R.appearance_clause
    R.appearance_clause = lambda character, **_: "a woman"
    try:
        got = asset_prompts("lena")
    finally:
        R.appearance_clause = real
    assert len(got) == len(LOOKS) == 10
    assert got[0] == ("lena, portrait picture of a woman from the mid-thigh up, her body faces the "
                      "camera, she looks directly at the camera and makes a neutral expression, her "
                      "hair worn loose, standing in a kitchen wearing a casual outfit")
    import re

    for p in got:
        for word in ("light", "lighting", "sunlight", "makeup", "skin", "focus", "photorealistic",
                     "beautiful", "sun"):
            assert not re.search(rf"\b{word}\b", p, re.I), f"{word!r} is back in a sweep prompt: {p}"


def test_a_no_hair_sweep_says_nothing_about_her_hair():
    """Jeremy, 2026-11-07: sylvie's bob came out in ponytails and buns because the
    looks asked for them - leave hair out so the sweep shows the LoRA's default."""
    import sourcemode.assets.render as R
    from asset_scenes import asset_prompts

    real = R.appearance_clause
    R.appearance_clause = lambda character, **_: "a woman"
    try:
        bare, full = asset_prompts("lena", hair=False), asset_prompts("lena")
    finally:
        R.appearance_clause = real
    for p in bare:
        assert not re.search(r"\b(hair|ponytail|bun)\b", p), p
    assert bare[0] == full[0].replace("her hair worn loose, ", "")
    assert "--no-hair" in EVAL.read_text(encoding="utf-8")
    assert "--no-hair" in (ENGINE_ROOT / "scripts" / "train_character.ps1").read_text(encoding="utf-8")


def test_the_eval_keeps_no_second_description_of_a_character():
    src = EVAL.read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for forbidden in ("FEATURE = {", "FEATURE_NEG", 'SUBJECT = "a woman"', "LOOK = (",
                      "from favorable_scenes import"):
        assert forbidden not in body, f"dense_epoch_eval.py grew a second source: {forbidden}"
    assert "appearance_negative(" in body
    assert "appearance_check(" in body


def test_the_eval_has_one_scene_set():
    """favorable and standard composed their own prompt. They are shelved, and a
    request for them must stop at the guard rather than silently render."""
    src = EVAL.read_text(encoding="utf-8")
    guard = 'SCENE_SET not in ("asset", "tiebreaker")'
    assert guard in src
    assert "raise SystemExit" in src.split(guard)[1][:400]


def test_every_eval_prompt_carries_her_appearance():
    """The thing the second path lacked: age and the appearance sentence.

    One deliberate subtraction since 2026-10-04: a look that puts the hair UP
    drops the length words, because a prompt asserting long hair and a bun
    renders both - measured 10/10 across geena and cindy. Everything that
    carries identity, the pink included, still has to survive that.
    """
    from asset_scenes import asset_prompts
    from sourcemode.assets.appearance import drop_length

    want = clause("vivienne")
    assert "pink" in want                   # the record is the one that was fixed
    short = drop_length(want)
    assert "pink" in short, "stripping length must never cost an identity trait"
    for p in asset_prompts("vivienne"):
        assert want in p or short in p


@pytest.fixture
def records(tmp_path, monkeypatch):
    """raven with her bangs negative, zara with none - not the live records."""
    import sourcemode.assets.appearance as A
    p = tmp_path / "appearance.json"
    p.write_text(json.dumps({"raven": {"age": 24, "prompt": "a woman with a full fringe",
                                       "negative": "no bangs, centre part"},
                             "zara": {"age": 22, "prompt": "a woman with long dark hair"}}),
                 encoding="utf-8")
    monkeypatch.setattr(A, "APPEARANCE", p)
    monkeypatch.setattr(A, "_cache", None)
    yield p
    A.reload()


def test_the_characters_negative_reaches_the_pack_and_the_eval(records):
    """It used to live only in the eval. Now one accessor feeds both."""
    from sourcemode.config import load_config
    from sourcemode.pose.native import NEGATIVE, build_native_workflow

    neg = negative("raven")
    assert "no bangs" in neg
    assert character_negative("raven") == neg

    nodes = build_native_workflow(load_config(), "plate.png", "x", 1, "t",
                                  lora="sourcemode/x.safetensors", negative_extra=neg)
    blob = json.dumps(nodes)
    assert "no bangs" in blob
    assert NEGATIVE.split(",")[0] in blob          # the shared block is still there

    # the eval composes it the same way, from the same accessor
    src = EVAL.read_text(encoding="utf-8")
    assert "_NEG = appearance_negative(CHAR)" in src
    assert '"NEGATIVE": NEGATIVE + (", " + _NEG if _NEG else "")' in src


def test_a_character_with_no_negative_gets_the_shared_block_unchanged(records):
    from sourcemode.config import load_config
    from sourcemode.pose.native import NEGATIVE, build_native_workflow

    assert negative("zara") == ""
    nodes = build_native_workflow(load_config(), "plate.png", "x", 1, "t",
                                  lora="sourcemode/x.safetensors", negative_extra=negative("zara"))
    assert NEGATIVE in json.dumps(nodes)
    assert "no bangs" not in json.dumps(nodes)


# --- the pre-flight -----------------------------------------------------------

def test_an_undocumented_character_fails_the_preflight():
    r = check("nobody_v9_who_does_not_exist")
    assert r["ok"] is False
    assert any(m.startswith("age") for m in r["missing"])
    assert any(m.startswith("prompt") for m in r["missing"])
    assert r["has_record"] is False


def test_a_documented_character_passes_it(monkeypatch):
    import sourcemode.assets.appearance as A

    rec = {"age": 25, "prompt": "a woman with red hair"}
    rec["confirmed"] = {"fingerprint": A.record_fingerprint(rec)}   # Jeremy confirmed it
    doc = {"look": {"x": rec}, "ages": {}}
    monkeypatch.setattr(A, "_load", lambda: doc)
    r = A.check("x")
    assert r["ok"] is True
    assert r["missing"] == []


def test_the_preflight_warns_without_blocking_on_the_soft_fields(monkeypatch):
    import sourcemode.assets.appearance as A

    rec = {"prompt": "a woman"}
    rec["confirmed"] = {"fingerprint": A.record_fingerprint(rec)}
    doc = {"look": {"y": rec}, "ages": {"y": 30}}
    monkeypatch.setattr(A, "_load", lambda: doc)
    r = A.check("y")
    assert r["ok"] is True                         # age + prompt present, confirmed
    assert not any(w.startswith("frame") for w in r["warnings"])   # no Fit field since 2026-10-10


@pytest.mark.parametrize("who", ["vivienne", "raven", "amanda", "zara"])
def test_the_characters_already_on_disk_pass_or_say_exactly_why(who):
    """Not a guarantee they all pass - a statement that the check is readable."""
    r = check(who)
    for m in r["missing"]:
        assert " - " in m, "a missing field must say what it is and why it matters"


def test_the_preflight_flag_does_not_land_in_a_positional_slot():
    """dense_epoch_eval reads argv by index; a bare flag left in argv shifts
    every positional after it. The exact bug class that once killed a job four
    seconds after it had waited seven hours for the card."""
    src = EVAL.read_text(encoding="utf-8")
    m = re.search(r"_BARE = \{([^}]*)\}", src)
    assert m and '"--allow-incomplete-appearance"' in m.group(1) and '"--no-description"' in m.group(1)
    assert '"--with-description"' in m.group(1)
    assert re.search(r"elif _a in _BARE:\s*\n\s*_BARESEEN\.add\(_a\)", src)


def test_the_sweep_renders_trigger_and_scene_only_unless_asked_for_her_sentence():
    """Jeremy, 2026-10-17: "I only want you to use the prompt and the trigger
    word. I don't want you to incorporate the description of the character."
    The default arm replaces her appearance clause with the sex anchor; only
    --with-description puts the sentence back. The preflight must know the flag
    too, or it would eat the positional after it."""
    src = EVAL.read_text(encoding="utf-8")
    assert re.search(r'WITH_DESCRIPTION = "--with-description" in _BARESEEN\s*\n'
                     r'if not WITH_DESCRIPTION:\s*\n(?:.*\n){1,4}\s*_render\.appearance_clause = '
                     r'lambda character, \*\*_: young\("a woman", age_of\(character\)\)',
                     src)
    assert '"no_description": not WITH_DESCRIPTION' in src
    from sourcemode.gpu.preflight import _positional
    assert _positional(["python", "x.py", "a", "--with-description", "b"]) == ["python", "x.py", "a", "b"]


def test_a_mans_sweep_never_says_woman_she_her_or_dress():
    """Jeremy, 2026-11-07: his own sweep rendered 90 women - every scene said
    "a woman" and the gender check called 0/90 male "clean"."""
    from asset_scenes import LOOKS, asset_prompts

    got = asset_prompts("jeremy", man=True)
    assert len(got) == len(LOOKS)
    for p in got:
        assert "a man" in p and " he looks" in p
        assert not re.search(r"\b(woman|she|her|dress|hair|ponytail|bun|flirty)\b", p), p
    src = EVAL.read_text(encoding="utf-8")
    assert 'captions_say_his(CKPT.parent / "image_src")' in src and "Is this him?" in src


def test_a_mans_set_is_read_from_his_captions(tmp_path):
    """The first cut matched "he" inside "the" and read every set as tied, so
    jeremy's second sweep was women again (2026-11-07). Behaviour, not presence."""
    from asset_scenes import captions_say_his

    man, woman = tmp_path / "m", tmp_path / "w"
    man.mkdir(); woman.mkdir()
    for i, (m, w) in enumerate([
        ("jeremy, the kitchen, turned toward his left, wearing the grey shirt",
         "nat, the kitchen, turned toward her left, wearing the grey shirt"),
        ("jeremy, facing the camera, wearing a suit, in the office",
         "nat, facing the camera, wearing a dress, in the office, there"),
        ("jeremy, his hands in his pockets, at the beach",
         "nat, her hair worn loose, at the beach, other weather")]):
        (man / f"src_{i}.txt").write_text(m, encoding="utf-8")
        (woman / f"src_{i}.txt").write_text(w, encoding="utf-8")
    assert captions_say_his(man) is True
    assert captions_say_his(woman) is False


def test_a_mans_tiebreaker_is_his_twenty_slots():
    """Jeremy, 2026-11-08: "run tiebreaker on Jeremy epochs 23 and 24"."""
    from asset_scenes import TIEBREAKER, tiebreaker_prompts

    got = tiebreaker_prompts("jeremy", man=True)
    assert len(got) == len(TIEBREAKER) == len(set(got)) == 20
    for p in got:
        assert p.startswith("jeremy, portrait picture of a man") and " he looks" in p
        assert not re.search(r"\b(woman|girl|she|her|dress|skirt|blouse|hair|ponytail)\b", p), p
    assert "tiebreaker_prompts(TRIGGER, man=MAN)" in EVAL.read_text(encoding="utf-8")


def test_young_woman_unless_she_is_over_30():
    """Jeremy, 2026-11-08: "woman" aged the photos, "girl" made them children -
    "young woman for all"."""
    from sourcemode.assets.appearance import young

    assert young("a woman with a slim figure", 18) == "a young woman with a slim figure"
    assert young("a young woman with red hair", 22) == "a young woman with red hair"
    assert young("a beautiful girl with a medium build", 24) == "a beautiful young woman with a medium build"
    assert young("A woman and two girls", 25) == "A young woman and two young women"
    assert young("a 25-year-old woman with red hair", 25) == "a 25-year-old woman with red hair"
    # fiona's record, 2026-11-09: an age already given with "young" stays as written
    assert young("an 18-year-old young woman with a petite figure", 18) == "an 18-year-old young woman with a petite figure"
    assert young("a woman with red hair", None) == "a young woman with red hair"
    assert young("a young woman with red hair", 31) == "a woman with red hair"
    assert young("the womanly figure", 20) == "the womanly figure"


def test_the_sweep_anchor_and_her_clause_say_young_woman(records):
    """The records keep his words (and his confirmation); the prompt says young woman."""
    import sourcemode.assets.appearance as A

    A.reload()
    assert clause("zara") == "a young woman with long dark hair"
    assert "girl" not in clause("raven")