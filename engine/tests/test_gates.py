"""Gates tests.

Real-embedding tests run only when insightface + onnxruntime are installed
(uv sync --extra gates) and skip cleanly otherwise. The "unavailable" path is
always tested via monkeypatching.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sourcemode.gates.base import GateResult
from sourcemode.gates.identity import (
    UNAVAILABLE_DETAILS,
    IdentityScorer,
    calibrate_identity,
    insightface_available,
)
from sourcemode.gates.video import score_video
from sourcemode.source import load_source, save_source
from tests.conftest import GWEN_DIR, REPO_ROOT, copy_gwen_refs

needs_insightface = pytest.mark.skipif(
    not insightface_available(), reason="insightface/onnxruntime not installed (uv sync --extra gates)"
)
needs_gwen = pytest.mark.skipif(not (GWEN_DIR / "source.json").exists(), reason="gwen assets missing")


def test_unavailable_path(monkeypatch, chars_root, sample_source, tmp_path):
    monkeypatch.setattr("sourcemode.gates.identity.insightface_available", lambda: False)
    scorer = IdentityScorer(chars_root)
    result = scorer.score(tmp_path / "whatever.png", sample_source)
    assert result == GateResult(score=None, passed=None, details=UNAVAILABLE_DETAILS)


def test_uncalibrated_path_annotates(monkeypatch, chars_root, sample_source, tmp_path):
    monkeypatch.setattr("sourcemode.gates.identity.insightface_available", lambda: True)
    scorer = IdentityScorer(chars_root)
    result = scorer.score(tmp_path / "x.png", sample_source)
    assert result.score is None and result.passed is None
    assert "not calibrated" in result.details


def test_video_scoring_propagates_unavailable(monkeypatch, chars_root, sample_source, tmp_path):
    class UnavailableScorer:
        def score(self, asset_path, source):
            return GateResult(score=None, passed=None, details=UNAVAILABLE_DETAILS)

    fake_video = tmp_path / "clip.webp"
    fake_video.write_bytes(b"x")

    # short-circuit frame extraction so ffmpeg isn't needed
    frames = [tmp_path / "f1.png"]
    for f in frames:
        f.write_bytes(b"img")
    monkeypatch.setattr("sourcemode.gates.video.extract_frames", lambda *a, **k: frames)

    result = score_video(fake_video, sample_source, UnavailableScorer())
    assert result.details == UNAVAILABLE_DETAILS


def test_video_scoring_min_mean_and_first_below(monkeypatch, chars_root, sample_source, tmp_path):
    scores = iter([0.9, 0.7, 0.2, 0.8])

    class SeqScorer:
        def score(self, asset_path, source):
            return GateResult(score=next(scores), passed=None)

    frames = []
    for i in range(4):
        f = tmp_path / f"f{i}.png"
        f.write_bytes(b"img")
        frames.append(f)
    monkeypatch.setattr("sourcemode.gates.video.extract_frames", lambda *a, **k: frames)

    source = sample_source.model_copy(update={"identity_threshold": 0.5})
    fake_video = tmp_path / "clip.webp"
    fake_video.write_bytes(b"x")
    result = score_video(fake_video, source, SeqScorer(), stride=8, fps=16.0)
    assert result.score == pytest.approx(0.2)
    assert result.passed is False
    assert result.extras["mean"] == pytest.approx((0.9 + 0.7 + 0.2 + 0.8) / 4, abs=1e-3)
    assert result.extras["first_below_threshold_s"] == pytest.approx(2 * 8 / 16.0)


@needs_insightface
@needs_gwen
def test_calibration_and_impostor_ordering(tmp_path):
    """Calibrate on Gwen's real refs; a heavily transformed ref (flipped +
    hue-shifted + blurred, i.e. a synthetic 'different face') must score lower
    than the real refs.

    Caveat (per spec): the transform heuristic is weak — a flip+hue+blur of the
    same face can still embed close to the original. If this assertion proves
    flaky on real hardware, the fixture should become an actual different
    person's face rather than the test being weakened to always pass.
    """
    import cv2
    import numpy as np

    chars_root = tmp_path / "characters"
    gwen = load_source(REPO_ROOT / "characters", "gwen")
    gwen = gwen.model_copy(update={"identity_embedding_path": None, "identity_threshold": None})
    save_source(chars_root, gwen, force=True)
    copy_gwen_refs(chars_root / "gwen" / "references")

    calibrated = calibrate_identity(chars_root, gwen)
    assert calibrated.identity_threshold is not None
    assert calibrated.identity_threshold >= 0.30
    assert (chars_root / "gwen" / calibrated.identity_embedding_path).exists()

    scorer = IdentityScorer(chars_root)
    ref_path = chars_root / "gwen" / "references" / "ref-01-supporting.png"
    same = scorer.score(ref_path, calibrated)
    assert same.score is not None and same.score > 0.30

    img = cv2.imread(str(ref_path))
    flipped = cv2.flip(img, 1)
    hsv = cv2.cvtColor(flipped, cv2.COLOR_BGR2HSV).astype(np.int16)
    hsv[..., 0] = (hsv[..., 0] + 60) % 180
    shifted = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    blurred = cv2.GaussianBlur(shifted, (31, 31), 12)
    impostor_path = tmp_path / "impostor.png"
    cv2.imwrite(str(impostor_path), blurred)

    impostor = scorer.score(impostor_path, calibrated)
    if impostor.score is not None:
        assert impostor.score < same.score, (
            f"impostor {impostor.score:.3f} should score below same-character {same.score:.3f}"
        )
