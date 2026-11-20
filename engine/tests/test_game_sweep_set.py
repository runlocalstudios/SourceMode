"""The game sweep set: ten of a shipped character's own looks as the sweep.

Jeremy, 2026-11-20: "re-run a new epoch sweep using prompts from one of the
existing game models' game assets ... use 5 casual, then 1 of each from each of
the other gropings (workout, fancy dining, fancy town, work, casual date)".
"""

from __future__ import annotations

import sys
from collections import Counter

from sourcemode.assets import render as R
from sourcemode.assets.pack import STUDIO_BACKDROP
from sourcemode.config import ENGINE_ROOT

sys.path.insert(0, str(ENGINE_ROOT / "scripts" / "eval"))
from asset_scenes import GAME_LOOKS, game_prompts  # noqa: E402


def test_five_casual_and_one_of_each_other_category():
    assert Counter(look["category"] for look in GAME_LOOKS) == {
        "casual": 5, "workout": 1, "fancy_dining_gallery": 1, "fancy_town": 1,
        "casual_date": 1, "work": 1}


def test_each_prompt_is_the_packs_own_for_that_look(monkeypatch):
    monkeypatch.setattr(R, "appearance_clause", lambda c, **_: "a young woman")
    ps = game_prompts("mimi")
    assert len(set(ps)) == 10 and ps == game_prompts("mimi")     # the draw is fixed
    for look, p in zip(GAME_LOOKS, ps):
        assert p.startswith("mimi, ")
        assert STUDIO_BACKDROP in p
        assert " ".join(look["outfit"].split()[:4]) in p
        assert "a young woman" in p
