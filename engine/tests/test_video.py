"""The Video tab's module: legs, the still, the chain, keepers, the queue route.

Jeremy, 2026-10-14: "We never set up the video capability to create from an
existing asset or to generate a new T2I then animate?" Everything here runs
without a GPU, ffmpeg or ComfyUI: the chain is exercised through fakes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from sourcemode import video as V


def test_legs_split_evenly_and_never_exceed_the_cap():
    assert V.legs_for(5, 6.0) == [5.0]
    assert V.legs_for(6, 6.0) == [6.0]
    assert V.legs_for(8, 6.0) == [4.0, 4.0]            # never a 6 and a 2
    assert V.legs_for(12, 6.0) == [6.0, 6.0]
    assert V.legs_for(15, 6.0) == [5.0, 5.0, 5.0]
    assert V.leg_cap_seconds({"video": {"fps": 24, "max_frames": 145}}) == 6.0
    assert V.leg_cap_seconds({"video": {"fps": 16, "max_frames": 81}}) == 5.0


def test_validate_names_every_problem_in_plain_words(tmp_path: Path):
    bad = V.VideoSpec(character="", motion="", seconds=99, quality="ultra", takes=0, source={})
    p = V.validate(bad, leg_cap_s=6.0)
    assert len(p) == 6 and any("character" in x for x in p) and any("motion" in x for x in p)
    keeper = tmp_path / "k.png"; Image.new("RGB", (8, 12)).save(keeper)
    good = V.VideoSpec(character="amanda", motion="she smiles", source={"kind": "keeper", "path": str(keeper)})
    assert V.validate(good, leg_cap_s=6.0) == []
    gone = V.VideoSpec(character="amanda", motion="x", source={"kind": "keeper", "path": str(tmp_path / "no.png")})
    assert V.validate(gone, leg_cap_s=6.0) == ["the keeper is not on disk"]
    still = V.VideoSpec(character="amanda", motion="x", source={"kind": "still", "outfit": "", "framing": "feet"})
    assert len(V.validate(still, leg_cap_s=6.0)) == 2


def test_cost_counts_the_still_and_every_take():
    s = V.VideoSpec(character="a", motion="m", seconds=6, quality="medium", takes=2,
                    source={"kind": "still", "outfit": "x"})
    assert V.estimate_seconds(s) == V.STILL_SECONDS + 100.0 * 6 * 2
    s.source = {"kind": "keeper", "path": "x"}
    assert V.estimate_seconds(s) == 1200.0


def test_the_still_is_bucketed_by_centre_crop(tmp_path: Path):
    src = tmp_path / "src.png"; Image.new("RGB", (1024, 1536), (90, 10, 10)).save(src)
    out = tmp_path / "source.png"
    assert V.normalize_source(src, out, 1024, 1280) == (1024, 1280)
    assert Image.open(out).size == (1024, 1280)
    slot = V.still_slot(V.VideoSpec(character="a", motion="m", source={"kind": "still", "outfit": "a red dress",
                                                                        "framing": "chest", "setting": "a cafe"}))
    assert slot["framing_natural"] == "framed from the chest up" and slot["outfit"] == "a red dress"
    assert slot["turn"] == "front" and slot["setting"] == "a cafe"


def test_stitch_drops_the_seam_frame_of_every_leg_after_the_first(tmp_path: Path):
    legs = [tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "c.mp4"]
    args = V.stitch_args(legs, tmp_path / "out.mp4", 24, ffmpeg="ffmpeg")
    fc = args[args.index("-filter_complex") + 1]
    assert fc.startswith("[0:v]null[v0];[1:v]select='gte(n,1)'")
    assert "concat=n=3:v=1:a=0[out]" in fc and args[-1].endswith("out.mp4") and "-r" in args
    assert V.video_output([{"filename": "x.png"}, {"filename": "take.mp4", "type": "output"}])["filename"] == "take.mp4"
    assert V.video_output([{"filename": "x.png"}]) is None
    # a leg handed off before its end is cut there
    fc = V.stitch_args(legs[:2], tmp_path / "o.mp4", 24, ffmpeg="ffmpeg", keep=[115, None])
    fc = fc[fc.index("-filter_complex") + 1]
    assert fc.startswith("[0:v]select='lt(n,115)',setpts=N/FRAME_RATE/TB[v0];[1:v]select='gte(n,1)',")


def test_the_handoff_is_the_sharpest_of_the_last_frames(tmp_path: Path):
    import shutil
    import subprocess

    import numpy as np

    ff = V.ffmpeg_exe({"video": {}}) or shutil.which("ffmpeg")
    if not ff:
        pytest.skip("no ffmpeg")
    d = tmp_path / "f"; d.mkdir()
    rng = np.random.default_rng(0)
    for i in range(24):   # one sharp frame, 3 from the end, among flat ones
        a = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8) if i == 20 else np.full((64, 64, 3), 128, np.uint8)
        Image.fromarray(a).save(d / f"{i:03d}.png")
    clip = tmp_path / "c.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", "24", "-i", str(d / "%03d.png"),
                    "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv444p", str(clip)], check=True)
    assert V.sharpest_tail_frame(clip, tmp_path / "h.png", ffmpeg=ff) == 3
    assert (tmp_path / "h.png").is_file()


class FakeClient:
    """Enough of ComfyUIClient for a take: records uploads, hands back a 'video'."""
    def __init__(self, tmp: Path):
        self.tmp, self.uploads, self.submitted = tmp, [], []

    def upload_image(self, p):
        self.uploads.append(Path(p).name); return f"up/{Path(p).name}"

    def submit(self, wf):
        self.submitted.append(wf); return f"p{len(self.submitted)}"

    def wait(self, pid, timeout_s=0):
        return {"outputs": {"64": {"images": [{"filename": f"{pid}.mp4", "type": "output"}]}}}

    def outputs(self, entry):
        return [f for o in entry["outputs"].values() for f in o["images"]]

    def fetch(self, desc, dest):
        Path(dest).write_bytes(b"mp4"); return dest


def _cfg(tmp_path: Path) -> dict:
    return {"video": {"width": 64, "height": 80, "fps": 24, "max_frames": 145, "shift": 8.0,
                      "lora_strength": 0.6},
            "render": {"medium": {"steps": 4, "cfg": 1.0, "wan_lightning_high": "", "wan_lightning_low": ""}},
            "models": {"wan_i2v_high_fp8": "h.safetensors", "wan_i2v_low_fp8": "l.safetensors",
                       "umt5": "t5", "wan_vae": "vae"},
            "paths": {"workflows": str(Path(__file__).resolve().parents[2] / "workflows")}}


def test_a_chained_take_runs_each_leg_from_the_matched_last_frame(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(V, "ffmpeg_exe", lambda cfg=None: "ffmpeg")
    calls = {"extract": [], "match": [], "stitch": []}
    def fake_extract(video, dest, *, ffmpeg, n=8, run=None):
        calls["extract"].append(video.name); Image.new("RGB", (64, 80)).save(dest); return 0
    def fake_match(frame, ref, dest):
        calls["match"].append((frame.name, ref.name)); Image.new("RGB", (64, 80)).save(dest)
    def fake_stitch(legs, dest, fps, *, ffmpeg, keep=None, run=None):
        calls["stitch"].append([l.name for l in legs]); dest.write_bytes(b"final")
    monkeypatch.setattr(V, "sharpest_tail_frame", fake_extract)
    monkeypatch.setattr(V, "color_match", fake_match)
    monkeypatch.setattr(V, "stitch", fake_stitch)
    src = tmp_path / "source.png"; Image.new("RGB", (64, 80)).save(src)
    out = tmp_path / "set"; out.mkdir()
    spec = V.VideoSpec(character="amanda", motion="she smiles", seconds=10, quality="medium",
                       source={"kind": "keeper", "path": str(src)})
    client = FakeClient(tmp_path)
    rec = V.render_take(cfg, client, spec, src, out, take=1, seed=100, log=lambda s: None)
    assert len(rec["legs"]) == 2 and rec["legs"][0]["frames"] == 117 and rec["legs"][1]["seed"] == 102   # 5 s at 24 fps snaps to 4n+1
    # leg 2 starts from leg 1's last frame, matched against the ORIGINAL source
    assert client.uploads == ["source.png", "take_01_leg_02_start.png"]
    assert calls["match"] == [("take_01_leg_01_last.png", "source.png")]
    assert calls["stitch"] == [["take_01_leg_01.mp4", "take_01_leg_02.mp4"]]
    assert (out / "take_01.mp4").read_bytes() == b"final"
    assert json.loads((out / "take_01.json").read_text())["seconds"] == pytest.approx((117 * 2 - 1) / 24, 0.01)
    # every leg carries the same pacing clause
    for wf in client.submitted:
        texts = [v["inputs"]["text"] for v in wf.values() if v.get("class_type") == "CLIPTextEncode"]
        assert any(V.PACING in t and "she smiles" in t for t in texts)
    # a single leg writes the take straight, no stitch
    spec.seconds = 5
    rec = V.render_take(cfg, client, spec, src, out, take=2, seed=200, log=lambda s: None)
    assert len(rec["legs"]) == 1 and calls["stitch"] == [["take_01_leg_01.mp4", "take_01_leg_02.mp4"]]
    assert (out / "take_02.mp4").is_file()


def test_keepers_are_her_judged_keeps_newest_first_and_clips_list_her_sets(tmp_path: Path):
    from sourcemode.assets.judge import make_set, record_verdict
    root = tmp_path / "judge"
    img = []
    for i in range(3):
        p = tmp_path / f"s{i}.png"; Image.new("RGB", (8, 8)).save(p); img.append(p)
    items = [{"id": f"i{i}", "path": p, "arm": "a", "group": str(i)} for i, p in enumerate(img)]
    make_set(root, "shoot_amanda_club", "Amanda - Club", items, meta={"character": "amanda"})
    make_set(root, "shoot_other", "Other", items, meta={"character": "mei"})
    record_verdict(root, "shoot_amanda_club", "i0", "keep")
    record_verdict(root, "shoot_amanda_club", "i1", "reject")
    record_verdict(root, "shoot_amanda_club", "i2", "keep")
    record_verdict(root, "shoot_other", "i1", "keep")
    k = V.keepers(root, "amanda")
    assert {x["item"] for x in k} == {"i0", "i2"} and all(x["set"] == "shoot_amanda_club" for x in k)
    assert V.keepers(root, "nobody") == []
    lib = tmp_path / "lib"; d = lib / "amanda" / "2026-10-14_video_smile"; d.mkdir(parents=True)
    (d / "spec.json").write_text(json.dumps({"takes": 2, "seconds": 5, "motion": "she smiles"}))
    (d / "take_01.mp4").write_bytes(b"x")
    (d / "take_01.json").write_text(json.dumps({"seconds": 5.0, "seed": 1100, "legs": [{}]}))
    c = V.clips(lib, "amanda")
    assert len(c) == 1 and c[0]["takes"][0]["seed"] == 1100 and c[0]["done"] is False
    (d / "take_02.mp4").write_bytes(b"x")
    assert V.clips(lib, "amanda")[0]["done"] is True


def test_the_queue_route_validates_and_writes_one_job(tmp_path: Path, monkeypatch):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from sourcemode.monitor.video_page import video_router

    lib = tmp_path / "lib"; (lib / "amanda").mkdir(parents=True)
    keeper = lib / "amanda" / "k.png"; Image.new("RGB", (8, 12)).save(keeper)
    cfg = {**_cfg(tmp_path), "paths": {"outputs": str(tmp_path / "out"), "library": str(lib),
                                       "judge": str(tmp_path / "out" / "judge")}}
    monkeypatch.setattr("sourcemode.library.library_dir", lambda c: lib)
    monkeypatch.setattr("sourcemode.config.outputs_dir", lambda c: tmp_path / "out")
    monkeypatch.setattr("sourcemode.gpu.preflight.preflight", lambda job, out, prev=None: [])
    app = FastAPI(); app.include_router(video_router(cfg))
    c = TestClient(app)
    assert c.post("/video/queue", json={"character": "amanda", "motion": "", "source": {}}).status_code == 400
    r = c.post("/video/queue", json={"character": "amanda", "motion": "she smiles", "seconds": 5,
                                     "quality": "medium", "takes": 2,
                                     "source": {"kind": "keeper", "path": str(keeper)}})
    assert r.status_code == 200, r.text
    jid = r.json()["queued"]
    from sourcemode.gpu import queue as q
    doc = q.load(q.queue_path(tmp_path / "out"))
    job = q.find(doc, jid)
    assert job["kind"] == "video" and job["cmd"][1].endswith("run_video.py") and job["cmd"][2].endswith(".json")
    spec = json.loads(Path(job["cmd"][2]).read_text(encoding="utf-8"))
    assert spec["takes"] == 2 and spec["source"]["kind"] == "keeper"
    # a keeper outside the library and outputs is refused
    outside = tmp_path / "x.png"; Image.new("RGB", (8, 8)).save(outside)
    r = c.post("/video/queue", json={"character": "amanda", "motion": "m", "source": {"kind": "keeper", "path": str(outside)}})
    assert r.status_code == 404
    assert c.get("/video/file", params={"path": str(outside)}).status_code == 404
    assert c.get("/video").status_code == 200 and "SourceMode video" in c.get("/video").text


def test_speech_frames_cover_the_line_and_the_s2v_graph_carries_the_voice(tmp_path: Path):
    # 3.3 s at 16 fps is 53.8 frames -> 57 (4n+1, rounded UP so she is never cut off)
    assert V.speech_frames(3.3) == 57
    assert V.speech_frames(4.75) == 77 and V.speech_frames(0.1) == 5
    assert V.speech_frames(7.5) == 121 and V.speech_frames(7.6) is None
    cfg = {"paths": {"workflows": str(Path(__file__).resolve().parents[2] / "workflows")},
           "models": {"wan_s2v_fp8": "s2v.safetensors", "umt5": "umt5.safetensors", "wan_vae": "vae.safetensors",
                      "wan_audio_encoder": "wav2vec.safetensors"}}
    nodes, settings = V.s2v_workflow(cfg, positive="she talks", negative="blurry", image_name="still.png",
                                     audio_name="line.wav", frames=97, seed=8100, prefix="video/amanda/s2v")
    by = {n["class_type"]: n for n in nodes.values()}
    assert by["UNETLoader"]["inputs"]["unet_name"] == "s2v.safetensors"
    assert by["WanSoundImageToVideo"]["inputs"]["length"] == 97
    assert by["WanSoundImageToVideo"]["inputs"]["width"] == 720 and by["WanSoundImageToVideo"]["inputs"]["height"] == 1280
    assert by["LoadAudio"]["inputs"]["audio"] == "line.wav"
    assert by["CreateVideo"]["inputs"]["audio"] == ["70", 0] and by["CreateVideo"]["inputs"]["fps"] == 16.0
    assert by["KSampler"]["inputs"]["seed"] == 8100 and by["KSampler"]["inputs"]["steps"] == 20
    assert settings["CFG"] == 6.0


def test_an_end_image_makes_a_first_last_frame_leg(tmp_path: Path):
    from sourcemode.render.passes import build_video_workflow

    cfg = _cfg(tmp_path)
    wf, s = build_video_workflow(cfg, "nadia", positive="p", negative="n", image_name="a.png",
                                 end_image_name="b.png", seed=1, render_pass="medium", duration_s=5)
    flf = [v for v in wf.values() if v.get("class_type") == "WanFirstLastFrameToVideo"]
    assert len(flf) == 1 and s["END_IMAGE"] == "b.png"
    images = {k: v["inputs"]["image"] for k, v in wf.items() if v.get("class_type") == "LoadImage"}
    assert images[flf[0]["inputs"]["start_image"][0]] == "a.png"
    assert images[flf[0]["inputs"]["end_image"][0]] == "b.png"
    wf, _ = build_video_workflow(cfg, "nadia", positive="p", negative="n", image_name="a.png",
                                 seed=1, render_pass="medium", duration_s=5)
    assert any(v.get("class_type") == "WanImageToVideo" for v in wf.values())


def test_every_story_names_photos_it_has():
    import glob
    for f in glob.glob(str(Path(__file__).resolve().parents[2] / "video-stories" / "*.json")):
        st = json.loads(Path(f).read_text(encoding="utf-8"))
        for i, s in enumerate(st["segments"]):
            # a chained leg after the first starts on the previous leg's last frame
            if i == 0 or not st.get("chain"):
                assert s["start"] in st["photos"], f
            assert not s.get("end") or s["end"] in st["photos"], f
            # 5.06 s at 16 fps is the model's 81 frames
            assert 1 <= float(s["seconds"]) <= 5.1, f
            if st.get("chain") and i:
                assert s.get("end") or st["segments"][i - 1].get("end"), f"{f}: two free legs in a row at {i + 1}"
        if st.get("voice"):
            assert V.script_beats(st.get("script", "")), f


def test_ramp_correct_removes_a_brightness_pulse_and_lands_on_the_end_key():
    """cheer_joi_v2's legs brightened +5..+13 then snapped at the next photo."""
    import cv2
    import numpy as np

    rng = np.random.default_rng(1)
    base = rng.integers(60, 160, (32, 32, 3)).astype(np.float32)
    start, end = base.astype(np.uint8), np.clip(base + 20, 0, 255).astype(np.uint8)
    # a leg that drifts 30 levels brighter than the blend by its middle
    frames = [np.clip(base + 20 * t + 30 * np.sin(np.pi * t), 0, 255).astype(np.uint8)
              for t in np.linspace(0, 1, 9)]

    def L(img):
        return cv2.cvtColor(img.astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)[:, :, 0].mean()

    out = V.ramp_correct(frames, start, end)
    want = [L(start) + (L(end) - L(start)) * t for t in np.linspace(0, 1, 9)]
    assert max(abs(L(f) - w) for f, w in zip(out, want)) < 0.5
    assert abs(L(out[-1]) - L(end)) < 0.5 and abs(L(out[0]) - L(start)) < 0.5
    # the uncorrected leg really did pulse
    assert max(abs(L(f) - w) for f, w in zip(frames, want)) > 5


def test_key_stills_and_test_renders_stay_out_of_the_clip_list(tmp_path: Path):
    home = tmp_path / "nadia"
    for name in ("2026-10-30_video_cheer-joi-v3-keys", "2026-10-31_video_cheer-joi-v3-test-move",
                 "2026-10-29_video_cheer-joi-v2"):
        (home / name).mkdir(parents=True)
    (home / "2026-10-30_video_cheer-joi-v3-keys" / "kneel_video.mp4").write_bytes(b"x")
    (home / "2026-10-31_video_cheer-joi-v3-test-move" / "spec.json").write_text("{}", encoding="utf-8")
    (home / "2026-10-31_video_cheer-joi-v3-test-move" / "take_01.mp4").write_bytes(b"x")
    (home / "2026-10-29_video_cheer-joi-v2" / "spec.json").write_text("{}", encoding="utf-8")
    (home / "2026-10-29_video_cheer-joi-v2" / "take_01.mp4").write_bytes(b"x")
    assert [s["name"] for s in V.clips(tmp_path, "nadia")] == ["2026-10-29_video_cheer-joi-v2"]
