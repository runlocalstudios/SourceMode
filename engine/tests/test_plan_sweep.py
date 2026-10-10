"""plan(): a running train job adds its sweep only while it is still training.

Rivera, 2026-10-10: the timeline read "20 of 90 renders, then the sweep at
134 min" - the job was already in its sweep, so the sweep was counted twice.
"""
from __future__ import annotations

from sourcemode.monitor import queue_page as QP


def _state(phase: str, eta_s: float, line: str) -> dict:
    job = {"id": "j1", "who": "rivera", "what": "LoRA training, then the epoch sweep",
           "kind": "train", "status": "running", "hold": False,
           "state": {"status": "running"},
           "estimate": {"total_s": 30000.0, "sweep_s": 8040.0, "basis": "x"}}
    return {"jobs": [job], "now": {"phase": phase, "eta_s": eta_s, "progress_line": line}}


def test_in_the_sweep_the_eta_is_the_sweep_and_nothing_is_added(monkeypatch):
    monkeypatch.setattr(QP, "candidates", lambda cfg: [])
    monkeypatch.setattr(QP, "queue_state", lambda cfg, status: _state("sweep", 5600.0, "20 of 90 renders"))
    b = QP.plan({})["blocks"][0]
    assert b["end_s"] - b["start_s"] == 5600.0
    assert "then the sweep" not in b["basis"]


def test_while_training_the_sweep_still_follows(monkeypatch):
    monkeypatch.setattr(QP, "candidates", lambda cfg: [])
    monkeypatch.setattr(QP, "queue_state", lambda cfg, status: _state("train", 3600.0, "step 10 of 3600"))
    b = QP.plan({})["blocks"][0]
    assert b["end_s"] - b["start_s"] == 3600.0 + 8040.0
    assert "then the sweep at 134 min" in b["basis"]
