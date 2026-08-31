"""Render passes: build fully-substituted workflows for a shot.

draft  = lightning/distill LoRA on, low steps (fast look-dev)
final  = lightning off, full steps
Presets come from config [render.draft]/[render.final]. Sampler settings
(steps/cfg/shift) mirror the verified ComfyUI exports in workflows/real/.

Unset LoRA slots (no trained character LoRA yet, lightning off) are pruned
from the graph before submit — ComfyUI validates lora_name against disk even
for unexecuted branches.
"""

from __future__ import annotations

import math
from pathlib import Path

from ..source import CharacterSource
from .workflow import (
    PLACEHOLDER_LORA,
    load_template,
    prune_placeholder_loras,
    substitute,
    validate_lora_stack,
)


def snap_frames(duration_s: float, fps: int, max_frames: int = 81) -> int:
    """Wan wants 4n+1 frame counts. Default cap 81 (e2egen constraint); Jeremy's
    working I2V graph runs 145 frames, so the cap is configurable via [video].max_frames."""
    frames = int(round(duration_s * fps))
    frames = min(frames, max_frames)
    return max(5, (math.floor((frames - 1) / 4) * 4) + 1)


def _lora_entry(path: str | None, strength: float, **flags) -> dict:
    return {"path": path or "", "strength": strength, **flags}


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
    width: int | None = None,
    height: int | None = None,
) -> tuple[dict, dict]:
    """Return (workflow_nodes, settings_used) for the Wan 2.2 I2V two-stage template."""
    preset = cfg["render"][render_pass]
    models = cfg["models"]
    video = cfg["video"]

    lora_high = source.lora_paths.wan_high_noise or ""
    lora_low = source.lora_paths.wan_low_noise or ""
    lightning_high = preset.get("wan_lightning_high", "")
    lightning_low = preset.get("wan_lightning_low", "")
    lightning_strength = float(preset.get("lightning_strength", 1.0))
    identity_strength = 1.0

    loras = [
        _lora_entry(lora_high, identity_strength, is_identity=True),
        _lora_entry(lora_low, identity_strength, is_identity=True),
        _lora_entry(lightning_high, lightning_strength, is_distill=True),
        _lora_entry(lightning_low, lightning_strength, is_distill=True),
    ]
    validate_lora_stack([lora for lora in loras if lora["path"]])

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
        "LIGHTNING_HIGH": lightning_high,
        "LIGHTNING_LOW": lightning_low,
        "LIGHTNING_STRENGTH": lightning_strength,
        "SHIFT": float(video.get("shift", 5.0)),
        "SEED": int(seed),
        "STEPS": steps,
        "CFG_HIGH": float(preset.get("cfg_high", preset["cfg"])),
        "CFG_LOW": float(preset.get("cfg_low", preset["cfg"])),
        "WIDTH": int(width or video["width"]),
        "HEIGHT": int(height or video["height"]),
        "LENGTH": snap_frames(duration_s, int(video["fps"]), int(video.get("max_frames", 81))),
        "FPS": int(video["fps"]),
        "BOUNDARY_STEP": max(1, steps // 2),
        "FILENAME_PREFIX": f"sourcemode/{source.character_id}",
    }
    from ..config import workflows_dir  # noqa: PLC0415

    template = load_template(workflows_dir(cfg), "wan22_i2v")
    return prune_placeholder_loras(substitute(template, settings)), settings


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
    image_lora = source.lora_paths.image_lora or ""
    lightning = preset.get("qwen_t2i_lightning", "")
    lightning_strength = float(preset.get("lightning_strength", 1.0))
    validate_lora_stack(
        [
            lora
            for lora in (
                _lora_entry(image_lora, 1.0, is_identity=True),
                _lora_entry(lightning, lightning_strength, is_distill=True),
            )
            if lora["path"]
        ]
    )

    settings = {
        "MODEL": cfg["models"]["qwen_image"],
        "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"],
        "POSITIVE": positive,
        "NEGATIVE": negative,
        "LORA_PATH": image_lora,
        "LORA_STRENGTH": 1.0,
        "LIGHTNING": lightning,
        "LIGHTNING_STRENGTH": lightning_strength,
        "SHIFT": float(cfg["render"].get("qwen_shift", 3.1)),
        "SEED": int(seed),
        "STEPS": int(preset.get("qwen_t2i_steps", preset["steps"])),
        "CFG": float(preset.get("qwen_t2i_cfg", preset["cfg"])),
        "WIDTH": width,
        "HEIGHT": height,
        "FILENAME_PREFIX": f"sourcemode/{source.character_id}_kf",
    }
    from ..config import workflows_dir  # noqa: PLC0415

    template = load_template(workflows_dir(cfg), "qwen_image_t2i")
    return prune_placeholder_loras(substitute(template, settings)), settings


def build_edit_workflow(
    cfg: dict,
    source: CharacterSource,
    *,
    instruction: str,
    negative: str,
    image_name: str,
    seed: int,
    render_pass: str,
    filename_prefix: str | None = None,
) -> tuple[dict, dict]:
    """Return (workflow_nodes, settings_used) for the Qwen-Image-Edit 2511 template.

    Output resolution is chosen by FluxKontextImageScale from the input image
    (~1MP), matching the verified export.
    """
    preset = cfg["render"][render_pass]
    image_lora = source.lora_paths.image_lora or ""
    lightning = preset.get("qwen_edit_lightning", "")
    lightning_strength = float(preset.get("lightning_strength", 1.0))
    validate_lora_stack(
        [
            lora
            for lora in (
                _lora_entry(image_lora, 1.0, is_identity=True),
                _lora_entry(lightning, lightning_strength, is_distill=True),
            )
            if lora["path"]
        ]
    )

    settings = {
        "MODEL": cfg["models"]["qwen_edit"],
        "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"],
        "POSITIVE": instruction,
        "NEGATIVE": negative,
        "IMAGE": image_name,
        "LORA_PATH": image_lora,
        "LORA_STRENGTH": 1.0,
        "LIGHTNING": lightning,
        "LIGHTNING_STRENGTH": lightning_strength,
        "SHIFT": float(cfg["render"].get("qwen_shift", 3.1)),
        "SEED": int(seed),
        "STEPS": int(preset.get("qwen_edit_steps", preset["steps"])),
        "CFG": float(preset.get("qwen_edit_cfg", preset["cfg"])),
        "FILENAME_PREFIX": filename_prefix or f"sourcemode/{source.character_id}_edit",
    }
    from ..config import workflows_dir  # noqa: PLC0415

    template = load_template(workflows_dir(cfg), "qwen_image_edit")
    return prune_placeholder_loras(substitute(template, settings)), settings


def models_summary(settings: dict) -> dict:
    return {k: v for k, v in settings.items() if k in ("MODEL", "MODEL_HIGH", "MODEL_LOW", "UMT5", "VAE", "TEXT_ENCODER")}


def loras_summary(settings: dict) -> list[dict]:
    out = []
    for key in ("LORA_PATH", "LORA_HIGH", "LORA_LOW"):
        if settings.get(key):
            out.append({"name": settings[key], "strength": settings["LORA_STRENGTH"]})
    for key in ("LIGHTNING", "LIGHTNING_HIGH", "LIGHTNING_LOW"):
        if settings.get(key):
            out.append({"name": settings[key], "strength": settings["LIGHTNING_STRENGTH"]})
    return out
