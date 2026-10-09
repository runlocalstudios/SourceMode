"""A set he has declared finished is never re-rolled.

Jeremy, 2026-10-09: "Don't requeue any of the Jaina influencer stuff it's all
fine" - the re-roll had queued itself on his last verdict.
"""

from pathlib import Path

from PIL import Image

from sourcemode.assets.judge import make_set
from sourcemode.monitor import queue_page as QP


def _set(root: Path, set_id: str, **meta):
    img = root.parent / "img" / f"{set_id}.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(img)
    make_set(root, set_id, set_id, [{"id": "a", "path": img, "arm": "x", "group": "0",
                                     "redo": {"kind": "seed"}}], meta=meta)


def test_a_no_redo_set_never_reaches_the_queue(tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    root = out / "judge"
    cfg = {"paths": {"outputs": str(out)}}
    monkeypatch.setattr("sourcemode.assets.judge.judge_root", lambda c: root)
    _set(root, "shoot_jaina_influencer_b01", no_redo="his words")

    def boom(*a, **k):
        raise AssertionError("redoable() must not even be consulted for a no_redo set")
    monkeypatch.setattr("sourcemode.assets.redo.redoable", boom)
    assert QP.queue_redo_if_complete(cfg, "shoot_jaina_influencer_b01") is None
    assert not (out / "gpu-queue").exists()


def test_an_ordinary_set_still_consults_the_re_roll(tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    root = out / "judge"
    cfg = {"paths": {"outputs": str(out)}}
    monkeypatch.setattr("sourcemode.assets.judge.judge_root", lambda c: root)
    _set(root, "shoot_other")
    seen = []
    monkeypatch.setattr("sourcemode.assets.redo.redoable",
                        lambda r, s: seen.append(s) or {"n": 0, "n_pool": 0})
    assert QP.queue_redo_if_complete(cfg, "shoot_other") is None
    assert seen == ["shoot_other"]
