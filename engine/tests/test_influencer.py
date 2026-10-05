"""The influencer pack: 14 feed photos per batch, her job and hobbies from the game."""

from __future__ import annotations

import re
from collections import Counter

import pytest

from sourcemode.assets import influencer as I
from sourcemode.assets.appearance import GAME_CHARACTERS, game_facts
from sourcemode.assets.render import shot_prompt
from sourcemode.assets.shoots import BY_ID, lookup

MIX = {"job": 3, "hobby": 3, "lifestyle": 2, "sightseeing": 2, "pool": 1, "beach": 1,
       "boudoir": 2}


def test_a_batch_is_fourteen_in_the_agreed_mix():
    slots = I.slots("zara", 1)
    assert len(slots) == 14 == sum(MIX.values())
    assert Counter(s["tone"] for s in slots) == MIX


def test_sightseeing_is_one_international_and_one_us():
    sights = [s["setting"] for s in I.slots("zara", 1) if s["tone"] == "sightseeing"]
    assert any("international" in s for s in sights)
    assert any("United States" in s for s in sights)


def test_a_batch_is_reproducible_and_batches_differ():
    assert I.slots("zara", 2) == I.slots("zara", 2)
    a, b = I.slots("zara", 1), I.slots("zara", 2)
    assert [s["setting"] + s["outfit"] for s in a] != [s["setting"] + s["outfit"] for s in b]


def test_two_characters_do_not_get_the_same_feed():
    a, b = I.slots("zara", 1), I.slots("nobody_at_all", 1)
    assert [s["outfit"] for s in a] != [s["outfit"] for s in b]


def test_ids_are_unique_and_carry_the_batch():
    ids = [s["id"] for s in I.slots("zara", 3)]
    assert len(set(ids)) == 14
    assert all(i.startswith("influencer_b03_") for i in ids)


def test_a_character_the_game_does_not_know_still_gets_a_full_batch():
    slots = I.slots("nobody_at_all", 1)
    assert Counter(s["tone"] for s in slots) == MIX
    assert all(s["setting"] and s["outfit"] and s["stance"] for s in slots)


def test_boudoir_carries_no_lingerie():
    """Jeremy, 2026-10-05: swimwear and boudoir for suggestive, no lingerie to start."""
    pat = re.compile(r"lingerie|lace|bra\b|bralette|panties|thong|teddy|garter|corset", re.I)
    for b in range(1, 6):
        for s in I.slots("zara", b):
            if s["tone"] == "boudoir":
                assert not pat.search(s["outfit"]), s


def test_no_pose_puts_her_on_her_back():
    """A face upside down at the bottom of the frame collapses identity (0/12)."""
    for b in range(1, 6):
        for s in I.slots("zara", b):
            assert "on her back" not in s["stance"]


def test_every_prompt_goes_through_the_one_builder_without_footwear():
    for s in I.slots("zara", 1):
        p = shot_prompt("zara", s, "zara", backdrop=s["setting"])
        assert p.startswith("zara. ")
        assert not re.search(r"\b(sneakers|heels|boots|sandals)\b", p), s["id"]


@pytest.mark.skipif(not GAME_CHARACTERS.is_file(), reason="game repo not checked out")
def test_zaras_job_and_hobbies_come_from_her_schedule():
    sched = game_facts("zara")["schedule"]
    work = {loc for loc, outfit in sched if outfit in I.WORK_OUTFITS}
    play = {loc for loc, outfit in sched if outfit not in I.WORK_OUTFITS}
    slots = I.slots("zara", 1)
    assert {s["place"] for s in slots if s["tone"] == "job"} <= work
    assert {s["place"] for s in slots if s["tone"] == "hobby"} <= play


@pytest.mark.skipif(not GAME_CHARACTERS.is_file(), reason="game repo not checked out")
def test_every_scheduled_location_in_the_game_has_a_scene():
    """A new location in the game must get a scene here, not silently drop out."""
    src = GAME_CHARACTERS.read_text(encoding="utf-8", errors="replace")
    used = set(re.findall(r"'location':\s*'(\w+)'", src))
    assert used - set(I.PLACES) == set()


def test_the_pack_is_on_the_shoots_tab_and_a_batch_resolves_for_redo():
    assert BY_ID["influencer"].shots == 14
    sh = lookup("influencer_b04")
    assert sh.id == "influencer_b04" and sh.batch == 4
    assert [s["id"] for s in sh.plan(character="zara")] == [s["id"] for s in I.slots("zara", 4)]
    assert lookup("boudoir") is BY_ID["boudoir"]
    assert lookup("no_such_shoot") is None


def test_next_batch_counts_what_is_on_disk(tmp_path):
    assert I.next_batch(tmp_path) == 1
    (tmp_path / "influencer_b01").mkdir()
    (tmp_path / "influencer_b02").mkdir()
    (tmp_path / "boudoir").mkdir()
    assert I.next_batch(tmp_path) == 3
