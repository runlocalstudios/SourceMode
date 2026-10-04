"""The 80-shot manifest: read-only original, per-character working copy.

Prompts are preserved byte-for-byte on import. Only an explicit edit through the
app changes a working-copy prompt, and the original text is kept beside it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import MANIFESTS_DIR, MANIFEST_PATH


def load_original(path: Path = MANIFEST_PATH) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def working_path(character: str) -> Path:
    return MANIFESTS_DIR / f"{character.lower()}.json"


def import_manifest(character: str, source: Path = MANIFEST_PATH, force: bool = False) -> dict:
    """Create the working copy for a character. Existing copies are kept unless forced."""
    wp = working_path(character)
    if wp.is_file() and not force:
        return json.loads(wp.read_text(encoding="utf-8"))
    src = load_original(source)
    shots = []
    for s in src["shots"]:
        shots.append({
            "id": s["id"],
            "filename": s["filename"].replace("<character>", character.lower()),
            "hair_needs_length": s.get("hair_needs_length"),
            "prompt": s["prompt"],
            "original_prompt": s["prompt"],
            "edited": False,
        })
    doc = {
        "character": character.lower(),
        "source": str(source),
        "imported": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "approval_stop_after": src.get("approval_stop_after", 4),
        "shots": shots,
    }
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write(wp, doc)
    return doc


def load_working(character: str) -> dict | None:
    wp = working_path(character)
    return json.loads(wp.read_text(encoding="utf-8")) if wp.is_file() else None


def edit_prompt(character: str, shot_id: str, prompt: str) -> dict:
    doc = load_working(character)
    if doc is None:
        raise FileNotFoundError("import the manifest first")
    for s in doc["shots"]:
        if s["id"] == shot_id:
            s["prompt"] = prompt
            s["edited"] = prompt != s["original_prompt"]
            break
    else:
        raise KeyError(shot_id)
    _atomic_write(working_path(character), doc)
    return doc


def _atomic_write(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
