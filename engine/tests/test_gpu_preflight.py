"""`gpu add` refuses a job that would die in its first minute.

Every case here is a job that really was queued and really did die fast: a
missing script, a flag in a positional slot, a training into a folder that
already holds checkpoints, a sweep of a checkpoint that does not exist.
"""

import sys
from pathlib import Path

from sourcemode.gpu.preflight import preflight

PY = sys.executable


def _job(cmd, cwd):
    return {"cmd": cmd, "cwd": str(cwd)}


def test_a_clean_python_script_passes(tmp_path):
    s = tmp_path / "ok.py"
    s.write_text("print('hi')\n", encoding="utf-8")
    assert preflight(_job([PY, str(s)], tmp_path), tmp_path) == []


def test_missing_script_and_bad_cwd_are_named(tmp_path):
    out = preflight(_job([PY, str(tmp_path / "gone.py")], tmp_path), tmp_path)
    assert any("does not exist" in p for p in out)
    assert preflight(_job([PY, "x.py"], tmp_path / "nowhere"), tmp_path) == \
        [f"cwd {tmp_path / 'nowhere'} does not exist"]


def test_a_script_that_does_not_compile_is_caught(tmp_path):
    s = tmp_path / "bad.py"
    s.write_text("def (:\n", encoding="utf-8")
    out = preflight(_job([PY, str(s)], tmp_path), tmp_path)
    assert any("does not compile" in p for p in out)


def test_relative_script_resolves_against_cwd(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    assert preflight(_job([PY, "scripts/ok.py"], tmp_path), tmp_path) == []


def test_dense_epoch_eval_flag_in_a_positional_slot(tmp_path):
    # the 2026-10-03 failure: "--scenes" landed in the epoch-offset slot
    s = tmp_path / "dense_epoch_eval.py"
    s.write_text("", encoding="utf-8")
    ck = tmp_path / "lora"; ck.mkdir()
    (ck / "x_v2-000020.safetensors").write_bytes(b"0")
    cmd = [PY, str(s), "nobody", "x_v2", "24", "16", "24", "nobody", str(ck), "20",
           "--allow-incomplete-appearance", "--epochs", "20,22"]
    out = preflight(_job(cmd, tmp_path), tmp_path)
    assert out == ["epoch 22: x_v2-000022.safetensors is not in " + str(ck)]
    # and the epoch that exists is not complained about
    cmd[-1] = "20"
    assert preflight(_job(cmd, tmp_path), tmp_path) == []


def test_dense_epoch_eval_without_checkpoints(tmp_path):
    s = tmp_path / "dense_epoch_eval.py"
    s.write_text("", encoding="utf-8")
    cmd = [PY, str(s), "nobody", "x_v2", "24", "16", "24", "nobody", str(tmp_path / "none"), "20",
           "--allow-incomplete-appearance"]
    out = preflight(_job(cmd, tmp_path), tmp_path)
    assert out == [f"checkpoint folder {tmp_path / 'none'} does not exist"]


def test_unconfirmed_appearance_is_a_problem_for_a_sweep(tmp_path):
    s = tmp_path / "dense_epoch_eval.py"
    s.write_text("", encoding="utf-8")
    ck = tmp_path / "lora"; ck.mkdir()
    (ck / "x_v2.safetensors").write_bytes(b"0")
    cmd = [PY, str(s), "nobody_at_all", "x_v2", "24", "16", "24", "nobody_at_all", str(ck), "20"]
    out = preflight(_job(cmd, tmp_path), tmp_path)
    assert len(out) == 1 and "appearance record is not ready" in out[0]


def test_training_refuses_existing_checkpoints_and_unapproved_set(tmp_path, monkeypatch):
    # train_character.ps1 is looked up by name; parsing is skipped when the
    # file is empty, so the per-script guard is what is under test
    s = tmp_path / "train_character.ps1"
    s.write_text("", encoding="utf-8")
    outputs = tmp_path / "outputs"
    ds = outputs / "lora-datasets" / "nobody_v2"
    (ds / "image_src").mkdir(parents=True)
    (ds / "lora").mkdir()
    (ds / "lora" / "nobody_v2-000001.safetensors").write_bytes(b"0")
    previews = tmp_path / "previews"
    (previews / "previews").mkdir(parents=True)
    monkeypatch.setattr("sourcemode.gpu.preflight.TRAIN_DISK_GB", 0)
    cmd = ["powershell.exe", "-File", str(s), "-Ds", "nobody_v2", "-Char", "nobody"]
    out = preflight({"cmd": cmd, "cwd": str(tmp_path), "requires_approval": "nobody_v2"}, outputs, previews)
    assert any("already holds 1 checkpoints" in p for p in out)
    assert any("not approved" in p for p in out)
    assert any("appearance record" in p for p in out)


def test_prompt_ab_needs_find_and_two_arms(tmp_path):
    s = tmp_path / "prompt_ab.py"
    s.write_text("", encoding="utf-8")
    ck = tmp_path / "lora"; ck.mkdir()
    (ck / "x_v2-000023.safetensors").write_bytes(b"0")
    cmd = [PY, str(s), "nobody_at_all", "x_v2", "23", str(ck), "nobody", "--arms", "A=x"]
    out = preflight(_job(cmd, tmp_path), tmp_path)
    assert "--find is required" in out
    assert any("--arms needs at least two" in p for p in out)
    assert not any("no checkpoint" in p for p in out)
