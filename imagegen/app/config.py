"""Paths and settings. Everything local; the key never leaves this process."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

HOST = os.environ.get("IMAGEGEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("IMAGEGEN_PORT", "8790"))

REFERENCES_DIR = Path(os.environ.get(
    "IMAGEGEN_REFERENCES", r"C:\Epic Games\Files\cnc info\codex\references"))
CODEX_OUTPUTS_DIR = Path(os.environ.get(
    "IMAGEGEN_CODEX_OUTPUTS", r"C:\Epic Games\Files\cnc info\codex\outputs\lora-gen-80"))
MANIFEST_PATH = Path(os.environ.get(
    "IMAGEGEN_MANIFEST",
    str(Path.home() / ".codex" / "skills" / "lora-gen-80" / "references" / "codex_manifest_80_main_v4.json")))

DATA_DIR = ROOT / "data"
MANIFESTS_DIR = DATA_DIR / "manifests"
PRICING_PATH = DATA_DIR / "pricing.json"
OUTPUTS_DIR = Path(os.environ.get("IMAGEGEN_OUTPUTS", str(ROOT / "outputs")))

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

MODELS = ["gpt-image-2.5-sunburst", "gpt-image-2.5-flare", "gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini"]
SIZES = ["1024x1536", "1024x1024", "1536x1024"]
QUALITIES = ["low", "medium", "high", "xhigh", "max"]
# "none" omits the parameter. The 2.5 models REJECT it: sunburst returned
# invalid_input_fidelity_model ("does not support the 'input_fidelity' parameter",
# req_88d3c62855f24ccd97e93f4f5d281fe0, 2026-10-04) on the first real pilot
# request. Measured on sunburst; flare is the same family and is treated the same
# until a request proves otherwise. The gpt-image-2 / 1.5 / 1 line does accept it,
# and it is worth having there - it is what carries a face off the references.
INPUT_FIDELITY = ["none", "high", "low"]
NO_INPUT_FIDELITY = ["gpt-image-2.5-sunburst", "gpt-image-2.5-flare"]
MODERATION = ["auto", "low"]

DEFAULT_SETTINGS = {
    "model": "gpt-image-2.5-sunburst",
    "size": "1024x1536",
    "quality": "high",
    # The default model is a 2.5 one, which rejects the parameter - see above.
    "input_fidelity": "none",
    "moderation": "auto",
    "output_format": "png",
}


def api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or None


def mock_mode() -> bool:
    return os.environ.get("IMAGEGEN_MOCK", "") == "1"
