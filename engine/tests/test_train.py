from pathlib import Path

import pytest

from sourcemode.gates.base import GateResult
from sourcemode.train.image import ImageTrainerNotConfigured, build_image_lora_cmd
from sourcemode.train.select import rank_checkpoints
from sourcemode.train.wan import build_wan_lora_cmd, wan_dataset_toml


def _flag_value(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]


def test_wan_cmd_low_expert_flags(cfg, sample_source, tmp_path):
    plan = build_wan_lora_cmd(cfg, sample_source, tmp_path / "dataset", "low")
    cache_latents, cache_te, train = plan["commands"]

    assert cache_latents[1].endswith("wan_cache_latents.py")
    assert "--i2v" in cache_latents
    assert "--vae" in cache_latents
    assert "--clip" not in cache_latents  # Wan 2.2 needs no CLIP

    assert cache_te[1].endswith("wan_cache_text_encoder_outputs.py")
    assert "--t5" in cache_te

    assert train[0].endswith("accelerate.exe")
    assert _flag_value(train, "--task") == "i2v-A14B"
    assert _flag_value(train, "--network_module") == "networks.lora_wan"
    assert _flag_value(train, "--network_dim") == "32"
    assert _flag_value(train, "--network_alpha") == "16"
    assert _flag_value(train, "--network_args") == "loraplus_lr_ratio=4"
    assert _flag_value(train, "--optimizer_type") == "adamw8bit"
    assert _flag_value(train, "--learning_rate") == "1.6e-4"
    assert _flag_value(train, "--timestep_sampling") == "sigmoid"
    assert _flag_value(train, "--discrete_flow_shift") == "5.0"
    assert _flag_value(train, "--min_timestep") == "0"
    assert _flag_value(train, "--max_timestep") == "875"
    assert "--fp8_base" in train and "--fp8_scaled" in train
    assert "--gradient_checkpointing" in train
    assert "--preserve_distribution_shape" in train
    # trains against fp16 DiT weights, never fp8_scaled files
    assert "fp16" in _flag_value(train, "--dit")
    assert "--save_every_n_steps" in train


def test_wan_cmd_high_expert_timesteps(cfg, sample_source, tmp_path):
    plan = build_wan_lora_cmd(cfg, sample_source, tmp_path / "dataset", "high")
    train = plan["commands"][2]
    assert _flag_value(train, "--min_timestep") == "875"
    assert _flag_value(train, "--max_timestep") == "1000"
    assert "high" in _flag_value(train, "--dit")


def test_wan_cmd_rejects_unknown_expert(cfg, sample_source, tmp_path):
    with pytest.raises(ValueError):
        build_wan_lora_cmd(cfg, sample_source, tmp_path, "medium")


def test_dataset_toml_carries_resolution(tmp_path):
    toml = wan_dataset_toml(tmp_path / "ds", resolution=1024)
    assert "resolution = [1024, 1024]" in toml
    assert 'caption_extension = ".txt"' in toml


def test_image_trainer_placeholder(cfg, sample_source, tmp_path):
    with pytest.raises(ImageTrainerNotConfigured) as err:
        build_image_lora_cmd(cfg, sample_source, tmp_path)
    assert "image_trainer_path" in str(err.value)


class MappedScorer:
    """Fake scorer: score by filename prefix."""

    def __init__(self, mapping):
        self.mapping = mapping

    def score(self, asset_path: Path, source) -> GateResult:
        for key, value in self.mapping.items():
            if key in asset_path.name or key in str(asset_path.parent):
                return GateResult(score=value, passed=None)
        return GateResult(score=0.0, passed=None)


def test_select_ranks_checkpoints(sample_source, tmp_path):
    for name, score in [("ckpt_a", "low"), ("ckpt_b", "high")]:
        d = tmp_path / name
        d.mkdir()
        (d / "sample1.png").write_bytes(b"x")
        (d / "sample2.png").write_bytes(b"x")

    scorer = MappedScorer({"ckpt_a": 0.4, "ckpt_b": 0.9})
    ranking = rank_checkpoints(tmp_path, sample_source, scorer)
    assert [r["checkpoint"] for r in ranking] == ["ckpt_b", "ckpt_a"]
    assert ranking[0]["mean_score"] == pytest.approx(0.9)
    assert ranking[0]["n_scored"] == 2


def test_select_reports_unavailable(sample_source, tmp_path):
    d = tmp_path / "ckpt"
    d.mkdir()
    (d / "s.png").write_bytes(b"x")

    class Unavailable:
        def score(self, asset_path, source):
            return GateResult(score=None, passed=None, details="insightface not installed")

    ranking = rank_checkpoints(tmp_path, sample_source, Unavailable())
    assert ranking[0]["unavailable"] == "insightface not installed"
