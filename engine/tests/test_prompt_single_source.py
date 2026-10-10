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


def test_the_eval_renders_exactly_what_the_pack_renders():
    """asset_prompts() is shot_prompt() per look with a real setting swapped in
    for the key backdrop. True by construction today; pinned so an inlined copy
    cannot drift."""
    from asset_scenes import LOOKS, SETTINGS, asset_prompts

    got = asset_prompts("amanda")
    assert len(got) == len(LOOKS)
    for i, look in enumerate(LOOKS):
        want = shot_prompt("amanda", dict(look, pose="standing"),
                           backdrop=SETTINGS[i % len(SETTINGS)])
        assert got[i] == want, f"look {look['id']} drifted from shot_prompt"


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


def test_the_characters_negative_reaches_the_pack_and_the_eval():
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


def test_a_character_with_no_negative_gets_the_shared_block_unchanged():
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

    rec = {"age": 25, "prompt": "a woman with red hair", "frame": "curvy frame"}
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
    assert any(w.startswith("frame") for w in r["warnings"])


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
    assert re.search(r"elif _a in _BARE:\s*\n\s*_BARESEEN\.add\(_a\)", src)
