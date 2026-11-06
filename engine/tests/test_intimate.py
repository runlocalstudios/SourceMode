import json

import pytest
from PIL import Image

from sourcemode.assets import intimate as I
from sourcemode.assets import shoots as S

_REAL_RUN_SYNC = I.run_sync      # before the autouse fixture replaces it


@pytest.fixture(autouse=True)
def _no_npm(monkeypatch):
    """Never the game's npm from pytest: every ship sees a sync that succeeded."""
    monkeypatch.setattr(I, "run_sync", lambda game_root: {"ok": True, "cmd": "npm run sync:intimate",
                                                          "output": "wrote src/data/intimatePacks.js: 1 lingerie, 1 pajamas"})


def _world(tmp_path, monkeypatch, keep=("standing", "kneeling", "crawling"), shoot="lingerie"):
    """A library with a rendered lingerie shoot, a verdict file, and a game repo."""
    import sourcemode.assets.judge as J
    import sourcemode.library as L
    lib = tmp_path / "library"
    judge = tmp_path / "judge"
    d = lib / "nadia" / f"2026-10-29_shoot_{shoot}"
    d.mkdir(parents=True, exist_ok=True)      # a second call re-judges the same shoot
    plan = S.BY_ID[shoot].plan(character="nadia", outfit="x")
    verdicts = {}
    for s in plan:
        Image.new("RGB", (64, 96), "red").save(d / f"{s['id']}.png")
        verdicts[s["id"]] = "keep" if s["tag"] in keep else "reject"
    (judge / "verdicts").mkdir(parents=True, exist_ok=True)
    (judge / "verdicts" / f"shoot_nadia_{shoot}.json").write_text(json.dumps(verdicts), encoding="utf-8")
    monkeypatch.setattr(L, "library_dir", lambda cfg: lib)
    monkeypatch.setattr(J, "judge_root", lambda cfg: judge)
    # never the real matte in a test: BiRefNet is a model load
    import sourcemode.assets.cutout as C
    monkeypatch.setattr(C, "hybrid_remover", lambda: (lambda im: im.convert("RGBA")))
    return tmp_path / "outputs", tmp_path / "game"


def test_keepers_are_the_kept_shots_in_pose_order_with_their_chat_tags(tmp_path, monkeypatch):
    _world(tmp_path, monkeypatch)
    k = I.keepers({}, "nadia")
    assert [x["tag"] for x in k] == ["standing", "kneeling", "crawling"]
    assert all(x["path"].is_file() for x in k)


def test_nothing_rendered_or_judged_means_no_keepers(tmp_path, monkeypatch):
    import sourcemode.assets.judge as J
    import sourcemode.library as L
    monkeypatch.setattr(L, "library_dir", lambda cfg: tmp_path / "nowhere")
    monkeypatch.setattr(J, "judge_root", lambda cfg: tmp_path / "nojudge")
    assert I.keepers({}, "nadia") == []


def test_staging_writes_the_chat_names_and_the_base_file_and_never_the_game(tmp_path, monkeypatch):
    out, game = _world(tmp_path, monkeypatch)
    rec = I.stage({}, out, "nadia")
    d = I.staging_dir(out, "nadia")
    names = sorted(p.name for p in d.glob("*.webp"))
    assert names == sorted(["nadia_lingerie_standing.webp", "nadia_lingerie_kneeling.webp",
                            "nadia_lingerie_crawling.webp", "lingerie_01.webp"])
    assert rec["base_from"] == "standing" and rec["poses"] == ["standing", "kneeling", "crawling"]
    assert Image.open(d / "lingerie_01.webp").mode == "RGBA"           # a cutout since 2026-11-01
    # chillafterdark cd95d04: no characterAppearance.js line any more; the
    # game's sync:intimate registers packs from the base files on disk
    assert not (d / "registration.js").exists() and "registration" not in rec
    assert rec["outfit"] == "lingerie" and I.record_path(out, "nadia").name == "intimate.json"
    assert not game.exists()


