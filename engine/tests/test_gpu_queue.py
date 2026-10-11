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
    kw.setdefault("produced", lambda job: None)
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


# --- a job left running by a dead runner -------------------------------------

def _orphaned(tmp_path):
    """j1 running as PID 68892 (a shoot), j2 queued behind it."""
    path = q.queue_path(tmp_path)
    doc = q.empty()
    a = q.add(doc, kind="shoot", label="cat:club", cwd=".",
              cmd=["python.exe", "C:/x/run_shoots.py", "cat", "club"])
    _add(doc, "gigi:influencer", kind="shoot")
    q.mark_running(doc, a["id"], 68892, "log")
    q.save(path, doc)
    return path


def test_an_orphaned_job_that_is_still_alive_is_waited_on(tmp_path):
    """2026-10-10: the runner died printing START; the cat shoot kept rendering,
    and nothing in busy() matches a shoot."""
    path = _orphaned(tmp_path)
    procs = [(68892, "python.exe C:/x/run_shoots.py cat club"), (4, "System")]
    r = _runner(tmp_path, procs=lambda: procs)
    for _ in range(20):
        assert r.step(dry_run=True) == "busy"
    doc = q.load(path)
    assert [j["status"] for j in doc["jobs"]] == ["running", "queued"]


def test_a_recycled_pid_is_not_the_job(tmp_path):
    path = _orphaned(tmp_path)
    r = _runner(tmp_path, procs=lambda: [(68892, "notepad.exe"), (4, "System")])
    assert r.step(dry_run=True) == "dry-run"
    j = q.load(path)["jobs"][0]
    assert j["status"] == "failed" and j["exit_code"] is None
    assert "exit code unknown" in j["note"]


def test_once_the_orphan_ends_it_is_closed_and_the_queue_moves_on(tmp_path):
    path = _orphaned(tmp_path)
    procs = [(68892, "python.exe C:/x/run_shoots.py cat club"), (4, "System")]
    r = _runner(tmp_path, procs=lambda: procs)
    assert r.step(dry_run=True) == "busy"
    procs.pop(0)
    assert r.step(dry_run=True) == "dry-run"
    assert q.load(path)["jobs"][0]["status"] == "failed"


def test_an_unreadable_process_list_waits_rather_than_guessing(tmp_path):
    path = _orphaned(tmp_path)
    r = _runner(tmp_path, procs=lambda: [])
    assert r.step(dry_run=True) == "busy"
    assert q.load(path)["jobs"][0]["status"] == "running"


def test_the_runner_log_survives_an_emoji_shortcode_and_a_dumb_console(tmp_path, monkeypatch):
    """"shoot:cat:club" became a cat emoji under rich, and cp1252 killed the runner."""
    import io
    import sys

    from sourcemode import cli

    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    monkeypatch.setattr(cli, "_gpu_paths", lambda: (tmp_path, None))
    seen = []

    class FakeRunner:
        def __init__(self, out, log, poll):
            self.log = log

        def serve(self, once, dry_run):
            self.log("START j106 shoot:cat:club pid=1 -> x")
            self.log("caf\u00e9 \U0001f431")
            seen.append(True)

    monkeypatch.setattr("sourcemode.gpu.runner.Runner", FakeRunner)
    cli.gpu_run(once=True, dry_run=True, poll=0)
    assert seen
    text = (tmp_path / "logs" / "gpu-runner.log").read_text(encoding="utf-8")
    assert "shoot:cat:club" in text and "\U0001f431" in text


def test_an_orphan_that_wrote_everything_is_closed_as_done(tmp_path):
    """cat:club, 2026-10-10: all 8 shots written, recorded as failed."""
    path = _orphaned(tmp_path)
    r = _runner(tmp_path, procs=lambda: [(4, "System")], produced=lambda job: (8, 8))
    assert r.step(dry_run=True) == "dry-run"
    j = q.load(path)["jobs"][0]
    assert j["status"] == "done" and j["exit_code"] == 0
    assert "8 of 8 images written" in j["note"]


def test_an_orphan_that_fell_short_is_still_unknown(tmp_path):
    path = _orphaned(tmp_path)
    r = _runner(tmp_path, procs=lambda: [(4, "System")], produced=lambda job: (5, 8))
    assert r.step(dry_run=True) == "dry-run"
    j = q.load(path)["jobs"][0]
    assert j["status"] == "failed" and j["exit_code"] is None
