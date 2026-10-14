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
- **A job a dead runner left behind is still a job on the card.** 2026-10-10:
  the runner crashed printing its START line, and the cat shoot it had just
  launched kept rendering as an orphan. A fresh runner saw no queued head in
  the way and nothing in `busy` that matches a shoot, so it would have started
  the next shoot on top of it. Any job still marked running whose process is
  alive is waited on; once it is gone it is closed with its exit code unknown.
- **A job that fails FAST pauses the queue.** `dense_epoch_eval.py` once died in
  four seconds on an argv bug after waiting seven hours for the card, and the next
  job took the slot 30 seconds later. A quick non-zero exit is a broken
  invocation, not a result, so the rest of the queue is not fed to it.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from pathlib import Path

from . import queue as q
from .busy import gpu_busy, process_list
from .lease import acquire, lease_path, release

FAST_FAIL_SECONDS = 60
POLL_SECONDS = 60
#: the CPU lane's share of the cores. 8 of 24: a TTS model gains little past
#: eight threads, and the card's job keeps the rest for decoding, uploads and
#: the InsightFace passes that saturate every core they are given.
CPU_LANE_THREADS = 8
RESTART_FLAG = "runner.restart"


def log_name(job: dict) -> str:
    """The job's log file name. 2026-10-10: "shoot:gigi:influencer" made
    "gpu-j107-gigi" - NTFS read the colon as an alternate data stream, so the
    file was empty and the log hid inside it. Characters Windows forbids in a
    file name become "_"."""
    return f"gpu-{job['id']}-" + re.sub(r'[<>:"/\\|?*]', "_", str(job["label"])) + ".log"


def still_running(job: dict, processes: list[tuple[int, str]]) -> bool:
    """Is this job's own process alive? Same PID AND the job's script in its
    command line, so a recycled PID is not mistaken for the job."""
    pid = job.get("pid")
    if not pid:
        return False
    key = next((c for c in job.get("cmd", []) if c.lower().endswith(".py")),
               (job.get("cmd") or [""])[-1]).lower()
    return any(p == pid and key in (cmd or "").lower() for p, cmd in processes)


