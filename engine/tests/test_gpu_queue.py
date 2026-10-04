"""The GPU queue: order, the lease, and every way a guard is allowed to give up.

The point of these tests is the negatives. On 2026-10-03 two LoRA trainings ran
at once because a wait loop proceeded after four hours, so the cases that matter
are "it waits" and "it does not look past the head job" - neither of which can be
observed from a passing happy path.
"""

import json

import pytest

from sourcemode.gpu import busy as busy_mod
from sourcemode.gpu import lease as lease_mod
from sourcemode.gpu import queue as q
from sourcemode.gpu.runner import Runner


def _add(doc, label, **kw):
    return q.add(doc, kind=kw.pop("kind", "train"), label=label, cmd=["cmd", label],
                 cwd=".", **kw)


# --- order -----------------------------------------------------------------

def test_file_order_is_run_order_and_survives_a_round_trip(tmp_path):
    path = q.queue_path(tmp_path)
    doc = q.empty()
    for name in ("vivienne_v2", "zara_v2", "marisol_v2"):
        _add(doc, name)
    q.save(path, doc)

    doc = q.load(path)
    assert [j["label"] for j in doc["jobs"]] == ["vivienne_v2", "zara_v2", "marisol_v2"]
    assert q.head(doc)["label"] == "vivienne_v2"

    q.move(doc, doc["jobs"][2]["id"], 0)
    q.save(path, doc)
    assert [j["label"] for j in q.load(path)["jobs"]] == ["marisol_v2", "vivienne_v2", "zara_v2"]


def test_a_held_job_keeps_its_place_but_is_never_picked(tmp_path):
    doc = q.empty()
    first = _add(doc, "vivienne_v2")
    _add(doc, "zara_v2")
    q.set_hold(doc, first["id"], True)
    assert q.head(doc)["label"] == "zara_v2"
    assert doc["jobs"][0]["label"] == "vivienne_v2", "a hold must not reorder anything"
    q.set_hold(doc, first["id"], False)
    assert q.head(doc)["label"] == "vivienne_v2"


def test_the_same_work_cannot_be_queued_twice_by_accident(tmp_path):
    doc = q.empty()
    _add(doc, "zara_v2")
    assert q.duplicate_of(doc, "train", "zara_v2") is not None
    assert q.duplicate_of(doc, "train", "marisol_v2") is None
    q.mark_running(doc, doc["jobs"][0]["id"], 123, "log")
    assert q.duplicate_of(doc, "train", "zara_v2") is not None, "running counts as queued"
    q.mark_finished(doc, doc["jobs"][0]["id"], 0)
    assert q.duplicate_of(doc, "train", "zara_v2") is None, "a finished job is not a duplicate"


def test_a_running_job_is_not_cancellable_from_the_queue(tmp_path):
    doc = q.empty()
    job = _add(doc, "zara_v2")
    q.mark_running(doc, job["id"], 7, "log")
    with pytest.raises(ValueError):
        q.cancel(doc, job["id"])


def test_save_leaves_no_partial_file(tmp_path):
    path = q.queue_path(tmp_path)
    doc = q.empty()
    _add(doc, "zara_v2")
    q.save(path, doc)
    assert json.loads(path.read_text(encoding="utf-8"))["jobs"][0]["label"] == "zara_v2"
    assert not list(path.parent.glob("*.tmp"))


# --- the lease -------------------------------------------------------------

def test_a_second_runner_cannot_take_a_live_lease(tmp_path):
    lp = lease_mod.lease_path(tmp_path)
    lease_mod.acquire(lp)
    with pytest.raises(RuntimeError):
        lease_mod.acquire(lp)


def test_lease_staleness_is_liveness_never_age(tmp_path, monkeypatch):
    lp = lease_mod.lease_path(tmp_path)
    lease_mod.acquire(lp, pid=424242)

    monkeypatch.setattr(lease_mod, "pid_alive", lambda pid: False)
    assert lease_mod.holder(lp) is None, "a dead owner's lease must not block a new runner"
    lease_mod.acquire(lp, pid=1)

    monkeypatch.setattr(lease_mod, "pid_alive", lambda pid: True)
    old = json.loads(lp.read_text(encoding="utf-8"))
    old["started_at"] = "1999-01-01T00:00:00+00:00"
    lp.write_text(json.dumps(old), encoding="utf-8")
    assert lease_mod.holder(lp) is not None, "age alone must never make a lease stale"
    with pytest.raises(RuntimeError):
        lease_mod.acquire(lp)


def test_the_liveness_probe_asks_and_does_not_kill(tmp_path):
    """The first version of pid_alive used os.kill(pid, 0), which on Windows is
    TerminateProcess - it killed the runner whose lease it was checking. The only
    test that can catch that is one that probes a live process and then looks."""
    import subprocess
    import sys

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert lease_mod.pid_alive(child.pid) is True
        assert lease_mod.pid_alive(child.pid) is True
        assert child.poll() is None, "the probe terminated the process it asked about"
    finally:
        child.kill()
        child.wait(timeout=10)
    assert lease_mod.pid_alive(child.pid) is False


def test_the_liveness_probe_says_dead_for_an_impossible_pid():
    assert lease_mod.pid_alive(0) is False
    assert lease_mod.pid_alive(-1) is False
    assert lease_mod.pid_alive(0x7FFFFFF0) is False


