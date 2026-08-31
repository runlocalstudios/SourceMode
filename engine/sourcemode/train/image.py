"""musubi-tuner command builder for the Qwen-Image identity LoRA.

Flag names verified against the installed musubi-tuner 0.3.4
(docs/qwen_image.md + qwen_image_train_network.py argparse):
- Training CANNOT load fp8_scaled/fp8_e4m3fn model FILES: it needs the bf16
  DiT (qwen_image_2512_bf16) + non-fp8 text encoder (qwen_2.5_vl_7b);
  --fp8_base --fp8_scaled quantize at load instead (~30 GB @ 1024/bs1).
- The ComfyUI qwen_image_vae.safetensors IS accepted for training.
- --network_module networks.lora_qwen_image; sampling during training via
  --sample_prompts (line format: prompt --w --h --d seed --s steps --l cfg
  --n negative), saved to <output_dir>/sample/.
- Docs recommend --timestep_sampling shift --weighting_scheme none
  --discrete_flow_shift 2.2 for Qwen-Image (much lower shift than video).
- Checkpoints save as {output_name}-{epoch:06d}.safetensors.
"""

from __future__ import annotations

from pathlib import Path

from ..source import CharacterSource
from .dataset import choose_epochs, choose_num_repeats, collect_images, dataset_toml

# Fixed FRONTAL sample prompts: identity scoring is pose-sensitive, so
# checkpoint-selection samples must all be frontal for scores to be comparable.
SAMPLE_PROMPT_TEMPLATES = [
    "{trigger}, medium close-up, neutral expression, soft daylight, plain grey background",
    "{trigger}, medium shot, slight smile, warm indoor lamp light, cozy living room",
    "{trigger}, close-up, serious expression, overcast daylight, city street",
    "{trigger}, medium close-up, laughing, golden hour, park",
]
SAMPLE_SEED_BASE = 1001
SAMPLE_STEPS = 20
SAMPLE_CFG = 4.0  # matches [render.final] qwen_t2i_cfg


class ImageTrainerNotConfigured(RuntimeError):
    pass


def sample_prompts_text(source: CharacterSource) -> str:
    lines = ["# fixed frontal prompts for checkpoint selection (pose-sensitive scorer)"]
    for i, template in enumerate(SAMPLE_PROMPT_TEMPLATES):
        prompt = template.format(trigger=source.trigger_token)
        line = f"{prompt} --w 1024 --h 1024 --d {SAMPLE_SEED_BASE + i} --s {SAMPLE_STEPS} --l {SAMPLE_CFG}"
        if source.negative_block:
            line += f" --n {source.negative_block}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def build_image_lora_cmd(
    cfg: dict,
    source: CharacterSource,
    dataset_dir: Path,
    *,
    output_dir: Path | None = None,
    resolution: int = 1024,
    num_repeats: int | None = None,
    max_train_epochs: int | None = None,
    learning_rate: str = "1e-4",
    network_dim: int = 32,
    network_alpha: int = 16,
    blocks_to_swap: int = 0,
    seed: int = 42,
) -> dict:
    """Return the full plan: dataset toml, sample prompts, cache+train commands."""
    musubi = Path(cfg["training"]["musubi_tuner_path"])
    if not (musubi / "src" / "musubi_tuner" / "qwen_image_train_network.py").exists():
        raise ImageTrainerNotConfigured(
            f"musubi-tuner at {musubi} has no qwen_image_train_network.py — "
            "check [training].musubi_tuner_path"
        )
    python = musubi / ".venv" / "Scripts" / "python.exe"
    accelerate = musubi / ".venv" / "Scripts" / "accelerate.exe"
    models_dir = Path(cfg["paths"]["models"])
    dit = models_dir / "diffusion_models" / cfg["models"]["qwen_image_bf16"]
    vae = models_dir / "vae" / cfg["models"]["qwen_vae"]
    text_encoder = models_dir / "text_encoders" / cfg["models"]["qwen_text_encoder_bf16"]

    dataset_dir = Path(dataset_dir)
    n_images = len(collect_images(dataset_dir))
    num_repeats = num_repeats or choose_num_repeats(n_images)
    steps_per_epoch = n_images * num_repeats
    max_train_epochs = max_train_epochs or choose_epochs(steps_per_epoch)

    toml_path = dataset_dir / "dataset_qwen.toml"
    output_dir = Path(output_dir) if output_dir else dataset_dir.parent / "lora_image"
    output_name = f"{source.character_id}_image"
    sample_prompts_path = output_dir / "sample_prompts.txt"

    cache_latents = [
        str(python), str(musubi / "src" / "musubi_tuner" / "qwen_image_cache_latents.py"),
        "--dataset_config", str(toml_path),
        "--vae", str(vae),
        "--model_version", "original",
    ]
    cache_te = [
        str(python), str(musubi / "src" / "musubi_tuner" / "qwen_image_cache_text_encoder_outputs.py"),
        "--dataset_config", str(toml_path),
        "--text_encoder", str(text_encoder),
        "--batch_size", "1",
        "--model_version", "original",
    ]
    train = [
        str(accelerate), "launch",
        "--num_cpu_threads_per_process", "1",
        "--mixed_precision", "bf16",
        str(musubi / "src" / "musubi_tuner" / "qwen_image_train_network.py"),
        "--dit", str(dit),
        "--vae", str(vae),
        "--text_encoder", str(text_encoder),
        "--model_version", "original",
        "--dataset_config", str(toml_path),
        "--sdpa",
        "--mixed_precision", "bf16",
        "--fp8_base",
        "--fp8_scaled",
        "--optimizer_type", "adamw8bit",
        "--learning_rate", learning_rate,
        "--gradient_checkpointing",
        "--max_data_loader_n_workers", "2",
        "--persistent_data_loader_workers",
        "--network_module", "networks.lora_qwen_image",
        "--network_dim", str(network_dim),
        "--network_alpha", str(network_alpha),
        "--timestep_sampling", "shift",
        "--weighting_scheme", "none",
        "--discrete_flow_shift", "2.2",
        "--max_train_epochs", str(max_train_epochs),
        "--save_every_n_epochs", "1",
        "--sample_prompts", str(sample_prompts_path),
        "--sample_every_n_epochs", "1",
        "--seed", str(seed),
        "--output_dir", str(output_dir),
        "--output_name", output_name,
    ]
    if blocks_to_swap > 0:
        train += ["--blocks_to_swap", str(blocks_to_swap)]

    return {
        "kind": "image",
        "dataset_toml": dataset_toml(
            dataset_dir, cache_dirname="_cache_qwen", resolution=resolution, num_repeats=num_repeats
        ),
        "dataset_toml_path": toml_path,
        "sample_prompts": sample_prompts_text(source),
        "sample_prompts_path": sample_prompts_path,
        "output_dir": output_dir,
        "output_name": output_name,
        "n_images": n_images,
        "num_repeats": num_repeats,
        "steps_per_epoch": steps_per_epoch,
        "max_train_epochs": max_train_epochs,
        "total_steps": steps_per_epoch * max_train_epochs,
        "commands": [cache_latents, cache_te, train],
    }
