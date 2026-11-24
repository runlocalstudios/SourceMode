"""Dev servers nobody is using any more, shown on the Queue page.

2026-11-24: three `vercel dev` servers for chillafterdark had been running since
2026-09-28, about 1.8 cores each, started by a session that retried on a new
port three times and exited. Nothing showed them. Jeremy: "add number 1 to the
source mode review page just so that I can see it and have it be top of mind."

A dev server is a stray when either is true:

- **the shell that started it is gone** - walking up its parents ends at a
  process that is not the desktop or a Windows service, so no window owns it;
- **it has run for more than a day** - whatever owns it, nobody is watching it.

One row per tree, at the top-most process that looks like a dev server, with the
CPU time of everything under it. `find_strays` is pure over a process table, so
it is tested without a machine.

    GET  /queue/strays            the rows
    POST /queue/stray/{pid}/kill  kill that tree - only a pid in the rows above
"""

from __future__ import annotations

import re
import time

DAY_S = 86400.0

# `vercel dev`, `vite`, `next dev`, `npm run dev` and friends, as they appear in
# a Windows command line: `"...\vc.js" dev`, `cmd /C "vite --port 54929"`.
DEV = re.compile(
    r"\b(vercel|vc\.js|next|astro)\"?\s+dev\b"
    r"|\bvite(\.js)?\"?(\s|$)"
    r"|\b(npm|pnpm|yarn|bun)(\.cmd)?\"?\s+(run\s+)?dev\b"
    r"|\bwebpack(\.js)?\"?\s+serve\b",
    re.I,
)

# Where a chain of parents ends when a window or a service still owns it.
OWNED_ROOTS = {"explorer.exe", "wininit.exe", "services.exe", "winlogon.exe",
               "smss.exe", "system", "system idle process"}


def find_strays(procs: list[dict], now: float, cwd_of=None) -> list[dict]:
    """`procs`: {pid, ppid, name, cmdline, started, cpu_s} for every process."""
    by_pid = {p["pid"]: p for p in procs}

    def parent(p):
        up = by_pid.get(p["ppid"])
        # a parent younger than its child is a reused pid: the real one is gone
        if up is None or up is p or up["started"] > p["started"] + 1:
            return None
        return up

    def chain(p):
        out, seen = [], {p["pid"]}
        while (p := parent(p)) is not None and p["pid"] not in seen:
            seen.add(p["pid"])
            out.append(p)
        return out

    kids: dict[int, list[dict]] = {}
    for p in procs:
        if parent(p) is not None:
            kids.setdefault(p["ppid"], []).append(p)

    def tree(p):
        out, todo = [], [p]
        while todo:
            x = todo.pop()
            out.append(x)
            todo.extend(kids.get(x["pid"], []))
        return out

    rows = []
    for p in procs:
        if not DEV.search(p["cmdline"] or ""):
            continue
        ups = chain(p)
        if any(DEV.search(u["cmdline"] or "") for u in ups):
            continue  # a row is the top of its tree
        root = ups[-1] if ups else p
        orphaned = (root["name"] or "").lower() not in OWNED_ROOTS
        age_s = now - p["started"]
        if not (orphaned or age_s > DAY_S):
            continue
        cwd = None
        if cwd_of is not None:
            try:
                cwd = cwd_of(p["pid"])
            except Exception:  # noqa: BLE001 - psutil raises assorted OS errors
                cwd = None
        rows.append({
            "pid": p["pid"], "cmd": _short(p["cmdline"]), "cwd": cwd,
            "age": _age(age_s), "age_s": round(age_s),
            "cpu_h": round(sum(x["cpu_s"] for x in tree(p)) / 3600, 1),
            "orphaned": orphaned,
        })
    return sorted(rows, key=lambda r: -r["age_s"])


def _short(cmdline: str) -> str:
    """`vercel dev --listen 5210 --yes`, not the four quoted paths before it."""
    m = DEV.search(cmdline)
    tail = cmdline[m.start():].replace('"', "").strip()
    return re.sub(r"\s+", " ", tail)[:80]


def _age(s: float) -> str:
    if s >= 2 * DAY_S:
        return f"{int(s // DAY_S)} days"
    if s >= 3600:
        return f"{int(s // 3600)} hours"
    return f"{max(1, int(s // 60))} minutes"


# What a dev server, or the shell that launched one, runs as.
HOSTS = {"node.exe", "bun.exe", "deno.exe", "cmd.exe", "bash.exe", "sh.exe",
         "powershell.exe", "pwsh.exe"}


def snapshot() -> list[dict]:
    """The part of the live process table a dev server can be in: every HOSTS
    process, what is above it and what is under it. [] without psutil.

    Asking psutil about all 455 processes took 27 s on 2026-11-24: `ppid()`
    takes a whole system snapshot per call, and a process this user cannot open
    falls back to a slow path. So the parents come from ONE snapshot, and the
    per-process reads go only to the chains that hold a HOSTS process.
    """
    try:
        import psutil  # noqa: PLC0415
    except ImportError:
        return []
    ppid = psutil._ppid_map()  # noqa: SLF001 - the one-call form of ppid()
    names = {p.pid: p.info["name"] or "" for p in psutil.process_iter(["name"])}
    hosts = {pid for pid, n in names.items() if n.lower() in HOSTS}
    keep: set[int] = set()
    for pid in names:
        chain, x = [], pid
        while x in names and x not in chain:
            chain.append(x)
            x = ppid.get(x)
        if hosts.intersection(chain):
            keep.update(chain)
    out = []
    for pid in keep:
        row = {"pid": pid, "ppid": ppid.get(pid) or 0, "name": names[pid],
               "cmdline": "", "started": 0.0, "cpu_s": 0.0}
        try:
            proc = psutil.Process(pid)
            row["started"] = proc.create_time()
            t = proc.cpu_times()
            row["cpu_s"] = t.user + t.system
            if pid in hosts:
                row["cmdline"] = " ".join(proc.cmdline())
        except psutil.Error:
            pass  # gone, or not ours to read: the row keeps what was read
        out.append(row)
    return out


def _cwd(pid: int) -> str:
    import psutil  # noqa: PLC0415

    return psutil.Process(pid).cwd()


_cache: tuple[float, list[dict]] = (0.0, [])


def strays(fresh: bool = False) -> list[dict]:
    """Reading every command line on Windows is slow, so one read a minute."""
    global _cache
    if fresh or time.monotonic() - _cache[0] > 60:
        _cache = (time.monotonic(), find_strays(snapshot(), time.time(), _cwd))
    return _cache[1]


def kill(pid: int) -> list[dict]:
    """Kill one stray's whole tree. KeyError unless `pid` is a stray right now -
    this route never kills a pid it was merely handed."""
    import psutil  # noqa: PLC0415

    if pid not in {r["pid"] for r in strays(fresh=True)}:
        raise KeyError(pid)
    top = psutil.Process(pid)
    for p in [*top.children(recursive=True), top]:
        try:
            p.kill()
        except psutil.Error:
            pass  # already gone
    time.sleep(0.5)
    return strays(fresh=True)
