"""Checkpoint selection: score each checkpoint's sample images, rank by identity.

Sample layouts understood:
- musubi sampling: <output_dir>/sample/{name}_e{epoch:06d}_{prompt:02d}_{ts}_{seed}.png
  (also step-based {name}_{steps:06d}_...) — grouped by the e######/###### token.
- subdirectories per checkpoint containing images (tests, ad-hoc layouts).

Ranking: by mean (image LoRA, comparable frontal samples) or min (video LoRA,
worst-frame-matters) identity score, rounded to 3 decimals; ties break toward
the EARLIER checkpoint (less overfit). Works with any Scorer — inject a fake
for tests or dry runs.

Prompt-inertia check: the 4 sample prompts vary background/lighting, so their
mean color/brightness should differ. Near-identical image statistics across a
checkpoint's samples mean the LoRA is overriding the prompt ("prompt inertia").
"""

from __future__ import annotations

import re
from pathlib import Path

from ..gates.base import Scorer
from ..source import CharacterSource

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_SAMPLE_TOKEN = re.compile(r"_(e?\d{6})_")
INERTIA_BRIGHTNESS_STD = 8.0  # of 0-255; below this the samples are suspiciously uniform


def _epoch_number(name: str) -> int:
    """Sortable position of a checkpoint group ('e000003' -> 3, 'ckpt-000010' -> 10)."""
    m = re.search(r"(\d+)\s*$", name.replace("e", "").replace("step", ""))
    if m:
        return int(m.group(1))
    digits = re.findall(r"\d+", name)
    return int(digits[-1]) if digits else 0


def _sample_images(checkpoint_dir: Path) -> dict[str, list[Path]]:
    """Map checkpoint name -> its sample images."""
    checkpoint_dir = Path(checkpoint_dir)
    if (checkpoint_dir / "sample").is_dir():
        checkpoint_dir = checkpoint_dir / "sample"
    groups: dict[str, list[Path]] = {}
    for sub in sorted(checkpoint_dir.iterdir()):
        if sub.is_dir():
            imgs = [p for p in sorted(sub.rglob("*")) if p.suffix.lower() in IMAGE_EXTS]
            if imgs:
                groups[sub.name] = imgs
        elif sub.suffix.lower() in IMAGE_EXTS:
            m = _SAMPLE_TOKEN.search(sub.stem)
            key = m.group(1) if m else (sub.stem.split("_")[-2] if "_" in sub.stem else sub.stem)
            groups.setdefault(key, []).append(sub)
    return groups


def _brightness_stats(images: list[Path]) -> dict | None:
    """Mean-brightness spread across a checkpoint's samples (None if PIL/files unreadable)."""
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return None
    means = []
    for path in images:
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail((64, 64))
            pixels = list(img.getdata())
            means.append(sum(sum(p) / 3 for p in pixels) / len(pixels))
        except Exception:  # noqa: BLE001 — unreadable sample never blocks ranking
            return None
    if len(means) < 2:
        return None
    mean = sum(means) / len(means)
    std = (sum((m - mean) ** 2 for m in means) / len(means)) ** 0.5
    return {"brightness_std": round(std, 2), "prompt_inertia": std < INERTIA_BRIGHTNESS_STD}


def rank_checkpoints(
    checkpoint_dir: Path,
    source: CharacterSource,
    scorer: Scorer,
    *,
    by: str = "mean",
    check_inertia: bool = False,
) -> list[dict]:
    """Return [{checkpoint, mean_score, min_score, n_scored, unavailable, ...}] best-first.

    `by` is "mean" or "min"; ties (3 decimals) break toward earlier checkpoints.
    """
    if by not in ("mean", "min"):
        raise ValueError(f"by must be 'mean' or 'min', got {by!r}")
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
            continue
        if not scores:
            continue
        row = {"checkpoint": name, "mean_score": sum(scores) / len(scores),
               "min_score": min(scores), "n_scored": len(scores), "unavailable": None}
        if check_inertia:
            stats = _brightness_stats(images)
            if stats:
                row.update(stats)
        results.append(row)

    key_field = "mean_score" if by == "mean" else "min_score"

    def sort_key(r: dict):
        score = r[key_field]
        return (score is None, -round(score, 3) if score is not None else 0.0, _epoch_number(r["checkpoint"]))

    results.sort(key=sort_key)
    return results
