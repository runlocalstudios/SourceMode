"""One status dict from the three sources, plus an hour of GPU history."""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path

from .comfy import sample_comfy
from .gpu import sample_gpu
from .training import sample_training


def summarise(gpu: dict | None, training: dict, comfy: dict) -> dict:
    """The one line the phone shows. Decided here so the page stays dumb.

    kind: training | rendering | busy | idle | unknown"""
    if training["active"]:
        prog = training.get("progress") or {}
        detail = None
        if training.get("epoch") and training.get("epochs"):
            detail = f"epoch {training['epoch']}/{training['epochs']}"
        frac = (prog["step"] / prog["total"]) if prog.get("total") else None
        return {"kind": "training", "title": f"Training {training.get('character') or 'LoRA'}",
                "detail": detail, "progress": frac, "eta_s": prog.get("eta_s"),
                "step": prog.get("step"), "total": prog.get("total")}
    if comfy.get("reachable") and comfy.get("running"):
        label = next((lab for lab in comfy.get("labels", []) if lab), None)
        return {"kind": "rendering", "title": "Rendering" + (f" {label}" if label else ""),
                "detail": f"{comfy['pending']} queued" if comfy.get("pending") else None,
                "progress": None, "eta_s": None}
    if gpu is None:
        return {"kind": "unknown", "title": "GPU unreadable",
                "detail": "nvidia-smi failed — state unknown", "progress": None, "eta_s": None}
    busy = (gpu.get("util_pct") or 0) > 20
    return {"kind": "busy" if busy else "idle",
            "title": "Busy (untracked process)" if busy else "Idle",
            "detail": None, "progress": None, "eta_s": None}


class Sampler:
    def __init__(self, cfg: dict, *, history_s: int = 3600):
        self.cfg = cfg
        self.sample_s = float(cfg["monitor"]["sample_s"])
        self.log_dir = Path(cfg["monitor"]["training_log_dir"])
        if not self.log_dir.is_absolute():
            from ..config import ENGINE_ROOT  # noqa: PLC0415

            self.log_dir = ENGINE_ROOT / self.log_dir
        self.history: deque[tuple[float, float | None, float | None]] = deque(
            maxlen=max(1, int(history_s / self.sample_s)))
        self.latest: dict | None = None
        self.started = time.time()
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def sample_once(self) -> dict:
        gpu = sample_gpu()
        training = sample_training(self.log_dir)
        comfy = sample_comfy(self.cfg["comfyui"]["host"], self.cfg["comfyui"]["port"])
        now = time.time()
        status = {
            "sampled_at": now,
            "uptime_s": now - self.started,
            "gpu": gpu,
            "training": training,
            "comfyui": comfy,
            "job": summarise(gpu, training, comfy),
        }
        with self._lock:
            self.latest = status
            self.history.append((now, gpu and gpu.get("util_pct"), gpu and gpu.get("mem_used_mb")))
        return status

    def status(self) -> dict:
        with self._lock:
            return self.latest or {"sampled_at": None, "gpu": None, "training": None,
                                   "comfyui": None, "job": {"kind": "unknown", "title": "Starting"}}

    def history_points(self, max_points: int = 360) -> list[dict]:
        with self._lock:
            pts = list(self.history)
        stride = max(1, len(pts) // max_points)
        return [{"t": t, "util": u, "mem": m} for t, u, m in pts[::stride]]

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.sample_once()
            except Exception:  # noqa: BLE001 — a bad sample must not kill the loop
                pass
            self._stop.wait(self.sample_s)

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self.run_forever, name="monitor-sampler", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()
