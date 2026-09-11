"""Review API: the pure parts over real sidecar files, plus the router if httpx is present."""

import json
from pathlib import Path

import pytest
from PIL import Image

from sourcemode.assets.catalog import make_plan
from sourcemode.assets.review import candidates, characters, place_with_picks, safe_path, save_picks, thumbnail


def cutout(root: Path, char: str, slot_dir: str | None, name: str, score, flags=(), asset=None):
    d = root / char / "cutouts" / (slot_dir or "loose"); d.mkdir(parents=True, exist_ok=True)
    png = d / f"{name}.png"; wp = d / f"{name}.webp"
    im = Image.new("RGBA", (40, 60), (0, 0, 0, 0)); im.paste((200, 30, 30, 255), (10, 10, 30, 60))
    im.save(png); im.save(wp, "WEBP", exact=True)
    side = {"source": f"C:/r/{slot_dir}/{name}.png", "outputs": {"png": str(png), "webp": str(wp)},
            "report": {"flags": list(flags), "partial": 0.01, "coverage": 0.3}, "score": score}
    if asset:
        side["asset"] = asset
    (d / f"{name}.json").write_text(json.dumps(side))
    return side


def test_safe_path_refuses_escapes(tmp_path: Path):
    (tmp_path / "a.png").write_bytes(b"x"); (tmp_path.parent / "outside.png").write_bytes(b"x")
    assert safe_path(tmp_path, "a.png") == (tmp_path / "a.png").resolve()
    assert safe_path(tmp_path, "../outside.png") is None
    assert safe_path(tmp_path, str((tmp_path / "a.png").resolve())) is None      # absolute refused
    assert safe_path(tmp_path, "missing.png") is None
    assert safe_path(tmp_path, "") is None


def test_thumbnail_snaps_width_and_caches(tmp_path: Path):
    src = tmp_path / "big.png"; Image.new("RGBA", (1024, 1536), (0, 0, 255, 255)).save(src)
    t = thumbnail(src, 350, tmp_path / "_thumbs")
    assert Image.open(t).size == (360, 540) and t.name.startswith("big_360_")
    assert thumbnail(src, 350, tmp_path / "_thumbs") == t                        # same file, cached


def test_candidates_groups_by_slot_ranks_and_applies_saved_picks(tmp_path: Path):
    plan = make_plan("sunny", counts={"casual": 1, "work": 1})
    (tmp_path / "sunny").mkdir(); (tmp_path / "sunny" / "plan.json").write_text(json.dumps(plan))
    a = {"character": "sunny", "category": "casual", "look": 1, "pose": "standing"}
    cutout(tmp_path, "sunny", "casual_01_standing", "shot_00", 0.9, flags=("hollow",), asset=a)
    cutout(tmp_path, "sunny", "casual_01_standing", "shot_01", 0.8, asset=a)
    cutout(tmp_path, "sunny", None, "loose_01", 0.7)                              # no slot -> unassigned
    c = candidates(tmp_path, "sunny")
    assert c["plan"] == "plan.json" and [s["id"] for s in c["slots"]] == ["casual_01", "work_01"]
    casual = c["slots"][0]
    assert [x["file"] for x in casual["candidates"]] == ["shot_01.png", "shot_00.png"]   # unflagged first
    assert casual["picked"] == "shot_01.png" and casual["auto"] is True
    assert c["slots"][1]["candidates"] == [] and c["slots"][1]["picked"] is None
    assert [u["file"] for u in c["unassigned"]] == ["loose_01.png"]
    assert casual["candidates"][0]["png"].startswith("sunny/cutouts/casual_01_standing/")   # relative to root
    save_picks(tmp_path, "sunny", {"casual_01": "shot_00.png"})
    c2 = candidates(tmp_path, "sunny")
    assert c2["slots"][0]["picked"] == "shot_00.png" and c2["slots"][0]["auto"] is False
    assert characters(tmp_path) == [{"character": "sunny", "candidates": 3, "plan": "plan.json", "placed": 0}]


def test_place_with_picks_honours_the_saved_choice(tmp_path: Path):
    plan = make_plan("sunny", counts={"casual": 1})
    (tmp_path / "sunny").mkdir(); (tmp_path / "sunny" / "plan.json").write_text(json.dumps(plan))
    a = {"character": "sunny", "category": "casual", "look": 1, "pose": "standing"}
    cutout(tmp_path, "sunny", "casual_01_standing", "shot_00", 0.9, asset=a)
    cutout(tmp_path, "sunny", "casual_01_standing", "shot_01", 0.6, asset=a)
    save_picks(tmp_path, "sunny", {"casual_01": "shot_01.webp", "_unassigned": ["x"]})
    m = place_with_picks(tmp_path, "sunny")
    assert m["slots"][0]["from"].endswith("shot_01.png") and m["slots"][0]["overridden"]
    assert (tmp_path / "sunny" / "outfits" / "casual_01_standing.webp").exists()
    assert m["sheet"] == "sunny/review/mapping_checkerboard.jpg"
    with pytest.raises(FileNotFoundError):
        place_with_picks(tmp_path, "nobody")


def test_router_end_to_end(tmp_path: Path, monkeypatch):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sourcemode.assets.review import review_router
    plan = make_plan("sunny", counts={"casual": 1})
    (tmp_path / "sunny").mkdir(); (tmp_path / "sunny" / "plan.json").write_text(json.dumps(plan))
    a = {"character": "sunny", "category": "casual", "look": 1, "pose": "standing"}
    cutout(tmp_path, "sunny", "casual_01_standing", "shot_00", 0.9, asset=a)
    app = FastAPI(); app.include_router(review_router({"assets": {"staging": str(tmp_path)}}))
    c = TestClient(app)
    assert c.get("/assets").json()["characters"][0]["character"] == "sunny"
    cand = c.get("/assets/sunny").json()
    png = cand["slots"][0]["candidates"][0]["png"]
    assert c.get("/assets/file", params={"p": png}).status_code == 200
    assert c.get("/assets/file", params={"p": png, "w": 160}).headers["content-type"].startswith("image/png")
    assert c.get("/assets/file", params={"p": "../secrets"}).status_code == 404
    assert c.get("/assets/nobody").status_code == 404
    assert c.post("/assets/sunny/picks", json={"picks": {"casual_01": "shot_00.png"}}).status_code == 200
    assert c.post("/assets/sunny/picks", json={"nope": 1}).status_code == 400
    m = c.post("/assets/sunny/place").json()
    assert m["slots"][0]["file"] == "casual_01_standing.webp"
