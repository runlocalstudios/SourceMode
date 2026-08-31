"""Load/save CharacterSource JSON with approved-version protection.

Layout: characters/<id>/source.json is current; superseded versions are archived
to characters/<id>/versions/<version>.json on bump. An approved version is never
overwritten in place — identity edits require a bump. Operational fields
(embedding path, threshold, lora paths) may be updated on an approved version
via update_operational, since they don't change the approved identity itself.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .model import CharacterSource

OPERATIONAL_FIELDS = {"identity_embedding_path", "identity_threshold", "lora_paths"}


class ApprovedVersionError(RuntimeError):
    pass


def character_dir(characters_root: Path, character_id: str) -> Path:
    return characters_root / character_id


def source_path(characters_root: Path, character_id: str) -> Path:
    return character_dir(characters_root, character_id) / "source.json"


def load_source(characters_root: Path, character_id: str) -> CharacterSource:
    path = source_path(characters_root, character_id)
    if not path.exists():
        raise FileNotFoundError(f"no source.json for character {character_id!r} at {path}")
    return CharacterSource.model_validate_json(path.read_text(encoding="utf-8"))


def save_source(characters_root: Path, source: CharacterSource, *, force: bool = False) -> Path:
    """Write source.json. Refuses to modify an approved version (bump instead)."""
    path = source_path(characters_root, source.character_id)
    if path.exists() and not force:
        existing = CharacterSource.model_validate_json(path.read_text(encoding="utf-8"))
        if existing.approved and existing.version == source.version:
            changed = {
                k for k in existing.model_dump()
                if existing.model_dump()[k] != source.model_dump()[k]
            }
            if changed - OPERATIONAL_FIELDS:
                raise ApprovedVersionError(
                    f"{source.character_id} {source.version} is approved and immutable "
                    f"(changed: {sorted(changed - OPERATIONAL_FIELDS)}); run `sourcemode source bump` first"
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def update_operational(characters_root: Path, character_id: str, **fields) -> CharacterSource:
    """Update only operational fields (allowed even on approved versions)."""
    unknown = set(fields) - OPERATIONAL_FIELDS
    if unknown:
        raise ValueError(f"not operational fields: {sorted(unknown)}")
    source = load_source(characters_root, character_id)
    updated = source.model_copy(update=fields)
    save_source(characters_root, updated, force=True)
    return updated


def bump_version(characters_root: Path, character_id: str) -> CharacterSource:
    """Archive the current version and start the next one (unapproved)."""
    source = load_source(characters_root, character_id)
    archive_dir = character_dir(characters_root, character_id) / "versions"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f"{source.version}.json"
    if not archive.exists():
        shutil.copy2(source_path(characters_root, character_id), archive)
    bumped = source.model_copy(update={"version": source.next_version(), "approved": False})
    save_source(characters_root, bumped, force=True)
    return bumped


def load_source_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
