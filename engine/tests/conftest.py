from __future__ import annotations

from pathlib import Path

import pytest

from sourcemode.config import ENGINE_ROOT, load_config

REPO_ROOT = ENGINE_ROOT.parent


@pytest.fixture()
def cfg():
    return load_config(env={})


def make_test_cfg(cfg: dict, tmp_path: Path) -> dict:
    """Copy of the real config with outputs redirected into tmp."""
    import copy

    c = copy.deepcopy(cfg)
    c["paths"]["outputs"] = str(tmp_path / "outputs")
    return c


@pytest.fixture()
def tmp_cfg(cfg, tmp_path):
    return make_test_cfg(cfg, tmp_path)
