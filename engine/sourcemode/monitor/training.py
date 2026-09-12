"""Progress of a musubi-tuner LoRA run, from its log and the process table.

musubi writes tqdm lines like
    steps:  13%|█▎        | 216/1640 [31:07<3:25:09,  8.64s/it, avr_loss=0.051]
and, at start-up, the dataset path and epoch count. Everything here is a pure
function of that text so it can be tested against captured logs.
"""

from __future__ import annotations

import re
from pathlib import Path

STEPS_RE = re.compile(
    r"steps:\s+(?P<pct>\d+)%\|[^|]*\|\s*(?P<step>\d+)/(?P<total>\d+)\s*"
    r"\[(?P<elapsed>[\d:]+)<(?P<remaining>[\d:?]+),\s*(?P<rate>[\d.?]+)(?P<unit>s/it|it/s)"
    r"(?:,\s*avr_loss=(?P<loss>[\d.]+))?"
)
# \s+ rather than literal spaces: a log captured through a PowerShell redirect
# is hard-wrapped at the console width, so "from " and the path, or "epoch数:"
# and its number, can land on different lines.
DATASET_RE = re.compile(r"Load\s+dataset\s+config\s+from\s+(?P<path>\S+)")
# The Japanese half of musubi's bilingual labels ("epoch数", "1epochのバッチ数")
# arrives as "??" when the launching console's codepage can't encode it, so
# match it as any run of non-space characters before the colon.
EPOCHS_RE = re.compile(r"num\s+epochs\s+/\s+\S+:\s*(?P<n>\d+)")
BATCHES_RE = re.compile(r"num\s+batches\s+per\s+epoch\s+/\s+\S+:\s*(?P<n>\d+)")
TRAINER_MARKERS = ("qwen_image_train_network", "wan_train_network")


def _hms_to_s(s: str) -> int | None:
    if "?" in s:
        return None
    total = 0
    for p in s.split(":"):
        total = total * 60 + int(p)
    return total


def parse_progress(text: str) -> dict | None:
    """The LAST tqdm progress line in the log, as numbers. None if there is none yet."""
    last = None
    for m in STEPS_RE.finditer(text.replace("\r", "\n")):
        last = m
    if last is None:
        return None
    try:
        rate = float(last["rate"])
    except ValueError:  # tqdm's very first line: "[00:00<?, ?it/s]"
        rate = None
    if rate is None:
        s_per_it = None
    else:
        s_per_it = rate if last["unit"] == "s/it" else (1.0 / rate if rate else None)
    return {
        "step": int(last["step"]),
        "total": int(last["total"]),
        "elapsed_s": _hms_to_s(last["elapsed"]),
        "eta_s": _hms_to_s(last["remaining"]),
        "s_per_it": s_per_it,
        "loss": float(last["loss"]) if last["loss"] else None,
    }


def parse_run_info(text: str) -> dict:
    """Character, epoch count and batches-per-epoch from the log header."""
    info: dict = {"character": None, "epochs": None, "batches_per_epoch": None}
    m = DATASET_RE.search(text)
    if m:
        # .../lora-datasets/<character>/dataset_*.toml
        parts = Path(m["path"].replace("\\", "/")).parts
        if "lora-datasets" in parts:
            i = parts.index("lora-datasets")
            if i + 1 < len(parts):
                info["character"] = parts[i + 1]
    m = EPOCHS_RE.search(text)
    if m:
        info["epochs"] = int(m["n"])
    m = BATCHES_RE.search(text)
    if m:
        info["batches_per_epoch"] = int(m["n"])
    return info


