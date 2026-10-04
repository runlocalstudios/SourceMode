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
    assert info == {"n": 0, "character": None, "kind": None, "complete": False}


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
