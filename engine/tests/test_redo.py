"""Judge the set, then re-roll what was rejected - and only after it is finished.

Jeremy, 2026-10-04: "if I reject them, you queue an item to regenerate a
replacement for that. single or multiple rejected photos" and "I want you to
queue and wait until the whole set has been judged until you determine which
shots need to be regenerated."

The loop leans entirely on behaviour `make_set` already had - content hashing
plus `drop_stale_verdicts` - so the tests that matter are: a replacement
re-opens exactly its own item, every other verdict survives, and nothing is
offered until the set is complete.
"""

from __future__ import annotations

from pathlib import Path

from sourcemode.assets.judge import load_verdicts, make_set, record_verdict
from sourcemode.assets.redo import (
    ATTEMPT_STRIDE, complete, judge_item, redoable, rejected, retry_seed)


def _png(p: Path, colour: tuple[int, int, int]) -> Path:
    from PIL import Image

    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 12), colour).save(p)
    return p


def _set(root: Path, imgs: Path, n: int = 3) -> str:
    items = [judge_item({"id": f"casual_{i:02d}", "look": i, "category": "casual"},
                        _png(imgs / f"casual_{i:02d}.png", (i * 40, 10, 10)),
                        kind="pack", character="nobody", source="plan_28.json",
                        seed=7100 + i)
             for i in range(1, n + 1)]
    make_set(root, "pack_nobody", "Nobody - wardrobe pack", items)
    return "pack_nobody"


def test_a_half_judged_set_offers_nothing(tmp_path):
    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _set(root, imgs)
    record_verdict(root, sid, "casual_01", "reject")
    assert complete(root, sid) is False
    info = redoable(root, sid)
    assert info == {"n": 0, "n_pool": 0, "n_render": 0, "character": None,
                    "kind": None, "complete": False}


def test_a_finished_set_offers_exactly_its_rejects(tmp_path):
    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _set(root, imgs)
    record_verdict(root, sid, "casual_01", "reject")
    record_verdict(root, sid, "casual_02", "keep")
    record_verdict(root, sid, "casual_03", "reject")
    assert complete(root, sid) is True
    info = redoable(root, sid)
    assert info["n"] == 2
    assert info["character"] == "nobody"
    assert info["kind"] == "pack"
    assert {r["id"] for r in rejected(root, sid)} == {"casual_01", "casual_03"}


def test_a_set_with_no_rejects_offers_nothing(tmp_path):
    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _set(root, imgs)
    for i in (1, 2, 3):
        record_verdict(root, sid, f"casual_{i:02d}", "keep")
    assert redoable(root, sid)["n"] == 0


def test_an_item_with_no_redo_block_is_never_offered(tmp_path):
    # An epoch sweep arm is a checkpoint comparison, not a shot to re-roll.
    root, imgs = tmp_path / "judge", tmp_path / "img"
    make_set(root, "dense_x", "sweep", [
        {"id": "ep16", "path": _png(imgs / "a.png", (1, 2, 3)), "arm": "epoch 16"},
        {"id": "ep18", "path": _png(imgs / "b.png", (4, 5, 6)), "arm": "epoch 18"}])
    record_verdict(root, "dense_x", "ep16", "reject")
    record_verdict(root, "dense_x", "ep18", "reject")
    assert complete(root, "dense_x") is True
    assert redoable(root, "dense_x")["n"] == 0


def test_a_replacement_reopens_only_its_own_item(tmp_path):
    """The whole loop, without a GPU: judge 3, re-render 1, re-write the set."""
    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _set(root, imgs)
    record_verdict(root, sid, "casual_01", "reject")
    record_verdict(root, sid, "casual_02", "keep")
    record_verdict(root, sid, "casual_03", "keep")

    from sourcemode.assets.judge import load_set

    doc = load_set(root, sid)
    rows = {it["id"]: dict(it) for it in doc["items"]}
    # the re-roll: same path, DIFFERENT pixels
    _png(imgs / "casual_01.png", (200, 200, 200))
    rows["casual_01"]["redo"] = {**rows["casual_01"]["redo"], "attempt": 1}
    make_set(root, sid, doc["title"], list(rows.values()))

    v = load_verdicts(root, sid)
    assert "casual_01" not in v, "the replacement must come back unjudged"
    assert v["casual_02"] == "keep" and v["casual_03"] == "keep"
    assert complete(root, sid) is False


def test_an_untouched_keep_is_never_reopened(tmp_path):
    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _set(root, imgs)
    for i in (1, 2, 3):
        record_verdict(root, sid, f"casual_{i:02d}", "keep")
    from sourcemode.assets.judge import load_set

    doc = load_set(root, sid)
    make_set(root, sid, doc["title"], [dict(it) for it in doc["items"]])
    assert len(load_verdicts(root, sid)) == 3


def test_a_retry_cannot_hand_back_the_same_draw():
    assert retry_seed(7100, 0) == 7100
    assert retry_seed(7100, 1) == 7100 + ATTEMPT_STRIDE
    assert retry_seed(7100, 2) == 7100 + 2 * ATTEMPT_STRIDE
    # Neighbouring slots on different attempts must not collide: slot seeds are
    # 1000 apart in render_plan and 1 apart in a shoot, both far under the stride.
    seen = {retry_seed(7100 + s, a) for s in range(0, 28_000, 1000) for a in range(4)}
    assert len(seen) == 28 * 4


