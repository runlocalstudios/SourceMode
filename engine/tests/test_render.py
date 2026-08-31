import json
from pathlib import Path

import pytest

from sourcemode.render.client import ComfyUIClient
from sourcemode.render.passes import build_keyframe_workflow, build_video_workflow, snap_frames
from sourcemode.render.sidecar import read_sidecar, write_sidecar
from sourcemode.render.workflow import (
    LoraCompositionError,
    MissingPlaceholderError,
    substitute,
    validate_lora_stack,
)

TEMPLATE = json.dumps({
    "_meta": {"warning": "test"},
    "nodes": {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{POSITIVE}}"}},
        "2": {"class_type": "KSampler", "inputs": {"seed": "{{SEED}}", "steps": "{{STEPS}}", "denoise": "{{STRENGTH}}"}},
    },
})


def test_substitute_strings_and_numbers():
    nodes = substitute(TEMPLATE, {"POSITIVE": 'a "quoted" prompt\nline2', "SEED": 42, "STEPS": 8, "STRENGTH": 0.5})
    assert nodes["1"]["inputs"]["text"] == 'a "quoted" prompt\nline2'
    assert nodes["2"]["inputs"]["seed"] == 42
    assert isinstance(nodes["2"]["inputs"]["seed"], int)
    assert nodes["2"]["inputs"]["denoise"] == 0.5
    assert "_meta" not in nodes


def test_substitute_missing_placeholder_raises():
    with pytest.raises(MissingPlaceholderError) as err:
        substitute(TEMPLATE, {"POSITIVE": "x", "SEED": 1, "STEPS": 2})
    assert "STRENGTH" in str(err.value)


def test_lora_composition_rule():
    validate_lora_stack([
        {"path": "id.safetensors", "strength": 1.0, "is_identity": True},
        {"path": "lightning.safetensors", "strength": 0.6, "is_identity": False},
    ])
    with pytest.raises(LoraCompositionError):
        validate_lora_stack([{"path": "id.safetensors", "strength": 1.1, "is_identity": True}])
    with pytest.raises(LoraCompositionError):
        validate_lora_stack([{"path": "style.safetensors", "strength": 0.7, "is_identity": False}])


def test_snap_frames_4n_plus_1_capped():
    assert snap_frames(5.0, 16) == 77  # 80 frames -> snapped down to 4n+1
    assert snap_frames(1.0, 16) == 13
    assert snap_frames(8.0, 16) == 81
    assert (snap_frames(3.3, 16) - 1) % 4 == 0


def test_build_video_workflow_substitutes_fully(tmp_cfg, sample_source):
    nodes, settings = build_video_workflow(
        tmp_cfg, sample_source,
        positive="positive text", negative="negative text",
        image_name="kf.png", seed=7, render_pass="draft", duration_s=4.0,
    )
    dumped = json.dumps(nodes)
    assert "{{" not in dumped
    assert settings["SEED"] == 7
    assert nodes["6"]["inputs"]["text"] == "positive text"
    assert nodes["7"]["inputs"]["text"] == "negative text"
    assert nodes["52"]["inputs"]["image"] == "kf.png"


def test_build_keyframe_workflow_substitutes_fully(tmp_cfg, sample_source):
    nodes, settings = build_keyframe_workflow(
        tmp_cfg, sample_source, positive="p", negative="n", seed=3, render_pass="final",
    )
    assert "{{" not in json.dumps(nodes)
    assert settings["STEPS"] == tmp_cfg["render"]["final"]["steps"]


def test_sidecar_roundtrip(tmp_path):
    artifact = tmp_path / "video.webp"
    artifact.write_bytes(b"fake")
    write_sidecar(
        artifact,
        source_version="v002", prompt_hash="abc123", seed=99,
        models={"MODEL_LOW": "low.safetensors"},
        loras=[{"name": "id.safetensors", "strength": 1.0}],
        render_pass="draft", settings={"kind": "video"},
    )
    data = read_sidecar(artifact)
    assert data["source_version"] == "v002"
    assert data["prompt_hash"] == "abc123"
    assert data["seed"] == 99
    assert data["pass"] == "draft"
    assert data["loras"][0]["strength"] == 1.0
    assert data["settings"]["kind"] == "video"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeSession:
    """Mocked HTTP server: records requests, plays scripted responses."""

    def __init__(self):
        self.posts = []
        self.gets = []
        self.history_calls = 0

    def post(self, url, json=None, files=None, timeout=None):
        self.posts.append((url, json))
        if url.endswith("/prompt"):
            return FakeResponse(payload={"prompt_id": "pid-1"})
        return FakeResponse(payload={"name": "up.png", "subfolder": ""})

    def get(self, url, params=None, timeout=None):
        self.gets.append((url, params))
        if "/history/" in url:
            self.history_calls += 1
            if self.history_calls < 2:
                return FakeResponse(payload={})  # not done yet
            return FakeResponse(payload={
                "pid-1": {
                    "status": {"status_str": "success"},
                    "outputs": {"60": {"images": [{"filename": "out.webp", "subfolder": "", "type": "output"}]}},
                }
            })
        if url.endswith("/view"):
            return FakeResponse(content=b"artifact-bytes")
        return FakeResponse()


def test_client_submit_poll_fetch(tmp_path):
    session = FakeSession()
    client = ComfyUIClient("127.0.0.1", 8188, session=session, client_id="cid")
    prompt_id = client.submit({"1": {"class_type": "X", "inputs": {}}})
    assert prompt_id == "pid-1"
    url, payload = session.posts[0]
    assert url == "http://127.0.0.1:8188/prompt"
    assert payload["client_id"] == "cid"
    entry = client.wait(prompt_id, poll_s=0.0)
    files = client.outputs(entry)
    assert files == [{"filename": "out.webp", "subfolder": "", "type": "output"}]
    dest = client.fetch(files[0], tmp_path / "out.webp")
    assert Path(dest).read_bytes() == b"artifact-bytes"
