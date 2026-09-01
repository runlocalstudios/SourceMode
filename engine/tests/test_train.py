from pathlib import Path

import pytest

from sourcemode.gates.base import GateResult
from sourcemode.train.dataset import (
    DatasetError,
    choose_epochs,
    choose_num_repeats,
    dataset_hash,
    dataset_toml,
    validate_captions,
)
from sourcemode.train.image import build_image_lora_cmd, sample_prompts_text
from sourcemode.train.select import rank_checkpoints
from sourcemode.train.wan import build_wan_lora_cmd


def _flag_value(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]


def make_dataset(tmp_path: Path, n: int = 36, trigger: str = "testchar_tk") -> Path:
    d = tmp_path / "dataset"
    d.mkdir()
    for i in range(n):
        (d / f"img_{i:02d}.png").write_bytes(b"fakepng")
        (d / f"img_{i:02d}.txt").write_text(f"{trigger}, frontal, neutral, shot {i}", encoding="utf-8")
    return d


# --- dataset config ---------------------------------------------------------


def test_validate_captions_ok(tmp_path):
    d = make_dataset(tmp_path, n=3)
    entries = validate_captions(d, "testchar_tk")
    assert len(entries) == 3
    assert all(e["caption"].startswith("testchar_tk") for e in entries)


def test_validate_captions_fails_loudly_on_all_problems(tmp_path):
    d = make_dataset(tmp_path, n=3)
    (d / "img_00.txt").unlink()  # missing
    (d / "img_01.txt").write_text("", encoding="utf-8")  # empty
    (d / "img_02.txt").write_text("no trigger here", encoding="utf-8")  # no trigger
    with pytest.raises(DatasetError) as err:
        validate_captions(d, "testchar_tk")
    msg = str(err.value)
    assert "3 caption problem(s)" in msg
    assert "missing caption" in msg and "is empty" in msg and "does not start with trigger" in msg


def test_dataset_hash_changes_with_content(tmp_path):
    d = make_dataset(tmp_path, n=2)
    h1 = dataset_hash(d, "testchar_tk")
    (d / "img_01.txt").write_text("testchar_tk, different", encoding="utf-8")
    assert dataset_hash(d, "testchar_tk") != h1


def test_choose_num_repeats_36_images_lands_in_range():
    r = choose_num_repeats(36)
    assert 150 <= 36 * r <= 250


def test_choose_num_repeats_large_dataset_stays_1():
    assert choose_num_repeats(300) == 1


def test_choose_epochs_targets_2000_3000():
    epochs = choose_epochs(180)
    assert 2000 <= epochs * 180 <= 3000


def test_dataset_toml_keys(tmp_path):
    toml = dataset_toml(tmp_path / "ds", cache_dirname="_cache_qwen", resolution=1024, num_repeats=5)
    assert "resolution = [1024, 1024]" in toml
    assert 'caption_extension = ".txt"' in toml
    assert "batch_size = 1" in toml
    assert "enable_bucket = true" in toml
    assert "num_repeats = 5" in toml
    assert "_cache_qwen" in toml


# --- image LoRA builder -----------------------------------------------------


def test_image_cmd_flags(cfg, sample_source, tmp_path):
    d = make_dataset(tmp_path)
    plan = build_image_lora_cmd(cfg, sample_source, d)
    cache_latents, cache_te, train = plan["commands"]

    assert cache_latents[1].endswith("qwen_image_cache_latents.py")
    assert _flag_value(cache_latents, "--model_version") == "original"
    assert "--vae" in cache_latents

    assert cache_te[1].endswith("qwen_image_cache_text_encoder_outputs.py")
    # training-grade (non-fp8) text encoder, not the ComfyUI fp8_scaled one
    assert "fp8" not in _flag_value(cache_te, "--text_encoder")

    assert train[0].endswith("accelerate.exe")
    assert _flag_value(train, "--network_module") == "networks.lora_qwen_image"
    assert _flag_value(train, "--network_dim") == "32"
    assert _flag_value(train, "--network_alpha") == "16"
    assert _flag_value(train, "--optimizer_type") == "adamw8bit"
    assert _flag_value(train, "--learning_rate") == "1e-4"
    assert _flag_value(train, "--timestep_sampling") == "shift"
    assert _flag_value(train, "--discrete_flow_shift") == "2.2"
    assert _flag_value(train, "--weighting_scheme") == "none"
    assert "--fp8_base" in train and "--fp8_scaled" in train
    assert "--gradient_checkpointing" in train
    # bf16 DiT file, never the fp8 inference file
    assert "bf16" in _flag_value(train, "--dit")
    assert _flag_value(train, "--save_every_n_epochs") == "1"
    assert _flag_value(train, "--sample_every_n_epochs") == "1"
    assert "--blocks_to_swap" not in train  # default 0 = omitted


