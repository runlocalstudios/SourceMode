from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sourcemode.config import ENGINE_ROOT, load_config
from sourcemode.source import CharacterSource, save_source

REPO_ROOT = ENGINE_ROOT.parent
GWEN_DIR = REPO_ROOT / "characters" / "gwen"


@pytest.fixture()
def cfg():
    return load_config(env={})


@pytest.fixture()
def sample_source() -> CharacterSource:
    return CharacterSource(
        character_id="testchar",
        name="Test Char",
        version="v001",
        trigger_token="testchar_tk",
        invariants=["hair: bright blue bob", "eyes: grey"],
        wardrobe_states={"default": "", "armor": " wearing scuffed armor"},
        reference_images=["references/a.png", "references/b.png"],
        approved_sheet=["references/a.png", "references/b.png"],
        negative_block="text, watermark, extra limbs",
    )


@pytest.fixture()
def chars_root(tmp_path: Path, sample_source: CharacterSource) -> Path:
    root = tmp_path / "characters"
    save_source(root, sample_source)
    return root


@pytest.fixture()
def gwen_available() -> bool:
    return (GWEN_DIR / "source.json").exists()


def make_test_cfg(cfg: dict, tmp_path: Path) -> dict:
    """Copy of the real config with outputs redirected into tmp."""
    import copy

    c = copy.deepcopy(cfg)
    c["paths"]["outputs"] = str(tmp_path / "outputs")
    return c


@pytest.fixture()
def tmp_cfg(cfg, tmp_path):
    return make_test_cfg(cfg, tmp_path)


def copy_gwen_refs(dest: Path) -> list[Path]:
    src = GWEN_DIR / "references"
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(src.glob("*.png")):
        out.append(Path(shutil.copy2(p, dest / p.name)))
    return out
