"""gates report: CSV + contact sheet from a folder of images (fake scorer, real PIL)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from sourcemode.gates.base import GateResult
from sourcemode.gates.report import report_directory

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


class NameScorer:
    """Score derived from the filename so ordering is deterministic."""

    def score(self, asset_path: Path, source) -> GateResult:
        if "bad" in asset_path.name:
            return GateResult(score=0.2, passed=False)
        if "noface" in asset_path.name:
            return GateResult(score=None, passed=None, details="no face detected")
        return GateResult(score=0.9, passed=True)


def _png(path: Path):
    Image.new("RGB", (64, 96), (120, 60, 60)).save(path)


def test_report_directory_writes_csv_and_contact_sheet(tmp_path, sample_source):
    src_dir = tmp_path / "imgs"
    src_dir.mkdir()
    for name in ("good_a.png", "bad_b.png", "good_c.png", "noface_d.png"):
        _png(src_dir / name)
    (src_dir / "notes.txt").write_text("ignored", encoding="utf-8")

    out = tmp_path / "review"
    summary = report_directory(src_dir, sample_source, NameScorer(), out, name="unit")

    assert summary["images"] == 4
    assert summary["scored"] == 3
    assert summary["failed"] == 1
    assert Path(summary["contact_sheet"]).exists()

    with open(summary["csv"], newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["file"] for r in rows[:2]] == ["good_a.png", "good_c.png"]  # sorted best-first
    assert rows[-1]["file"] == "noface_d.png"  # unscored images sink to the bottom
    assert rows[2]["file"] == "bad_b.png" and rows[2]["passed"] == "False"

    sheet = Image.open(summary["contact_sheet"])
    assert sheet.width == 4 * 256
