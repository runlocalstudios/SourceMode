"""A prompt says nothing about her body beyond her own appearance sentence.

History: `render.py` hardcoded ", fitted to her tiny frame" for everyone
(right for amanda, wrong for cici). A per-character Fit field replaced it,
with a fallback that derived "tiny frame" from `figure` - which is how
vivienne, whose sentence says "slim, slender figure", was being told she had
a tiny frame her description never used. Jeremy, 2026-10-10: "Get rid of the
fit drop down. It's too confusing ... there's no reason to limit it to five
types of frames when we can have somebody with a skinny frame but super wide
hips." The clause, the field and the fallback are gone.
"""

from __future__ import annotations

import json
import re

import pytest

import sourcemode.assets.appearance as A
from sourcemode.assets.appearance import APPEARANCE, CONFIRM_FIELDS, clause
from sourcemode.assets.render import shot_prompt

SLOT = {"id": "casual_01", "look": 1, "category": "casual", "pose": "standing",
        "outfit": "a pleated mini skirt and a cropped tee", "hair": "her hair worn loose"}
CHARS = [k for k in json.loads(APPEARANCE.read_text(encoding="utf-8")) if not k.startswith("_")]


def test_no_body_shape_is_hardcoded_in_the_prompt_builder():
    import inspect

    import sourcemode.assets.render as R

    body = inspect.getsource(R.shot_prompt) + inspect.getsource(R.natural_prompt)
    for shape in ("tiny frame", "curvy frame", "fitted to her", "fitted_clause", "petite", "large bust"):
        assert shape not in body, f"the prompt builder still carries {shape!r}"
    assert not hasattr(R, "fitted_clause") and not hasattr(A, "frame")


@pytest.mark.parametrize("who", CHARS)
def test_the_only_body_text_in_a_prompt_is_her_own_sentence(who):
    p = shot_prompt(who, SLOT, who)
    sentence = clause(who)
    assert not sentence or sentence in p
    # the key backdrop says "nothing else in frame"; his own sentence may say "petite frame"
    rest = p.replace(sentence, "")
    assert "fitted to her" not in p and not re.search(r"\b(?!in\b)\w+ frame\b", rest), p


def test_a_record_with_no_sentence_gets_no_body_text(monkeypatch):
    doc = {"look": {"nobody": {"age": 25, "build": "slim", "figure": "slim, slender frame"}}, "ages": {}}
    monkeypatch.setattr(A, "_load", lambda: doc)
    assert not re.search(r"\b(?!in\b)\w+ frame\b", shot_prompt("nobody", SLOT, "nobody"))


def test_the_fit_field_is_not_a_confirmation_field_and_no_record_carries_it():
    assert CONFIRM_FIELDS == ("prompt", "negative")
    d = json.loads(APPEARANCE.read_text(encoding="utf-8"))
    for k, v in d.items():
        if not k.startswith("_"):
            assert isinstance(v, dict) and "frame" not in v, k


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
