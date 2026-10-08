"""The Looks tab lists every female key character the game declares, record or not.

Jordan, Eve and Aura were key characters with Lora-Gen sets done and no entry
in appearance.json, so the tab never showed them (2026-10-08).
"""

import json

import pytest

import sourcemode.assets.appearance as A

GAME = """
export const CHARACTERS = {
  jordan: {
    id: 'jordan', name: 'Jordan', emoji: 'x', age: 28, sex: 'F',
    schedules: [],
    keyCharacter: true, stageLabels: null,
  },
  barkeep: {
    id: 'barkeep', name: 'Barkeep', age: 50, sex: 'M',
    keyCharacter: true,
  },
  extra: {
    id: 'extra', name: 'Extra', age: 30, sex: 'F',
    keyCharacter: false,
  },
  eve: {
    id:              'eve',
    name:            'Eve',
    age: 29, sex: 'F',
    keyCharacter:    true,
  },
};
"""


@pytest.fixture
def game(tmp_path, monkeypatch):
    g = tmp_path / "characters.js"
    g.write_text(GAME, encoding="utf-8")
    p = tmp_path / "appearance.json"
    p.write_text(json.dumps({"jordan": {"prompt": "a woman with dark hair"}}), encoding="utf-8")
    monkeypatch.setattr(A, "GAME_CHARACTERS", g)
    monkeypatch.setattr(A, "APPEARANCE", p)
    monkeypatch.setattr(A, "AGES", tmp_path / "ages.json")
    monkeypatch.setattr(A, "_cache", None)
    yield
    A.reload()


def test_female_key_characters_only(game):
    assert A.key_characters() == ["eve", "jordan"]


def test_the_looks_list_includes_a_key_character_with_no_record(game):
    from sourcemode.monitor.appearance_page import records

    rows = {r["character"]: r for r in records()}
    assert set(rows) == {"eve", "jordan"}
    assert rows["eve"]["prompt"] == "" and not rows["eve"]["confirmed"]
    assert rows["jordan"]["prompt"] == "a woman with dark hair"


def test_a_missing_game_file_lists_only_our_records(game, monkeypatch, tmp_path):
    monkeypatch.setattr(A, "GAME_CHARACTERS", tmp_path / "nope.js")
    assert A.key_characters() == []
