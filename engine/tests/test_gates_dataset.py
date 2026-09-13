"""Dataset gate: the pure evaluator against the exact failures that cost us five LoRAs,
plus the walker driven by an injected measurer so no InsightFace is needed.
"""

import numpy as np
import pytest
from PIL import Image

from sourcemode.gates.dataset import (
    DatasetGateError,
    DatasetMeasurements,
    FaceMetrics,
    evaluate,
    gate_dataset,
    measure_dataset,
)


def emb(seed: int, spread: float = 0.05):
    """A unit vector near a shared centre; spread controls how different it is."""
    rng = np.random.default_rng(seed)
    v = np.ones(64) + spread * rng.standard_normal(64)
    return v / np.linalg.norm(v)


def good(n: int = 12) -> DatasetMeasurements:
    return DatasetMeasurements(
        faces=[FaceMetrics(f"img_{i:02d}.png", 420, -20 + i * 4, emb(i, 0.35)) for i in range(n)],
        captions={f"img_{i:02d}.png": f"char_ch, wearing outfit number {i} on a balcony at dusk, "
                                      f"turned to the left, laughing at something off camera"
                  for i in range(n)},
        n_images=n, bucket_px=1024, render_size=(1024, 1024),
    )


def checks(report):
    return {f["check"]: f["passed"] for f in report["findings"]}


def test_a_healthy_dataset_passes_every_check():
    r = evaluate(good(), trigger="char_ch")
    assert r["passed"] and r["failed"] == [] and r["score"] == 1.0


def test_catches_the_face_resolution_failure_that_broke_the_loras():
    m = good()
    for f in m.faces:                      # what priyanka's set actually looked like
        f.face_px = 180
    r = evaluate(m, trigger="char_ch")
    assert not r["passed"] and "face_resolution" in r["failed"]
    detail = next(f["detail"] for f in r["findings"] if f["check"] == "face_resolution")
    assert "180px" in detail and "22px in latent" in detail


def test_catches_tiny_faces_even_when_the_median_is_fine():
    m = good(12)
    for f in m.faces[:6]:
        f.face_px = 90
    r = evaluate(m, trigger="char_ch")
    assert "tiny_faces" in r["failed"]


def test_catches_boilerplate_captions():
    m = good()
    m.captions = {k: "char_ch, the same woman as a close-up portrait, in a different setting"
                  for k in m.captions}
    r = evaluate(m, trigger="char_ch")
    assert "caption_variety" in r["failed"]
    assert checks(r)["caption_detail"] is True                  # long enough, just not unique


def test_catches_thin_captions_and_a_missing_trigger():
    m = good()
    m.captions = {k: f"char_ch, photo {i}" for i, k in enumerate(m.captions)}
    r = evaluate(m, trigger="char_ch")
    assert "caption_detail" in r["failed"]
    m.captions["img_00.png"] = "a woman on a balcony at dusk, turned to the left, laughing softly"
    assert "caption_trigger" in evaluate(m, trigger="char_ch")["failed"]


def test_catches_self_identical_pairs():
    m = good()
    m.self_pair_names = ["img_00.png", "img_01.png"]
    r = evaluate(m, trigger="char_ch")
    assert "self_pairs" in r["failed"]
    assert "reproduce the input face unchanged" in next(
        f["detail"] for f in r["findings"] if f["check"] == "self_pairs")


def test_catches_sunnys_frontal_only_angle_spread():
    m = good()
    for i, f in enumerate(m.faces):
        f.yaw_deg = -6 + i * 0.5                                # ~6 degrees, as sunny's set was
    r = evaluate(m, trigger="char_ch")
    assert "angle_spread" in r["failed"]


def test_catches_a_different_person_and_a_too_homogeneous_set():
    m = good()
    m.faces[3].embedding = -m.faces[3].embedding                # nothing like the rest
    r = evaluate(m, trigger="char_ch")
    assert "identity_coherence" in r["failed"] and "img_03.png" in next(
        f["detail"] for f in r["findings"] if f["check"] == "identity_coherence")

    same = DatasetMeasurements(
        faces=[FaceMetrics(f"i{i}.png", 420, -20 + i * 4, emb(0, 0.0)) for i in range(10)],
        captions={f"i{i}.png": f"char_ch, outfit {i} on a balcony at dusk, turned left, laughing"
                  for i in range(10)}, n_images=10)
    r2 = evaluate(same, trigger="char_ch")
    assert "identity_variety" in r2["failed"] and "duplicates" in r2["failed"]


def test_catches_the_train_render_resolution_mismatch():
    m = good()
    m.render_size = (1024, 1536)                                # what we actually generate
    r = evaluate(m, trigger="char_ch")
    assert "resolution_match" in r["failed"]
    m.bucket_px = 1536
    assert checks(evaluate(m, trigger="char_ch"))["resolution_match"] is True


def test_reports_images_with_no_detectable_face():
    m = good()
    m.no_face = ["img_99.png"]
    assert "face_detected" in evaluate(m, trigger="char_ch")["failed"]


