from pathlib import Path

from sourcemode.bootstrap.sheet import bootstrap_sheet
from sourcemode.gates.base import GateResult


class FakeRenderClient:
    def __init__(self, fail_slugs=()):
        self.fail_slugs = set(fail_slugs)
        self.calls = []

    def render_sheet_job(self, source, job, dest: Path) -> bool:
        self.calls.append(job["slug"])
        if job["slug"] in self.fail_slugs:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"png")
        return True


class ThresholdScorer:
    """Rejects any image whose slug contains 'profile' (stand-in for drift)."""

    def score(self, asset_path: Path, source) -> GateResult:
        if "profile" in asset_path.name:
            return GateResult(score=0.1, passed=False)
        return GateResult(score=0.9, passed=True)


def test_dry_run_prints_and_writes_nothing(tmp_cfg, chars_root, sample_source):
    lines = []
    summary = bootstrap_sheet(tmp_cfg, sample_source, chars_root, dry_run=True, log=lines.append)
    assert summary == {"jobs": 36, "rendered": 0, "rejected": 0, "dry_run": True}
    assert len(lines) == 36
    assert not (chars_root / "testchar" / "dataset").exists()


def test_render_writes_images_and_captions(tmp_cfg, chars_root, sample_source):
    client = FakeRenderClient()
    summary = bootstrap_sheet(
        tmp_cfg, sample_source, chars_root, client=client, scorer=None,
        dry_run=False, gates_enabled=False, log=lambda *_: None,
    )
    assert summary["rendered"] == 36
    dataset = chars_root / "testchar" / "dataset"
    pngs = list(dataset.glob("*.png"))
    txts = list(dataset.glob("*.txt"))
    assert len(pngs) == 36 and len(txts) == 36
    caption = txts[0].read_text(encoding="utf-8")
    assert caption.startswith(sample_source.trigger_token)


def test_gate_moves_drifters_to_rejected(tmp_cfg, chars_root, sample_source):
    summary = bootstrap_sheet(
        tmp_cfg, sample_source, chars_root, client=FakeRenderClient(), scorer=ThresholdScorer(),
        dry_run=False, gates_enabled=True, log=lambda *_: None,
    )
    dataset = chars_root / "testchar" / "dataset"
    rejected = dataset / "_rejected"
    # 9 views x 2 expr x 2 light; the two profile views (left/right) => 8 jobs
    assert summary["rejected"] == 8
    assert len(list(rejected.glob("*.png"))) == 8
    assert len(list(rejected.glob("*.txt"))) == 8
    # kept images do not include profiles
    assert not [p for p in dataset.glob("*.png") if "profile" in p.name]


def test_gates_disabled_keeps_everything(tmp_cfg, chars_root, sample_source):
    summary = bootstrap_sheet(
        tmp_cfg, sample_source, chars_root, client=FakeRenderClient(), scorer=ThresholdScorer(),
        dry_run=False, gates_enabled=False, log=lambda *_: None,
    )
    assert summary["rejected"] == 0
