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
    def fake_extract(video, dest, *, ffmpeg, run=None):
        calls["extract"].append(video.name); Image.new("RGB", (64, 80)).save(dest)
    def fake_match(frame, ref, dest):
        calls["match"].append((frame.name, ref.name)); Image.new("RGB", (64, 80)).save(dest)
    def fake_stitch(legs, dest, fps, *, ffmpeg, run=None):
        calls["stitch"].append([l.name for l in legs]); dest.write_bytes(b"final")
    monkeypatch.setattr(V, "extract_last_frame", fake_extract)
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
