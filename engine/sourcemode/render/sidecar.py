"""Every render writes a sidecar YAML: full provenance for the artifact."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml


def write_sidecar(
    artifact_path: Path,
    *,
    source_version: str,
    prompt_hash: str,
    seed: int,
    models: dict,
    loras: list[dict],
    render_pass: str,
    settings: dict,
) -> Path:
    sidecar = Path(str(artifact_path) + ".yaml")
    payload = {
        "artifact": Path(artifact_path).name,
        "source_version": source_version,
        "prompt_hash": prompt_hash,
        "seed": seed,
        "models": models,
        "loras": loras,
        "pass": render_pass,
        "settings": settings,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return sidecar


def read_sidecar(artifact_path: Path) -> dict:
    return yaml.safe_load(Path(str(artifact_path) + ".yaml").read_text(encoding="utf-8"))
