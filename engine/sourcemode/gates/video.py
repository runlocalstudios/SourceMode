"""Video identity scoring: sample every Nth frame with ffmpeg, score each frame.

Reports min/mean score and the first timestamp below threshold.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from ..source import CharacterSource
from .base import GateResult, Scorer

DEFAULT_FRAME_STRIDE = 8


def extract_frames(video_path: Path, out_dir: Path, stride: int, fps_hint: float = 16.0) -> list[Path]:
    """Extract every `stride`-th frame to PNG files. Requires ffmpeg on PATH."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "frame_%05d.png")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(video_path),
        "-vf", f"select=not(mod(n\\,{stride}))",
        "-vsync", "vfr",
        pattern,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return sorted(out_dir.glob("frame_*.png"))


def score_video(
    video_path: Path,
    source: CharacterSource,
    scorer: Scorer,
    *,
    stride: int = DEFAULT_FRAME_STRIDE,
    fps: float = 16.0,
) -> GateResult:
    frames_scores: list[tuple[float, float]] = []  # (timestamp_s, score)
    with tempfile.TemporaryDirectory(prefix="sourcemode_frames_") as tmp:
        try:
            frames = extract_frames(Path(video_path), Path(tmp), stride)
        except FileNotFoundError:
            return GateResult(score=None, passed=None, details="ffmpeg not found on PATH")
        except subprocess.CalledProcessError as err:
            return GateResult(score=None, passed=None, details=f"ffmpeg failed: {err.stderr.decode(errors='replace')[:200]}")

        for i, frame in enumerate(frames):
            result = scorer.score(frame, source)
            if result.score is None:
                # Scorer unavailable/uncalibrated — propagate its annotation.
                return result
            frames_scores.append((i * stride / fps, result.score))

    if not frames_scores:
        return GateResult(score=None, passed=None, details="no frames extracted")

    scores = [s for _, s in frames_scores]
    min_score = min(scores)
    mean_score = sum(scores) / len(scores)
    threshold = source.identity_threshold
    first_below = None
    if threshold is not None:
        for ts, s in frames_scores:
            if s < threshold:
                first_below = ts
                break
    passed = None if threshold is None else min_score >= threshold
    return GateResult(
        score=min_score,
        passed=passed,
        details="",
        extras={
            "mean": round(mean_score, 4),
            "min": round(min_score, 4),
            "frames_scored": len(scores),
            "threshold": threshold,
            "first_below_threshold_s": first_below,
        },
    )
