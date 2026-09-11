"""Monitor readout: every source has a pure parser, tested here without hardware."""

from pathlib import Path

from sourcemode.monitor.comfy import job_label, parse_queue, sample_comfy
from sourcemode.monitor.gpu import parse_nvidia_smi, sample_gpu
from sourcemode.monitor.sampler import summarise
from sourcemode.monitor.training import (
    epoch_of, find_latest_log, parse_progress, parse_run_info, sample_training, trainer_running,
)

# Captured from the gabi_v1 run, 2026-09-10 — tqdm overwrites with \r, so a real log
# has many progress lines on one "line".
GABI_LOG = (
    "INFO:musubi_tuner.training.trainer_base:Load dataset config from "
    "C:\\dev\\sourcemode\\engine\\outputs\\lora-datasets\\gabi\\dataset_qwen_edit.toml\n"
    "override steps. steps for 20 epochs is / 指定エポックまでのステップ数: 1640\n"
    "  num batches per epoch / 1epochのバッチ数: 82\n"
    "  num epochs / epoch数: 20\n"
    "steps:   0%|          | 0/1640 [00:00<?, ?it/s]\r"
    "steps:  13%|█▎        | 215/1640 [31:00<3:25:30,  8.64s/it, avr_loss=0.052]\r"
    "steps:  13%|█▎        | 216/1640 [31:07<3:25:09,  8.64s/it, avr_loss=0.051] "
)


def test_parse_progress_takes_last_line():
    p = parse_progress(GABI_LOG)
    assert p == {"step": 216, "total": 1640, "elapsed_s": 31 * 60 + 7,
                 "eta_s": 3 * 3600 + 25 * 60 + 9, "s_per_it": 8.64, "loss": 0.051}


def test_parse_progress_none_before_first_step():
    assert parse_progress("INFO: loading model\n") is None
    # the very first tqdm line has an unknown ETA; must not crash
    p = parse_progress("steps:   0%|          | 0/1640 [00:00<?, ?it/s]")
    assert p["step"] == 0 and p["eta_s"] is None


def test_parse_run_info_finds_character_and_epochs():
    info = parse_run_info(GABI_LOG)
    assert info == {"character": "gabi", "epochs": 20, "batches_per_epoch": 82}


def test_epoch_of():
    assert epoch_of(0, 82) == 1
    assert epoch_of(82, 82) == 1
    assert epoch_of(83, 82) == 2
    assert epoch_of(1640, 82) == 20
    assert epoch_of(10, None) is None


def test_sample_training_reads_newest_log(tmp_path: Path):
    old = tmp_path / "old.log"; old.write_text("steps: 100%|██| 10/10 [00:10<00:00, 1.00s/it]", encoding="utf-8")
    new = tmp_path / "gabi_v1.log"; new.write_text(GABI_LOG, encoding="utf-8")
    import os, time
    os.utime(old, (time.time() - 100, time.time() - 100))
    assert find_latest_log(tmp_path) == new
    t = sample_training(tmp_path, running=True)
    assert t["active"] is True and t["character"] == "gabi"
    assert t["epoch"] == 3 and t["epochs"] == 20
    assert t["progress"]["eta_s"] == 12309


def test_sample_training_finished_log_no_process(tmp_path: Path):
    (tmp_path / "done.log").write_text(
        "num batches per epoch / 1epochのバッチ数: 5\nnum epochs / epoch数: 2\n"
        "steps: 100%|██| 10/10 [00:10<00:00, 1.00s/it]", encoding="utf-8")
    t = sample_training(tmp_path, running=False)
    assert t["active"] is False and t["progress"]["step"] == 10


def test_sample_training_unknown_process_infers_from_log(tmp_path: Path, monkeypatch):
    """No process table (psutil missing): a log short of its total counts as active."""
    from sourcemode.monitor import training as tr
    monkeypatch.setattr(tr, "trainer_running", lambda: None)
    (tmp_path / "run.log").write_text(GABI_LOG, encoding="utf-8")
    t = sample_training(tmp_path)
    assert t["process"] is None and t["active"] is True
    (tmp_path / "run.log").write_text(
        "num epochs / epoch数: 1\nsteps: 100%|██| 10/10 [00:10<00:00, 1.00s/it]", encoding="utf-8")
    assert sample_training(tmp_path)["active"] is False


def test_sample_training_reads_utf16_log(tmp_path: Path):
    """PowerShell `*>` writes UTF-16LE with a BOM; the gabi_v2 run was invisible until this."""
    (tmp_path / "gabi_v2.log").write_bytes(b"\xff\xfe" + GABI_LOG.encode("utf-16-le"))
    t = sample_training(tmp_path, running=True)
    assert t["character"] == "gabi" and t["epochs"] == 20
    assert t["progress"]["step"] == 216 and t["progress"]["eta_s"] == 12309


def test_parse_run_info_survives_console_wrapping():
    """A PowerShell-redirected log is hard-wrapped at ~80 columns mid-line."""
    wrapped = (
        "INFO:musubi_tuner.training.trainer_base:Load dataset config from \r\n"
        "C:\\dev\\sourcemode\\engine\\outputs\\lora-datasets\\gabi_v2\\dataset_qwen_edit.toml\r\n"
        "  num batches per epoch / 1epochのバッチ数: \r\n83\r\n"
        "  num epochs / \r\nepoch数: 20\r\n"
    )
    assert parse_run_info(wrapped) == {"character": "gabi_v2", "epochs": 20, "batches_per_epoch": 83}
    # and the console codepage may have replaced the Japanese labels with "?"
    mojibake = "  num batches per epoch / 1epoch?????: 83\r\n  num epochs / epoch?: 20\r\n"
    assert parse_run_info(mojibake) == {"character": None, "epochs": 20, "batches_per_epoch": 83}


