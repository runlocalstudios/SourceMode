"""An asset prompt may not assert a body shape the character's data contradicts.

`render.py` hardcoded ", fitted to her tiny frame" into every character's
prompt. It was written for amanda and is correct for her; it was also being
sent for cici, whose own record reads "curvy", "hourglass", "large bust, full
hips", and would have been sent for marisol and geena.

Same defect as vivienne's prompt saying "long black hair" over a LoRA trained
on pink underlights: explicit text beats a learned association, so a wrong
assertion is worse than silence. Silence is therefore the default.
"""

from __future__ import annotations

import json

import pytest

from sourcemode.assets.appearance import frame
from sourcemode.assets.render import fitted_clause, shot_prompt

SLOT = {"id": "casual_01", "look": 1, "category": "casual", "pose": "standing",
        "outfit": "a pleated mini skirt and a cropped tee", "hair": "her hair worn loose"}


def test_no_body_shape_is_hardcoded_in_the_prompt_builder():
    """The literal that caused this must not come back.

    Scoped to shot_prompt's own body with its docstring removed, because
    fitted_clause's docstring quotes the phrase on purpose to explain it.
    """
    import ast
    import inspect
    import textwrap

    import sourcemode.assets.render as R

    tree = ast.parse(textwrap.dedent(inspect.getsource(R.shot_prompt)))
    fn = tree.body[0]
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)):
        fn.body = fn.body[1:]                      # drop the docstring
    body = ast.unparse(fn)
    for shape in ("tiny frame", "curvy frame", "petite", "large bust"):
        assert shape not in body, f"shot_prompt hard-codes {shape!r}"
    assert "fitted_clause(character)" in body


def test_a_character_with_no_record_is_told_nothing():
    """Before this, EVERY character was told she had a tiny frame.

    Named characters are deliberately not hard-coded here: this test used to
    cite marisol and geena, and broke the day they were documented - which is
    the right outcome for them and the wrong reason for a test to fail. The
    rule is about the absence of a record, so the subject is a name that has
    none and never will.
    """
    for who in ("nobody_who_does_not_exist", "", "a_name_with_no_record"):
        assert frame(who) == ""
        assert fitted_clause(who) == ""
        assert "fitted to her" not in shot_prompt(who or "x", SLOT, who or "x")


@pytest.mark.parametrize(("who", "want"), [("amanda", "tiny"), ("zara", "tiny"),
                                           ("cici", "curvy")])
def test_the_frame_comes_from_the_characters_own_record(who, want):
    assert want in frame(who)
    assert f"fitted to her {want} frame" in shot_prompt(who, SLOT, who)


def test_cici_is_never_called_tiny():
    """Her record says curvy and hourglass; the renderer said tiny."""
    assert "tiny" not in shot_prompt("cici", SLOT, "cici")


def test_a_frame_is_derived_only_from_body_text_that_says_so(tmp_path, monkeypatch):
    """No body text means no frame - the fallback never guesses a default."""
    import sourcemode.assets.appearance as A

    doc = {"look": {"nobody": {"age": 25, "build": "", "figure": ""},
                    "slim_one": {"age": 25, "figure": "slim, slender frame"},
                    "curvy_one": {"age": 25, "build": "curvy", "figure": "hourglass"},
                    "vague_one": {"age": 25, "build": "average", "figure": "normal"}},
           "ages": {}}
    monkeypatch.setattr(A, "_load", lambda: doc)
    assert A.frame("nobody") == ""
    assert A.frame("vague_one") == ""          # unrecognised text is not a guess
    assert A.frame("slim_one") == "tiny frame"
    assert A.frame("curvy_one") == "curvy frame"
    assert A.frame("not_in_the_file") == ""


def test_an_explicit_frame_overrides_the_derivation(monkeypatch):
    import sourcemode.assets.appearance as A

    doc = {"look": {"x": {"age": 25, "build": "curvy", "frame": "tiny frame"}}, "ages": {}}
    monkeypatch.setattr(A, "_load", lambda: doc)
    assert A.frame("x") == "tiny frame"


@pytest.mark.parametrize(("outfit", "want"), [
    ("a pleated pastel-pink mini skirt and a white cropped tee knotted at the waist, white sneakers",
     "a pleated pastel-pink mini skirt and a white cropped tee knotted at the waist"),
    ("a black shirt-dress, black tights, black ankle boots", "a black shirt-dress, black tights"),
    ("a satin bralette and micro skirt with platform boots", "a satin bralette and micro skirt"),
    ("a fitted black cocktail dress", "a fitted black cocktail dress"),
])
def test_footwear_is_dropped_from_a_thigh_up_asset(outfit, want):
    """Jeremy, 2026-10-05: no shoes in a game asset unless he asks."""
    from sourcemode.assets.render import drop_footwear

    assert drop_footwear(outfit) == want
    p = shot_prompt("x", dict(SLOT, outfit=outfit), "x")
    assert "sneakers" not in p and "boots" not in p
    assert "sneakers" in shot_prompt("x", dict(SLOT, outfit=outfit, shoes=True), "x") \
        or "sneakers" not in outfit


def test_the_appearance_file_is_still_valid_json_and_keyed_by_character():
    from sourcemode.assets.appearance import APPEARANCE

    d = json.loads(APPEARANCE.read_text(encoding="utf-8"))
    for k, v in d.items():
        if k.startswith("_"):
            continue
        assert isinstance(v, dict), k
        if "frame" in v:
            assert isinstance(v["frame"], str) and v["frame"].strip(), k
