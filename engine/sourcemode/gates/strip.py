"""Frame strip: extract every Nth frame of a video, score each, compose a
single PNG row with the identity score printed under each frame.

Pure annotation like every gate — the strip is a review artifact, nothing
blocks. Reuses the ffmpeg extraction from gates.video.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..source import CharacterSource
from .base import Scorer
from .video import extract_frames

TILE_W = 200
LABEL_H = 22


def frame_strip(
    video_path: Path,
    source: CharacterSource,
    scorer: Scorer,
    out_png: Path,
    *,
    stride: int = 12,
    fps: float = 24.0,
) -> dict:
    """Write a one-row strip of every `stride`-th frame with scores; return stats."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    scored: list[tuple[Path, float | None]] = []
    tiles: list[Image.Image] = []
    with tempfile.TemporaryDirectory(prefix="sourcemode_strip_") as tmp:
        frames = extract_frames(Path(video_path), Path(tmp), stride)
        if not frames:
            raise RuntimeError(f"no frames extracted from {video_path}")
        for frame in frames:
            result = scorer.score(frame, source)
            scored.append((frame, result.score))
            img = Image.open(frame).convert("RGB")
            scale = TILE_W / img.width
            tiles.append(img.resize((TILE_W, max(1, int(img.height * scale)))))

    tile_h = max(t.height for t in tiles)
    strip = Image.new("RGB", (TILE_W * len(tiles), tile_h + LABEL_H), (24, 24, 24))
    draw = ImageDraw.Draw(strip)
    threshold = source.identity_threshold
    for i, ((_, score), tile) in enumerate(zip(scored, tiles)):
        x = i * TILE_W
        strip.paste(tile, (x, 0))
        ts = i * stride / fps
        label = "no score" if score is None else f"{score:.3f}"
        color = (230, 230, 230)
        if score is not None and threshold is not None and score < threshold:
            color = (255, 90, 90)
        draw.text((x + 4, tile_h + 4), f"{ts:4.1f}s  {label}", fill=color)

    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    strip.save(out_png)

    scores = [s for _, s in scored if s is not None]
    return {
        "strip": str(out_png),
        "frames": len(scored),
        "min": round(min(scores), 4) if scores else None,
        "mean": round(sum(scores) / len(scores), 4) if scores else None,
    }