def test_image_cmd_step_budget(cfg, sample_source, tmp_path):
    d = make_dataset(tmp_path)
    plan = build_image_lora_cmd(cfg, sample_source, d)
    assert plan["steps_per_epoch"] == 36 * plan["num_repeats"]
    assert 2000 <= plan["total_steps"] <= 3000


def test_image_cmd_blocks_to_swap(cfg, sample_source, tmp_path):
    d = make_dataset(tmp_path)
    plan = build_image_lora_cmd(cfg, sample_source, d, blocks_to_swap=16)
    assert _flag_value(plan["commands"][2], "--blocks_to_swap") == "16"


def test_sample_prompts_frontal_and_fixed(sample_source):
    text = sample_prompts_text(sample_source)
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert len(lines) == 4
    for ln in lines:
        assert ln.startswith("testchar_tk, ")
        assert "--w 1024" in ln and "--h 1024" in ln and "--d " in ln
        assert "--n text, watermark, extra limbs" in ln


# --- wan LoRA builder -------------------------------------------------------


def test_wan_cmd_low_expert_flags(cfg, sample_source, tmp_path):
    d = make_dataset(tmp_path)
    plan = build_wan_lora_cmd(cfg, sample_source, d, "low")
    cache_latents, cache_te, train = plan["commands"]

    assert cache_latents[1].endswith("wan_cache_latents.py")
    assert "--i2v" in cache_latents
    assert "--clip" not in cache_latents  # Wan 2.2 needs no CLIP

    assert cache_te[1].endswith("wan_cache_text_encoder_outputs.py")
    # official Wan-AI T5 .pth — musubi cannot read the ComfyUI umt5 safetensors
    assert _flag_value(cache_te, "--t5").endswith("models_t5_umt5-xxl-enc-bf16.pth")

    assert _flag_value(train, "--task") == "i2v-A14B"
    # fp16 DiT files force fp16 mixed precision (musubi wan_train_network.py:63)
    assert _flag_value(train, "--mixed_precision") == "fp16"
    assert _flag_value(train, "--network_module") == "networks.lora_wan"
    assert _flag_value(train, "--network_args") == "loraplus_lr_ratio=4"
    assert _flag_value(train, "--learning_rate") == "1.6e-4"
    assert _flag_value(train, "--timestep_sampling") == "sigmoid"
    assert _flag_value(train, "--discrete_flow_shift") == "5.0"
    assert _flag_value(train, "--min_timestep") == "0"
    assert _flag_value(train, "--max_timestep") == "875"
    assert "--preserve_distribution_shape" in train
    assert "fp16" in _flag_value(train, "--dit")
    assert _flag_value(train, "--save_every_n_epochs") == "1"
    assert 2000 <= plan["total_steps"] <= 3000


def test_wan_cmd_high_expert_timesteps(cfg, sample_source, tmp_path):
    d = make_dataset(tmp_path)
    plan = build_wan_lora_cmd(cfg, sample_source, d, "high")
    train = plan["commands"][2]
    assert _flag_value(train, "--min_timestep") == "875"
    assert _flag_value(train, "--max_timestep") == "1000"
    assert "high" in _flag_value(train, "--dit")


def test_wan_cmd_rejects_unknown_expert(cfg, sample_source, tmp_path):
    d = make_dataset(tmp_path)
    with pytest.raises(ValueError):
        build_wan_lora_cmd(cfg, sample_source, d, "medium")


# --- checkpoint selection ---------------------------------------------------


class MappedScorer:
    """Fake scorer: score by filename/dirname substring."""

    def __init__(self, mapping):
        self.mapping = mapping

    def score(self, asset_path: Path, source) -> GateResult:
        for key, value in self.mapping.items():
            if key in asset_path.name or key in str(asset_path.parent):
                return GateResult(score=value, passed=None)
        return GateResult(score=0.0, passed=None)


def test_select_ranks_by_mean(sample_source, tmp_path):
    for name in ("ckpt_a", "ckpt_b"):
        d = tmp_path / name
        d.mkdir()
        (d / "sample1.png").write_bytes(b"x")
        (d / "sample2.png").write_bytes(b"x")
    scorer = MappedScorer({"ckpt_a": 0.4, "ckpt_b": 0.9})
    ranking = rank_checkpoints(tmp_path, sample_source, scorer)
    assert [r["checkpoint"] for r in ranking] == ["ckpt_b", "ckpt_a"]
    assert ranking[0]["mean_score"] == pytest.approx(0.9)


def test_select_groups_musubi_sample_names(sample_source, tmp_path):
    # musubi layout: flat sample/ dir, {name}_e{epoch:06d}_{prompt:02d}_{ts}_{seed}.png
    sample = tmp_path / "sample"
    sample.mkdir()
    for epoch, score_tag in [(1, "early"), (2, "late")]:
        for i in range(2):
            (sample / f"gwen_image_e{epoch:06d}_{i:02d}_20260831_1001.png").write_bytes(b"x")
    scorer = MappedScorer({"e000001": 0.8, "e000002": 0.6})
    ranking = rank_checkpoints(tmp_path, sample_source, scorer)
    assert [r["checkpoint"] for r in ranking] == ["e000001", "e000002"]
    assert ranking[0]["n_scored"] == 2