def produced(job: dict) -> tuple[int, int] | None:
    """(written, expected) images for a job, counted the way the GPU page counts
    them, or None when the job's output cannot be counted."""
    try:
        from ..config import load_config  # noqa: PLC0415
        from ..monitor.queue_page import job_done, job_expect  # noqa: PLC0415

        exp = job_expect(job)
        if not exp:
            return None
        done = job_done(load_config(), job)
        return None if done is None else (int(done), int(exp[0]))
    except Exception:  # noqa: BLE001 - a count that cannot be made is "unknown"
        return None


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
                 sleeper=time.sleep, approval=approval_ok, busy=gpu_busy,
                 procs=process_list, produced=produced, cpu_threads: int = CPU_LANE_THREADS):
        self.outputs = outputs_root
        self.qpath = q.queue_path(outputs_root)
        self.logs = outputs_root / "logs"
        self.log = log
        self.poll = poll
        self.sleep = sleeper
        self.approval = approval
        self.busy = busy
        self.procs = procs
        self.produced = produced
        self.cpu_threads = int(cpu_threads)
        self._said: str | None = None
        self._said_cpu: str | None = None
        # one file, two lanes in one process: every load-modify-save holds this
        self._lock = threading.RLock()
        self._cpu_busy = False
        self._gpu_busy = False

    def _say_once(self, msg: str) -> None:
        """Waiting is normal; saying so once per change keeps the log readable."""
        if msg != self._said:
            self.log(msg)
            self._said = msg

    def cpu_env(self) -> dict:
        """The CPU lane's environment: every threading library capped to the
        lane's share, so a TTS run cannot take all 24 cores from the card's job."""
        n = str(self.cpu_threads)
        env = dict(os.environ)
        env.update({"OMP_NUM_THREADS": n, "MKL_NUM_THREADS": n, "OPENBLAS_NUM_THREADS": n,
                    "NUMEXPR_NUM_THREADS": n, "TORCH_NUM_THREADS": n, "SOURCEMODE_LANE": "cpu"})
        return env

    def _start(self, job: dict) -> subprocess.Popen:
        self.logs.mkdir(parents=True, exist_ok=True)
        log_path = self.logs / log_name(job)
        handle = log_path.open("ab")
        cpu = q.lane_of(job) == "cpu"
        extra: dict = {}
        if cpu:
            extra["env"] = self.cpu_env()
            # below normal: when both lanes want a core, the card's job wins
            flag = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
            if flag:
                extra["creationflags"] = flag
        proc = subprocess.Popen(job["cmd"], cwd=job["cwd"], stdout=handle,
                                stderr=subprocess.STDOUT, close_fds=True, **extra)
        with self._lock:
            doc = q.load(self.qpath)
            q.mark_running(doc, job["id"], proc.pid, str(log_path))
            q.save(self.qpath, doc)
        self.log(f"START {job['id']} {job['kind']}:{job['label']}{' [cpu lane]' if cpu else ''} "
                 f"pid={proc.pid} -> {log_path}")
        return proc

    def _finish(self, job: dict, exit_code: int, seconds: float) -> None:
        with self._lock:
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

    # --- the CPU lane ----------------------------------------------------------
    def _say_once_cpu(self, msg: str) -> None:
        if msg != self._said_cpu:
            self.log(msg)
            self._said_cpu = msg

    def cpu_step(self, *, dry_run: bool = False) -> str:
        """One decision for the CPU lane. Same rules as the card's: it waits, it
        never looks past a blocked head, it honours the pause - but it never
        waits on the card, and the card never waits on it."""
        with self._lock:
            doc = q.load(self.qpath)
        if doc["paused"]:
            self._say_once_cpu(f"cpu lane: wait - queue PAUSED - {doc['pause_reason']}")
            return "paused"
        left = q.running(doc, "cpu")
        if left:
            # an orphan on this lane is waited on exactly as the card's are; the
            # main loop closes it once it is gone
            procs = self.procs()
            if not procs or any(still_running(j, procs) for j in left):
                self._say_once_cpu("cpu lane: wait - " + ", ".join(j["id"] for j in left)
                                   + " still running from an earlier runner")
                return "busy"
            return "busy"
        job = q.head(doc, "cpu")
        if job is None:
            self._say_once_cpu("cpu lane: nothing queued")
            return "empty"
        if job["requires_approval"]:
            ok, why = self.approval(job["requires_approval"])
            if not ok:
                self._say_once_cpu(f"cpu lane: wait - {job['id']} {job['label']} blocked - {why}")
                return "blocked"
        if dry_run:
            self.log(f"DRY RUN cpu lane would start {job['id']} {job['kind']}:{job['label']}: {' '.join(job['cmd'])}")
            return "dry-run"
        self._said_cpu = None
        self._cpu_busy = True
        try:
            proc = self._start(job)
            started = time.monotonic()
            code = proc.wait()
            self._finish(job, code, time.monotonic() - started)
        finally:
            self._cpu_busy = False
        return "ran"

    def _cpu_loop(self, stop: threading.Event) -> None:
        while not stop.is_set():
            if self.restart_requested():          # start nothing new; let both lanes drain
                stop.wait(self.poll)
                continue
            try:
                what = self.cpu_step()
            except Exception as ex:  # noqa: BLE001 - the lane logs and keeps serving
                self.log(f"cpu lane: ERROR {ex!r}")
                what = "error"
            if what != "ran":
                stop.wait(self.poll)

    def restart_requested(self) -> bool:
        """`sourcemode gpu restart` drops a flag; the runner exits when BOTH
        lanes are idle, so new code takes over between jobs and never under one."""
        return (self.outputs / "gpu-queue" / RESTART_FLAG).is_file()

    def step(self, *, dry_run: bool = False) -> str:
        """One decision. Returns what it did, which is usually 'wait: <why>'."""
        doc = q.load(self.qpath)
        if doc["paused"]:
            self._say_once(f"wait: queue PAUSED - {doc['pause_reason']}")
            return "paused"

        # step() blocks in proc.wait() for its own children, so anything marked
        # running here was started by a runner that is no longer alive
        left = q.running(doc)
        if left:
            procs = self.procs()
            if not procs:
                self._say_once("wait: cannot read the process list, so cannot tell whether "
                               + ", ".join(j["id"] for j in left) + " is still running")
                return "busy"
            for j in left:
                if still_running(j, procs):
                    self._say_once(f"wait: {j['id']} {j['label']} is still running as PID {j['pid']},"
                                   f" left by an earlier runner - waiting for it to finish")
                    return "busy"
            for j in left:
                # 2026-10-10: cat:club wrote all 8 shots and was recorded as
                # failed because only the exit code was lost. Count its output.
                got = self.produced(j)
                if got and got[1] and got[0] >= got[1]:
                    q.mark_finished(doc, j["id"], 0)
                    q.find(doc, j["id"])["note"] = ((j.get("note") or "") + "; " if j.get("note") else "") + (
                        f"runner died while it ran; closed as done - {got[0]} of {got[1]} images written")
                    self.log(f"END {j['id']} {j['kind']}:{j['label']} done - its runner died while it ran,"
                             f" but all {got[1]} images were written")
                    continue
                q.mark_lost(doc, j["id"])
                self.log(f"LOST {j['id']} {j['kind']}:{j['label']} - its runner died while it ran;"
                         f" the process has ended, exit code unknown"
                         + (f", {got[0]} of {got[1]} images written" if got else ""))
            with self._lock:
                q.save(self.qpath, doc)

        job = q.head(doc, "gpu")
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
        self._gpu_busy = True
        try:
            proc = self._start(job)
            started = time.monotonic()
            code = proc.wait()
            self._finish(job, code, time.monotonic() - started)
        finally:
            self._gpu_busy = False
        return "ran"

    def serve(self, *, once: bool = False, dry_run: bool = False) -> None:
        lp = lease_path(self.outputs)
        rec = acquire(lp)
        self.log(f"gpu runner up, lease PID {rec['pid']}; queue {self.qpath}")
        stop = threading.Event()
        cpu_thread = None
        if not once and not dry_run:
            cpu_thread = threading.Thread(target=self._cpu_loop, args=(stop,), name="cpu-lane", daemon=True)
            cpu_thread.start()
            self.log(f"cpu lane up: {self.cpu_threads} threads, below-normal priority")
        try:
            while True:
                # a restart is honoured BETWEEN jobs: nothing new starts on either
                # lane, and the runner leaves once what is running has ended
                if self.restart_requested() and not once:
                    if not self._cpu_busy and not self._gpu_busy:
                        (self.outputs / "gpu-queue" / RESTART_FLAG).unlink(missing_ok=True)
                        self.log("restart requested and both lanes idle - exiting for the new runner")
                        return
                    self._say_once("wait: restart requested - finishing what is running, starting nothing new")
                    self.sleep(self.poll)
                    continue
                what = self.step(dry_run=dry_run)
                if once and what in ("ran", "dry-run", "empty"):
                    return
                if what != "ran":
                    self.sleep(self.poll)
        finally:
            stop.set()
            release(lp)
            self.log("gpu runner down, lease released")
