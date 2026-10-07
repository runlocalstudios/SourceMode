"""Monitor readout: every source has a pure parser, tested here without hardware."""

from pathlib import Path

import pytest

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


def test_sample_training_reads_stderr_companion(tmp_path: Path):
    """Start-Process -RedirectStandardOutput/-RedirectStandardError splits the streams:
    header in name.log, tqdm progress (stderr) in name.log.err."""
    header, progress = GABI_LOG.split("steps:", 1)
    (tmp_path / "sunny_t2i.log").write_text(header, encoding="utf-8")
    (tmp_path / "sunny_t2i.log.err").write_text("steps:" + progress, encoding="utf-8")
    t = sample_training(tmp_path, running=True)
    assert t["character"] == "gabi" and t["epochs"] == 20
    assert t["progress"]["step"] == 216 and t["epoch"] == 3


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


def test_monitor_host_prefers_the_argument_then_the_env_var(monkeypatch):
    """The committed default stays loopback because the service has no auth.

    A box that wants remote judging opts in with SOURCEMODE_MONITOR_HOST rather
    than the repo shipping a wide-open bind address. start-monitor.ps1 documented
    this override from the start, but nothing read it.
    """
    from sourcemode.monitor.service import monitor_host

    cfg = {"monitor": {"host": "127.0.0.1"}}
    monkeypatch.delenv("SOURCEMODE_MONITOR_HOST", raising=False)
    assert monitor_host(cfg) == "127.0.0.1"
    monkeypatch.setenv("SOURCEMODE_MONITOR_HOST", "0.0.0.0")
    assert monitor_host(cfg) == "0.0.0.0"
    assert monitor_host(cfg, "100.76.82.42") == "100.76.82.42"   # argument still wins


def test_hub_serves_both_tabs_and_their_counts(tmp_path: Path):
    """One bookmarkable page. The review pages have colliding scripts and both use
    location.hash, so the hub frames them rather than merging them. The GPU tab is
    first: the question on walking up to the box is what it is doing and what is
    next."""
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from PIL import Image

    from sourcemode.assets.judge import make_set, record_verdict
    from sourcemode.monitor.hub import hub_router
    from sourcemode.train.preview import build_preview, record_approval

    jroot, proot = tmp_path / "judge", tmp_path / "prev"
    img = tmp_path / "i"; img.mkdir()
    items = []
    for i in range(2):
        p = img / f"{i}.png"; Image.new("RGB", (8, 8)).save(p)
        items.append({"id": str(i), "path": p, "arm": "A", "group": str(i)})
    make_set(jroot, "done_set", "t", items)
    for i in ("0", "1"):
        record_verdict(jroot, "done_set", i, "keep")
    make_set(jroot, "open_set", "t", items)          # unjudged

    ds = tmp_path / "ds" / "image_face"; ds.mkdir(parents=True)
    q = ds / "a.png"; Image.new("RGB", (8, 8)).save(q); q.with_suffix(".txt").write_text("x", encoding="utf-8")
    build_preview(proot, tmp_path / "ds", measure=False)

    cfg = {"assets": {"judge": str(jroot)}, "train": {"previews": str(proot)},
           "paths": {"outputs": str(tmp_path / "out")}}
    app = FastAPI(); app.include_router(hub_router(cfg))
    c = TestClient(app)

    page = c.get("/").text
    # The GPU tab opens first and is the only frame with an initial src; the other
    # two load on first use so switching back keeps their place.
    assert 'id=p_gpu class="pane on" src="/queue"' in page
    assert "<iframe id=p_judge class=pane" in page
    assert "{gpu:'/queue',judge:'/judge',dataset:'/dataset',shoots:'/shoots',looks:'/appearance'}" in page
    assert "<iframe id=p_shoots class=pane" in page
    assert "show(start[0]||'gpu',start[1])" in page
    # The shell renders the card's state outside the frames, so a glance at any
    # tab answers "what is the card doing".
    assert 'id=nowbar' in page

    assert c.get("/hub/counts").json() == {"gpu": 0, "judge": 1, "datasets": 1}

    # /hub/now carries the same counts plus the sentence and the severity. With
    # nothing queued and nothing running, something is still waiting on him.
    now = c.get("/hub/now").json()
    assert now["counts"] == {"gpu": 0, "judge": 1, "datasets": 1}
    assert now["severity"] == "you"
    assert now["line"] == "Nothing is running"
    assert now["degraded"] == []

    record_approval(proot, "ds", True)
    assert c.get("/hub/counts").json() == {"gpu": 0, "judge": 1, "datasets": 0}


def test_one_broken_manifest_does_not_500_the_badges(tmp_path: Path):
    """`/hub/counts` used to wrap only `gpu` in try/except while `judge` and
    `datasets` called list_sets()/list_previews() bare - and list_sets() reads
    s["items"] and s["title"] with no guard. One malformed file among the 88 in
    outputs/judge/sets/ therefore took out all three badges."""
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from sourcemode.monitor.hub import hub_router

    jroot, proot = tmp_path / "judge", tmp_path / "prev"
    (jroot / "sets").mkdir(parents=True)
    (jroot / "sets" / "broken.json").write_text("{not json", encoding="utf-8")

    cfg = {"assets": {"judge": str(jroot)}, "train": {"previews": str(proot)},
           "paths": {"outputs": str(tmp_path / "out")}}
    app = FastAPI()
    app.include_router(hub_router(cfg))
    r = TestClient(app).get("/hub/now")
    assert r.status_code == 200
    d = r.json()
    assert "judge" in d["degraded"]          # it says which one it could not read
    assert d["counts"]["datasets"] == 0      # and the others still answer


def test_log_mtime_prefers_the_stderr_sidecar(tmp_path: Path, monkeypatch):
    """tqdm writes progress to STDERR, so on a live run the .log stops moving
    while the .log.err keeps going. Line 183 used to overwrite the correct
    max(log, err) with the .log alone: on a healthy run on 2026-10-04 that
    reported 196.8 minutes of silence against the sidecar's 6 seconds, which
    would make any staleness test call every running job dead.
    """
    import os

    from sourcemode.monitor import training as T

    d = tmp_path / "training"
    d.mkdir()
    log = d / "zara_v2.log"
    log.write_text("num train images * repeats / 100" + chr(10)
                   + "epoch to train: 24" + chr(10), encoding="utf-8")
    err = d / "zara_v2.log.err"
    err.write_text("steps:  50%|#####     | 1180/2360 [1:40:12<1:40:12,  5.09s/it]" + chr(10),
                   encoding="utf-8")

    old = 1_700_000_000.0
    os.utime(log, (old, old))                 # the header, written once at start
    os.utime(err, (old + 11_800, old + 11_800))   # tqdm, still going

    monkeypatch.setattr(T, "trainer_running", lambda: True)
    out = T.sample_training(d)
    assert out["log_mtime"] == old + 11_800, (
        "log_mtime must be the NEWER of the log and its .err sidecar")


def test_log_mtime_is_the_log_when_there_is_no_sidecar(tmp_path: Path, monkeypatch):
    import os

    from sourcemode.monitor import training as T

    d = tmp_path / "training"
    d.mkdir()
    log = d / "solo.log"
    log.write_text("epoch to train: 24" + chr(10), encoding="utf-8")
    os.utime(log, (1_700_000_500.0, 1_700_000_500.0))
    monkeypatch.setattr(T, "trainer_running", lambda: False)
    assert T.sample_training(d)["log_mtime"] == 1_700_000_500.0