def test_select_by_min_ranks_on_worst_frame(sample_source, tmp_path):
    sample = tmp_path / "sample"
    sample.mkdir()
    # e1: scores 0.9 / 0.5 (mean .7, min .5) — e2: 0.65 / 0.65 (mean .65, min .65)
    (sample / "x_e000001_00_ts_1.png").write_bytes(b"x")
    (sample / "x_e000001_hi_01_ts_1.png").write_bytes(b"x")
    (sample / "x_e000002_00_ts_1.png").write_bytes(b"x")
    (sample / "x_e000002_01_ts_1.png").write_bytes(b"x")

    class PerFile:
        def score(self, asset_path, source):
            if "e000001" in asset_path.name:
                return GateResult(score=0.9 if "hi" in asset_path.name else 0.5, passed=None)
            return GateResult(score=0.65, passed=None)

    by_mean = rank_checkpoints(tmp_path, sample_source, PerFile(), by="mean")
    assert by_mean[0]["checkpoint"] == "e000001"
    by_min = rank_checkpoints(tmp_path, sample_source, PerFile(), by="min")
    assert by_min[0]["checkpoint"] == "e000002"


def test_select_tie_breaks_toward_earlier_checkpoint(sample_source, tmp_path):
    sample = tmp_path / "sample"
    sample.mkdir()
    for epoch in (3, 1, 2):
        (sample / f"x_e{epoch:06d}_00_ts_1.png").write_bytes(b"x")

    class Constant:
        def score(self, asset_path, source):
            return GateResult(score=0.75, passed=None)

    ranking = rank_checkpoints(tmp_path, sample_source, Constant())
    assert [r["checkpoint"] for r in ranking] == ["e000001", "e000002", "e000003"]


def test_select_near_tie_prefers_better_worst_sample(sample_source, tmp_path):
    """Bianca case: e4 led on mean by 0.003 but its worst sample was 0.106 lower."""
    sample = tmp_path / "sample"
    sample.mkdir()
    for epoch in (4, 5):
        for i in range(2):
            (sample / f"x_e{epoch:06d}_{i:02d}_ts_1.png").write_bytes(b"x")

    class Bianca:
        # e4: 0.874/0.522 -> mean 0.698, min 0.522
        # e5: 0.762/0.628 -> mean 0.695, min 0.628
        def score(self, asset_path, source):
            e4 = "e000004" in asset_path.name
            first = "_00_" in asset_path.name
            if e4:
                return GateResult(score=0.874 if first else 0.522, passed=None)
            return GateResult(score=0.762 if first else 0.628, passed=None)

    ranking = rank_checkpoints(tmp_path, sample_source, Bianca())
    assert ranking[0]["checkpoint"] == "e000005"  # near-tie on mean -> better min wins
    assert ranking[0]["min_score"] == pytest.approx(0.628)

    # a real mean gap (outside tolerance) still decides
    strict = rank_checkpoints(tmp_path, sample_source, Bianca(), tolerance=0.0001)
    assert strict[0]["checkpoint"] == "e000004"


def test_select_rejects_unknown_by(sample_source, tmp_path):
    with pytest.raises(ValueError):
        rank_checkpoints(tmp_path, sample_source, MappedScorer({}), by="median")


def test_select_reports_unavailable(sample_source, tmp_path):
    d = tmp_path / "ckpt"
    d.mkdir()
    (d / "s.png").write_bytes(b"x")

    class Unavailable:
        def score(self, asset_path, source):
            return GateResult(score=None, passed=None, details="insightface not installed")

    ranking = rank_checkpoints(tmp_path, sample_source, Unavailable())
    assert ranking[0]["unavailable"] == "insightface not installed"


def test_select_flags_prompt_inertia(sample_source, tmp_path):
    from PIL import Image

    inert = tmp_path / "sample"
    inert.mkdir()
    # e1: identical grey images -> inertia; e2: varied brightness -> ok
    for i in range(3):
        Image.new("RGB", (32, 32), (128, 128, 128)).save(inert / f"x_e000001_{i:02d}_ts_1.png")
    for i, v in enumerate((30, 128, 220)):
        Image.new("RGB", (32, 32), (v, v, v)).save(inert / f"x_e000002_{i:02d}_ts_1.png")

    class Constant:
        def score(self, asset_path, source):
            return GateResult(score=0.8, passed=None)

    ranking = rank_checkpoints(tmp_path, sample_source, Constant(), check_inertia=True)
    rows = {r["checkpoint"]: r for r in ranking}
    assert rows["e000001"]["prompt_inertia"] is True
    assert rows["e000002"]["prompt_inertia"] is False
