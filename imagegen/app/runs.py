"""Run records: one folder per run, run.json committed atomically after every
state change, references snapshotted so a run can be reproduced exactly."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import OUTPUTS_DIR
from .refs import sha256

STATES = ("pending", "running", "saved", "failed", "blocked", "uncertain")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_dir(character: str, run_id: str, outputs: Path = OUTPUTS_DIR) -> Path:
    return outputs / character.lower() / run_id


# Quality goes in the FILENAME so two pilots of the same shot can sit in one
# folder and be compared side by side: cat_shot_001_low.png vs _med.png.
# Jeremy, 2026-10-04.
QUALITY_TAG = {"low": "low", "medium": "med", "high": "high", "xhigh": "xhigh", "max": "max"}


def quality_suffixed(filename: str, quality: str | None) -> str:
    """`cat_shot_001.png` + medium -> `cat_shot_001_med.png`. Unchanged with no quality."""
    if not quality:
        return filename
    stem, _, ext = filename.rpartition(".")
    if not stem:  # no extension to split on
        return f"{filename}_{QUALITY_TAG.get(quality, quality)}"
    return f"{stem}_{QUALITY_TAG.get(quality, quality)}.{ext}"


def new_run_id(character: str, label: str, outputs: Path = OUTPUTS_DIR) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = "".join(c if c.isalnum() else "-" for c in (label or "run")).strip("-").lower()[:24] or "run"
    rid = f"{stamp}_{slug}"
    i = 1
    while run_dir(character, rid, outputs).exists():
        i += 1
        rid = f"{stamp}_{slug}_{i}"
    return rid


def create_run(character: str, label: str, settings: dict, refs: list[Path], shots: list[dict],
               spend_ceiling_usd: float | None, estimate: dict, outputs: Path = OUTPUTS_DIR) -> dict:
    rid = new_run_id(character, label, outputs)
    d = run_dir(character, rid, outputs)
    (d / "refs").mkdir(parents=True)
    snap = []
    for p in refs:
        shutil.copy2(p, d / "refs" / p.name)
        snap.append({"name": p.name, "sha256": sha256(p), "source": str(p)})
    run = {
        "run_id": rid, "character": character.lower(), "label": label, "created": now(),
        "settings": dict(settings), "references": snap,
        "spend_ceiling_usd": spend_ceiling_usd, "estimate": estimate,
        # Bound here, before anything is sent: the filename a shot will be saved
        # under is decided once, at run creation, and never recomputed.
        "shots": [{"id": s["id"],
                   "filename": quality_suffixed(s["filename"], settings.get("quality")),
                   "prompt": s["prompt"],
                   "state": "pending", "attempts": []} for s in shots],
        "totals": {"spent_estimate_usd": 0.0, "unknown_cost_attempts": 0, "saved": 0},
        "paused": False, "pause_reason": None,
        "billing_actual_usd": None,
    }
    save_run(run, outputs)
    return run


def save_run(run: dict, outputs: Path = OUTPUTS_DIR) -> None:
    d = run_dir(run["character"], run["run_id"], outputs)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "run.json.tmp"
    tmp.write_text(json.dumps(run, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(d / "run.json")


def load_run(character: str, run_id: str, outputs: Path = OUTPUTS_DIR) -> dict:
    return json.loads((run_dir(character, run_id, outputs) / "run.json").read_text(encoding="utf-8"))


def list_runs(outputs: Path = OUTPUTS_DIR) -> list[dict]:
    out = []
    if not outputs.is_dir():
        return out
    for rj in outputs.glob("*/*/run.json"):
        try:
            r = json.loads(rj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        counts = {}
        for s in r["shots"]:
            counts[s["state"]] = counts.get(s["state"], 0) + 1
        out.append({"run_id": r["run_id"], "character": r["character"], "label": r["label"],
                    "created": r["created"], "settings": r["settings"], "counts": counts,
                    "totals": r["totals"], "paused": r.get("paused"), "pause_reason": r.get("pause_reason")})
    return sorted(out, key=lambda r: r["created"], reverse=True)


def reconcile(run: dict, outputs: Path = OUTPUTS_DIR) -> dict:
    """On load: a shot whose final file exists is `saved` no matter what the record
    says; a shot recorded `running` with no file was interrupted and is `uncertain`
    (it may have been billed). Never regenerates a saved shot."""
    d = run_dir(run["character"], run["run_id"], outputs)
    changed = False
    for s in run["shots"]:
        f = d / s["filename"]
        if f.is_file() and s["state"] != "saved":
            s["state"] = "saved"; changed = True
        elif s["state"] == "running":
            s["state"] = "uncertain"; changed = True
            if s["attempts"]:
                s["attempts"][-1].setdefault("error", {"kind": "uncertain", "message": "server stopped while the request was outstanding"})
                s["attempts"][-1]["finished"] = s["attempts"][-1].get("finished") or now()
    if changed:
        recount(run)
        save_run(run, outputs)
    return run


def recount(run: dict) -> None:
    t = run["totals"]
    t["saved"] = sum(1 for s in run["shots"] if s["state"] == "saved")
    spent, unknown = 0.0, 0
    for s in run["shots"]:
        for a in s["attempts"]:
            if a.get("cost_usd") is not None:
                spent += a["cost_usd"]
            elif a.get("sent"):
                unknown += 1
    t["spent_estimate_usd"] = round(spent, 4)
    t["unknown_cost_attempts"] = unknown
