"""The Gallery tab: her clips first, then every photo set, newest first."""

from pathlib import Path

import pytest
from PIL import Image


def test_gallery_lists_clips_then_photo_sets(tmp_path: Path, monkeypatch):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from sourcemode.monitor.gallery_page import gallery_router

    lib = tmp_path / "lib"
    home = lib / "amanda"
    shoot = home / "2026-10-20_shoot_boudoir"; (shoot / "_web").mkdir(parents=True)
    Image.new("RGB", (8, 12)).save(shoot / "boudoir_00.png")
    Image.new("RGB", (8, 12)).save(shoot / "_web" / "boudoir_00_300.jpg")   # a thumbnail, not a photo
    sweep = home / "2026-10-22_sweep_v2-asset" / "ep19"; sweep.mkdir(parents=True)
    Image.new("RGB", (8, 12)).save(sweep / "s_00.png")
    vid = home / "2026-10-28_video_desk-toy"; vid.mkdir()
    (vid / "spec.json").write_text('{"takes": 1}', encoding="utf-8")
    (vid / "take_01.mp4").write_bytes(b"x")
    Image.new("RGB", (8, 12)).save(vid / "source_src.png")                  # the clip's input
    (home / "2026-10-27_voice_reference").mkdir()
    (lib / "loras").mkdir()
    monkeypatch.setattr("sourcemode.library.library_dir", lambda c: lib)
    app = FastAPI(); app.include_router(gallery_router({}))
    c = TestClient(app)

    assert [x["character"] for x in c.get("/gallery/characters").json()] == ["amanda"]
    m = c.get("/gallery/media", params={"character": "amanda"}).json()
    assert [Path(v["file"]).name for v in m["videos"]] == ["take_01.mp4"]
    assert [s["name"] for s in m["sets"]] == ["2026-10-22_sweep_v2-asset", "2026-10-20_shoot_boudoir"]
    assert [Path(p).name for p in m["sets"][1]["images"]] == ["boudoir_00.png"]
    assert c.get("/gallery/media", params={"character": "../x"}).status_code == 400
    assert "SourceMode gallery" in c.get("/gallery").text
