"""Checkpoint selection: score each checkpoint's sample images, rank by identity.

Expects <checkpoint_dir>/<checkpoint_name>/*.png|jpg sample images (or sample
images named after the checkpoint). Works with any Scorer — inject a fake for
tests or dry runs.
"""

from __future__ import annotations

from pathlib import Path

from ..gates.base import Scorer
from ..source import CharacterSource

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _sample_images(checkpoint_dir: Path) -> dict[str, list[Path]]:
    """Map checkpoint name -> its sample images.

    Layout A: subdirectories per checkpoint containing images.
    Layout B (musubi sampling): a flat 'sample' dir with files prefixed by
    checkpoint step (name_stepNNNN_*.png) — grouped by the stem prefix.
    """
    checkpoint_dir = Path(checkpoint_dir)
    groups: dict[str, list[Path]] = {}
    for sub in sorted(checkpoint_dir.iterdir()):
        if sub.is_dir():
            imgs = [p for p in sorted(sub.rglob("*")) if p.suffix.lower() in IMAGE_EXTS]
            if imgs:
                groups[sub.name] = imgs
        elif sub.suffix.lower() in IMAGE_EXTS:
            key = sub.stem.split("_")[-2] if "_" in sub.stem else sub.stem
            groups.setdefault(key, []).append(sub)
    return groups


def rank_checkpoints(
    checkpoint_dir: Path,
    source: CharacterSource,
    scorer: Scorer,
) -> list[dict]:
    """Return [{checkpoint, mean_score, min_score, n_scored, unavailable}] best-first."""
    results = []
    for name, images in _sample_images(checkpoint_dir).items():
        scores = []
        unavailable = None
        for img in images:
            r = scorer.score(img, source)
            if r.score is None:
                unavailable = r.details
                break
            scores.append(r.score)
        if unavailable is not None:
            results.append({"checkpoint": name, "mean_score": None, "min_score": None,
                            "n_scored": 0, "unavailable": unavailable})
        elif scores:
            results.append({"checkpoint": name, "mean_score": sum(scores) / len(scores),
                            "min_score": min(scores), "n_scored": len(scores), "unavailable": None})
    results.sort(key=lambda r: (r["mean_score"] is None, -(r["mean_score"] or 0.0)))
    return results
