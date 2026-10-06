"""A training job's card follows it into its closing epoch sweep.

jaina_v2, 2026-10-06: the trainer finished, the sweep started inside the same
job, and the card kept reading "step 3600 of 3600" - the frozen tqdm.
"""

from __future__ import annotations

import sourcemode.config as C
from sourcemode.monitor.queue_page import _sweep_progress


def _setup(tmp_path, monkeypatch, log_lines, renders):
    monkeypatch.setattr(C, "outputs_dir", lambda cfg: tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "x_v2.log").write_text("\n".join(log_lines), encoding="utf-8")
    for ep, n in renders.items():
        d = tmp_path / "dense_x_v2_asset" / f"ep{ep:02d}"
        d.mkdir(parents=True)
        for i in range(n):
            (d / f"scene_{i:02d}.png").write_bytes(b"")
    return {"label": "x_v2", "kind": "train"}


def test_still_training_has_no_sweep(tmp_path, monkeypatch):
    run = _setup(tmp_path, monkeypatch, ["checking approval for x_v2",
                                         "START train x_v2 (rank 32)"], {})
    assert _sweep_progress({}, run) is None


def test_sweep_counts_its_renders(tmp_path, monkeypatch):
    run = _setup(tmp_path, monkeypatch, ["checking approval for x_v2", "END train x_v2 exit 0",
                                         "START x eval, epochs 16-24 x 10 scenes (asset)"],
                 {16: 10, 17: 10, 18: 3})
    assert _sweep_progress({}, run) == (23, 90)


def test_an_earlier_attempts_sweep_does_not_count(tmp_path, monkeypatch):
    run = _setup(tmp_path, monkeypatch, ["checking approval for x_v2",
                                         "START x eval, epochs 16-24 x 10 scenes",
                                         "checking approval for x_v2", "START train x_v2"], {})
    assert _sweep_progress({}, run) is None
