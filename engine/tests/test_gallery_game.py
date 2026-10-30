"""The Gallery tab's Game assets row: her shipped art first, else what is staged
or rendered, each group saying which."""

from pathlib import Path

import pytest
from PIL import Image

from sourcemode.monitor import gallery_page as G


def _world(tmp_path: Path):
    game = tmp_path / "game"
    out = tmp_path / "outputs"
    lib = tmp_path / "lib"
    g = game / "src" / "assets" / "characters" / "jojo"
    for n in ("casual_01_standing.webp", "work_01_standing.webp"):
        (g / "outfits").mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 12)).save(g / "outfits" / n)
    (g / "portraits").mkdir()
    Image.new("RGB", (8, 12)).save(g / "portraits" / "profile.webp")
    # intimate: nothing in the game, staged under outputs
    st = out / "game-assets" / "jojo" / "intimate"; st.mkdir(parents=True)
    Image.new("RGB", (8, 12)).save(st / "jojo_lingerie_kneeling.webp")
    (st / "intimate.json").write_text("{}", encoding="utf-8")
    # selfies: only rendered, in the library
    sel = lib / "jojo" / "2026-10-20_selfies_selfies"; sel.mkdir(parents=True)
    Image.new("RGB", (8, 12)).save(sel / "selfie_casual_01.png")
    return game, out, lib


def test_groups_come_from_the_game_first_then_staging_then_renders(tmp_path):
    game, out, lib = _world(tmp_path)
    groups = {g["key"]: g for g in G.game_groups("jojo", game, out, lib)}
    assert list(groups) == ["pack", "selfies", "intimate", "portrait"]      # no home art: no button
    assert groups["pack"]["source"] == "in the game" and len(groups["pack"]["images"]) == 2
    assert groups["intimate"]["source"] == "staged, not shipped"
    assert groups["intimate"]["images"][0]["name"] == "jojo_lingerie_kneeling.webp"
    assert groups["selfies"]["source"] == "rendered, not shipped"
    # library files thumbnail through the Video tab; game and staging files are served as they are
    assert groups["selfies"]["images"][0]["thumb"].startswith("/video/thumb?")
    assert groups["pack"]["images"][0]["thumb"].startswith("/gallery/game-file?")


def test_a_pack_with_nothing_shipped_or_staged_shows_the_newest_render_per_look(tmp_path):
    game, out, lib = _world(tmp_path)
    import shutil
    shutil.rmtree(game / "src" / "assets" / "characters" / "jojo" / "outfits")
    r = out / "game-assets" / "jojo" / "renders" / "casual_01_standing"; r.mkdir(parents=True)
    Image.new("RGB", (8, 12)).save(r / "shot_00_s7100.png")
    Image.new("RGB", (8, 12)).save(r / "shot_00_s7100_a1.png")
    (out / "game-assets" / "jojo" / "renders" / "_web").mkdir()
    groups = {g["key"]: g for g in G.game_groups("jojo", game, out, lib)}
    assert groups["pack"]["source"] == "rendered, not staged" and len(groups["pack"]["images"]) == 1


def test_the_game_file_route_serves_only_game_and_staging_images(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    game, out, lib = _world(tmp_path)
    monkeypatch.setattr(G, "GAME_ROOT", game)
    monkeypatch.setattr("sourcemode.config.outputs_dir", lambda c: out)
    monkeypatch.setattr("sourcemode.library.library_dir", lambda c: lib)
    app = FastAPI(); app.include_router(G.gallery_router({}))
    c = TestClient(app)
    j = c.get("/gallery/game", params={"character": "jojo"}).json()
    assert [g["key"] for g in j["groups"]] == ["pack", "selfies", "intimate", "portrait"]
    ok = game / "src" / "assets" / "characters" / "jojo" / "outfits" / "casual_01_standing.webp"
    assert c.get("/gallery/game-file", params={"path": str(ok)}).status_code == 200
    assert c.get("/gallery/game-file", params={"path": str(out / "game-assets" / "jojo" / "intimate" / "intimate.json")}).status_code == 404
    assert c.get("/gallery/game-file", params={"path": str(lib / "jojo" / "2026-10-20_selfies_selfies" / "selfie_casual_01.png")}).status_code == 404
    assert c.get("/gallery/game", params={"character": "../x"}).status_code == 400
    assert "Game assets" in c.get("/gallery").text
    # nothing was written beside the game's files
    assert sorted(p.name for p in (game / "src" / "assets" / "characters" / "jojo" / "outfits").iterdir()) == \
        ["casual_01_standing.webp", "work_01_standing.webp"]
