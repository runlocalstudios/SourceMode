"""One random seed per sweep, shared by every epoch, kept for re-runs.

Until 2026-10-11 every sweep rendered scene i on 8800 + i, for every character.
Vivienne's kitchen and coffee shop kept 1 of 20 on those draws and 5 of 8 on
fresh seeds with the same prompt and checkpoint.
"""

from __future__ import annotations

import json
import sys

from sourcemode.config import ENGINE_ROOT

sys.path.insert(0, str(ENGINE_ROOT / "scripts" / "eval"))

from asset_scenes import LEGACY_SEED, sweep_seed  # noqa: E402


def test_a_new_sweep_draws_its_own_seed(tmp_path):
    seeds = {sweep_seed(tmp_path / f"s{i}") for i in range(5)}
    assert len(seeds) == 5
    assert LEGACY_SEED not in seeds


def test_a_rerun_renders_the_same_draws(tmp_path):
    first = sweep_seed(tmp_path)
    assert sweep_seed(tmp_path) == first
    assert sweep_seed(tmp_path, given=123) == first     # the stored seed wins
    assert json.loads((tmp_path / "seed.json").read_text())["seed"] == first


def test_a_seed_can_be_given(tmp_path):
    assert sweep_seed(tmp_path, given=4242) == 4242


def test_a_sweep_already_on_disk_keeps_the_old_seed(tmp_path):
    """Finishing a pre-change sweep on new seeds would mix two sets of draws."""
    (tmp_path / "ep20").mkdir()
    (tmp_path / "ep20" / "scene_00.png").write_bytes(b"")
    assert sweep_seed(tmp_path) == LEGACY_SEED
