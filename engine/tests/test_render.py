import json
from pathlib import Path

import pytest

from sourcemode.render.client import ComfyUIClient, ComfyUIError
from sourcemode.render.passes import (
    build_edit_workflow,
    build_keyframe_workflow,
    build_video_workflow,
    snap_frames,
)
from sourcemode.render.sidecar import read_sidecar, write_sidecar
from sourcemode.render.workflow import (
    PLACEHOLDER_LORA,
    LoraCompositionError,
    MissingPlaceholderError,
    prune_placeholder_loras,
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
        {"path": "style.safetensors", "strength": 0.6, "is_identity": False},
        {"path": "lightning.safetensors", "strength": 1.0, "is_distill": True},
    ])
    with pytest.raises(LoraCompositionError):
        validate_lora_stack([{"path": "id.safetensors", "strength": 1.1, "is_identity": True}])
    with pytest.raises(LoraCompositionError):
        validate_lora_stack([{"path": "style.safetensors", "strength": 0.7, "is_identity": False}])
    with pytest.raises(LoraCompositionError):
        validate_lora_stack([{"path": "lightning.safetensors", "strength": 1.1, "is_distill": True}])


def test_prune_placeholder_loras_rewires_chains():
    nodes = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
        "2": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": "", "strength_model": 1.0}},
        "3": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["2", 0], "lora_name": PLACEHOLDER_LORA, "strength_model": 1.0}},
        "4": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["3", 0], "lora_name": "real.safetensors", "strength_model": 1.0}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "seed": 1}},
    }
    prune_placeholder_loras(nodes)
    assert "2" not in nodes and "3" not in nodes
    assert nodes["4"]["inputs"]["model"] == ["1", 0]  # chain collapsed onto the UNET
    assert nodes["5"]["inputs"]["model"] == ["4", 0]  # real LoRA kept


def test_prune_all_loras_connects_consumer_to_source():
    nodes = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "m.safetensors"}},
        "2": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": "", "strength_model": 1.0}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "seed": 1}},
    }
    prune_placeholder_loras(nodes)
    assert nodes["5"]["inputs"]["model"] == ["1", 0]


def test_snap_frames_4n_plus_1_capped():
    assert snap_frames(5.0, 16) == 77  # 80 frames -> snapped down to 4n+1
    assert snap_frames(1.0, 16) == 13
    assert snap_frames(8.0, 16) == 81
    assert (snap_frames(3.3, 16) - 1) % 4 == 0
    assert snap_frames(8.0, 24, max_frames=145) == 145  # raised cap (real graph runs 145)
    assert snap_frames(60.0, 24, max_frames=145) == 145


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
    # no trained character LoRA -> identity slots pruned; draft lightning kept
    lora_names = [n["inputs"]["lora_name"] for n in nodes.values() if n["class_type"] == "LoraLoaderModelOnly"]
    assert lora_names == [
        tmp_cfg["render"]["draft"]["wan_lightning_high"],
        tmp_cfg["render"]["draft"]["wan_lightning_low"],
    ]


def test_video_generic_lora_fallback(tmp_cfg, sample_source):
    # no character wan LoRA + generic [video] LoRA configured -> generic fills
    # the slot at the capped non-identity strength
    tmp_cfg["video"]["lora_low"] = "styles/moody.safetensors"
    nodes, settings = build_video_workflow(
        tmp_cfg, sample_source, positive="p", negative="n",
        image_name="kf.png", seed=1, render_pass="final", duration_s=2.0,
    )
    assert settings["LORA_LOW"] == "styles/moody.safetensors"
    assert settings["LORA_STRENGTH_LOW"] == 0.6
    assert settings["LORA_HIGH"] == ""  # nothing configured for high -> pruned
    loras = [(n["inputs"]["lora_name"], n["inputs"]["strength_model"])
             for n in nodes.values() if n["class_type"] == "LoraLoaderModelOnly"]
    assert loras == [("styles/moody.safetensors", 0.6)]


def test_video_character_lora_beats_generic(tmp_cfg, sample_source):
    tmp_cfg["video"]["lora_low"] = "styles/moody.safetensors"
    src = sample_source.model_copy(update={
        "lora_paths": sample_source.lora_paths.model_copy(update={"wan_low_noise": "char/id.safetensors"})
    })
    _, settings = build_video_workflow(
        tmp_cfg, src, positive="p", negative="n",
        image_name="kf.png", seed=1, render_pass="final", duration_s=2.0,
    )
    assert settings["LORA_LOW"] == "char/id.safetensors"
    assert settings["LORA_STRENGTH_LOW"] == 1.0


