"""The one ordered list of GPU jobs, and the only thing that decides run order.

Before this existed, order lived in whichever PowerShell script a session happened
to write: on 2026-10-03 the order Jeremy set that day survived only as a COMMENT
inside `engine/scripts/eval/train_zara.ps1`, in a temp folder. The file order here
IS the run order, nothing recomputes it, and `gpu list` is the answer to "what is
running and what is next".

    outputs/gpu-queue/queue.json   {version, next_id, paused, pause_reason, jobs[]}

A job's `status` is only ever queued / running / done / failed / cancelled.
"Blocked on approval" is NOT a status: it is computed at read time from the
approval record, so re-approving a set clears it with no queue edit.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
ACTIVE = ("queued", "running")


def queue_dir(outputs_root: Path) -> Path:
    return outputs_root / "gpu-queue"


def queue_path(outputs_root: Path) -> Path:
    return queue_dir(outputs_root) / "queue.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty() -> dict:
    return {"version": VERSION, "next_id": 1, "paused": False, "pause_reason": "", "jobs": []}


def load(path: Path) -> dict:
    """The queue, or a fresh empty one. Never raises on a missing file."""
    if not path.is_file():
        return empty()
    doc = json.loads(path.read_text(encoding="utf-8"))
    for key, value in empty().items():
        doc.setdefault(key, value)
    return doc


def save(path: Path, doc: dict) -> None:
    """Atomic: a reader never sees half a queue, and a crash never truncates it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def add(doc: dict, *, kind: str, label: str, cmd: list[str], cwd: str,
        requires_approval: str | None = None, note: str = "") -> dict:
    """Append a job at the END of the queue. Appending is the only way work is
    requested: a session adds a job, it does not write its own launcher."""
    job = {
        "id": f"j{doc['next_id']:03d}",
        "kind": kind,
        "label": label,
        "cmd": list(cmd),
        "cwd": cwd,
        "requires_approval": requires_approval,
        "note": note,
        "status": "queued",
        "hold": False,
        "added_at": now(),
        "started_at": None,
        "ended_at": None,
        "exit_code": None,
        "pid": None,
        "log": None,
    }
    doc["next_id"] += 1
    doc["jobs"].append(job)
    return job


def find(doc: dict, job_id: str) -> dict | None:
    for j in doc["jobs"]:
        if j["id"] == job_id:
            return j
    return None


def duplicate_of(doc: dict, kind: str, label: str) -> dict | None:
    """An already-queued or running job for the same work. Adding the same job
    twice is how a retry turns into a double run, so callers check this."""
    for j in doc["jobs"]:
        if j["kind"] == kind and j["label"] == label and j["status"] in ACTIVE:
            return j
    return None


def move(doc: dict, job_id: str, to_index: int) -> list[dict]:
    """Reorder. `to_index` is 0-based over the whole list and is clamped."""
    jobs = doc["jobs"]
    cur = next((i for i, j in enumerate(jobs) if j["id"] == job_id), None)
    if cur is None:
        raise KeyError(job_id)
    job = jobs.pop(cur)
    jobs.insert(max(0, min(to_index, len(jobs))), job)
    return jobs


def reorder(doc: dict, ids: list[str]) -> list[dict]:
    """Set the order to exactly `ids`. One call, so a drag never lands the queue in
    an intermediate order - and any job the caller did not mention keeps its
    relative place at the end rather than being dropped."""
    by_id = {j["id"]: j for j in doc["jobs"]}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise KeyError(", ".join(unknown))
    ordered = [by_id[i] for i in ids]
    ordered += [j for j in doc["jobs"] if j["id"] not in set(ids)]
    doc["jobs"] = ordered
    return ordered


def set_hold(doc: dict, job_id: str, hold: bool) -> dict:
    """Held jobs keep their place in the order but are never picked. This is the
    ONLY way to let the runner move past a job: it is an explicit act, not a
    timeout, and not something the runner decides for itself."""
    job = find(doc, job_id)
    if job is None:
        raise KeyError(job_id)
    job["hold"] = hold
    return job


def cancel(doc: dict, job_id: str) -> dict:
    job = find(doc, job_id)
    if job is None:
        raise KeyError(job_id)
    if job["status"] == "running":
        raise ValueError(f"{job_id} is running - stop it deliberately, not by cancelling")
    job["status"] = "cancelled"
    job["ended_at"] = now()
    return job


def restore(doc: dict, job_id: str) -> dict:
    """Un-cancel a job. It comes back HELD, never runnable straight away.

    Cancelling is soft - the job stays in the file - so a mis-click is repairable,
    which is the whole point: Jeremy clicked Remove meaning Hold on 2026-10-04 and
    it took a hand-edit of queue.json to put it back. Coming back held means a
    restore can never itself start nine hours of GPU work.
    """
    job = find(doc, job_id)
    if job is None:
        raise KeyError(job_id)
    if job["status"] != "cancelled":
        raise ValueError(f"{job_id} is {job['status']}, not cancelled")
    job.update(status="queued", hold=True, ended_at=None, exit_code=None, pid=None)
    return job


def head(doc: dict) -> dict | None:
    """The first job that is queued and not held - the next one to run, and the
    one the runner WAITS on. It never looks past it: order is the order Jeremy set."""
    for j in doc["jobs"]:
        if j["status"] == "queued" and not j["hold"]:
            return j
    return None


def running(doc: dict) -> list[dict]:
    return [j for j in doc["jobs"] if j["status"] == "running"]


def mark_running(doc: dict, job_id: str, pid: int, log: str) -> dict:
    job = find(doc, job_id)
    job.update(status="running", started_at=now(), pid=pid, log=log)
    return job


def mark_finished(doc: dict, job_id: str, exit_code: int) -> dict:
    job = find(doc, job_id)
    job.update(status="done" if exit_code == 0 else "failed",
               ended_at=now(), exit_code=exit_code, pid=None)
    return job


def pause(doc: dict, reason: str) -> dict:
    doc["paused"] = True
    doc["pause_reason"] = reason
    return doc


def resume(doc: dict) -> dict:
    doc["paused"] = False
    doc["pause_reason"] = ""
    return doc
