"""Non-billable verification with the mock client."""
import json
from pathlib import Path

import pytest

from app import manifest as manifest_mod
from app import pricing as pricing_mod
from app import refs as refs_mod
from app import runs as runs_mod
from app.client import MockClient
from app.worker import Worker

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def env(tmp_path, monkeypatch):
    refs = tmp_path / "refs"; refs.mkdir()
    from PIL import Image
    for n in ("cici_face.jpg", "cici_portrait1.jpg", "priya_face.jpg", "priyanka_face.png"):
        Image.new("RGB", (64, 96), (200, 100, 100)).save(refs / n)
    src = {"approval_stop_after": 4, "shots": [
        {"id": f"shot_{i:03d}", "filename": f"<character>_shot_{i:03d}.png", "hair_needs_length": "long",
         "prompt": f"Prompt {i} with  exact   spacing, <character> stays literal, and unicode – é."} for i in range(1, 7)]}
    man = tmp_path / "manifest.json"; man.write_text(json.dumps(src), encoding="utf-8")
    monkeypatch.setattr(manifest_mod, "MANIFESTS_DIR", tmp_path / "work")
    monkeypatch.setattr(manifest_mod, "MANIFEST_PATH", man)
    # The live pricing file accumulates OBSERVED usage from real runs, and every
    # estimate depends on it - so a test reading it straight breaks the next time
    # Jeremy runs a pilot (which is exactly what happened on 2026-10-04: a `high`
    # run made two tests fail for no reason of their own). Copy the prices, drop
    # the observations, and let each test record whatever it needs.
    pricing = tmp_path / "pricing.json"
    pr = json.loads((ROOT / "data" / "pricing.json").read_text(encoding="utf-8"))
    pr["observed"] = {}
    pricing.write_text(json.dumps(pr), encoding="utf-8")
    observed_before = {}   # the copy above starts with none
    return {"refs": refs, "manifest": man, "outputs": tmp_path / "out", "pricing": pricing,
            "src": src, "observed_before": observed_before}


def make_run(env, client, shots=None, ceiling=None, label="t"):
    doc = manifest_mod.import_manifest("cici", env["manifest"])
    chosen = refs_mod.references_for("cici", env["refs"])
    sel = [s for s in doc["shots"] if shots is None or s["id"] in shots]
    pr = pricing_mod.load(env["pricing"])
    est = pricing_mod.estimate(pr, "gpt-image-2.5-sunburst", "1024x1536", "high", len(chosen))
    run = runs_mod.create_run("cici", label, {"model": "gpt-image-2.5-sunburst", "size": "1024x1536", "quality": "high",
                                              "input_fidelity": "high", "moderation": "auto", "output_format": "png"},
                              chosen, sel, ceiling, est, env["outputs"])
    w = Worker(client, env["outputs"], env["pricing"], sleep=lambda s: None)
    return run, w


def test_reference_discovery_exact_name(env):
    assert [p.name for p in refs_mod.references_for("priya", env["refs"])] == ["priya_face.jpg"]
    assert [p.name for p in refs_mod.references_for("PRIYANKA", env["refs"])] == ["priyanka_face.png"]
    assert refs_mod.list_characters(env["refs"]) == ["cici", "priya", "priyanka"]


def test_import_preserves_prompts_and_maps_filenames(env):
    doc = manifest_mod.import_manifest("cici", env["manifest"])
    for a, b in zip(doc["shots"], env["src"]["shots"]):
        assert a["prompt"] == b["prompt"]
        assert a["original_prompt"] == b["prompt"]
    assert doc["shots"][0]["filename"] == "cici_shot_001.png"
    # the original file is untouched
    assert json.loads(env["manifest"].read_text(encoding="utf-8")) == env["src"]
    # an edit is recorded without losing the original
    manifest_mod.edit_prompt("cici", "shot_002", "changed")
    doc = manifest_mod.load_working("cici")
    assert doc["shots"][1]["prompt"] == "changed" and doc["shots"][1]["edited"]
    assert doc["shots"][1]["original_prompt"] == env["src"]["shots"][1]["prompt"]


def test_shot_to_filename_and_usage_logged(env):
    client = MockClient()
    run, w = make_run(env, client, ["shot_001", "shot_003"])
    w.start(run); w.join(10)
    d = runs_mod.run_dir("cici", run["run_id"], env["outputs"])
    # The name is whatever was bound at create time (quality-suffixed since 2026-10-04).
    assert [s["filename"] for s in run["shots"]] == ["cici_shot_001_high.png", "cici_shot_003_high.png"]
    for s in run["shots"]:
        assert (d / s["filename"]).is_file()
    assert not (d / "cici_shot_002_high.png").exists()
    assert client.calls[0]["prompt"] == run["shots"][0]["prompt"]
    assert len(client.calls[0]["refs"]) == 2 and all("refs" in r for r in client.calls[0]["refs"])
    saved = json.loads((d / "run.json").read_text(encoding="utf-8"))
    assert [s["state"] for s in saved["shots"]] == ["saved", "saved"]
    a = saved["shots"][0]["attempts"][0]
    assert a["usage"]["output_tokens"] == 10550 and a["cost_usd"] > 0 and a["request_id"]
    assert saved["totals"]["saved"] == 2 and saved["totals"]["spent_estimate_usd"] > 0
    pr = pricing_mod.load(env["pricing"])
    assert pr["observed"] == env["observed_before"]            # mock usage never feeds the estimates