def test_release_never_drops_another_runners_lease(tmp_path):
    lp = lease_mod.lease_path(tmp_path)
    lease_mod.acquire(lp, pid=999)
    assert lease_mod.release(lp, pid=1000) is False
    assert lp.is_file()
    assert lease_mod.release(lp, pid=999) is True


# --- the busy probe --------------------------------------------------------

def test_busy_matches_the_work_and_not_the_wrapper_that_asks():
    procs = [
        (1, "python.exe musubi_tuner/qwen_image_train_network.py --dit x"),
        (2, "python.exe dense_epoch_eval.py zara zara_v2 24"),
        (3, "sourcemode.exe assets render --plan x"),
        (4, "powershell.exe -File train_character.ps1 -Ds zara_v2"),
        (5, "sourcemode.exe gpu run"),
        (6, "chrome.exe --type=renderer"),
    ]
    hits = {h["pid"]: h["pattern"] for h in busy_mod.busy(procs)}
    assert set(hits) == {1, 2, 3}
    assert hits[1] == "qwen_image_train_network"
    assert hits[3] == "assets+render"
    # 4 and 5 are wrappers. A probe that matched them would see its own caller,
    # which is how a kill filter once killed the script that issued it.


def test_busy_can_ignore_our_own_children():
    procs = [(11, "qwen_image_train_network.py")]
    assert busy_mod.busy(procs, ignore_pids={11}) == []


# --- the runner's decisions ------------------------------------------------

def _runner(tmp_path, **kw):
    kw.setdefault("busy", lambda: [])
    kw.setdefault("approval", lambda ds: (True, ""))
    return Runner(tmp_path, log=lambda m: None, poll=0, sleeper=lambda s: None, **kw)


def test_it_waits_while_the_card_is_busy_and_never_proceeds(tmp_path):
    path = q.queue_path(tmp_path)
    doc = q.empty()
    _add(doc, "zara_v2")
    q.save(path, doc)

    held = [{"pid": 30144, "pattern": "qwen_image_train_network", "cmd": "..."}]
    r = _runner(tmp_path, busy=lambda: held)
    for _ in range(50):  # however long it waits, it must not start
        assert r.step() == "busy"
    assert q.load(path)["jobs"][0]["status"] == "queued"

    held.clear()
    assert r.step(dry_run=True) == "dry-run"


def test_an_unapproved_head_job_stops_the_queue_instead_of_being_skipped(tmp_path):
    path = q.queue_path(tmp_path)
    doc = q.empty()
    _add(doc, "zara_v2", requires_approval="zara_v2")
    _add(doc, "marisol_v2")
    q.save(path, doc)

    r = _runner(tmp_path, approval=lambda ds: (False, "not approved"))
    assert r.step() == "blocked"
    assert q.load(path)["jobs"][1]["status"] == "queued", "it must NOT run the job behind it"

    # Getting past it is an explicit act, not a timeout.
    doc = q.load(path)
    q.set_hold(doc, doc["jobs"][0]["id"], True)
    q.save(path, doc)
    assert r.step(dry_run=True) == "dry-run"


def test_a_pause_stops_everything_until_it_is_cleared(tmp_path):
    path = q.queue_path(tmp_path)
    doc = q.empty()
    _add(doc, "zara_v2")
    q.pause(doc, "fast failure")
    q.save(path, doc)

    r = _runner(tmp_path)
    assert r.step() == "paused"
    doc = q.load(path)
    q.resume(doc)
    q.save(path, doc)
    assert r.step(dry_run=True) == "dry-run"


def test_a_job_that_fails_fast_pauses_the_queue(tmp_path):
    """dense_epoch_eval.py once died in four seconds on an argv bug after waiting
    seven hours for the card, and the next job took the slot 30 seconds later."""
    path = q.queue_path(tmp_path)
    doc = q.empty()
    job = _add(doc, "zara_v2")
    q.save(path, doc)

    _runner(tmp_path)._finish(job, exit_code=2, seconds=4)
    doc = q.load(path)
    assert doc["jobs"][0]["status"] == "failed"
    assert doc["paused"] is True
    assert "too fast to be a result" in doc["pause_reason"]


def test_a_slow_failure_does_not_pause_the_queue(tmp_path):
    path = q.queue_path(tmp_path)
    doc = q.empty()
    job = _add(doc, "zara_v2")
    q.save(path, doc)

    _runner(tmp_path)._finish(job, exit_code=1, seconds=7200)
    doc = q.load(path)
    assert doc["jobs"][0]["status"] == "failed"
    assert doc["paused"] is False, "a real run that failed is a result; keep going"


def test_it_actually_runs_a_job_end_to_end(tmp_path):
    import sys

    path = q.queue_path(tmp_path)
    doc = q.empty()
    q.add(doc, kind="other", label="hello", cwd=str(tmp_path),
          cmd=[sys.executable, "-c", "print('from the queue')"])
    q.save(path, doc)

    r = _runner(tmp_path)
    assert r.step() == "ran"
    doc = q.load(path)
    job = doc["jobs"][0]
    assert job["status"] == "done"
    assert job["exit_code"] == 0
    log = (tmp_path / "logs") / f"gpu-{job['id']}-hello.log"
    assert "from the queue" in log.read_text(encoding="utf-8")
    assert q.head(doc) is None
