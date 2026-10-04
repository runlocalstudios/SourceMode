"""The single runner: one job at a time, in the queue's order, forever.

Design rules, each of them a scar:

- **It waits; it never gives up and proceeds.** No duration in this file may let
  a job start. The 2026-10-03 double training came from a wait loop that logged
  "card busy 4h - proceeding" and launched on top of a live run.
- **It never looks past a blocked head job.** An unapproved set at the head stops
  the queue and says so; moving past it needs an explicit `gpu hold`. Order is
  what Jeremy set, not what the runner finds convenient.
- **It knows its own children, so no completion markers are involved at all.**
  A marker that was already present once fired a job instantly, four minutes into
  a seven-hour run; waiting on `proc.wait()` cannot have that bug.
- **A job that fails FAST pauses the queue.** `dense_epoch_eval.py` once died in
  four seconds on an argv bug after waiting seven hours for the card, and the next
  job took the slot 30 seconds later. A quick non-zero exit is a broken
  invocation, not a result, so the rest of the queue is not fed to it.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from . import queue as q
from .busy import gpu_busy
from .lease import acquire, lease_path, release

FAST_FAIL_SECONDS = 60
POLL_SECONDS = 60


def approval_ok(ds_id: str) -> tuple[bool, str]:
    """Reuses the engine's own approval record - the same check `sourcemode train
    approved` makes, called in-process rather than shelled out, so there is one
    implementation of "is this set approved"."""
    from ..config import load_config  # noqa: PLC0415
    from ..train.preview import approval_state, preview_root  # noqa: PLC0415

    st = approval_state(preview_root(load_config()), ds_id)
    if st["approved"]:
        return True, ""
    if st["stale"]:
        return False, f"approval STALE for {ds_id} - images or captions changed since it was approved"
    return False, f"{ds_id} is not approved - run `sourcemode train preview` and review it"


class Runner:
    def __init__(self, outputs_root: Path, *, log=print, poll: float = POLL_SECONDS,
                 sleeper=time.sleep, approval=approval_ok, busy=gpu_busy):
        self.outputs = outputs_root
        self.qpath = q.queue_path(outputs_root)
        self.logs = outputs_root / "logs"
        self.log = log
        self.poll = poll
        self.sleep = sleeper
        self.approval = approval
        self.busy = busy
        self._said: str | None = None

    def _say_once(self, msg: str) -> None:
        """Waiting is normal; saying so once per change keeps the log readable."""
        if msg != self._said:
            self.log(msg)
            self._said = msg

    def _start(self, job: dict) -> subprocess.Popen:
        self.logs.mkdir(parents=True, exist_ok=True)
        log_path = self.logs / f"gpu-{job['id']}-{job['label']}.log"
        handle = log_path.open("ab")
        proc = subprocess.Popen(job["cmd"], cwd=job["cwd"], stdout=handle,
                                stderr=subprocess.STDOUT, close_fds=True)
        doc = q.load(self.qpath)
        q.mark_running(doc, job["id"], proc.pid, str(log_path))
        q.save(self.qpath, doc)
        self.log(f"START {job['id']} {job['kind']}:{job['label']} pid={proc.pid} -> {log_path}")
        return proc

    def _finish(self, job: dict, exit_code: int, seconds: float) -> None:
        doc = q.load(self.qpath)
        q.mark_finished(doc, job["id"], exit_code)
        verdict = "done" if exit_code == 0 else "FAILED"
        if exit_code != 0 and seconds < FAST_FAIL_SECONDS:
            reason = (f"{job['id']} {job['label']} exited {exit_code} after {seconds:.0f}s - "
                      f"too fast to be a result, so the queue is paused rather than fed to it")
            q.pause(doc, reason)
            self.log("PAUSED: " + reason)
        q.save(self.qpath, doc)
        self.log(f"END {job['id']} {job['kind']}:{job['label']} {verdict} exit={exit_code} in {seconds:.0f}s")

    def step(self, *, dry_run: bool = False) -> str:
        """One decision. Returns what it did, which is usually 'wait: <why>'."""
        doc = q.load(self.qpath)
        if doc["paused"]:
            self._say_once(f"wait: queue PAUSED - {doc['pause_reason']}")
            return "paused"

        job = q.head(doc)
        if job is None:
            self._say_once("wait: nothing queued")
            return "empty"

        if job["requires_approval"]:
            ok, why = self.approval(job["requires_approval"])
            if not ok:
                self._say_once(f"wait: {job['id']} {job['label']} blocked - {why}"
                               f" (re-approve it, or `gpu hold {job['id']}` to let the queue past)")
                return "blocked"

        held = self.busy()
        if held:
            who = ", ".join(f"PID {h['pid']} ({h['pattern']})" for h in held)
            self._say_once(f"wait: card busy - {who}; {job['id']} {job['label']} is next")
            return "busy"

        if dry_run:
            self.log(f"DRY RUN would start {job['id']} {job['kind']}:{job['label']}: {' '.join(job['cmd'])}")
            return "dry-run"

        self._said = None
        proc = self._start(job)
        started = time.monotonic()
        code = proc.wait()
        self._finish(job, code, time.monotonic() - started)
        return "ran"

    def serve(self, *, once: bool = False, dry_run: bool = False) -> None:
        lp = lease_path(self.outputs)
        rec = acquire(lp)
        self.log(f"gpu runner up, lease PID {rec['pid']}; queue {self.qpath}")
        try:
            while True:
                what = self.step(dry_run=dry_run)
                if once and what in ("ran", "dry-run", "empty"):
                    return
                if what != "ran":
                    self.sleep(self.poll)
        finally:
            release(lp)
            self.log("gpu runner down, lease released")