def test_resume_never_regenerates_saved(env):
    client = MockClient(script=[None, "transient", "transient", "transient", "transient"])
    run, w = make_run(env, client, ["shot_001", "shot_002"])
    w.start(run); w.join(10)
    d = runs_mod.run_dir("cici", run["run_id"], env["outputs"])
    assert run["shots"][0]["state"] == "saved" and run["shots"][1]["state"] == "failed"
    assert len(run["shots"][1]["attempts"]) == 4            # bounded
    first_bytes = (d / run["shots"][0]["filename"]).read_bytes()
    # restart: reload from disk, reconcile, retry only the failed one
    client2 = MockClient()
    loaded = runs_mod.reconcile(runs_mod.load_run("cici", run["run_id"], env["outputs"]), env["outputs"])
    w2 = Worker(client2, env["outputs"], env["pricing"], sleep=lambda s: None)
    w2.run = loaded; w2.retry_shot("shot_002"); w2.start(loaded); w2.join(10)
    assert len(client2.calls) == 1 and client2.calls[0]["prompt"].startswith("Prompt 2")
    assert (d / loaded["shots"][0]["filename"]).read_bytes() == first_bytes   # preserved
    assert loaded["shots"][1]["state"] == "saved"


def test_interrupted_running_becomes_uncertain(env):
    client = MockClient()
    run, w = make_run(env, client, ["shot_001"])
    run["shots"][0]["state"] = "running"; run["shots"][0]["attempts"].append({"started": "x", "sent": True})
    runs_mod.save_run(run, env["outputs"])
    loaded = runs_mod.reconcile(runs_mod.load_run("cici", run["run_id"], env["outputs"]), env["outputs"])
    assert loaded["shots"][0]["state"] == "uncertain"
    assert loaded["totals"]["unknown_cost_attempts"] == 1
    w.run = loaded; w.start(loaded); w.join(10)
    assert client.calls == []                                  # not retried automatically


def test_quota_pauses_queue(env):
    client = MockClient(script=[None, "quota", None])
    run, w = make_run(env, client, ["shot_001", "shot_002", "shot_003"])
    w.start(run); w.join(10)
    assert [s["state"] for s in run["shots"]] == ["saved", "blocked", "pending"]
    assert run["paused"] and "quota" in run["pause_reason"] and "req_mock_q" in run["pause_reason"]
    assert len(client.calls) == 2                              # nothing sent after the quota error
    err = run["shots"][1]["attempts"][0]["error"]
    assert err["code"] == "insufficient_quota" and err["status"] == 429


def test_auth_and_config_pause(env):
    for kind in ("auth", "config"):
        client = MockClient(script=[kind])
        run, w = make_run(env, client, ["shot_001", "shot_002"], label=kind)
        w.start(run); w.join(10)
        assert run["paused"] and run["shots"][0]["state"] == "blocked" and run["shots"][1]["state"] == "pending"
        assert len(client.calls) == 1


def test_rate_limit_bounded_then_continues(env):
    client = MockClient(script=["rate_limit", "rate_limit", None, None])
    run, w = make_run(env, client, ["shot_001", "shot_002"])
    w.start(run); w.join(10)
    assert [s["state"] for s in run["shots"]] == ["saved", "saved"]
    assert len(run["shots"][0]["attempts"]) == 3 and len(client.calls) == 4


def test_moderation_marks_failed_and_continues(env):
    client = MockClient(script=["moderation", None])
    run, w = make_run(env, client, ["shot_001", "shot_002"])
    w.start(run); w.join(10)
    assert [s["state"] for s in run["shots"]] == ["failed", "saved"]
    assert run["shots"][0]["attempts"][0]["error"]["kind"] == "moderation"
    assert run["shots"][0]["attempts"][0]["cost_usd"] is None and run["totals"]["unknown_cost_attempts"] == 1


def test_uncertain_outcome_not_retried(env):
    client = MockClient(script=["uncertain", None])
    run, w = make_run(env, client, ["shot_001", "shot_002"])
    w.start(run); w.join(10)
    assert run["shots"][0]["state"] == "uncertain" and len(run["shots"][0]["attempts"]) == 1
    assert run["shots"][1]["state"] == "saved"