def epoch_of(step: int, batches_per_epoch: int | None) -> int | None:
    if not batches_per_epoch:
        return None
    return max(1, -(-step // batches_per_epoch))  # ceil


def find_latest_log(log_dir: Path) -> Path | None:
    logs = [p for p in log_dir.glob("*.log") if p.is_file()]
    if not logs:
        return None
    return max(logs, key=lambda p: p.stat().st_mtime)


def trainer_running(process_iter=None) -> bool | None:
    """Is a musubi trainer process alive? None when the process table can't be read."""
    if process_iter is None:
        try:
            import psutil  # noqa: PLC0415
        except ImportError:
            return None
        process_iter = lambda: psutil.process_iter(["cmdline"])  # noqa: E731
    try:
        for proc in process_iter():
            info = proc.info if hasattr(proc, "info") else proc
            cmd = " ".join(info.get("cmdline") or [])
            if any(mark in cmd for mark in TRAINER_MARKERS):
                return True
        return False
    except Exception:  # noqa: BLE001 — psutil raises assorted OS errors on Windows
        return None


def decode_log(head: bytes, tail: bytes) -> str:
    """Decode by BOM. A log written through PowerShell 5.1's `*>` redirect is
    UTF-16LE; decoding that as UTF-8 yields NUL-interleaved text that matches
    nothing, and the readout silently shows a run with no progress (gabi_v2,
    2026-09-10). Odd-length UTF-16 slices are trimmed to a code-unit boundary."""
    if head.startswith(b"\xff\xfe"):
        enc, head = "utf-16-le", head[2:]
        if len(head) % 2:
            head = head[:-1]
        if len(tail) % 2:
            tail = tail[1:]
        sep = "\n".encode(enc)
    elif head.startswith(b"\xfe\xff"):
        enc, head = "utf-16-be", head[2:]
        if len(head) % 2:
            head = head[:-1]
        if len(tail) % 2:
            tail = tail[1:]
        sep = "\n".encode(enc)
    else:
        enc, sep = "utf-8", b"\n"
        if head.startswith(b"\xef\xbb\xbf"):
            head = head[3:]
    return (head + sep + tail).decode(enc, errors="replace")


def read_tail(path: Path, max_bytes: int = 200_000, head_bytes: int = 150_000) -> str:
    """Head plus tail of a log: the header is near the front, tqdm lines at the end.

    The head must be generous: musubi dumps the whole dataset config before the
    epoch count, and a two-dataset config in UTF-16 put "num epochs" at byte
    ~82 000 (gabi_v2) — past a 20 KB head and short of a 200 KB tail."""
    size = path.stat().st_size
    with path.open("rb") as f:
        head = f.read(min(size, head_bytes))
        f.seek(size - max_bytes if size > max_bytes else 0)
        tail = f.read()
    return decode_log(head, tail)


def sample_training(log_dir: Path, *, running: bool | None = None) -> dict:
    """Training state: active?, which character, progress, ETA.

    `running` is the process-table answer (None = unknown). A finished log with
    no live process reports active=False but keeps the last numbers so the
    readout can say what finished and when."""
    if running is None:
        running = trainer_running()
    log = find_latest_log(log_dir) if log_dir.exists() else None
    out: dict = {"active": bool(running), "process": running, "log": str(log) if log else None,
                 "character": None, "progress": None, "epoch": None, "epochs": None,
                 "log_mtime": None}
    if log is None:
        return out
    text = read_tail(log)
    # A launcher that redirects stdout and stderr separately (PowerShell
    # Start-Process) puts musubi's header in <name>.log and tqdm's progress —
    # which goes to stderr — in <name>.log.err. Read both.
    err = log.with_name(log.name + ".err")
    if err.exists():
        text = text + "\n" + read_tail(err)
        out["log_mtime"] = max(log.stat().st_mtime, err.stat().st_mtime)
    info = parse_run_info(text)
    prog = parse_progress(text)
    out["character"] = info["character"]
    out["epochs"] = info["epochs"]
    out["log_mtime"] = log.stat().st_mtime
    if prog:
        out["progress"] = prog
        out["epoch"] = epoch_of(prog["step"], info["batches_per_epoch"])
        if running is None:
            # can't see processes: infer from whether the log is still short of done
            out["active"] = prog["step"] < prog["total"]
    return out
