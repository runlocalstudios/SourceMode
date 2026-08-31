"""Execute a training plan: write config files + manifest, run the sequence.

The CLI's --run executes cache latents -> cache TE -> train IN PROCESS and
blocks until done; callers who need detachment launch the whole CLI detached
(PowerShell Start-Process redirecting to a log) and poll the log. The manifest
(characters/<id>/training/<output_name>_manifest.json, committed) records the
dataset hash + exact commands so any render traces back to its training run.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from ..source import CharacterSource
from .dataset import dataset_hash


def write_plan_files(plan: dict) -> None:
    toml_path = Path(plan["dataset_toml_path"])
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    toml_path.write_text(plan["dataset_toml"], encoding="utf-8")
    Path(plan["output_dir"]).mkdir(parents=True, exist_ok=True)
    if "sample_prompts_path" in plan:
        Path(plan["sample_prompts_path"]).write_text(plan["sample_prompts"], encoding="utf-8")


def write_manifest(
    characters_root: Path,
    source: CharacterSource,
    plan: dict,
    dataset_dir: Path,
) -> Path:
    manifest = {
        "kind": plan["kind"],
        "character_id": source.character_id,
        "source_version": source.version,
        "trigger_token": source.trigger_token,
        "dataset_dir": str(dataset_dir),
        "dataset_hash": dataset_hash(dataset_dir, source.trigger_token),
        "n_images": plan["n_images"],
        "num_repeats": plan["num_repeats"],
        "steps_per_epoch": plan["steps_per_epoch"],
        "max_train_epochs": plan["max_train_epochs"],
        "total_steps": plan["total_steps"],
        "output_dir": str(plan["output_dir"]),
        "output_name": plan["output_name"],
        "commands": [" ".join(c) for c in plan["commands"]],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out = characters_root / source.character_id / "training" / f"{plan['output_name']}_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out


def execute_plan(plan: dict, log=print) -> None:
    """Run the plan's commands sequentially; raises on the first failure."""
    import sys  # noqa: PLC0415

    for cmd in plan["commands"]:
        log(f"[train] running: {cmd[1] if len(cmd) > 1 else cmd[0]}")
        sys.stdout.flush()
        started = time.monotonic()
        subprocess.run(cmd, check=True)
        log(f"[train] done in {time.monotonic() - started:.0f}s")
        sys.stdout.flush()
