"""The new-character form, and the gaps it exists to close.

Each test here names a real failure this project recorded. The form is only
worth building if it would have caught them.
"""

from __future__ import annotations

import json

import pytest

from sourcemode.assets.character_new import (
    FIELDS, appearance_clause, appearance_record, create, game_snippet, missing, thin,
    wardrobe_record)

FULL = {
    "character": "nova", "name": "Nova", "age": "27", "ethnicity": "Latina",
    "skin": "olive-tan", "build": "slim and athletic",
    "hair": "very long dark brown hair with a vivid turquoise dyed underlayer",
    "eyes": "dark brown eyes", "bust": "medium", "frame": "slim athletic frame",
    "features": "freckles across her nose", "job": "bartender",
    "style": "edgy downtown", "palette": "black and rust",
    "avoid": "nothing pastel", "negative": "plain brown hair with no colour",
}


def test_every_required_field_is_named_when_blank():
    gaps = missing({})
    assert "Id" in gaps and "Age" in gaps and "Hair" in gaps and "Eyes" in gaps
    assert missing(FULL) == []


def test_the_composed_clause_carries_the_dyed_layer():
    # vivienne swept 90 renders at 0/90 because her record said nothing about
    # the pink, so the prompt asserted "long black hair". The hair field is
    # required and it reaches the clause.
    c = appearance_clause(FULL)
    assert "27-year-old Latina woman" in c
    assert "turquoise dyed underlayer" in c
    assert "dark brown eyes" in c
    assert "olive-tan skin" in c


def test_a_blank_frame_is_never_defaulted():
    # render.py hardcoded "fitted to her tiny frame" for everyone, which was
    # true for amanda and asserted for cici, whose record says curvy.
    rec = appearance_record({**FULL, "frame": ""})
    assert "frame" not in rec
    assert "Frame" in " ".join(thin({**FULL, "frame": ""}))


def test_a_negative_is_carried_onto_the_record():
    # raven's anti-bangs negative lived in the eval and never reached her pack.
    rec = appearance_record(FULL)
    assert rec["negative"] == "plain brown hair with no colour"


def test_thin_warns_without_blocking():
    # Gates annotate; they do not block. A thin record still creates.
    lean = {k: v for k, v in FULL.items() if k not in ("frame", "bust", "style", "job")}
    assert missing(lean) == []
    assert len(thin(lean)) == 4


def test_the_game_snippet_tells_you_to_keep_the_two_ages_equal():
    # Four shipped characters have a structured `age` that disagrees with the
    # prose in their own systemPrompt.
    s = game_snippet(FULL)
    assert "age:             27" in s
    assert "You are Nova, 27" in s
    assert "EQUAL" in s


def test_create_writes_both_records(tmp_path):
    (tmp_path / "appearance.json").write_text("{}", encoding="utf-8")
    (tmp_path / "wardrobe.json").write_text("{}", encoding="utf-8")
    out = create(FULL, characters_dir=tmp_path)
    assert out["written"] == ["appearance.json", "wardrobe.json"]
    app = json.loads((tmp_path / "appearance.json").read_text(encoding="utf-8"))
    ward = json.loads((tmp_path / "wardrobe.json").read_text(encoding="utf-8"))
    assert app["nova"]["age"] == 27
    assert "turquoise" in app["nova"]["prompt"]
    assert ward["nova"]["style"] == "edgy downtown"
    assert ward["nova"]["work"] == "bartender"


def test_the_written_record_satisfies_the_render_preflight(tmp_path, monkeypatch):
    """The whole point: a character created here can be rendered immediately."""
    (tmp_path / "appearance.json").write_text("{}", encoding="utf-8")
    create(FULL, characters_dir=tmp_path)
    rec = json.loads((tmp_path / "appearance.json").read_text(encoding="utf-8"))["nova"]
    from sourcemode.assets.appearance import REQUIRED

    for key in REQUIRED:
        assert rec.get(key), f"{key} is required by the pre-flight and is missing"


def test_creating_over_an_existing_character_is_refused(tmp_path):
    (tmp_path / "appearance.json").write_text('{"nova": {"age": 1}}', encoding="utf-8")
    with pytest.raises(ValueError, match="already has a record"):
        create(FULL, characters_dir=tmp_path)


def test_a_bad_id_is_refused(tmp_path):
    for bad in ("no va", "../nova", "9nova", "", "nova!"):
        with pytest.raises(ValueError):
            create({**FULL, "character": bad}, characters_dir=tmp_path)


def test_a_typed_capital_is_normalised_not_rejected(tmp_path):
    # "Nova" is what someone types; `nova` is the trigger, the dataset prefix
    # and the game id. Normalising is right - refusing would be pedantry.
    (tmp_path / "appearance.json").write_text("{}", encoding="utf-8")
    out = create({**FULL, "character": "Nova"}, characters_dir=tmp_path)
    assert out["character"] == "nova"


def test_every_field_has_a_hint_that_says_why_it_matters():
    # The form's whole value is that someone filling it in understands what
    # goes wrong without each field.
    for key, label, kind, hint in FIELDS:
        assert label and hint, key
        assert kind in ("need", "want")
