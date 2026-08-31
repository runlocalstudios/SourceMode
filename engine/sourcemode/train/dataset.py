"""Trainer dataset config: caption validation, TOML emitter, hashing, repeats.

One image dataset (characters/<id>/dataset) feeds both trainers. Each trainer
gets its own TOML with its own cache_directory so caches stay independently
clearable. Captions are validated loudly before anything is emitted: every
image must have a non-empty .txt caption starting with the trigger token.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class DatasetError(RuntimeError):
    pass


def collect_images(dataset_dir: Path) -> list[Path]:
    dataset_dir = Path(dataset_dir)
    if not dataset_dir.is_dir():
        raise DatasetError(f"dataset directory not found: {dataset_dir}")
    images = sorted(p for p in dataset_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS and p.is_file())
    if not images:
        raise DatasetError(f"no images in {dataset_dir}")
    return images


def validate_captions(dataset_dir: Path, trigger_token: str) -> list[dict]:
    """Every image needs a non-empty sibling .txt starting with the trigger token.

    Returns [{image, caption_file, caption}] or raises DatasetError listing
    every problem at once (fail loudly, fail completely).
    """
    entries = []
    problems = []
    for image in collect_images(dataset_dir):
        caption_file = image.with_suffix(".txt")
        if not caption_file.exists():
            problems.append(f"{image.name}: missing caption {caption_file.name}")
            continue
        caption = caption_file.read_text(encoding="utf-8").strip()
        if not caption:
            problems.append(f"{image.name}: caption {caption_file.name} is empty")
        elif not caption.startswith(trigger_token):
            problems.append(f"{image.name}: caption does not start with trigger {trigger_token!r}: {caption[:60]!r}")
        else:
            entries.append({"image": image, "caption_file": caption_file, "caption": caption})
    if problems:
        raise DatasetError(f"{len(problems)} caption problem(s) in {dataset_dir}:\n  " + "\n  ".join(problems))
    return entries


def dataset_hash(dataset_dir: Path, trigger_token: str) -> str:
    """SHA-256 over (filename, bytes) of every image + caption, sorted. Recorded
    in the training manifest so a render can be traced to exact training data."""
    h = hashlib.sha256()
    for entry in validate_captions(dataset_dir, trigger_token):
        for p in (entry["image"], entry["caption_file"]):
            h.update(p.name.encode("utf-8"))
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def choose_num_repeats(n_images: int, *, low: int = 150, high: int = 250) -> int:
    """Smallest num_repeats putting one epoch (batch 1) into [low, high] steps.

    If n_images alone exceeds `high`, repeats stay at 1 (epoch is just big)."""
    if n_images <= 0:
        raise DatasetError("dataset has no images")
    if n_images >= low:
        return 1
    repeats = -(-low // n_images)  # ceil(low / n)
    if n_images * repeats > high and repeats > 1:
        # prefer staying under `high` when the next-lower value is still close
        below = repeats - 1
        if n_images * below >= low * 0.9:
            return below
    return repeats


def choose_epochs(steps_per_epoch: int, *, target_total: int = 2500, min_total: int = 2000, max_total: int = 3000) -> int:
    """Epoch count landing total steps nearest target_total within [min, max]."""
    if steps_per_epoch <= 0:
        raise DatasetError("steps_per_epoch must be positive")
    epochs = max(1, round(target_total / steps_per_epoch))
    while epochs * steps_per_epoch < min_total:
        epochs += 1
    while epochs > 1 and epochs * steps_per_epoch > max_total:
        epochs -= 1
    return epochs


def dataset_toml(
    dataset_dir: Path,
    *,
    cache_dirname: str,
    resolution: int = 1024,
    num_repeats: int = 1,
    batch_size: int = 1,
) -> str:
    """musubi-tuner image-dataset TOML (keys verified in docs/dataset_config.md)."""
    d = str(Path(dataset_dir)).replace("\\", "/")
    cache = str(Path(dataset_dir) / cache_dirname).replace("\\", "/")
    return (
        "[general]\n"
        f"resolution = [{resolution}, {resolution}]\n"
        'caption_extension = ".txt"\n'
        f"batch_size = {batch_size}\n"
        "enable_bucket = true\n"
        "bucket_no_upscale = false\n"
        "\n"
        "[[datasets]]\n"
        f'image_directory = "{d}"\n'
        f'cache_directory = "{cache}"\n'
        f"num_repeats = {num_repeats}\n"
    )
