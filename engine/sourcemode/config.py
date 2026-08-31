"""Engine configuration: engine/config.toml + SOURCEMODE_* env overrides.

Env override convention: SOURCEMODE_<SECTION>_<KEY> (uppercase). A few legacy
aliases map to nicer names (SOURCEMODE_MODELS_DIR etc.). Values are coerced to
the type of the TOML default.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ENGINE_ROOT / "config.toml"

# Friendly aliases -> (section, key)
_ALIASES = {
    "SOURCEMODE_COMFYUI_HOST": ("comfyui", "host"),
    "SOURCEMODE_COMFYUI_PORT": ("comfyui", "port"),
    "SOURCEMODE_MODELS_DIR": ("paths", "models"),
    "SOURCEMODE_LORAS_DIR": ("paths", "loras"),
    "SOURCEMODE_OUTPUTS_DIR": ("paths", "outputs"),
    "SOURCEMODE_MUSUBI_TUNER_PATH": ("training", "musubi_tuner_path"),
    "SOURCEMODE_IDENTITY_GATE_ENABLED": ("gates", "identity_enabled"),
    "SOURCEMODE_QWEN3_URL": ("decomposer", "qwen3_url"),
}

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _coerce(raw: str, like: Any) -> Any:
    if isinstance(like, bool):
        low = raw.strip().lower()
        if low in _TRUTHY:
            return True
        if low in _FALSY:
            return False
        raise ValueError(f"cannot parse boolean from {raw!r}")
    if isinstance(like, int):
        return int(raw)
    if isinstance(like, float):
        return float(raw)
    return raw


def _apply_env(cfg: dict[str, Any], env: dict[str, str]) -> None:
    for var, value in env.items():
        if not var.startswith("SOURCEMODE_"):
            continue
        if var in _ALIASES:
            section, key = _ALIASES[var]
        else:
            # Generic SOURCEMODE_<SECTION>_<KEY>; section must exist to match.
            parts = var[len("SOURCEMODE_") :].lower().split("_", 1)
            if len(parts) != 2 or parts[0] not in cfg:
                continue
            section, key = parts
        if section in cfg and key in cfg[section]:
            cfg[section][key] = _coerce(value, cfg[section][key])
        else:
            cfg.setdefault(section, {})[key] = value


def load_config(path: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Load config.toml, then apply SOURCEMODE_* env overrides."""
    path = path or CONFIG_PATH
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    _apply_env(cfg, dict(os.environ) if env is None else env)
    return cfg


def resolve_path(cfg_value: str, base: Path | None = None) -> Path:
    """Resolve a config path; relative paths are anchored at the engine root."""
    p = Path(cfg_value)
    if not p.is_absolute():
        p = (base or ENGINE_ROOT) / p
    return p.resolve()


def characters_dir(cfg: dict[str, Any]) -> Path:
    return resolve_path(cfg["paths"]["characters"])


def workflows_dir(cfg: dict[str, Any]) -> Path:
    return resolve_path(cfg["paths"]["workflows"])


def outputs_dir(cfg: dict[str, Any]) -> Path:
    return resolve_path(cfg["paths"]["outputs"])
