"""GPU sample via nvidia-smi. One subprocess per sample; ~30 ms, fine at 1 Hz."""

from __future__ import annotations

import subprocess

QUERY = "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,power.limit"


def parse_nvidia_smi(text: str) -> dict | None:
    """Parse one `--format=csv,noheader,nounits` line. None if it doesn't look like one."""
    line = text.strip().splitlines()[0] if text.strip() else ""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != 7:
        return None

    def num(s: str) -> float | None:
        try:
            return float(s)
        except ValueError:  # "[N/A]" on some cards/drivers
            return None

    return {
        "name": parts[0],
        "util_pct": num(parts[1]),
        "mem_used_mb": num(parts[2]),
        "mem_total_mb": num(parts[3]),
        "temp_c": num(parts[4]),
        "power_w": num(parts[5]),
        "power_limit_w": num(parts[6]),
    }


def sample_gpu(runner=subprocess.run) -> dict | None:
    """Current GPU state, or None when nvidia-smi is missing or fails.

    None means *unknown*, and the readout must say so — never render an
    unreadable GPU as idle."""
    try:
        proc = runner(
            ["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return parse_nvidia_smi(proc.stdout)
