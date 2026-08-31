"""musubi-tuner command builders for Wan 2.2 LoRA training.

Builders only — nothing executes without --run. Flag names were read from the
installed musubi-tuner 0.3.4 (docs/wan.md + argparse source), recorded in
INVENTORY.md — notably:
- LoRA+ ratio is a --network_args kwarg (networks/lora.py:477), not a flag.
- Resolution lives in the dataset TOML, not on the CLI.
- fp8_scaled model FILES are unsupported: train against the fp16 DiT weights
  with --fp8_base --fp8_scaled quantizing at load.
- The T5 must be the OFFICIAL models_t5_umt5-xxl-enc-bf16.pth (Wan-AI HF repo):
  musubi's T5 loader uses its own key naming and cannot read the ComfyUI
  umt5_xxl safetensors (HF-style keys — verified against the file header).
- Timestep ranges: low expert 0-875 (spec default; musubi docs suggest 0-900
  for I2V low), high expert 875-1000, with --preserve_distribution_shape.
- Checkpoints save as {output_name}-{epoch:06d}.safetensors.
"""

from __future__ import annotations

from pathlib import Path

from ..source import CharacterSource
from .dataset import choose_epochs, choose_num_repeats, collect_images, dataset_toml

EXPERT_TIMESTEPS = {"low": (0, 875), "high": (875, 1000)}


def build_wan_lora_cmd(
    cfg: dict,
    source: CharacterSource,
    dataset_dir: Path,
    expert: str = "low",
    *,
    output_dir: Path | None = None,
    resolution: int = 1024,
    num_repeats: int | None = None,
    max_train_epochs: int | None = None,
    blocks_to_swap: int = 0,
    seed: int = 42,
) -> dict:
    """Return the full plan: dataset toml + cache latents -> cache TE -> train."""
    if expert not in EXPERT_TIMESTEPS:
        raise ValueError(f"expert must be 'low' or 'high', got {expert!r}")
    min_t, max_t = EXPERT_TIMESTEPS[expert]

    musubi = Path(cfg["training"]["musubi_tuner_path"])
    python = musubi / ".venv" / "Scripts" / "python.exe"
    accelerate = musubi / ".venv" / "Scripts" / "accelerate.exe"
    models_dir = Path(cfg["paths"]["models"])
    dit_key = "wan_i2v_high_fp16" if expert == "high" else "wan_i2v_low_fp16"
    dit = models_dir / "diffusion_models" / cfg["models"][dit_key]
    vae = models_dir / "vae" / cfg["models"]["wan_vae"]
    t5 = models_dir / "text_encoders" / cfg["models"]["wan_t5_train"]

    dataset_dir = Path(dataset_dir)
    n_images = len(collect_images(dataset_dir))
    num_repeats = num_repeats or choose_num_repeats(n_images)
    steps_per_epoch = n_images * num_repeats
    max_train_epochs = max_train_epochs or choose_epochs(steps_per_epoch)

    toml_path = dataset_dir / "dataset_wan.toml"
    output_dir = Path(output_dir) if output_dir else dataset_dir.parent / f"lora_wan_{expert}"
    output_name = f"{source.character_id}_wan22_{expert}"

    cache_latents = [
        str(python), str(musubi / "src" / "musubi_tuner" / "wan_cache_latents.py"),
        "--dataset_config", str(toml_path),
        "--vae", str(vae),
        "--i2v",
    ]
    cache_te = [
        str(python), str(musubi / "src" / "musubi_tuner" / "wan_cache_text_encoder_outputs.py"),
        "--dataset_config", str(toml_path),
        "--t5", str(t5),
        "--batch_size", "16",
    ]
    # The only trainable Wan 2.2 14B files are fp16 (no bf16 repackage exists);
    # musubi asserts mixed_precision must match the DiT file dtype
    # (wan_train_network.py:63), so Wan trains in fp16 — unlike Qwen (bf16).
    train = [
        str(accelerate), "launch",
        "--num_cpu_threads_per_process", "1",
        "--mixed_precision", "fp16",
        str(musubi / "src" / "musubi_tuner" / "wan_train_network.py"),
        "--task", "i2v-A14B",
        "--dit", str(dit),
        "--dataset_config", str(toml_path),
        "--sdpa",
        "--mixed_precision", "fp16",
        "--fp8_base",
        "--fp8_scaled",
        "--optimizer_type", "adamw8bit",
        "--learning_rate", "1.6e-4",
        "--gradient_checkpointing",
        "--max_data_loader_n_workers", "2",
        "--persistent_data_loader_workers",
        "--network_module", "networks.lora_wan",
        "--network_dim", "32",
        "--network_alpha", "16",
        "--network_args", "loraplus_lr_ratio=4",
        "--timestep_sampling", "sigmoid",
        "--discrete_flow_shift", "5.0",
        "--min_timestep", str(min_t),
        "--max_timestep", str(max_t),
        "--preserve_distribution_shape",
        "--max_train_epochs", str(max_train_epochs),
        "--save_every_n_epochs", "1",
        "--seed", str(seed),
        "--output_dir", str(output_dir),
        "--output_name", output_name,
    ]
    if blocks_to_swap > 0:
        train += ["--blocks_to_swap", str(blocks_to_swap)]

    return {
        "kind": f"wan_{expert}",
        "dataset_toml": dataset_toml(
            dataset_dir, cache_dirname="_cache_wan", resolution=resolution, num_repeats=num_repeats
        ),
        "dataset_toml_path": toml_path,
        "output_dir": output_dir,
        "output_name": output_name,
        "n_images": n_images,
        "num_repeats": num_repeats,
        "steps_per_epoch": steps_per_epoch,
        "max_train_epochs": max_train_epochs,
        "total_steps": steps_per_epoch * max_train_epochs,
        "commands": [cache_latents, cache_te, train],
    }
