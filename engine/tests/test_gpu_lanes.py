"""Two lanes, one runner (2026-10-14).

Jeremy: "can they be run concurrently when one runs on the CPU and one runs
on the GPU? ... I'm aligned with capping the CPU usage." A job declares its
lane; the card lane never waits on a CPU job, the CPU lane never waits on the
card, the CPU lane is capped and runs at low priority, and a restart is
honoured only between jobs.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

from sourcemode.gpu import queue as q
from sourcemode.gpu.runner import RESTART_FLAG, Runner


def _runner(tmp_path, **kw):
    kw.setdefault("busy", lambda: [])
    kw.setdefault("produced", lambda job: None)
    kw.setdefault("approval", lambda ds: (True, ""))
    kw.setdefault("procs", lambda: [(1, "x")])
    return Runner(tmp_path, log=lambda m: None, poll=0, sleeper=lambda s: None, cpu_threads=3, **kw)


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_a_job_declares_its_lane_and_each_lane_has_its_own_head(tmp_path):
    doc = q.empty()
    a = q.add(doc, kind="shoot", label="a", cmd=["x"], cwd=".")
    b = q.add(doc, kind="voice", label="b", cmd=["x"], cwd=".", lane="cpu")
    c = q.add(doc, kind="shoot", label="c", cmd=["x"], cwd=".")
    assert q.lane_of(a) == "gpu" and q.lane_of(b) == "cpu" and "lane" in b
    assert q.head(doc)["id"] == a["id"] and q.head(doc, "cpu")["id"] == b["id"]
    q.set_hold(doc, a["id"], True)
    assert q.head(doc, "gpu")["id"] == c["id"]              # the card lane skips nothing but its own held job
    assert q.head(doc, "cpu")["id"] == b["id"]
    legacy = {"id": "j001", "status": "queued", "hold": False}  # queued before lanes existed
    assert q.lane_of(legacy) == "gpu"
    with pytest.raises(ValueError):
        q.add(doc, kind="x", label="y", cmd=["x"], cwd=".", lane="tpu")
    assert [j["id"] for j in q.running(doc, "cpu")] == []


def test_the_cpu_lane_runs_while_the_card_is_busy_capped_and_the_card_lane_ignores_it(tmp_path):
    path = q.queue_path(tmp_path)
    doc = q.empty()
    out = tmp_path / "env.json"
    gpu = q.add(doc, kind="shoot", label="card", cmd=["x"], cwd=str(tmp_path))
    cpu = q.add(doc, kind="voice", label="amanda", cwd=str(tmp_path), lane="cpu",
                cmd=_py(f"import os,json;json.dump({{k:os.environ.get(k) for k in "
                        f"('OMP_NUM_THREADS','MKL_NUM_THREADS','TORCH_NUM_THREADS','SOURCEMODE_LANE')}},"
                        f"open(r'{out}','w'))"))
    q.save(path, doc)
    held = [{"pid": 30144, "pattern": "qwen_image_train_network", "cmd": "..."}]
    r = _runner(tmp_path, busy=lambda: held)
    assert r.step() == "busy"                                   # the card lane waits on the card
    assert r.cpu_step() == "ran"                                # the CPU lane does not
    doc = q.load(path)
    assert q.find(doc, cpu["id"])["status"] == "done" and q.find(doc, gpu["id"])["status"] == "queued"
    env = json.loads(out.read_text())
    assert env == {"OMP_NUM_THREADS": "3", "MKL_NUM_THREADS": "3", "TORCH_NUM_THREADS": "3",
                   "SOURCEMODE_LANE": "cpu"}
    assert r.cpu_step() == "empty"
    # a CPU job at the head of the FILE never blocks the card lane
    doc = q.load(path)
    q.add(doc, kind="voice", label="held-cpu", cmd=["x"], cwd=".", lane="cpu", requires_approval="nope")
    q.save(path, doc)
    r2 = _runner(tmp_path, approval=lambda ds: (False, "not approved"))
    assert r2.cpu_step() == "blocked"
    assert r2.step(dry_run=True) == "dry-run"                   # the card lane still sees its own head


def test_a_paused_queue_stops_the_cpu_lane_too(tmp_path):
    path = q.queue_path(tmp_path)
    doc = q.empty()
    q.add(doc, kind="voice", label="v", cmd=_py("print(1)"), cwd=str(tmp_path), lane="cpu")
    q.pause(doc, "fast failure")
    q.save(path, doc)
    assert _runner(tmp_path).cpu_step() == "paused"


def test_a_restart_is_honoured_only_when_both_lanes_are_idle(tmp_path):
    path = q.queue_path(tmp_path)
    q.save(path, q.empty())
    r = _runner(tmp_path)
    flag = tmp_path / "gpu-queue" / RESTART_FLAG
    flag.write_text("x")
    assert r.restart_requested()
    r._cpu_busy = True
    # serve() with a busy CPU lane must keep waiting, not exit: run it on a
    # thread and release the lane after a few polls
    waited = []
    r.sleep = lambda s: waited.append(s) or (setattr(r, "_cpu_busy", False) if len(waited) >= 3 else None)
    t = threading.Thread(target=r.serve, daemon=True); t.start(); t.join(10)
    assert not t.is_alive(), "serve() should have exited once the lane went idle"
    assert len(waited) >= 3 and not flag.exists()


def test_gpu_add_takes_the_lane_and_list_shows_it(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from sourcemode import cli

    monkeypatch.setattr(cli, "_gpu_paths", lambda: (tmp_path, q.queue_path(tmp_path)))
    monkeypatch.setattr("sourcemode.gpu.preflight.preflight", lambda *a, **k: [])
    monkeypatch.setattr("sourcemode.monitor.queue_page.expect_for", lambda cfg, cmd: None)
    res = CliRunner().invoke(cli.app, ["gpu", "add", "voice", "amanda", "--cpu", "--", "python", "-c", "pass"])
    assert res.exit_code == 0, res.output
    doc = q.load(q.queue_path(tmp_path))
    assert q.lane_of(doc["jobs"][0]) == "cpu" and "cpu lane" in res.output
    res = CliRunner().invoke(cli.app, ["gpu", "list"])
    assert "cpu lane" in res.output
    res = CliRunner().invoke(cli.app, ["gpu", "restart"])
    assert res.exit_code == 0 and (tmp_path / "gpu-queue" / RESTART_FLAG).is_file()
