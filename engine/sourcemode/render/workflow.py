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

# Composition rule: the identity LoRA may go up to 1.0; any style/motion LoRA
# is capped at 0.6 so it can't fight identity. Distill LoRAs (lightning/lightx2v
# timestep-distillation adapters) carry no subject content and are designed for
# strength 1.0 — they get their own cap (see DECISIONS.md).
MAX_IDENTITY_STRENGTH = 1.0
MAX_DISTILL_STRENGTH = 1.0
MAX_OTHER_STRENGTH = 0.6

# Keeps templates fully substituted in dry-run before real LoRAs exist; nodes
# carrying this (or an empty) lora_name are removed by prune_placeholder_loras.
PLACEHOLDER_LORA = "NONE.safetensors"


class MissingPlaceholderError(ValueError):
    pass


class LoraCompositionError(ValueError):
    pass


def validate_lora_stack(loras: list[dict]) -> None:
    """Each entry: {"path": str, "strength": float, "is_identity": bool, "is_distill": bool}."""
    for lora in loras:
        strength = float(lora["strength"])
        if lora.get("is_identity"):
            if strength > MAX_IDENTITY_STRENGTH:
                raise LoraCompositionError(
                    f"identity LoRA {lora['path']!r} strength {strength} > {MAX_IDENTITY_STRENGTH}"
                )
        elif lora.get("is_distill"):
            if strength > MAX_DISTILL_STRENGTH:
                raise LoraCompositionError(
                    f"distill LoRA {lora['path']!r} strength {strength} > {MAX_DISTILL_STRENGTH}"
                )
        elif strength > MAX_OTHER_STRENGTH:
            raise LoraCompositionError(
                f"non-identity LoRA {lora['path']!r} strength {strength} > {MAX_OTHER_STRENGTH}"
            )


def prune_placeholder_loras(nodes: dict, placeholder: str = PLACEHOLDER_LORA) -> dict:
    """Remove LoraLoaderModelOnly nodes whose lora_name is empty/placeholder.

    ComfyUI validates every node's lora_name against the files on disk — even
    nodes on an unexecuted branch — so unset LoRA slots must be removed, not
    pointed at a dummy file. Consumers of a pruned node's model output are
    rewired to the pruned node's own model input. Handles chains of prunable
    LoRAs. Returns the same dict, mutated.
    """
    while True:
        prune_id = next(
            (
                node_id
                for node_id, node in nodes.items()
                if node.get("class_type") == "LoraLoaderModelOnly"
                and node["inputs"].get("lora_name") in ("", placeholder)
            ),
            None,
        )
        if prune_id is None:
            return nodes
        upstream = nodes[prune_id]["inputs"]["model"]
        del nodes[prune_id]
        for node in nodes.values():
            for key, value in node["inputs"].items():
                if isinstance(value, list) and len(value) == 2 and value[0] == prune_id:
                    node["inputs"][key] = upstream


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
