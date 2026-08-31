"""GPU integration tests: real renders against a running ComfyUI.

Marked `gpu`; they skip cleanly when ComfyUI is unreachable or the models the
workflow needs are missing. Run with: uv run pytest -m gpu
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sourcemode.config import load_config
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.passes import build_edit_workflow, build_video_workflow
from sourcemode.source import load_source
from tests.conftest import GWEN_DIR, REPO_ROOT

pytestmark = pytest.mark.gpu

_cfg = load_config(env={})


def _client() -> ComfyUIClient:
    return ComfyUIClient(_cfg["comfyui"]["host"], _cfg["comfyui"]["port"])


def _models_present(*names: str) -> bool:
    models_dir = Path(_cfg["paths"]["models"])
    return all(any((models_dir / sub / n).exists() for sub in ("diffusion_models", "loras")) for n in names)


needs_comfy = pytest.mark.skipif(not _client().is_reachable(), reason="ComfyUI not reachable on 8188")
needs_gwen = pytest.mark.skipif(not (GWEN_DIR / "source.json").exists(), reason="gwen assets missing")


@pytest.fixture()
def gwen():
    return load_source(REPO_ROOT / "characters", "gwen")


@pytest.fixture()
def client():
    return _client()


@needs_comfy
@needs_gwen
def test_qwen_image_edit_smoke(gwen, client, tmp_path):
    if not _models_present(_cfg["models"]["qwen_edit"]):
        pytest.skip(f"{_cfg['models']['qwen_edit']} not downloaded")
    image_name = client.upload_image(GWEN_DIR / "references" / "ref-00-canonical.png")
    nodes, _ = build_edit_workflow(
        _cfg, gwen,
        instruction="same person, 3/4 left profile, neutral expression, preserve all facial features",
        negative=gwen.negative_block, image_name=image_name, seed=7, render_pass="draft",
        filename_prefix="sourcemode/test_edit_smoke",
    )
    prompt_id = client.submit(nodes)
    entry = client.wait(prompt_id, timeout_s=600)
    files = client.outputs(entry)
    assert files, "edit smoke produced no output files"
    dest = client.fetch(files[0], tmp_path / "edit_smoke.png")
    assert dest.stat().st_size > 10_000


@needs_comfy
@needs_gwen
def test_wan22_i2v_smoke(gwen, client, tmp_path):
    if not _models_present(_cfg["models"]["wan_i2v_high_fp8"], _cfg["models"]["wan_i2v_low_fp8"]):
        pytest.skip("wan i2v fp8 models not present")
    image_name = client.upload_image(GWEN_DIR / "references" / "ref-00-canonical.png")
    nodes, _ = build_video_workflow(
        _cfg, gwen, positive="the character stands still, breathing gently, subtle natural motion",
        negative=gwen.negative_block, image_name=image_name, seed=7, render_pass="draft",
        duration_s=1.0, width=480, height=480,
    )
    prompt_id = client.submit(nodes)
    entry = client.wait(prompt_id, timeout_s=1800)
    files = client.outputs(entry)
    assert files, "i2v smoke produced no output files"
    dest = client.fetch(files[0], tmp_path / "i2v_smoke.mp4")
    assert dest.stat().st_size > 10_000