def test_the_base_falls_back_to_the_first_keeper_when_standing_was_rejected(tmp_path, monkeypatch):
    out, _ = _world(tmp_path, monkeypatch, keep=("kneeling", "after"))
    rec = I.stage({}, out, "nadia")
    assert rec["base_from"] == "kneeling"


def test_shipping_copies_the_staged_files_into_her_intimate_folder_and_records_it(tmp_path, monkeypatch):
    out, game = _world(tmp_path, monkeypatch)
    I.stage({}, out, "nadia")
    dest = game / "src" / "assets" / "characters" / "nadia" / "intimate"
    dest.mkdir(parents=True)
    (dest / "lingerie_01.webp").write_bytes(b"old")
    rec = I.ship(out, "nadia", game)
    assert set(rec["files"]) == {"nadia_lingerie_standing.webp", "nadia_lingerie_kneeling.webp",
                                 "nadia_lingerie_crawling.webp", "lingerie_01.webp"}
    assert rec["overwrote"] == 1 and (dest / "nadia_lingerie_kneeling.webp").is_file()
    assert I.read_staged(out, "nadia")["shipped"]["files"] == rec["files"]
    assert rec["sync"]["ok"] and "intimatePacks" in rec["sync"]["output"]
    # a second ship of only one file
    rec2 = I.ship(out, "nadia", game, keep=["lingerie_01.webp"])
    assert rec2["files"] == ["lingerie_01.webp"] and "nadia_lingerie_kneeling.webp" in rec2["skipped"]


def test_ship_refuses_without_a_staging(tmp_path):
    with pytest.raises(ValueError):
        I.ship(tmp_path, "nadia", tmp_path / "game")


def test_every_lingerie_tag_is_a_chat_pose_the_game_detects_or_a_numbered_take_of_one():
    import re
    for p in S.LINGERIE_PACK:
        assert re.sub(r"\d+$", "", p["tag"]) in S.CHAT_POSES, p["tag"]
    assert {"kneeling", "crawling", "bendingover", "spreadwide", "lyingspread", "standingspread"} <= \
        {p["tag"] for p in S.LINGERIE_PACK}


def test_a_set_with_every_pose_kept_is_due_once_and_not_again_after_staging(tmp_path, monkeypatch):
    out, _ = _world(tmp_path, monkeypatch, keep=tuple(p["tag"] for p in S.LINGERIE_PACK))
    judge = tmp_path / "judge"
    plan = S.BY_ID["lingerie"].plan(character="nadia", outfit="x")
    (judge / "sets").mkdir(parents=True)
    (judge / "sets" / "shoot_nadia_lingerie.json").write_text(json.dumps(
        {"meta": {"character": "nadia", "shoot": "lingerie"}, "items": [{"id": s["id"]} for s in plan]}),
        encoding="utf-8")
    assert I.process_due(judge, out, "shoot_nadia_lingerie")
    I.stage({}, out, "nadia")
    assert I.process_due(judge, out, "shoot_nadia_lingerie") is None


def test_one_reject_means_not_due(tmp_path, monkeypatch):
    out, _ = _world(tmp_path, monkeypatch)
    judge = tmp_path / "judge"
    plan = S.BY_ID["lingerie"].plan(character="nadia", outfit="x")
    (judge / "sets").mkdir(parents=True)
    (judge / "sets" / "shoot_nadia_lingerie.json").write_text(json.dumps(
        {"meta": {"character": "nadia", "shoot": "lingerie"}, "items": [{"id": s["id"]} for s in plan]}),
        encoding="utf-8")
    assert I.process_due(judge, out, "shoot_nadia_lingerie") is None


def test_discard_drops_the_record_and_leaves_the_files(tmp_path, monkeypatch):
    out, _ = _world(tmp_path, monkeypatch)
    I.stage({}, out, "nadia")
    assert I.discard(out, "nadia") and I.read_staged(out, "nadia") is None
    assert (I.staging_dir(out, "nadia") / "lingerie_01.webp").is_file()


# --- the pajama pack, chillafterdark cd95d04 (2026-11-03) ---------------------

