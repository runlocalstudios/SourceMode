"""The library: one tree by character, dated, kind in the name; the planner moves
nothing and the apply step keeps every judge set pointing at its images.

Jeremy, 2026-10-09: "I don't think I'll ever be able to find or organize any of
the assets we have been creating."
"""

import json
import os
import time

import pytest
from PIL import Image

from sourcemode import library as L
from sourcemode.assets.judge import load_set, make_set, record_verdict

CHARS = {"jojo", "mei", "cat", "amanda", "bri"}


def _png(p, when=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4)).save(p)
    if when:
        os.utime(p, (when, when))
    return p


@pytest.fixture
def tree(tmp_path, monkeypatch):
    engine = tmp_path / "engine"
    out = engine / "outputs"
    sep_28 = time.mktime((2026, 9, 28, 12, 0, 0, 0, 0, -1))
    _png(out / "shoots" / "jojo" / "influencer_b01" / "a.png", sep_28)
    _png(out / "shoots" / "jojo" / "selfies" / "s.png")
    _png(out / "shoots" / "jojo" / "_superseded" / "old_b00" / "x.png")
    _png(out / "dense_mei_v2_asset_nodesc" / "e22_0.png")
    _png(out / "ab_cat_desc" / "A" / "scene_00.png")
    _png(out / "coarse_jojo_a2" / "x.png")
    _png(out / "twostage_amanda" / "x.png")
    _png(out / "headpatch_ab" / "x.png")
    _png(out / "photosets" / "bri" / "00_sundress" / "p.png")
    (out / "dense_bri_v2").mkdir()                       # empty: a sweep that never ran
    (out / "lora-datasets" / "jojo_v2").mkdir(parents=True)
    (out / "judge").mkdir()
    monkeypatch.chdir(engine)
    monkeypatch.setattr(L, "SETTLE_S", 0)   # fixture files are brand new; the in-use test re-arms it
    judge = out / "judge"
    make_set(judge, "ab_cat_desc", "Cat A/B",
             [{"id": "A__00", "path": os.path.join("outputs", "ab_cat_desc", "A", "scene_00.png"),
               "arm": "A", "group": "0"}],
             meta={"character": "cat", "renders_dir": out / "ab_cat_desc"})
    record_verdict(judge, "ab_cat_desc", "A__00", "keep")
    return engine, out, judge


def test_plan_files_every_folder_by_character_kind_and_date(tree):
    engine, out, judge = tree
    rows = {r["src"]: r for r in L.plan(out, judge, CHARS)}
    assert rows[os.path.join("shoots", "jojo", "influencer_b01")]["dst"] == os.path.join(
        "jojo", "2026-09-28_shoot_influencer-b01")
    assert rows[os.path.join("shoots", "jojo", "selfies")]["kind"] == "selfies"
    assert rows[os.path.join("shoots", "jojo", "_superseded", "old_b00")]["dst"].startswith(
        os.path.join("_experiments", "jojo"))
    mei = rows["dense_mei_v2_asset_nodesc"]
    assert (mei["character"], mei["kind"], mei["name"], mei["experiment"]) == ("mei", "sweep", "v2_asset_nodesc", False)
    assert mei["dst"].endswith("_sweep_v2-asset-nodesc")
    cat = rows["ab_cat_desc"]
    assert cat["kind"] == "ab" and cat["judge_sets"] == ["sets/ab_cat_desc.json"]
    assert rows["coarse_jojo_a2"]["experiment"] and rows["coarse_jojo_a2"]["kind"] == "sweep"
    assert rows["twostage_amanda"]["dst"].startswith(os.path.join("_experiments", "amanda"))
    assert rows["headpatch_ab"]["dst"].startswith(os.path.join("_experiments", "misc")) and rows["headpatch_ab"]["kind"] == "ab"
    assert rows[os.path.join("photosets", "bri")]["dst"].endswith("_shoot_photoset")
    assert rows["dense_bri_v2"]["action"] == "remove-empty"
    assert rows["lora-datasets"]["action"] == "stay" and rows["judge"]["action"] == "stay"


