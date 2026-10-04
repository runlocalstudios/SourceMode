"""Reference discovery: the full name before the first underscore, case-insensitive.

`priya_` must not match `priyanka_`, which a prefix match would do.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .config import IMAGE_SUFFIXES, REFERENCES_DIR


def character_of(path: Path) -> str:
    return path.stem.split("_", 1)[0].lower()


def list_characters(folder: Path = REFERENCES_DIR) -> list[str]:
    if not folder.is_dir():
        return []
    names = {character_of(p) for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and "_" in p.stem}
    return sorted(names)


def references_for(character: str, folder: Path = REFERENCES_DIR) -> list[Path]:
    if not folder.is_dir():
        return []
    want = character.lower()
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and character_of(p) == want)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