def test_medium_pass_is_lightning_video_final_keyframes(tmp_cfg, sample_source):
    nodes, settings = build_video_workflow(
        tmp_cfg, sample_source, positive="p", negative="n",
        image_name="kf.png", seed=1, render_pass="medium", duration_s=2.0,
    )
    assert settings["STEPS"] == 4 and settings["CFG_HIGH"] == 1.0
    lora_names = [n["inputs"]["lora_name"] for n in nodes.values() if n["class_type"] == "LoraLoaderModelOnly"]
    assert tmp_cfg["render"]["medium"]["wan_lightning_low"] in lora_names
    _, kf_settings = build_keyframe_workflow(
        tmp_cfg, sample_source, positive="p", negative="n", seed=1, render_pass="medium",
    )
    assert kf_settings["STEPS"] == 50 and kf_settings["CFG"] == 4.0
    assert kf_settings["LIGHTNING"] == ""  # keyframes at final quality in medium


def test_build_video_workflow_final_has_no_loras(tmp_cfg, sample_source):
    nodes, settings = build_video_workflow(
        tmp_cfg, sample_source, positive="p", negative="n",
        image_name="kf.png", seed=1, render_pass="final",
    )
    assert not [n for n in nodes.values() if n["class_type"] == "LoraLoaderModelOnly"]
    # per-stage CFG: high-noise sampler (adds noise) vs low-noise sampler
    samplers = {n["inputs"]["add_noise"]: n for n in nodes.values() if n["class_type"] == "KSamplerAdvanced"}
    assert samplers["enable"]["inputs"]["cfg"] == tmp_cfg["render"]["final"]["cfg_high"]
    assert samplers["disable"]["inputs"]["cfg"] == tmp_cfg["render"]["final"]["cfg_low"]
    assert settings["SHIFT"] == tmp_cfg["video"]["shift"]
    # samplers still chain to the models through ModelSamplingSD3
    samplers = [n for n in nodes.values() if n["class_type"] == "KSamplerAdvanced"]
    assert len(samplers) == 2
    assert all(nodes[s["inputs"]["model"][0]]["class_type"] == "ModelSamplingSD3" for s in samplers)


def test_build_keyframe_workflow_substitutes_fully(tmp_cfg, sample_source):
    nodes, settings = build_keyframe_workflow(
        tmp_cfg, sample_source, positive="p", negative="n", seed=3, render_pass="final",
    )
    assert "{{" not in json.dumps(nodes)
    assert settings["STEPS"] == tmp_cfg["render"]["final"]["qwen_t2i_steps"]


def test_build_edit_workflow_substitutes_and_prunes(tmp_cfg, sample_source):
    nodes, settings = build_edit_workflow(
        tmp_cfg, sample_source, instruction="same person, left profile",
        negative="n", image_name="ref.png", seed=9, render_pass="draft",
    )
    assert "{{" not in json.dumps(nodes)
    assert settings["STEPS"] == tmp_cfg["render"]["draft"]["qwen_edit_steps"]
    lora_names = [n["inputs"]["lora_name"] for n in nodes.values() if n["class_type"] == "LoraLoaderModelOnly"]
    assert lora_names == [tmp_cfg["render"]["draft"]["qwen_edit_lightning"]]
    # positive/negative both go through the reference-latent method into the sampler
    sampler = next(n for n in nodes.values() if n["class_type"] == "KSampler")
    pos = nodes[sampler["inputs"]["positive"][0]]
    neg = nodes[sampler["inputs"]["negative"][0]]
    assert pos["class_type"] == neg["class_type"] == "FluxKontextMultiReferenceLatentMethod"
    encode_pos = nodes[pos["inputs"]["conditioning"][0]]
    assert encode_pos["inputs"]["prompt"] == "same person, left profile"


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


def test_client_wait_survives_transient_poll_failures():
    class FlakySession(FakeSession):
        def get(self, url, params=None, timeout=None):
            if "/history/" in url and self.history_calls == 0:
                self.history_calls += 1
                raise TimeoutError("server busy mid-render")
            return super().get(url, params=params, timeout=timeout)

    client = ComfyUIClient(session=FlakySession(), client_id="cid")
    entry = client.wait("pid-1", poll_s=0.0, timeout_s=5.0)
    assert entry["status"]["status_str"] == "success"


def test_client_wait_still_raises_on_prompt_error():
    class ErrorSession(FakeSession):
        def get(self, url, params=None, timeout=None):
            if "/history/" in url:
                return FakeResponse(payload={"pid-1": {"status": {"status_str": "error"}}})
            return super().get(url, params=params, timeout=timeout)

    client = ComfyUIClient(session=ErrorSession(), client_id="cid")
    with pytest.raises(ComfyUIError):
        client.wait("pid-1", poll_s=0.0, timeout_s=5.0)


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