def test_the_old_tally_is_preserved_before_a_verdict_is_dropped(tmp_path):
    from sourcemode.assets.judge import history

    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _set(root, imgs)
    record_verdict(root, sid, "casual_01", "reject")
    record_verdict(root, sid, "casual_02", "keep")
    record_verdict(root, sid, "casual_03", "keep")
    from sourcemode.assets.judge import load_set

    doc = load_set(root, sid)
    _png(imgs / "casual_01.png", (9, 9, 9))
    make_set(root, sid, doc["title"], [dict(it) for it in doc["items"]])
    h = history(root, sid)
    assert h["runs"], "re-rendering must not silently erase the judged result"
    assert h["runs"][0]["reason"].startswith("1 images re-rendered")


# --- the pool: four candidates already on disk, so a reject is free ----------

def _pool_set(root, imgs, n_cand=3):
    """One look with `n_cand` candidates already rendered."""
    from sourcemode.assets.redo import pool_item

    cands = [{"source": str(_png(imgs / f"shot_{k:02d}.png", (k * 60, 20, 20))),
              "score": 0.9 - k / 100, "seed": 7100 + k} for k in range(n_cand)]
    it = pool_item({"id": "casual_01", "look": 1, "category": "casual"},
                   cands, character="zara", source="plan_28.json")
    make_set(root, "pack_zara", "Zara - wardrobe pack", [it])
    return "pack_zara"


def test_a_reject_shows_the_next_candidate_and_spends_no_gpu(tmp_path):
    from sourcemode.assets.redo import advance_pool

    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _pool_set(root, imgs)
    from sourcemode.assets.judge import load_set

    assert load_set(root, sid)["items"][0]["path"].endswith("shot_00.png")
    record_verdict(root, sid, "casual_01", "reject")
    moved = advance_pool(root, sid)
    assert moved == {"advanced": ["casual_01"], "exhausted": []}
    row = load_set(root, sid)["items"][0]
    assert row["path"].endswith("shot_01.png")
    assert row["redo"]["at"] == 1
    # and it is back to being unjudged, which is the whole point
    assert "casual_01" not in load_verdicts(root, sid)


def test_running_out_of_candidates_is_reported_not_silently_looped(tmp_path):
    from sourcemode.assets.redo import advance_pool

    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _pool_set(root, imgs, n_cand=3)
    for expect in (["casual_01"], ["casual_01"]):
        record_verdict(root, sid, "casual_01", "reject")
        assert advance_pool(root, sid)["advanced"] == expect
    # third reject: nothing left behind it
    record_verdict(root, sid, "casual_01", "reject")
    moved = advance_pool(root, sid)
    assert moved == {"advanced": [], "exhausted": ["casual_01"]}
    # it stays rejected, so the GPU path can pick it up
    assert load_verdicts(root, sid)["casual_01"] == "reject"
    assert redoable(root, sid)["n_render"] == 1


def test_a_deleted_candidate_is_skipped_as_exhausted(tmp_path):
    # "unless they've already been deleted" - a manifest can outlive the files.
    from sourcemode.assets.redo import advance_pool

    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _pool_set(root, imgs, n_cand=2)
    (imgs / "shot_01.png").unlink()
    record_verdict(root, sid, "casual_01", "reject")
    assert advance_pool(root, sid)["exhausted"] == ["casual_01"]


def test_pool_and_render_rejects_are_counted_separately(tmp_path):
    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _pool_set(root, imgs, n_cand=2)
    record_verdict(root, sid, "casual_01", "reject")
    info = redoable(root, sid)
    assert info["n_pool"] == 1 and info["n_render"] == 0


# --- an image that is not there is not judgeable ----------------------------

def test_a_missing_image_is_not_offered_and_cannot_take_a_verdict(tmp_path):
    """2026-10-04: ten of bianca's re-rolls were moved aside while the manifest
    still pointed at them. The page served ten broken images - "It just showed
    a little box with a question mark" - he rejected all ten, and those rejects
    auto-queued a GPU job duplicating work already in the queue.

    A re-roll always deletes the rejected file before rendering its
    replacement, so this window exists by design. A verdict is a record of what
    he saw; an item he cannot see must not be able to take one.
    """
    import pytest

    from sourcemode.assets.judge import record_verdict, set_payload

    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _set(root, imgs, n=3)
    record_verdict(root, sid, "casual_02", "keep")
    (imgs / "casual_01.png").unlink()

    p = set_payload(root, sid)
    # order is the stored blind shuffle, so compare as a set
    assert {i["id"] for i in p["items"]} == {"casual_02", "casual_03"}
    assert p["pending"] == 1
    with pytest.raises(FileNotFoundError):
        record_verdict(root, sid, "casual_01", "reject")
    # the keep he really made is untouched
    assert p["verdicts"] == {"casual_02": "keep"}


def test_a_verdict_can_still_be_CLEARED_after_its_image_vanishes(tmp_path):
    # Undo has to keep working, or a verdict recorded before the file went
    # missing is stuck forever.
    from sourcemode.assets.judge import load_verdicts, record_verdict

    root, imgs = tmp_path / "judge", tmp_path / "img"
    sid = _set(root, imgs, n=2)
    record_verdict(root, sid, "casual_01", "reject")
    (imgs / "casual_01.png").unlink()
    record_verdict(root, sid, "casual_01", None)
    assert "casual_01" not in load_verdicts(root, sid)