def test_measure_dataset_walks_dirs_captions_and_self_pairs(tmp_path):
    idir = tmp_path / "image_dir"; cdir = tmp_path / "control_dir"
    idir.mkdir(); cdir.mkdir()
    for i in range(3):
        im = Image.new("RGB", (800, 1200), (i * 40, 60, 90))
        im.save(idir / f"p{i}.png")
        (idir / f"p{i}.txt").write_text(f"char_ch, look {i} in a kitchen, three-quarter view", encoding="utf-8")
        # p0's control is a copy of its target -> a self pair; the others differ
        (im if i == 0 else Image.new("RGB", (800, 1200), (255, 255, 255))).save(cdir / f"p{i}.png")
    (idir / "nofacehere.png").parent.mkdir(exist_ok=True)
    Image.new("RGB", (800, 1200), (1, 2, 3)).save(idir / "nofacehere.png")

    def fake(path, bucket_px):
        assert bucket_px == 1024
        if "noface" in path.name:
            return None
        return FaceMetrics(path.name, 400, 10.0, emb(hash(path.name) % 99, 0.3))

    m = measure_dataset(tmp_path, render_size=(1024, 1024), measure_face=fake)
    assert m.n_images == 4 and len(m.faces) == 3 and m.no_face == ["nofacehere.png"]
    assert m.self_pair_names == ["p0.png"]
    assert len(m.captions) == 3                                  # the no-face image has none
    r = evaluate(m, trigger="char_ch")
    assert "self_pairs" in r["failed"] and "face_detected" in r["failed"]


def test_gate_dataset_annotates_by_default_and_blocks_only_when_asked(tmp_path):
    idir = tmp_path / "image_dir"; idir.mkdir()
    Image.new("RGB", (400, 600), (10, 20, 30)).save(idir / "a.png")
    (idir / "a.txt").write_text("char_ch, a short one", encoding="utf-8")

    def fake(path, bucket_px):
        return FaceMetrics(path.name, 100, 0.0, None)

    report = gate_dataset(tmp_path, trigger="char_ch", measure_face=fake)
    assert report["passed"] is False and report["score"] < 1.0   # annotated, did not raise
    with pytest.raises(DatasetGateError) as e:
        gate_dataset(tmp_path, trigger="char_ch", block=True, measure_face=fake)
    assert "face_resolution" in str(e.value)
    assert e.value.report["failed"]


def test_a_dataset_with_no_captions_at_all_fails_loudly():
    """Every caption check lives behind `if caps`, so an uncaptioned set once passed
    them all by silence. It must fail instead."""
    m = good()
    m.captions = {}
    r = evaluate(m, trigger="char_ch")
    assert "caption_present" in r["failed"]
    assert "12 of 12" in next(f["detail"] for f in r["findings"] if f["check"] == "caption_present")


def test_partially_captioned_dataset_fails_caption_present():
    m = good()
    m.captions.pop("img_00.png")
    assert "caption_present" in evaluate(m, trigger="char_ch")["failed"]


def test_angle_range_alone_is_not_enough_coverage():
    """priyanka's curated 33 spanned 34 deg on THREE off-axis images and passed the
    range check. Coverage must count how many images are actually turned."""
    m = good(33)
    for i, f in enumerate(m.faces):
        f.yaw_deg = -17.0 if i == 0 else (14.0 if i == 1 else (-12.0 if i == 2 else 0.0 + i * 0.1))
    r = evaluate(m, trigger="char_ch")
    assert checks(r)["angle_spread"] is True            # range 31 deg -- passes on outliers
    assert "angle_coverage" in r["failed"]              # but only 3/33 are turned
    assert "3/33" in next(f["detail"] for f in r["findings"] if f["check"] == "angle_coverage")


def test_a_genuinely_varied_set_passes_coverage():
    m = good(20)
    for i, f in enumerate(m.faces):
        f.yaw_deg = -40 + i * 4                          # gabi-like spread
    r = evaluate(m, trigger="char_ch")
    assert checks(r)["angle_coverage"] is True and r["passed"]


def test_no_upscale_reports_the_face_size_actually_trained(tmp_path):
    """bucket_no_upscale means a 1024 crop is never blown up to a 1536 bucket, so
    the gate must not report the upscaled width (gabi read 597px, trains at 398)."""
    from sourcemode.gates.dataset import _insightface_measurer
    import sourcemode.gates.dataset as ds

    idir = tmp_path / "image_dir"; idir.mkdir()
    Image.new("RGB", (1024, 1024), (30, 30, 30)).save(idir / "a.png")
    (idir / "a.txt").write_text("char_ch, a caption long enough to pass the detail check here ok", encoding="utf-8")
    seen = {}

    class FakeFace:
        bbox = (0, 0, 400.0, 500.0)
        pose = (0.0, 0.0, 0.0)
        normed_embedding = emb(1, 0.3)

    class FakeApp:
        def get(self, arr):
            seen["w"] = arr.shape[1]          # the width the trainer would see
            return [FakeFace()]

    ds._get_face_app = lambda: FakeApp()      # noqa: SLF001
    import sourcemode.gates.identity as ident
    ident._get_face_app = lambda: FakeApp()   # noqa: SLF001

    measure_dataset(tmp_path, bucket_px=1536, no_upscale=True,
                    measure_face=_insightface_measurer(no_upscale=True))
    assert seen["w"] == 1024                  # not upscaled to 1536
    measure_dataset(tmp_path, bucket_px=1536, no_upscale=False,
                    measure_face=_insightface_measurer(no_upscale=False))
    assert seen["w"] == 1536                  # upscaled when the TOML allows it
