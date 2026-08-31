from pathlib import Path

import pytest

from sourcemode.gates import strip as strip_mod
from sourcemode.gates.base import GateResult


class SeqScorer:
    """Fake scorer returning a fixed sequence of scores."""

    def __init__(self, scores):
        self.scores = list(scores)
        self.i = 0

    def score(self, asset_path: Path, source) -> GateResult:
        s = self.scores[self.i % len(self.scores)]
        self.i += 1
        return GateResult(score=s, passed=None)


def test_frame_strip_composes_and_reports(sample_source, tmp_path, monkeypatch):
    from PIL import Image

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    frames = []
    for i in range(3):
        p = frames_dir / f"frame_{i:05d}.png"
        Image.new("RGB", (100, 60), (i * 40, 100, 100)).save(p)
        frames.append(p)

    monkeypatch.setattr(strip_mod, "extract_frames", lambda video, out, stride: frames)

    out = tmp_path / "strip.png"
    stats = strip_mod.frame_strip(
        tmp_path / "fake.mp4", sample_source, SeqScorer([0.9, 0.5, 0.7]), out, stride=12, fps=24.0
    )
    assert out.exists()
    assert stats["frames"] == 3
    assert stats["min"] == pytest.approx(0.5)
    assert stats["mean"] == pytest.approx(0.7)

    from PIL import Image as I

    img = I.open(out)
    assert img.width == strip_mod.TILE_W * 3


def test_frame_strip_raises_on_no_frames(sample_source, tmp_path, monkeypatch):
    monkeypatch.setattr(strip_mod, "extract_frames", lambda video, out, stride: [])
    with pytest.raises(RuntimeError):
        strip_mod.frame_strip(tmp_path / "fake.mp4", sample_source, SeqScorer([1.0]), tmp_path / "s.png")
