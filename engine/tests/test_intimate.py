import json

from PIL import Image

from sourcemode.assets import intimate as I
from sourcemode.assets import shoots as S


def _world(tmp_path, monkeypatch, keep=("standing", "kneeling", "crawling")):
    """A library with a rendered lingerie shoot, a verdict file, and a game repo."""
    import sourcemode.assets.judge as J
    import sourcemode.library as L
    lib = tmp_path / "library"
    judge = tmp_path / "judge"
    shoot = lib / "nadia" / "2026-10-29_shoot_lingerie"
    shoot.mkdir(parents=True)
    plan = S.BY_ID["lingerie"].plan(character="nadia", outfit="x")
    verdicts = {}
    for s in plan:
        Image.new("RGB", (64, 96), "red").save(shoot / f"{s['id']}.png")
        verdicts[s["id"]] = "keep" if s["tag"] in keep else "reject"
    (judge / "verdicts").mkdir(parents=True)
    (judge / "verdicts" / "shoot_nadia_lingerie.json").write_text(json.dumps(verdicts), encoding="utf-8")
    monkeypatch.setattr(L, "library_dir", lambda cfg: lib)
    monkeypatch.setattr(J, "judge_root", lambda cfg: judge)
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
    assert Image.open(d / "lingerie_01.webp").mode == "RGB"
    assert "organized('nadia', 'lingerie', 'intimate/lingerie_01.webp', ['intimate']" in \
        (d / "registration.js").read_text(encoding="utf-8")
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
    # a second ship of only one file
    rec2 = I.ship(out, "nadia", game, keep=["lingerie_01.webp"])
    assert rec2["files"] == ["lingerie_01.webp"] and "nadia_lingerie_kneeling.webp" in rec2["skipped"]


def test_ship_refuses_without_a_staging(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        I.ship(tmp_path, "nadia", tmp_path / "game")


def test_every_lingerie_tag_is_a_chat_pose_the_game_detects_or_a_numbered_take_of_one():
    import re
    for p in S.LINGERIE_PACK:
        assert re.sub(r"\d+$", "", p["tag"]) in S.CHAT_POSES, p["tag"]
    assert {"kneeling", "crawling", "bendingover", "spreadwide", "lyingspread", "standingspread"} <= \
        {p["tag"] for p in S.LINGERIE_PACK}
