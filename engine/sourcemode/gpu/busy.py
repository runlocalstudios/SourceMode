"""Is the card already working, and whose work is it?

Ported from the wait loop in `engine/scripts/eval/train_zara.ps1` rather than
re-derived: that list of patterns is what the pipeline has learned to watch for.
The crucial change is in the CALLER - there is no timeout here and none above.
On 2026-10-03 that script found a live training, waited, and then proceeded
anyway at the 4-hour mark; a guard that expires is not a guard.

`wan_train_network` comes from monitor/training.py's TRAINER_MARKERS, which this
deliberately agrees with so the monitor and the runner never disagree about
whether something is training.
"""

from __future__ import annotations

import subprocess

# A substring of the command line. Matching the WORK (a trainer, an eval, a
# render) and never a wrapper means this cannot match the runner's own process
# or the script that asked the question - the self-kill class of bug.
PATTERNS = (
    "qwen_image_train_network",
    "wan_train_network",
    "qwen_image_cache_latents",
    "qwen_image_cache_text_encoder_outputs",
    "dense_epoch_eval.py",
    "caption_from_vl",
    "hair_recheck",
    "loragen_local",
)
# Asset work spells itself out across two words, so it needs both present.
PAIR_PATTERNS = (("assets", "render"), ("assets", "cutout"))


def matches(cmdline: str) -> str | None:
    """The pattern this command line is busy with, or None."""
    low = (cmdline or "").lower()
    for p in PATTERNS:
        if p.lower() in low:
            return p
    for a, b in PAIR_PATTERNS:
        if a in low and b in low:
            return f"{a}+{b}"
    return None


def busy(processes: list[tuple[int, str]], ignore_pids: set[int] | None = None) -> list[dict]:
    """GPU work currently running, as [{pid, pattern, cmd}].

    Takes the process list rather than reading it, so the decision is a pure
    function and is unit-tested without a GPU or a live training.
    """
    skip = ignore_pids or set()
    out = []
    for pid, cmd in processes:
        if pid in skip:
            continue
        hit = matches(cmd)
        if hit:
            out.append({"pid": pid, "pattern": hit, "cmd": (cmd or "")[:200]})
    return out


def process_list() -> list[tuple[int, str]]:
    """Every process as (pid, command line), via CIM. Windows-only by design.

    PowerShell is the only way to read command lines here, but nothing is parsed
    out of its text formatting: it emits JSON and this reads that.
    """
    ps = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress -Depth 3"
    )
    try:
        raw = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=60, check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    import json  # noqa: PLC0415

    try:
        rows = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(rows, dict):
        rows = [rows]
    return [(int(r["ProcessId"]), r.get("CommandLine") or "") for r in rows if r.get("ProcessId")]


def gpu_busy(ignore_pids: set[int] | None = None) -> list[dict]:
    return busy(process_list(), ignore_pids)
