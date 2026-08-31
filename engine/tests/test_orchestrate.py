import json
from pathlib import Path

import yaml

from sourcemode.gates.base import GateResult
from sourcemode.orchestrate.run import run_scene
from sourcemode.prompts.decompose import RuleBasedDecomposer

BRIEF = "Gwen walks slowly through a rainy neon market, worried, camera tracks from behind"


def test_dry_run_writes_scene_and_workflows(tmp_cfg, chars_root, sample_source, tmp_path):
    outputs = tmp_path / "outputs"
    results = run_scene(
        tmp_cfg, sample_source, chars_root, outputs, BRIEF, RuleBasedDecomposer(),
        render_pass="draft", dry_run=True, gates_enabled=False, log=lambda *_: None,
    )
    scene_path = Path(results["scene"])
    assert scene_path.exists()
    scene = yaml.safe_load(scene_path.read_text(encoding="utf-8"))
    assert scene["character_id"] == "testchar"
    assert len(scene["shots"]) == 1
    shot = scene["shots"][0]
    assert shot["prompt_hash"]
    assert sample_source.trigger_token in shot["keyframe_prompt"]
    assert "slowly" in shot["video_prompt"]
    assert shot["negative"] == sample_source.negative_block

    shot_dir = scene_path.parent / "shot_00"
    workflows = sorted(shot_dir.glob("*.workflow.json"))
    assert len(workflows) == 5  # 4 keyframe candidates + 1 video
    for wf in workflows:
        assert "{{" not in wf.read_text(encoding="utf-8")

    results_file = scene_path.parent / "results.yaml"
    assert results_file.exists()
    assert yaml.safe_load(results_file.read_text())["dry_run"] is True


class FakeClient:
    """Mocked ComfyUI: every render 'produces' a file; upload echoes a name."""

    def __init__(self):
        self.submitted = []
        self.counter = 0

    def submit(self, workflow):
        self.submitted.append(workflow)
        self.counter += 1
        return f"pid-{self.counter}"

    def wait(self, prompt_id):
        return {"status": {"status_str": "success"},
                "outputs": {"60": {"images": [{"filename": f"{prompt_id}.png", "subfolder": "", "type": "output"}]}}}

    def outputs(self, entry):
        for node in entry["outputs"].values():
            return node["images"]
        return []

    def fetch(self, desc, dest: Path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"artifact:" + desc["filename"].encode())
        return dest

    def upload_image(self, path: Path) -> str:
        return f"uploaded/{Path(path).name}"


class SeedScorer:
    """Fake identity scorer: candidate 2 always wins; frames score high."""

    def __init__(self):
        self.scored = []

    def score(self, asset_path: Path, source) -> GateResult:
        self.scored.append(Path(asset_path).name)
        name = Path(asset_path).name
        if "c2" in name:
            return GateResult(score=0.95, passed=True)
        return GateResult(score=0.5, passed=True)


def test_full_flow_with_mocked_client_and_gates_unavailable(tmp_cfg, chars_root, sample_source, tmp_path):
    """Live-shaped flow, but scorer unavailable: first candidate wins, no gate block."""
    results = run_scene(
        tmp_cfg, sample_source, chars_root, tmp_path / "out", BRIEF, RuleBasedDecomposer(),
        render_pass="draft", client=FakeClient(), scorer=None,
        dry_run=False, gates_enabled=False, log=lambda *_: None,
    )
    shot = results["shots"][0]
    assert shot["keyframe"].endswith("keyframe_c0.png")  # first candidate
    assert shot["video"] is not None
    # sidecars written for keyframes and video
    video = Path(shot["video"])
    assert (video.parent / (video.name + ".yaml")).exists()


def test_full_flow_with_fake_scorer_picks_best(tmp_cfg, chars_root, sample_source, tmp_path, monkeypatch):
    scorer = SeedScorer()
    # calibrated threshold so the video gate produces a pass/fail verdict
    calibrated = sample_source.model_copy(update={"identity_threshold": 0.4})
    # video gate: skip real ffmpeg by faking frame extraction
    monkeypatch.setattr(
        "sourcemode.gates.video.extract_frames",
        lambda video, out, stride, **k: [video],  # score the artifact itself as one 'frame'
    )
    results = run_scene(
        tmp_cfg, calibrated, chars_root, tmp_path / "out", BRIEF, RuleBasedDecomposer(),
        render_pass="draft", client=FakeClient(), scorer=scorer,
        dry_run=False, gates_enabled=True, log=lambda *_: None,
    )
    shot = results["shots"][0]
    assert shot["keyframe"].endswith("keyframe_c2.png")  # best score wins
    assert shot["gate"]["score"] == 0.5
    assert shot["gate"]["passed"] is True

    # candidates carry their scores in results.yaml
    scores = [c["score"] for c in shot["candidates"]]
    assert scores == [0.5, 0.5, 0.95, 0.5]
