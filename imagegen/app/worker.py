"""The generation queue. One run at a time, one outstanding request at a time.

Order of operations per shot, and it matters: bind the shot and its final filename,
mark it `running` and COMMIT, send, write the image to the final filename, record
usage, mark `saved` and COMMIT, then look at the next shot. Nothing is inferred from
timestamps or directory listings. The queue pauses itself on anything account-wide.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from . import pricing as pricing_mod
from .client import ApiError
from .runs import now, recount, run_dir, save_run

MAX_TRANSIENT_TRIES = 4
MAX_RATE_LIMIT_TRIES = 4
BACKOFF_S = (2, 5, 15, 30)
PAUSE_KINDS = {"quota", "auth", "config", "local_io"}


class Worker:
    def __init__(self, client, outputs: Path, pricing_path: Path, sleep=time.sleep):
        self.client = client
        self.outputs = outputs
        self.pricing_path = pricing_path
        self.sleep = sleep
        self.run: dict | None = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: threading.Thread | None = None
        self._only: set[str] | None = None
        self.lock = threading.RLock()
        self.log: list[str] = []

    # -- control ---------------------------------------------------------------
    def start(self, run: dict, only: list[str] | None = None) -> None:
        with self.lock:
            if self.active():
                raise RuntimeError("a run is already active")
            self.run = run
            run["paused"] = False
            run["pause_reason"] = None
            save_run(run, self.outputs)
            self._stop.clear()
            self._pause.clear()
            self._only = set(only) if only else None
            self._thread = threading.Thread(target=self._loop, daemon=True, name="imagegen-worker")
            self._thread.start()

    def pause(self, reason: str = "paused by user") -> None:
        self._pause.set()
        with self.lock:
            if self.run:
                self.run["paused"] = True
                self.run["pause_reason"] = reason
                save_run(self.run, self.outputs)

    def resume(self) -> None:
        with self.lock:
            if not self.run:
                raise RuntimeError("no run loaded")
            if self.active():
                self._pause.clear()
                self.run["paused"] = False
                self.run["pause_reason"] = None
                save_run(self.run, self.outputs)
            else:
                self.start(self.run)

    def active(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def retry_shot(self, shot_id: str) -> None:
        """Explicit retry of a failed/uncertain/blocked shot. The UI has warned that
        an uncertain one may already have been billed."""
        with self.lock:
            for s in self.run["shots"]:
                if s["id"] == shot_id and s["state"] in ("failed", "uncertain", "blocked"):
                    s["state"] = "pending"
            save_run(self.run, self.outputs)

    def _say(self, msg: str) -> None:
        self.log.append(f"{now()}  {msg}")
        del self.log[:-200]

    def _commit(self, run: dict, s: dict, state: str) -> None:
        with self.lock:
            s["state"] = state
            recount(run)
            save_run(run, self.outputs)

    def _pause_run(self, run: dict, reason: str) -> None:
        with self.lock:
            run["paused"] = True
            run["pause_reason"] = reason
            save_run(run, self.outputs)
        self._pause.set()
        self._say(f"PAUSED: {reason}")

    def _within_ceiling(self, run: dict) -> bool:
        ceiling = run.get("spend_ceiling_usd")
        if not ceiling:
            return True
        per = (run.get("estimate") or {}).get("per_image_usd") or 0.0
        return run["totals"]["spent_estimate_usd"] + per <= ceiling + 1e-9

    # -- the loop --------------------------------------------------------------
    def _loop(self) -> None:
        run = self.run
        d = run_dir(run["character"], run["run_id"], self.outputs)
        refs = [d / "refs" / r["name"] for r in run["references"]]
        for s in run["shots"]:
            if self._stop.is_set():
                return
            if self._only and s["id"] not in self._only:
                continue
            if s["state"] != "pending":
                continue
            while self._pause.is_set():
                if self._stop.is_set():
                    return
                self.sleep(0.2)
            if not self._within_ceiling(run):
                self._pause_run(run, "spending ceiling reached (estimate so far + reserve for one more image exceeds the ceiling)")
                return
            outcome = self._do_shot(run, s, refs, d)
            if outcome in PAUSE_KINDS:
                return
        self._say("queue finished")

    def _do_shot(self, run: dict, s: dict, refs: list[Path], d: Path) -> str:
        """Returns the shot's final outcome: saved | failed | uncertain | <pause kind>."""
        dest = d / s["filename"]
        if dest.exists():                      # never overwrite, never regenerate
            self._commit(run, s, "saved")
            return "saved"
        tries = 0
        while True:
            tries += 1
            attempt = {"started": now(), "sent": False, "request_id": None, "usage": None,
                       "cost_usd": None, "model_returned": None, "error": None}
            with self.lock:
                s["state"] = "running"
                s["attempts"].append(attempt)
                save_run(run, self.outputs)
            try:
                attempt["sent"] = True
                res = self.client.edit(s["prompt"], refs, run["settings"])
            except ApiError as e:
                attempt["finished"] = now()
                attempt["request_id"] = e.request_id
                attempt["error"] = {"kind": e.kind, "code": e.code, "status": e.status,
                                    "message": e.message, "request_id": e.request_id, "retry_after": e.retry_after}
                verdict, wait = self._after_error(run, s, e, tries)
                if verdict == "retry":
                    self._say(f"{s['id']} {e.kind} (try {tries}), waiting {wait}s")
                    self._commit(run, s, "pending")
                    self.sleep(wait)
                    continue
                return verdict
            # success: the file goes to its bound name first, then the record
            try:
                tmp = dest.with_suffix(dest.suffix + ".part")
                tmp.write_bytes(res.image_bytes)
                tmp.replace(dest)
            except OSError as e:
                attempt["finished"] = now()
                attempt["usage"] = res.usage
                attempt["error"] = {"kind": "local_io", "message": str(e)}
                self._commit(run, s, "uncertain")
                self._pause_run(run, f"could not save {dest.name}: {e}")
                return "local_io"
            attempt["finished"] = now()
            attempt["request_id"] = res.request_id
            attempt["model_returned"] = res.model_returned
            attempt["usage"] = res.usage
            pr = pricing_mod.load(self.pricing_path)
            attempt["cost_usd"] = pricing_mod.cost_of(pr, run["settings"]["model"], res.usage)
            # mock usage must never feed the real estimates
            if res.usage and getattr(self.client, "billable", True):
                pricing_mod.save(pricing_mod.record_observation(
                    pr, run["settings"]["model"], run["settings"]["size"], run["settings"]["quality"], res.usage),
                    self.pricing_path)
            self._commit(run, s, "saved")
            self._say(f"{s['id']} saved  cost~${attempt['cost_usd']}  req {res.request_id}")
            return "saved"

    def _after_error(self, run: dict, s: dict, e: ApiError, tries: int) -> tuple[str, float]:
        """Decide what an error means: ('retry', wait_s) or (final outcome, 0)."""
        if e.kind in PAUSE_KINDS:
            self._commit(run, s, "blocked")
            self._pause_run(run, f"{e.kind}: {e.code or ''} {e.message} (request {e.request_id})")
            return e.kind, 0
        if e.kind == "moderation":
            self._commit(run, s, "failed")
            self._say(f"{s['id']} moderation refusal - edit the prompt and retry by hand")
            return "failed", 0
        if e.kind == "rate_limit":
            if tries >= MAX_RATE_LIMIT_TRIES:
                self._commit(run, s, "blocked")
                self._pause_run(run, f"rate limited {tries} times in a row: {e.message}")
                return "quota", 0
            return "retry", (e.retry_after if e.retry_after else BACKOFF_S[min(tries - 1, len(BACKOFF_S) - 1)])
        # transient: a request that may have reached the server with no answer is UNCERTAIN
        if e.status is None and e.request_id is None:
            self._commit(run, s, "uncertain")
            self._say(f"{s['id']} UNCERTAIN: {e.message} - it may have been billed; retry only by hand")
            return "uncertain", 0
        if tries >= MAX_TRANSIENT_TRIES:
            self._commit(run, s, "failed")
            self._say(f"{s['id']} failed after {tries} transient errors")
            return "failed", 0
        return "retry", BACKOFF_S[min(tries - 1, len(BACKOFF_S) - 1)]
