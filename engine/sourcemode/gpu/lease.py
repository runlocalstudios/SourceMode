"""One runner, enforced by a lease whose staleness is decided by PID LIVENESS.

Every concurrency failure on this project came from a guard that expired on a
clock: the 4-hour "card busy - proceeding" fall-through, and a completion marker
that was already present so a job fired instantly. A lease held by a process that
is still alive is never stale, however old it is; a lease held by a dead process
is stale immediately. No duration appears anywhere in this file.

    outputs/gpu-queue/runner.lease   {pid, host, started_at}
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .queue import now


def lease_path(outputs_root: Path) -> Path:
    from .queue import queue_dir  # noqa: PLC0415

    return queue_dir(outputs_root) / "runner.lease"


# Error codes from OpenProcess: a process that exists but is not ours to query
# must read as ALIVE, and only "no such process" as dead.
_ERROR_ACCESS_DENIED = 5
_ERROR_INVALID_PARAMETER = 87
_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def pid_alive(pid: int) -> bool:
    """True if that pid is a live process. Asks; never touches the process.

    `os.kill(pid, 0)` is NOT a liveness probe on Windows. CPython maps every
    non-CTRL signal to TerminateProcess, so signal 0 KILLS the process it was
    meant to ask about: on 2026-10-04 this function, written that way, terminated
    the very runner whose lease it was checking. OpenProcess +
    GetExitCodeProcess only reads.
    """
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)  # POSIX: signal 0 really is just a permission probe
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        err = ctypes.get_last_error()
        # Access denied means it is running under another account - alive.
        return err == _ERROR_ACCESS_DENIED
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True  # it exists; we just could not read its exit code
        return code.value == _STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def holder(path: Path) -> dict | None:
    """The lease, only if its owner is still alive. A dead owner's lease is
    reported as absent rather than deleted here - acquire() does the cleanup."""
    rec = read(path)
    if rec and pid_alive(int(rec.get("pid", 0))):
        return rec
    return None


def acquire(path: Path, pid: int | None = None) -> dict:
    """Take the lease, or raise if a live runner already holds it."""
    held = holder(path)
    if held:
        raise RuntimeError(f"another runner already holds the lease (PID {held['pid']}, since {held['started_at']})")
    rec = {"pid": pid or os.getpid(), "host": os.environ.get("COMPUTERNAME", ""), "started_at": now()}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    from .queue import replace_retrying  # noqa: PLC0415 - the monitor reads this too
    replace_retrying(tmp, path)
    return rec


def release(path: Path, pid: int | None = None) -> bool:
    """Drop the lease if we hold it. Never removes another live runner's lease."""
    rec = read(path)
    if rec and rec.get("pid") == (pid or os.getpid()):
        path.unlink(missing_ok=True)
        return True
    return False
