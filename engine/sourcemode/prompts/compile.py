"""Compile a brief into a scene file: shots + compiled prompts + prompt_hash."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..source import CharacterSource
from .decompose import Decomposer
from .spec import ShotSpec
from .templates import keyframe_prompt, video_negative, video_prompt


def prompt_hash(source: CharacterSource, spec: ShotSpec, positive: str, negative: str) -> str:
    payload = json.dumps(
        {
            "source_version": source.version,
            "spec": spec.model_dump(),
            "positive": positive,
            "negative": negative,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def scene_slug(brief: str) -> str:
    words = re.findall(r"[a-z0-9]+", brief.lower())[:6]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return "-".join(words) + "-" + stamp


def compile_scene(source: CharacterSource, brief: str, decomposer: Decomposer) -> dict:
    shots = decomposer.decompose(brief)
    compiled = []
    for spec in shots:
        kf = keyframe_prompt(source, spec)
        vid = video_prompt(source, spec)
        neg = video_negative(source)
        compiled.append(
            {
                "spec": spec.model_dump(),
                "keyframe_prompt": kf,
                "video_prompt": vid,
                "negative": neg,
                "prompt_hash": prompt_hash(source, spec, vid, neg),
            }
        )
    return {
        "character_id": source.character_id,
        "source_version": source.version,
        "brief": brief,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "shots": compiled,
    }


def write_scene(scene: dict, outputs_root: Path, slug: str | None = None) -> Path:
    slug = slug or scene_slug(scene["brief"])
    scene_dir = outputs_root / "scenes" / slug
    scene_dir.mkdir(parents=True, exist_ok=True)
    path = scene_dir / "scene.yaml"
    path.write_text(yaml.safe_dump(scene, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def load_scene(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