def test_the_packs_table_names_both_packs_and_the_lingerie_record_keeps_its_old_name():
    assert set(I.PACKS) == {"lingerie", "pajamas"}
    assert I.PACKS["lingerie"] == {"shoot": "lingerie", "base": "lingerie_01.webp", "record": "intimate.json"}
    assert I.PACKS["pajamas"] == {"shoot": "pajamas", "base": "pajamas_01.webp", "record": "pajamas.json"}
    for name in ("keepers", "record_path", "read_staged", "chat_name", "stage", "tile", "discard", "ship"):
        assert "outfit" in getattr(I, name).__code__.co_varnames, name
    assert not hasattr(I, "registration")


def test_pajama_chat_names_and_base_follow_the_game_contract(tmp_path, monkeypatch):
    out, game = _world(tmp_path, monkeypatch, keep=("standing", "standingback", "kneeling2"), shoot="pajamas")
    assert I.chat_name("Nadia", "standingback", outfit="pajamas") == "nadia_pajamas_standingback.webp"
    rec = I.stage({}, out, "nadia", outfit="pajamas")
    d = I.staging_dir(out, "nadia")                     # the same folder the lingerie staging uses
    assert sorted(p.name for p in d.glob("*.webp")) == sorted([
        "nadia_pajamas_standing.webp", "nadia_pajamas_standingback.webp", "nadia_pajamas_kneeling2.webp",
        "pajamas_01.webp"])
    assert rec["base_from"] == "standing" and rec["outfit"] == "pajamas"
    assert I.record_path(out, "nadia", outfit="pajamas").name == "pajamas.json"
    assert I.read_staged(out, "nadia") is None          # lingerie's record untouched
    shipped = I.ship(out, "nadia", game, outfit="pajamas")
    dest = game / "src" / "assets" / "characters" / "nadia" / "intimate"
    assert (dest / "pajamas_01.webp").is_file() and (dest / "nadia_pajamas_kneeling2.webp").is_file()
    assert set(shipped["files"]) == set(rec["files"])


def test_staging_pajamas_beside_lingerie_leaves_the_lingerie_files_and_record_intact(tmp_path, monkeypatch):
    out, _ = _world(tmp_path, monkeypatch)
    li = I.stage({}, out, "nadia")
    _world(tmp_path, monkeypatch, keep=("standing", "sitting"), shoot="pajamas")
    I.stage({}, out, "nadia", outfit="pajamas")
    d = I.staging_dir(out, "nadia")
    for name in li["files"]:
        assert (d / name).is_file(), name
    assert I.read_staged(out, "nadia") == li
    assert (d / "_cutouts_pajamas").is_dir() and (d / "_cutouts_lingerie").is_dir()
    # a pajama restaging with one pose fewer removes only its own old files
    _world(tmp_path, monkeypatch, keep=("standing",), shoot="pajamas")
    I.stage({}, out, "nadia", outfit="pajamas")
    assert not (d / "nadia_pajamas_sitting.webp").exists()
    assert (d / "nadia_lingerie_kneeling.webp").is_file() and (d / "lingerie_01.webp").is_file()


def test_every_pajama_tag_is_a_chat_pose_the_game_detects_or_a_numbered_take_of_one():
    import re
    for p in S.PAJAMA_PACK:
        assert re.sub(r"\d+$", "", p["tag"]) in S.CHAT_POSES, p["tag"]
    assert {"standing", "standingside", "standingback", "sitting", "kneeling", "kneeling2", "showfeet",
            "crawling", "after"} == {p["tag"] for p in S.PAJAMA_PACK}


