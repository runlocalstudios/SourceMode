from pathlib import Path

import pytest

from sourcemode.train.dataset import (
    DatasetError,
    choose_epochs,
    choose_num_repeats,
    dataset_hash,
    dataset_toml,
    validate_captions,
)


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