def test_sample_training_header_deep_in_a_big_log(tmp_path: Path):
    """The epoch count came 80 KB in (after a long config dump) on a 700 KB log."""
    body = ("INFO:musubi_tuner.training.trainer_base:Load dataset config from "
            "C:/x/lora-datasets/gabi_v2/dataset_qwen_edit.toml\n"
            + "config line\n" * 6000                      # ~72 KB of dump
            + "  num batches per epoch / 1epochのバッチ数: 83\n  num epochs / epoch数: 20\n"
            + "steps:  50%|█████     | 830/1660 [2:00:00<2:00:00,  8.70s/it, avr_loss=0.05]\r" * 8000)
    (tmp_path / "big.log").write_text(body, encoding="utf-8")
    assert (tmp_path / "big.log").stat().st_size > 600_000
    t = sample_training(tmp_path, running=True)
    assert t["character"] == "gabi_v2" and t["epochs"] == 20 and t["epoch"] == 10
    assert t["progress"]["step"] == 830


def test_decode_log_handles_odd_utf16_slices():
    from sourcemode.monitor.training import decode_log
    full = b"\xff\xfe" + "steps:  10%|█| 1/10 [00:01<00:09,  1.00s/it]".encode("utf-16-le")
    # a tail slice that starts mid code-unit must not shift every character
    text = decode_log(full[:20], full[21:])
    assert "1/10" in text


def test_sample_training_no_logs(tmp_path: Path):
    t = sample_training(tmp_path / "missing", running=False)
    assert t == {"active": False, "process": False, "log": None, "character": None,
                 "progress": None, "epoch": None, "epochs": None, "log_mtime": None}


def test_trainer_running_matches_cmdline():
    procs = [{"cmdline": ["python", "C:/x/qwen_image_train_network.py", "--dit", "a"]}]
    assert trainer_running(lambda: procs) is True
    assert trainer_running(lambda: [{"cmdline": ["python", "main.py"]}]) is False
    assert trainer_running(lambda: [{"cmdline": None}]) is False


def test_parse_nvidia_smi():
    g = parse_nvidia_smi("NVIDIA GeForce RTX 5090, 99, 23835, 32607, 71, 512.30, 600.00\n")
    assert g["name"] == "NVIDIA GeForce RTX 5090"
    assert g["util_pct"] == 99 and g["mem_used_mb"] == 23835 and g["mem_total_mb"] == 32607
    assert g["temp_c"] == 71 and g["power_w"] == 512.3
    assert parse_nvidia_smi("garbage") is None
    assert parse_nvidia_smi("") is None
    assert parse_nvidia_smi("X, [N/A], 1, 2, 3, 4, 5")["util_pct"] is None


def test_sample_gpu_failure_is_unknown_not_idle():
    class Proc:
        returncode = 1; stdout = ""
    assert sample_gpu(runner=lambda *a, **k: Proc()) is None

    def boom(*a, **k):
        raise OSError("no nvidia-smi")
    assert sample_gpu(runner=boom) is None


def test_parse_queue_and_label():
    graph = {"9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "scan/gabi/work_03"}},
             "1": {"class_type": "KSampler", "inputs": {}}}
    q = parse_queue({"queue_running": [[0, "id", graph, {}, []]], "queue_pending": [[1, "b", {}, {}, []]] * 3})
    assert q == {"running": 1, "pending": 3, "labels": ["scan/gabi/work_03"]}
    assert job_label({}) is None
    assert parse_queue({}) == {"running": 0, "pending": 0, "labels": []}


def test_sample_comfy_unreachable():
    class Session:
        def get(self, *a, **k):
            raise ConnectionError
    assert sample_comfy("127.0.0.1", 1, session=Session())["reachable"] is False


def test_summarise_priorities():
    gpu = {"util_pct": 99}
    training = {"active": True, "character": "gabi", "epoch": 3, "epochs": 20,
                "progress": {"step": 216, "total": 1640, "eta_s": 12309}}
    j = summarise(gpu, training, {"reachable": True, "running": 1})
    assert j["kind"] == "training" and j["title"] == "Training gabi"
    assert j["detail"] == "epoch 3/20" and abs(j["progress"] - 216 / 1640) < 1e-9 and j["eta_s"] == 12309

    idle_training = {"active": False}
    j = summarise(gpu, idle_training, {"reachable": True, "running": 1, "pending": 2,
                                        "labels": ["scan/gabi/work_03"]})
    assert j["kind"] == "rendering" and "scan/gabi/work_03" in j["title"] and j["detail"] == "2 queued"

    assert summarise({"util_pct": 3}, idle_training, {"reachable": False})["kind"] == "idle"
    assert summarise({"util_pct": 80}, idle_training, {"reachable": False})["kind"] == "busy"
    # unreadable GPU must never be reported as idle
    assert summarise(None, idle_training, {"reachable": False})["kind"] == "unknown"
