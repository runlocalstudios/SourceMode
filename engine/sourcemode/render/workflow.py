"""ComfyUI workflow templating.

Templates live in workflows/*.json (API format) wrapped as
{"_meta": {...}, "nodes": {...}} so the header can carry the
TEMPLATE-UNVERIFIED warning; only "nodes" is POSTed.

Placeholders are {{NAME}} strings inside the JSON text. String values are
JSON-escaped in place; int/float values replace the QUOTED placeholder so the
result is a bare number. All placeholders must be resolved — leftovers raise.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

# Composition rule: the identity LoRA may go up to 1.0; any other LoRA
# (lightning/style/motion) is capped at 0.6 so it can't fight identity.
MAX_IDENTITY_STRENGTH = 1.0
MAX_OTHER_STRENGTH = 0.6


class MissingPlaceholderError(ValueError):
    pass


class LoraCompositionError(ValueError):
    pass


def validate_lora_stack(loras: list[dict]) -> None:
    """Each entry: {"path": str, "strength": float, "is_identity": bool}."""
    for lora in loras:
        strength = float(lora["strength"])
        if lora.get("is_identity"):
            if strength > MAX_IDENTITY_STRENGTH:
                raise LoraCompositionError(
                    f"identity LoRA {lora['path']!r} strength {strength} > {MAX_IDENTITY_STRENGTH}"
                )
        elif strength > MAX_OTHER_STRENGTH:
            raise LoraCompositionError(
                f"non-identity LoRA {lora['path']!r} strength {strength} > {MAX_OTHER_STRENGTH}"
            )


def load_template(workflows_dir: Path, name: str) -> str:
    """Return the raw template text (substitution happens on text, then parses)."""
    path = Path(workflows_dir) / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"workflow template not found: {path}")
    return path.read_text(encoding="utf-8")


def substitute(template_text: str, values: dict) -> dict:
    """Fill placeholders and return the node graph dict ready to POST."""
    text = template_text
    for key, value in values.items():
        token = "{{" + key + "}}"
        if isinstance(value, bool):
            text = text.replace(f'"{token}"', "true" if value else "false")
        elif isinstance(value, (int, float)):
            text = text.replace(f'"{token}"', json.dumps(value))
        else:
            text = text.replace(token, json.dumps(str(value))[1:-1])

    leftover = sorted(set(_PLACEHOLDER_RE.findall(text)))
    if leftover:
        raise MissingPlaceholderError(f"unresolved placeholders: {leftover}")

    doc = json.loads(text)
    return doc["nodes"] if isinstance(doc, dict) and "nodes" in doc else doc