def test_a_pajama_set_with_every_pose_kept_is_due_under_its_own_outfit(tmp_path, monkeypatch):
    out, _ = _world(tmp_path, monkeypatch, keep=tuple(p["tag"] for p in S.PAJAMA_PACK), shoot="pajamas")
    judge = tmp_path / "judge"
    plan = S.BY_ID["pajamas"].plan(character="nadia", outfit="x")
    (judge / "sets").mkdir(parents=True)
    (judge / "sets" / "shoot_nadia_pajamas.json").write_text(json.dumps(
        {"meta": {"character": "nadia", "shoot": "pajamas"}, "items": [{"id": s["id"]} for s in plan]}),
        encoding="utf-8")
    assert I.process_due(judge, out, "shoot_nadia_pajamas") is None            # not a lingerie set
    assert I.process_due(judge, out, "shoot_nadia_pajamas", outfit="pajamas")
    I.stage({}, out, "nadia", outfit="pajamas")
    assert I.process_due(judge, out, "shoot_nadia_pajamas", outfit="pajamas") is None


def test_ship_with_a_failing_sync_records_the_failure_and_still_copies(tmp_path, monkeypatch):
    out, game = _world(tmp_path, monkeypatch)
    I.stage({}, out, "nadia")
    monkeypatch.setattr(I, "run_sync", lambda game_root: {"ok": False, "cmd": "npm run sync:intimate",
                                                          "output": "npm ERR! missing script: sync:intimate"})
    rec = I.ship(out, "nadia", game)
    assert rec["sync"]["ok"] is False and "npm ERR" in rec["sync"]["output"]
    assert (game / "src" / "assets" / "characters" / "nadia" / "intimate" / "lingerie_01.webp").is_file()
    assert I.read_staged(out, "nadia")["shipped"]["sync"]["ok"] is False


def test_run_sync_calls_npm_in_the_game_repo_and_never_raises(tmp_path, monkeypatch):
    import subprocess
    calls = []

    class R:
        returncode = 1
        stdout = "boom"
        stderr = "npm ERR! x"

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(I.shutil, "which", lambda n: "C:/npm/npm.cmd")
    r = _REAL_RUN_SYNC(tmp_path)
    assert r["ok"] is False and "npm ERR! x" in r["output"] and "boom" in r["output"]
    assert calls[0][0][0] == "C:/npm/npm.cmd" and calls[0][0][1:] == ["run", "sync:intimate"]
    assert calls[0][1]["cwd"] == str(tmp_path)
    # no npm at all: a failure in words, not an exception
    monkeypatch.setattr(I.shutil, "which", lambda n: None)
    assert _REAL_RUN_SYNC(tmp_path)["ok"] is False


def test_the_characters_tab_serves_one_intimate_route_per_pack_and_refuses_an_unknown_one(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import sourcemode.assets.looks as LK
    from sourcemode.monitor.appearance_page import appearance_router
    out, game = _world(tmp_path, monkeypatch, keep=("standing", "sitting"), shoot="pajamas")
    I.stage({}, out, "nadia", outfit="pajamas")
    monkeypatch.setattr("sourcemode.config.outputs_dir", lambda c: out)
    monkeypatch.setattr(LK, "GAME_ROOT", game)
    app = FastAPI(); app.include_router(appearance_router({}))
    c = TestClient(app)
    assert c.get("/characters/nadia/intimate/socks").status_code == 404
    assert c.get("/characters/nadia/intimate/lingerie").json()["staged"] is None
    j = c.get("/characters/nadia/intimate/pajamas").json()
    assert j["outfit"] == "pajamas" and j["staged"]["poses"] == ["standing", "sitting"]
    tile = c.get("/characters/nadia/intimate/pajamas/look", params={"file": "pajamas_01.webp"})
    assert tile.status_code == 200
    # a re-staging reuses the file name, so the browser must never keep the old one
    assert "no-store" in tile.headers["cache-control"]
    assert c.get("/characters/nadia/intimate/lingerie/look", params={"file": "pajamas_01.webp"}).status_code == 404
    r = c.post("/characters/nadia/intimate/pajamas/ship", json={"keep": ["pajamas_01.webp"]}).json()
    assert r["files"] == ["pajamas_01.webp"] and r["sync"]["ok"]
    assert (game / "src" / "assets" / "characters" / "nadia" / "intimate" / "pajamas_01.webp").is_file()
    assert c.post("/characters/nadia/intimate/pajamas/discard", json={}).json()["discarded"]
