"""What ComfyUI is doing right now, from GET /queue.

queue_running / queue_pending entries are [number, prompt_id, prompt, extra, outputs];
the prompt is the node graph, so the SaveImage filename_prefix tells us the job.
"""

from __future__ import annotations

SAVE_NODES = ("SaveImage", "VHS_VideoCombine", "SaveAnimatedWEBP", "SaveVideo")


def job_label(prompt: dict | None) -> str | None:
    for node in (prompt or {}).values():
        if isinstance(node, dict) and node.get("class_type") in SAVE_NODES:
            prefix = node.get("inputs", {}).get("filename_prefix")
            if prefix:
                return str(prefix)
    return None


def parse_queue(data: dict) -> dict:
    running = data.get("queue_running") or []
    pending = data.get("queue_pending") or []
    labels = []
    for item in running:
        prompt = item[2] if isinstance(item, (list, tuple)) and len(item) > 2 else None
        labels.append(job_label(prompt))
    return {"running": len(running), "pending": len(pending), "labels": labels}


def sample_comfy(host: str, port: int, session=None, timeout: float = 2.0) -> dict:
    """{reachable, running, pending, labels}. Unreachable is a state, not an error."""
    if session is None:
        import requests  # noqa: PLC0415

        session = requests
    try:
        resp = session.get(f"http://{host}:{port}/queue", timeout=timeout)
        if resp.status_code != 200:
            return {"reachable": False, "running": 0, "pending": 0, "labels": []}
        return {"reachable": True, **parse_queue(resp.json())}
    except Exception:  # noqa: BLE001
        return {"reachable": False, "running": 0, "pending": 0, "labels": []}
