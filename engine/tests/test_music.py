"""The Music tab (2026-11-02): places, takes, verdicts and the ship into the game.

No model runs here. Takes are fake mp3 files, ffmpeg is a stub, and the game repo
is a tmp folder - the one place this code writes into the real game is Ship, and
the test proves it writes only `src/assets/music/<place>.mp3`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from sourcemode.music import core as M

REPO_PLACES = M.places_path()


@pytest.fixture()
def mcfg(tmp_cfg, tmp_path, monkeypatch):
    tmp_cfg["paths"]["library"] = str(tmp_path / "library")
    pj = tmp_path / "places.json"
    shutil.copy(REPO_PLACES, pj)
    monkeypatch.setattr(M, "places_path", lambda: pj)
    return tmp_cfg


def _take(cfg, place_id: str, n: int, **meta) -> Path:
    d = M.place_dir(cfg, place_id)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"take_{n:04d}.mp3"
    f.write_bytes(b"ID3fake")
    f.with_suffix(".json").write_text(json.dumps({"seed": n, "model": "turbo", **meta}), encoding="utf-8")
    return f


def test_the_repo_places_cover_every_district_and_the_four_first_venues():
    ids = {p["id"] for p in M.places(REPO_PLACES)}
    assert {"district_flats", "district_midtown", "district_hill", "district_central",
            "tavern", "chillTrap", "obsidian", "foundersClub"} <= ids
    for p in M.places(REPO_PLACES):
        M.check_place_id(p["id"])
        assert p["keyscale"] in M.KEYS and 40 <= p["bpm"] <= 200 and 30 <= p["seconds"] <= 360
        assert "instrumental" in p["tags"] and "no vocals" in p["tags"]


def test_an_edit_moves_only_the_prompt_and_refuses_nonsense(mcfg):
    p = M.update_place("tavern", {"tags": "instrumental, pub blues, steady", "bpm": "100", "id": "evil", "label": "x"})
    assert p["bpm"] == 100 and p["id"] == "tavern" and p["label"] == "Pints Half Full"
    for bad in ({"bpm": 20}, {"seconds": 5}, {"keyscale": "H minor"}, {"tags": "short"}):
        with pytest.raises(ValueError):
            M.update_place("tavern", bad)
    with pytest.raises(KeyError):
        M.update_place("nowhere", {"bpm": 90})


def test_a_spec_freezes_the_prompt_and_the_job_command_is_built_from_the_engine(mcfg):
    spec = M.write_spec(mcfg, "obsidian", count=3, model="turbo", seed=500)
    doc = json.loads(spec.read_text(encoding="utf-8"))
    assert doc["count"] == 3 and doc["seed"] == 500 and doc["tags"] == M.place("obsidian")["tags"]
    M.update_place("obsidian", {"bpm": 124})
    assert json.loads(spec.read_text(encoding="utf-8"))["bpm"] == 120   # the queued job renders what was asked
    cmd = M.make_command(spec)
    assert cmd[1].endswith("make_takes.py") and Path(cmd[1]).is_file() and cmd[2] == str(spec)
    with pytest.raises(ValueError):
        M.write_spec(mcfg, "obsidian", count=9, model="turbo")
    with pytest.raises(ValueError):
        M.write_spec(mcfg, "obsidian", count=2, model="flux")


@pytest.mark.parametrize("model", sorted(M.MODELS))
def test_the_workflow_fills_every_placeholder(cfg, model):
    wf = M.build_workflow(cfg, model=model, tags="instrumental, test", seed=7, bpm=90, seconds=180,
                          keyscale="D minor", prefix="sourcemode/music/t")
    assert "{{" not in json.dumps(wf)
    assert wf["104"]["inputs"]["unet_name"] == M.MODELS[model]["file"]
    assert wf["3"]["inputs"]["steps"] == M.MODELS[model]["steps"]
    assert wf["94"]["inputs"]["lyrics"] == "[Instrumental]" and wf["98"]["inputs"]["seconds"] == 180.0
    assert wf["107"]["class_type"] == "SaveAudioMP3"


def test_render_numbers_after_the_takes_already_there(mcfg):
    _take(mcfg, "tavern", 1)
    spec = M.write_spec(mcfg, "tavern", count=2, model="turbo", seed=40)

    class Fake:
        submitted = []

        def submit(self, wf):
            self.submitted.append(wf)
            return "p"

        def wait(self, pid, timeout_s=0):
            return {}

        def outputs(self, entry):
            return [{"filename": "x.mp3"}]

        def fetch(self, desc, dest):
            dest.write_bytes(b"ID3")
            return dest

    fake = Fake()
    made = M.render_spec(mcfg, spec, client=fake, log=lambda m: None)
    assert [m.name for m in made] == ["take_0002.mp3", "take_0003.mp3"]
    assert [w["3"]["inputs"]["seed"] for w in fake.submitted] == [40, 41]
    assert json.loads(made[1].with_suffix(".json").read_text())["seed"] == 41


def test_verdicts_toggle_and_takes_list_newest_first(mcfg):
    _take(mcfg, "chillTrap", 1); _take(mcfg, "chillTrap", 2)
    assert [t["name"] for t in M.takes(mcfg, "chillTrap")] == ["take_0002", "take_0001"]
    M.set_verdict(mcfg, "chillTrap", "take_0001", "reject")
    assert M.takes(mcfg, "chillTrap")[1]["verdict"] == "reject"
    M.set_verdict(mcfg, "chillTrap", "take_0001", None)
    assert M.takes(mcfg, "chillTrap")[1]["verdict"] is None
    with pytest.raises(ValueError):
        M.set_verdict(mcfg, "chillTrap", "take_0001", "maybe")
    with pytest.raises(ValueError):
        M.take_path(mcfg, "chillTrap", "../../x")


def test_the_process_command_trims_and_levels_but_never_fades():
    cmd = M.process_command("ffmpeg", Path("a.mp3"), Path("b.mp3"))
    chain = cmd[cmd.index("-af") + 1]
    assert "silenceremove" in chain and f"loudnorm=I={M.TARGET_LUFS}" in chain and "afade" not in chain
    assert "libmp3lame" in cmd and cmd[-1] == "b.mp3"


def test_ship_writes_only_the_place_track_into_the_game(mcfg, tmp_path):
    _take(mcfg, "foundersClub", 1)
    game = tmp_path / "game"
    mcfg.setdefault("music", {})["ffmpeg"] = "ffmpeg"

    def run(cmd, **kw):
        Path(cmd[-1]).write_bytes(b"ID3processed")

        class R:
            returncode, stderr = 0, ""
        return R()

    rec = M.ship(mcfg, "foundersClub", "take_0001", game_root=game, run=run)
    files = [p.relative_to(game).as_posix() for p in game.rglob("*") if p.is_file()]
    assert files == ["src/assets/music/foundersClub.mp3"]
    assert rec["replaced"] is False and M.shipped(mcfg)["foundersClub"]["take"] == "take_0001"
    assert M.takes(mcfg, "foundersClub")[0]["verdict"] == "keep"
    assert M.ship(mcfg, "foundersClub", "take_0001", game_root=game, run=run)["replaced"] is True


def test_a_failed_ffmpeg_ships_nothing(mcfg, tmp_path):
    _take(mcfg, "tavern", 1)
    mcfg.setdefault("music", {})["ffmpeg"] = "ffmpeg"

    class R:
        returncode, stderr = 1, "boom"
    with pytest.raises(RuntimeError):
        M.ship(mcfg, "tavern", "take_0001", game_root=tmp_path / "game", run=lambda c, **k: R())
    assert not (tmp_path / "game").exists()


def test_the_routes(mcfg, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from sourcemode.monitor.music_page import music_router

    _take(mcfg, "obsidian", 1)
    c = TestClient((lambda a: (a.include_router(music_router(mcfg)), a)[1])(FastAPI()))
    assert "Music" in c.get("/music").text
    d = c.get("/music/places").json()
    ob = next(p for p in d["places"] if p["id"] == "obsidian")
    assert ob["takes"][0]["name"] == "take_0001" and ob["shipped"] is None and "turbo" in d["models"]
    assert c.get("/music/file", params={"place": "obsidian", "name": "take_0001"}).status_code == 200
    assert c.get("/music/file", params={"place": "nowhere", "name": "take_0001"}).status_code == 404
    assert c.post("/music/place/obsidian", json={"bpm": 10}).status_code == 400
    assert c.post("/music/obsidian/verdict", json={"name": "take_0001", "verdict": "keep"}).json()["verdict"] == "keep"
    r = c.post("/music/obsidian/make", json={"count": 2, "model": "turbo"})
    assert r.status_code == 200, r.text
    from sourcemode.config import outputs_dir
    from sourcemode.gpu import queue as q
    job = next(j for j in q.load(q.queue_path(outputs_dir(mcfg)))["jobs"] if j["id"] == r.json()["queued"])
    assert job["kind"] == "music" and job["lane"] == "gpu" and job["cmd"][-1] == r.json()["spec"]