def test_plan_writes_the_table_and_moves_nothing(tree, tmp_path):
    engine, out, judge = tree
    before = sorted(str(p) for p in out.rglob("*"))
    pj, pm = L.write_plan(L.plan(out, judge, CHARS), tmp_path / "library")
    assert "nothing has moved" in pm.read_text(encoding="utf-8")
    assert json.loads(pj.read_text(encoding="utf-8"))
    assert sorted(str(p) for p in out.rglob("*")) == before


def test_apply_moves_rewrites_the_judge_set_and_links_keepers(tree, tmp_path):
    engine, out, judge = tree
    lib = tmp_path / "library"
    rows = L.plan(out, judge, CHARS)
    dry = L.apply(rows, out, lib, judge, dry_run=True)
    assert any(line.startswith("move ab_cat_desc") for line in dry)
    assert (out / "ab_cat_desc").is_dir() and not lib.exists()

    L.apply(rows, out, lib, judge)
    new = lib / [r for r in rows if r["src"] == "ab_cat_desc"][0]["dst"]
    assert (new / "A" / "scene_00.png").is_file() and not (out / "ab_cat_desc").exists()
    doc = load_set(judge, "ab_cat_desc")
    assert doc["items"][0]["path"] == str(new / "A" / "scene_00.png")
    assert doc["meta"]["renders_dir"] == str(new)
    assert (new / "kept" / "a-00.png").is_file()
    meta = json.loads((new / "set.json").read_text(encoding="utf-8"))
    assert meta["character"] == "cat" and meta["kind"] == "ab" and meta["kept"] == 1
    assert meta["moved_from"] == "outputs/ab_cat_desc" and meta["judge_sets"] == ["ab_cat_desc"]
    assert not (out / "dense_bri_v2").exists()
    assert (out / "lora-datasets" / "jojo_v2").is_dir()
    assert (lib / "jojo" / "2026-09-28_shoot_influencer-b01" / "a.png").is_file()


def test_apply_refuses_an_existing_destination(tree, tmp_path):
    engine, out, judge = tree
    lib = tmp_path / "library"
    rows = [r for r in L.plan(out, judge, CHARS) if r["src"] == "ab_cat_desc"]
    (lib / rows[0]["dst"]).mkdir(parents=True)
    log = L.apply(rows, out, lib, judge)
    assert log == [f"SKIP ab_cat_desc: {rows[0]['dst']} already exists"]
    assert (out / "ab_cat_desc").is_dir()


def test_set_dir_for_new_work(tmp_path):
    cfg = {"paths": {"library": str(tmp_path / "lib")}}
    d = L.set_dir(cfg, "Jojo", "shoot", "Influencer b02", date="2026-10-09")
    assert d == tmp_path / "lib" / "jojo" / "2026-10-09_shoot_influencer-b02" and d.is_dir()
    e = L.set_dir(cfg, "jojo", "probe", "x", date="2026-10-09", experiment=True)
    assert e.parent.parent == tmp_path / "lib" / "_experiments"
    with pytest.raises(ValueError):
        L.set_folder("2026-10-09", "photo", "x")


def test_apply_leaves_a_folder_a_running_job_is_still_writing(tree, tmp_path, monkeypatch):
    engine, out, judge = tree
    monkeypatch.setattr(L, "SETTLE_S", 15 * 60)
    lib = tmp_path / "library"
    rows = [r for r in L.plan(out, judge, CHARS) if r["src"] == "ab_cat_desc"]
    _png(out / "ab_cat_desc" / "A" / "scene_01.png")        # fresh: mtime is now
    log = L.apply(rows, out, lib, judge)
    assert log[0].startswith("SKIP ab_cat_desc: written") and (out / "ab_cat_desc").is_dir()


def test_names_do_not_repeat_the_kind():
    assert L._classify("jojo_video", {"jojo"}) == ("jojo", "video", "clips", False)
    assert L._classify("flux_realism_ab", set()) == ("misc", "ab", "flux_realism", True)
