"""A record renders only once Jeremy has confirmed its exact text.

bri's "lighter caramel ends" and jaina's freckles were drafted from photos,
never confirmed, and rendered into both sweeps (2026-10-06).
"""

from __future__ import annotations

import json

import pytest

import sourcemode.assets.appearance as A


@pytest.fixture
def records(tmp_path, monkeypatch):
    p = tmp_path / "appearance.json"
    p.write_text(json.dumps({"x": {"age": 25, "prompt": "a 25-year-old woman with red hair",
                                   "negative": "no bangs"}}), encoding="utf-8")
    monkeypatch.setattr(A, "APPEARANCE", p)
    monkeypatch.setattr(A, "_cache", None)
    yield p
    A.reload()


def test_an_unconfirmed_record_is_refused_like_a_missing_one(records):
    r = A.check("x")
    assert not r["ok"] and any(m.startswith("confirmed") for m in r["missing"])


def test_confirm_writes_his_text_and_passes(records):
    A.confirm("x", {"prompt": "a 25-year-old woman with  black hair", "negative": ""})
    rec = json.loads(records.read_text(encoding="utf-8"))["x"]
    assert rec["prompt"] == "a 25-year-old woman with black hair"
    assert "negative" not in rec              # an empty field is cleared, not kept
    assert A.confirmed("x") and A.check("x")["ok"]


def test_any_later_edit_unconfirms_it(records):
    A.confirm("x", {"prompt": "a 25-year-old woman with black hair"})
    doc = json.loads(records.read_text(encoding="utf-8"))
    doc["x"]["prompt"] += " and light freckles"
    records.write_text(json.dumps(doc), encoding="utf-8")
    A.reload()
    assert not A.confirmed("x")


def test_a_note_edit_does_not_unconfirm(records):
    A.confirm("x", {"prompt": "a 25-year-old woman with black hair"})
    doc = json.loads(records.read_text(encoding="utf-8"))
    doc["x"]["_note"] = "a remark"
    records.write_text(json.dumps(doc), encoding="utf-8")
    A.reload()
    assert A.confirmed("x")


def test_an_empty_prompt_cannot_be_confirmed(records):
    with pytest.raises(ValueError):
        A.confirm("x", {"prompt": "   "})


def test_render_age_overrides_and_blank_restores(records):
    A.confirm("x", {"prompt": "a woman with red hair", "age": "29"})
    assert json.loads(records.read_text(encoding="utf-8"))["x"]["age"] == 29
    assert A.age_of("x") == 29
    A.confirm("x", {"prompt": "a woman with red hair", "age": ""})
    assert "age" not in json.loads(records.read_text(encoding="utf-8"))["x"]
    with pytest.raises(ValueError):
        A.confirm("x", {"prompt": "a woman with red hair", "age": "15"})


def test_state_age_off_leaves_age_to_the_lora(records):
    """cat, 2026-10-07: age only where it pushes young or old."""
    A.confirm("x", {"prompt": "a woman with red hair", "state_age": False})
    assert A.clause("x") == "a woman with red hair"
    A.confirm("x", {"prompt": "a woman with red hair", "state_age": True})
    assert A.clause("x").startswith("a 25-year-old")
