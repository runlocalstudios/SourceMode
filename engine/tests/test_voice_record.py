"""Her voice record and the Characters-tab voice routes (2026-10-14).

Jeremy: "once I pick a voice for each character or create one, can those be
loaded into the characters screen as well?" and "There must be some way to
actually create these from scratch". No model runs here: the record, the set
listing and the queue route are exercised on files.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from sourcemode.voice import record as R


def _wav(p: Path, seconds: float = 0.1) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"\0\0" * int(8000 * seconds))
    return p


def test_the_record_round_trips_and_refuses_a_clip_that_is_not_there(tmp_path: Path):
    vj = tmp_path / "voices.json"
    assert R.get("amanda", vj) is None
    clip = _wav(tmp_path / "take_01.wav")
    rec = R.set_voice("Amanda", reference=clip, description="bright", model="parler", seed=1200, path=vj)
    assert rec["reference"] == str(clip) and rec["chosen_at"]
    got = R.get("amanda", vj)
    assert got["description"] == "bright" and got["on_disk"] is True
    with pytest.raises(FileNotFoundError):
        R.set_voice("amanda", reference=tmp_path / "nope.wav", path=vj)
    assert json.loads(vj.read_text())["_comment"]
    assert R.clear("amanda", vj) is True and R.get("amanda", vj) is None
    assert R.clear("amanda", vj) is False


def test_takes_list_her_voice_sets_with_clones_and_legacy_candidates(tmp_path: Path):
    lib = tmp_path / "lib"
    d = lib / "jojo" / "2026-10-14_voice_bright"
    (d).mkdir(parents=True)
    (d / "spec.json").write_text(json.dumps({"takes": 2, "description": "bright"}))
    _wav(d / "take_01.wav"); (d / "take_01.json").write_text(json.dumps({"seed": 1200, "seconds": 14.2, "description": "bright"}))
    _wav(d / "take_01_chatterbox.wav")
    sets = R.takes(lib, "jojo")
    assert len(sets) == 1 and sets[0]["done"] is False
    t = sets[0]["takes"]
    assert len(t) == 1 and t[0]["seed"] == 1200 and t[0]["clone"].endswith("take_01_chatterbox.wav")
    _wav(d / "take_02.wav")
    assert R.takes(lib, "jojo")[0]["done"] is True and R.takes(lib, "jojo")[0]["takes"][1]["clone"] is None
    # the September candidates: ref_<voice>.wav with jojo_<voice>.wav beside it
    old = lib / "jojo" / "2026-10-12_voice_female-candidates"; old.mkdir()
    _wav(old / "ref_af_bella.wav"); _wav(old / "jojo_af_bella.wav"); _wav(old / "ref_af_sky.wav")
    sets = R.takes(lib, "jojo")
    legacy = next(s for s in sets if "candidates" in s["name"])
    assert [x["take"] for x in legacy["takes"]] == ["ref_af_bella", "ref_af_sky"]
    assert legacy["takes"][0]["clone"].endswith("jojo_af_bella.wav") and legacy["takes"][1]["clone"] is None
    assert R.takes(lib, "nobody") == []


def test_the_routes_make_one_job_and_record_the_pick(tmp_path: Path, monkeypatch):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from sourcemode.monitor.voice_page import make_command, voice_router

    lib = tmp_path / "lib"; out = tmp_path / "out"; out.mkdir()
    vj = tmp_path / "voices.json"
    monkeypatch.setattr("sourcemode.library.library_dir", lambda c: lib)
    monkeypatch.setattr("sourcemode.config.outputs_dir", lambda c: out)
    monkeypatch.setattr("sourcemode.gpu.preflight.preflight", lambda job, o, prev=None: [])
    monkeypatch.setattr(R, "VOICES", vj)
    app = FastAPI(); app.include_router(voice_router({"paths": {"outputs": str(out), "library": str(lib)}}))
    c = TestClient(app)
    assert c.get("/voices/amanda").json()["voice"] is None
    assert c.post("/voices/amanda/make", json={"description": "short"}).status_code == 400
    r = c.post("/voices/amanda/make", json={"description": "A young woman with a bright, breathy voice.", "takes": 2,
                                            "name": "bright"})
    assert r.status_code == 200, r.text
    d = Path(r.json()["set"])
    spec = json.loads((d / "spec.json").read_text(encoding="utf-8"))
    assert spec["takes"] == 2 and spec["description"].endswith(R.QUALITY_TAIL) and spec["text"] == R.REFERENCE_TEXT
    from sourcemode.gpu import queue as q
    job = q.find(q.load(q.queue_path(out)), r.json()["queued"])
    assert job["kind"] == "voice" and "make_voice_parler.py" in job["cmd"][-1] and "clone_check.py" in job["cmd"][-1]
    assert "parler-tts" in job["cmd"][-1] and "chatterbox-tts" in job["cmd"][-1]
    # the same name again, once takes exist, is refused rather than overwritten
    _wav(d / "take_01.wav")
    assert c.post("/voices/amanda/make", json={"description": "A young woman with a bright, breathy voice.", "name": "bright"}).status_code == 409
    # picking a take records it; a wav outside the library is refused
    (d / "take_01.json").write_text(json.dumps({"seed": 1200, "description": "bright", "model": "parler"}))
    r = c.post("/voices/amanda/use", json={"reference": str(d / "take_01.wav")})
    assert r.status_code == 200 and r.json()["voice"]["seed"] == 1200
    assert c.get("/voices/amanda").json()["voice"]["on_disk"] is True
    outside = _wav(tmp_path / "x.wav")
    assert c.post("/voices/amanda/use", json={"reference": str(outside)}).status_code == 404
    assert c.get("/voices/file", params={"path": str(d / "take_01.wav")}).status_code == 200
    assert c.get("/voices/file", params={"path": str(outside)}).status_code == 404
    assert c.post("/voices/amanda/clear").json()["cleared"] is True
    cmd = make_command(Path("C:/x"), Path("C:/lib/amanda/2026-10-14_voice_bright"))
    assert cmd[0] == "powershell.exe" and "--isolated" in cmd[-1]
