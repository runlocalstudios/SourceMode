"""Render passes: build fully-substituted workflows for a shot.

draft  = lightning/distill LoRA on, low steps (fast look-dev)
final  = lightning off, full steps
Presets come from config [render.draft]/[render.final].
"""

from __future__ import annotations

import math
from pathlib import Path

from ..source import CharacterSource
from .workflow import load_template, substitute, validate_lora_stack

PLACEHOLDER_LORA = "NONE.safetensors"  # keeps the template valid in dry-run before LoRAs exist


def snap_frames(duration_s: float, fps: int) -> int:
    """Wan wants 4n+1 frame counts, capped at 81 (ported constraint from e2egen video.py)."""
    frames = int(round(duration_s * fps))
    frames = min(frames, 81)
    return max(5, (math.floor((frames - 1) / 4) * 4) + 1)


def build_video_workflow(
    cfg: dict,
    source: CharacterSource,
    *,
    positive: str,
    negative: str,
    image_name: str,
    seed: int,
    render_pass: str,
    duration_s: float = 5.0,
) -> tuple[dict, dict]:
    """Return (workflow_nodes, settings_used) for the Wan 2.2 I2V two-stage template."""
    preset = cfg["render"][render_pass]
    models = cfg["models"]
    video = cfg["video"]

    lora_high = source.lora_paths.wan_high_noise or PLACEHOLDER_LORA
    lora_low = source.lora_paths.wan_low_noise or PLACEHOLDER_LORA
    identity_strength = 1.0

    loras = [
        {"path": lora_high, "strength": identity_strength, "is_identity": True},
        {"path": lora_low, "strength": identity_strength, "is_identity": True},
    ]
    if render_pass == "draft" and preset.get("lightning_lora"):
        loras.append(
            {"path": preset["lightning_lora"], "strength": preset["lightning_strength"], "is_identity": False}
        )
    validate_lora_stack(loras)

    steps = int(preset["steps"])
    settings = {
        "MODEL_HIGH": models["wan_i2v_high_fp8"],
        "MODEL_LOW": models["wan_i2v_low_fp8"],
        "UMT5": models["umt5"],
        "VAE": models["wan_vae"],
        "POSITIVE": positive,
        "NEGATIVE": negative,
        "IMAGE": image_name,
        "LORA_HIGH": lora_high,
        "LORA_LOW": lora_low,
        "LORA_STRENGTH": identity_strength,
        "SEED": int(seed),
        "STEPS": steps,
        "CFG": float(preset["cfg"]),
        "WIDTH": int(video["width"]),
        "HEIGHT": int(video["height"]),
        "LENGTH": snap_frames(duration_s, int(video["fps"])),
        "FPS": int(video["fps"]),
        "BOUNDARY_STEP": max(1, steps // 2),
        "FILENAME_PREFIX": f"sourcemode/{source.character_id}",
    }
    from ..config import workflows_dir  # noqa: PLC0415

    template = load_template(workflows_dir(cfg), "wan22_i2v")
    return substitute(template, settings), settings


def build_keyframe_workflow(
    cfg: dict,
    source: CharacterSource,
    *,
    positive: str,
    negative: str,
    seed: int,
    render_pass: str,
    width: int = 1024,
    height: int = 1536,
) -> tuple[dict, dict]:
    """Return (workflow_nodes, settings_used) for the Qwen-Image T2I template."""
    preset = cfg["render"][render_pass]
    image_lora = source.lora_paths.image_lora or PLACEHOLDER_LORA
    validate_lora_stack([{"path": image_lora, "strength": 1.0, "is_identity": True}])

    settings = {
        "MODEL": cfg["models"].get("qwen_image", "qwen_image_fp8.safetensors"),
        "TEXT_ENCODER": cfg["models"].get("qwen_text_encoder", "qwen_3_8b.safetensors"),
        "VAE": cfg["models"].get("qwen_vae", "qwen_image_vae.safetensors"),
        "POSITIVE": positive,
        "NEGATIVE": negative,
        "LORA_PATH": image_lora,
        "LORA_STRENGTH": 1.0,
        "SEED": int(seed),
        "STEPS": int(preset["steps"]),
        "CFG": float(preset["cfg"]),
        "WIDTH": width,
        "HEIGHT": height,
        "FILENAME_PREFIX": f"sourcemode/{source.character_id}_kf",
    }
    from ..config import workflows_dir  # noqa: PLC0415

    template = load_template(workflows_dir(cfg), "qwen_image_t2i")
    return substitute(template, settings), settings


def models_summary(settings: dict) -> dict:
    return {k: v for k, v in settings.items() if k in ("MODEL", "MODEL_HIGH", "MODEL_LOW", "UMT5", "VAE", "TEXT_ENCODER")}


def loras_summary(settings: dict) -> list[dict]:
    out = []
    for key in ("LORA_PATH", "LORA_HIGH", "LORA_LOW"):
        if key in settings:
            out.append({"name": settings[key], "strength": settings["LORA_STRENGTH"]})
    return out
