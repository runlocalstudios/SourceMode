"""Where a dataset sits in the training order, and what approving would cost.

Approval IS the trigger and approval order IS the training order, so the page
that performs an approval should be able to say what approving does.

The bug these pin: comparing candidate approval times against
`approval_state(...)["at"]` is wrong for the case the feature exists for. A
dataset that is not approved yet has `at = None`; coerced to "" it sorts BEFORE
every real timestamp, so nothing is ever "ahead of it" and the answer collapses
to "queued + 1".
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from sourcemode.gpu import queue as q
from sourcemode.monitor.queue_page import position
from sourcemode.train.preview import build_preview, record_approval


def _cfg(tmp_path: Path) -> dict:
    return {"train": {"previews": str(tmp_path / "prev")},
            "assets": {"judge": str(tmp_path / "judge")},
            "paths": {"outputs": str(tmp_path / "out")}}


def _preview(tmp_path: Path, ds: str, n: int = 50) -> None:
    d = tmp_path / "sets" / ds / "image_face"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        p = d / f"{i}.png"
        Image.new("RGB", (8, 8)).save(p)
        p.with_suffix(".txt").write_text(
            "x, waist-up, her hair loose, in a kitchen, lit, smiling, facing the camera",
            encoding="utf-8")
    build_preview(tmp_path / "prev", tmp_path / "sets" / ds, dataset_id=ds, measure=False)


def _approve_at(tmp_path: Path, ds: str, when: str) -> None:
    """Approve, then rewrite the timestamp so an order can be asserted."""
    record_approval(tmp_path / "prev", ds, True)
    p = tmp_path / "prev" / "approvals" / f"{ds}.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["at"] = when
    p.write_text(json.dumps(rec), encoding="utf-8")


def test_an_unapproved_dataset_lands_last_not_queued_plus_one(tmp_path):
    """THE BUG. With three earlier approvals waiting, approving this one puts it
    behind all of them - not at position 1."""
    cfg = _cfg(tmp_path)
    for i, ds in enumerate(("a_v2", "b_v2", "c_v2")):
        _preview(tmp_path, ds)
        _approve_at(tmp_path, ds, f"2026-09-0{i + 1}T10:00:00+00:00")
    _preview(tmp_path, "mine_v2")           # never approved

    p = position(cfg, "mine_v2")
    assert p["approved"] is False
    assert p["counts_itself"] is False
    assert p["before_n"] == 3               # not 0
    assert p["place"] == 4                  # not 1
    assert p["ahead_s"] > 0


def test_an_approved_dataset_keeps_its_place_by_approval_time(tmp_path):
    cfg = _cfg(tmp_path)
    for i, ds in enumerate(("a_v2", "b_v2", "c_v2")):
        _preview(tmp_path, ds)
        _approve_at(tmp_path, ds, f"2026-09-0{i + 1}T10:00:00+00:00")

    assert position(cfg, "a_v2")["place"] == 1
    assert position(cfg, "b_v2")["place"] == 2
    assert position(cfg, "c_v2")["place"] == 3
    assert position(cfg, "b_v2")["counts_itself"] is True


def test_a_lapsed_approval_goes_to_the_back_not_back_to_where_it_was(tmp_path):
    """Re-approving is a NEW approval. The old timestamp is not the answer."""
    from sourcemode.train.preview import set_caption

    cfg = _cfg(tmp_path)
    _preview(tmp_path, "old_v2")
    _approve_at(tmp_path, "old_v2", "2026-09-01T10:00:00+00:00")
    for i, ds in enumerate(("b_v2", "c_v2")):
        _preview(tmp_path, ds)
        _approve_at(tmp_path, ds, f"2026-09-1{i + 1}T10:00:00+00:00")

    assert position(cfg, "old_v2")["place"] == 1          # while it still holds
    set_caption(tmp_path / "prev", "old_v2", "0.png", "x, waist-up, her hair in a bun")
    p = position(cfg, "old_v2")
    assert p["stale"] is True
    assert p["approved"] is False
    assert p["counts_itself"] is False
    assert p["place"] == 3                                 # behind b and c


def test_queued_jobs_come_before_every_approval(tmp_path):
    cfg = _cfg(tmp_path)
    _preview(tmp_path, "mine_v2")
    _approve_at(tmp_path, "mine_v2", "2026-09-01T10:00:00+00:00")

    out = tmp_path / "out"
    path = q.queue_path(out)
    doc = q.load(path)
    q.add(doc, kind="train", label="other_v2", cmd=["x"], cwd=".")
    q.save(path, doc)

    p = position(cfg, "mine_v2")
    assert p["queued_n"] == 1
    assert p["place"] == 2


def test_a_dataset_already_in_the_queue_is_not_counted_twice(tmp_path):
    """candidates() excludes anything already queued, so the only contribution
    is the queue row itself."""
    cfg = _cfg(tmp_path)
    _preview(tmp_path, "mine_v2")
    _approve_at(tmp_path, "mine_v2", "2026-09-01T10:00:00+00:00")
    out = tmp_path / "out"
    path = q.queue_path(out)
    doc = q.load(path)
    q.add(doc, kind="train", label="mine_v2", cmd=["x"], cwd=".")
    q.save(path, doc)

    p = position(cfg, "mine_v2")
    assert p["queued_n"] == 1
    assert p["before_n"] == 0
    assert p["place"] == 2


def test_position_carries_its_own_estimate_with_a_basis(tmp_path):
    cfg = _cfg(tmp_path)
    _preview(tmp_path, "mine_v2", n=50)
    p = position(cfg, "mine_v2")
    e = p["estimate"]
    assert e["total_s"] > 0
    assert e["steps"] == 50 * e["repeats"] * 24
    assert "50 images" in e["basis"]


def test_position_writes_nothing(tmp_path):
    cfg = _cfg(tmp_path)
    _preview(tmp_path, "mine_v2")
    out = tmp_path / "out"
    path = q.queue_path(out)
    q.save(path, q.load(path))
    before = path.stat().st_mtime_ns
    position(cfg, "mine_v2")
    assert path.stat().st_mtime_ns == before