def test_spend_ceiling_stops_new_requests(env):
    client = MockClient()
    run, w = make_run(env, client, ["shot_001", "shot_002", "shot_003"], ceiling=0.80)   # ~0.40 each in the mock
    w.start(run); w.join(10)
    states = [s["state"] for s in run["shots"]]
    assert states.count("saved") == 2 and states[2] == "pending"
    assert run["paused"] and "ceiling" in run["pause_reason"]


def test_existing_file_never_overwritten(env):
    client = MockClient()
    run, w = make_run(env, client, ["shot_001"])
    d = runs_mod.run_dir("cici", run["run_id"], env["outputs"])
    (d / run["shots"][0]["filename"]).write_bytes(b"precious")
    w.start(run); w.join(10)
    assert (d / run["shots"][0]["filename"]).read_bytes() == b"precious"
    assert client.calls == [] and run["shots"][0]["state"] == "saved"


def test_estimate_states_assumptions(env):
    pr = pricing_mod.load(env["pricing"])
    e = pricing_mod.estimate(pr, "gpt-image-2.5-sunburst", "1024x1536", "high", 3)
    assert e["per_image_usd"] > 0 and not e["observed"]
    assert any("ASSUMED" in a for a in e["assumptions"])
    pricing_mod.record_observation(pr, "gpt-image-2.5-sunburst", "1024x1536", "high",
                                   {"output_tokens": 8000, "image_in_tokens": 3000, "text_tokens": 200})
    e2 = pricing_mod.estimate(pr, "gpt-image-2.5-sunburst", "1024x1536", "high", 3)
    assert e2["observed"] and e2["tokens"]["image_out"] == 8000


def test_input_fidelity_is_omitted_when_none(monkeypatch):
    """The 2.5 models REJECT input_fidelity (invalid_input_fidelity_model), so an
    unused default must not travel with the request. Sending it is the whole bug:
    the first real pilot paused on it."""
    import sys
    import types

    sent = {}

    class FakeImages:
        def __init__(self):
            self.with_raw_response = self

        def edit(self, **kwargs):
            sent.update(kwargs)
            raise RuntimeError("stop after capturing the kwargs")

    class FakeOpenAI:
        def __init__(self, **_):
            self.images = FakeImages()

    fake = types.ModuleType("openai")
    fake.OpenAI = FakeOpenAI
    for name in ("AuthenticationError", "RateLimitError", "BadRequestError", "APIConnectionError",
                 "APITimeoutError", "InternalServerError", "NotFoundError"):
        setattr(fake, name, type(name, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "openai", fake)

    from app.client import ApiError, RealClient
    from app.config import DEFAULT_SETTINGS, NO_INPUT_FIDELITY

    ref = ROOT / "static" / "index.html"  # any real file; only its bytes are read
    base = {"model": "gpt-image-2.5-sunburst", "size": "1024x1536", "quality": "low"}

    for fidelity in (None, "", "none"):
        sent.clear()
        with pytest.raises(ApiError):
            RealClient("sk-test").edit("p", [ref], {**base, "input_fidelity": fidelity})
        assert "input_fidelity" not in sent, f"sent with input_fidelity={fidelity!r}"

    sent.clear()
    with pytest.raises(ApiError):
        RealClient("sk-test").edit("p", [ref], {**base, "input_fidelity": "high"})
    assert sent["input_fidelity"] == "high", "an explicit choice must still be sent"

    # The shipped default must not be one the default model rejects.
    assert DEFAULT_SETTINGS["model"] in NO_INPUT_FIDELITY
    assert DEFAULT_SETTINGS["input_fidelity"] == "none"


def test_quality_goes_in_the_filename(env):
    """Two pilots of the same shot must be able to share one folder."""
    from app.runs import create_run, quality_suffixed

    assert quality_suffixed("cat_shot_001.png", "medium") == "cat_shot_001_med.png"
    assert quality_suffixed("cat_shot_001.png", "low") == "cat_shot_001_low.png"
    assert quality_suffixed("cat_shot_001.png", "xhigh") == "cat_shot_001_xhigh.png"
    assert quality_suffixed("cat_shot_001.png", None) == "cat_shot_001.png"

    shots = [{"id": "shot_001", "filename": "cat_shot_001.png", "prompt": "p"}]
    # env["outputs"] is NOT optional: without it create_run writes into the real
    # outputs folder and leaves junk runs beside Jeremy's actual pilots.
    low = create_run("cat", "pilot-low", {"quality": "low"}, [], shots, None, {}, env["outputs"])
    med = create_run("cat", "pilot-med", {"quality": "medium"}, [], shots, None, {}, env["outputs"])
    assert low["shots"][0]["filename"] == "cat_shot_001_low.png"
    assert med["shots"][0]["filename"] == "cat_shot_001_med.png"
