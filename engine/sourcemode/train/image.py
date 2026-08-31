"""Image-LoRA trainer command builder.

Inventory found NEITHER AI-Toolkit NOR diffusion-pipe installed (fluxgym exists
under Pinokio but targets Flux dev — banned by the commercial-license rule).
TODO(training): install a Qwen-Image-capable trainer and implement; the likely
path is musubi-tuner's own qwen_image_train_network.py (Qwen-Image is Apache
2.0 and musubi 0.3.4 already ships the script). Until then this builder emits
an explanatory placeholder; [training].image_trainer_path is the config hook.
"""

from __future__ import annotations

from pathlib import Path

from ..source import CharacterSource


class ImageTrainerNotConfigured(RuntimeError):
    pass


def build_image_lora_cmd(cfg: dict, source: CharacterSource, dataset_dir: Path) -> dict:
    trainer = cfg["training"].get("image_trainer_path", "")
    if not trainer:
        raise ImageTrainerNotConfigured(
            "No image-LoRA trainer installed (AI-Toolkit / diffusion-pipe not found at inventory; "
            "musubi-tuner's qwen_image_train_network.py is the recommended path — see BACKLOG.md). "
            "Set [training].image_trainer_path or SOURCEMODE_TRAINING_IMAGE_TRAINER_PATH."
        )
    raise ImageTrainerNotConfigured(
        f"image trainer at {trainer!r} configured but the command builder is not implemented yet (BACKLOG)"
    )
