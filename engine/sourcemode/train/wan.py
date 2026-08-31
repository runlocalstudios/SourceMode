"""musubi-tuner command builders for Wan 2.2 LoRA training.

Builders only — nothing executes without --run. Flag names were read from the
installed musubi-tuner 0.3.4 (docs/wan.md + argparse source), recorded in
INVENTORY.md — notably:
- LoRA+ ratio is a --network_args kwarg (networks/lora.py:477), not a flag.
- Resolution lives in the dataset TOML, not on the CLI.
- fp8_scaled model FILES are unsupported: train against the fp16 DiT weights
  with --fp8_base --fp8_scaled quantizing at load.
- Timestep ranges: low expert 0-875 (spec default; musubi docs suggest 0-900
  for I2V low), high expert 875-1000, with --preserve_distribution_shape.
"""

from __future__ import annotations

from pathlib import Path

from ..source import CharacterSource

EXPERT_TIMESTEPS = {"low": (0, 875), "high": (875, 1000)}


def wan_dataset_toml(dataset_dir: Path, *, resolution: int = 1024, num_repeats: int = 1) -> str:
    """Dataset config for musubi-tuner (image dataset with .txt captions)."""
    d = str(Path(dataset_dir)).replace("\\", "/")
    cache = str(Path(dataset_dir) / "_cache").replace("\\", "/")
    return (
        "[general]\n"
        f"resolution = [{resolution}, {resolution}]\n"
        'caption_extension = ".txt"\n'
        "batch_size = 1\n"
        "enable_bucket = true\n"
        "bucket_no_upscale = false\n"
        "\n"
        "[[datasets]]\n"
        f'image_directory = "{d}"\n'
        f'cache_directory = "{cache}"\n'
        f"num_repeats = {num_repeats}\n"
    )


def build_wan_lora_cmd(
    cfg: dict,
    source: CharacterSource,
    dataset_dir: Path,
    expert: str = "low",
    *,
    output_dir: Path | None = None,
    max_train_steps: int = 1600,
    save_every_n_steps: int = 200,
    seed: int = 42,
) -> dict:
    """Return {"dataset_toml": str, "dataset_toml_path": Path, "commands": [argv, ...]}.

    Sequence: cache latents -> cache text-encoder outputs -> train.
    """
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
    t5 = models_dir / "text_encoders" / cfg["models"]["umt5"]

    dataset_dir = Path(dataset_dir)
    toml_path = dataset_dir / "dataset.toml"
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
    train = [
        str(accelerate), "launch",
        "--num_cpu_threads_per_process", "1",
        "--mixed_precision", "bf16",
        str(musubi / "src" / "musubi_tuner" / "wan_train_network.py"),
        "--task", "i2v-A14B",
        "--dit", str(dit),
        "--dataset_config", str(toml_path),
        "--sdpa",
        "--mixed_precision", "bf16",
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
        "--max_train_steps", str(max_train_steps),
        "--save_every_n_steps", str(save_every_n_steps),
        "--seed", str(seed),
        "--output_dir", str(output_dir),
        "--output_name", output_name,
    ]

    return {
        "dataset_toml": wan_dataset_toml(dataset_dir),
        "dataset_toml_path": toml_path,
        "output_dir": output_dir,
        "output_name": output_name,
        "commands": [cache_latents, cache_te, train],
    }
