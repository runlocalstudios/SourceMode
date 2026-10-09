"""The library: one tree by character, dated, kind in the name; the planner moves
nothing and the apply step keeps every judge set pointing at its images.

Jeremy, 2026-10-09: "I don't think I'll ever be able to find or organize any of
the assets we have been creating."
"""

import json
import os
import time
from pathlib import Path

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


# --- pruning: what a locked winner makes redundant -------------------------------

@pytest.fixture
def locked_world(tree, tmp_path, monkeypatch):
    """zara is locked to epoch 18; 19 is a loser. mei has a sweep but no lock.
    ab_old is 30 days old, ab_cat_desc (from `tree`) is fresh."""
    from sourcemode.train import locked as LK

    engine, out, judge = tree
    reg = tmp_path / "characters" / "loras.json"
    monkeypatch.setattr(LK, "REGISTRY", reg)
    cfg = {"paths": {"outputs": str(out), "library": str(tmp_path / "library")},
           "comfyui": {"loras_dir": str(tmp_path / "comfy")}}
    ck = out / "lora-datasets" / "zara_v2" / "lora"
    ck.mkdir(parents=True)
    (ck / "zara_v2-000018.safetensors").write_bytes(b"18")
    (ck / "zara_v2-000019.safetensors").write_bytes(b"19")
    LK.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
    stray = Path(cfg["comfyui"]["loras_dir"]) / "sourcemode" / "zara_v2" / "zara_v2-000019.safetensors"
    stray.write_bytes(b"19")
    _png(out / "dense_zara_v2_asset" / "ep18" / "scene_00.png")
    make_set(judge, "dense_zara_v2_asset", "zara sweep",
             [{"id": "e18", "path": os.path.join("outputs", "dense_zara_v2_asset", "ep18", "scene_00.png"),
               "arm": "zara_v2 epoch 18", "group": "0"}])
    old = time.time() - 30 * 86400
    _png(out / "selfie_ab" / "a.png", old)
    return cfg, out, judge, ck, stray


def test_prune_plan_lists_only_what_a_lock_makes_redundant(locked_world):
    cfg, out, judge, ck, stray = locked_world
    all_rows = L.prune_plan(cfg, out, judge)
    rows = {Path(r["path"]).name: r for r in all_rows}
    assert rows["dense_zara_v2_asset"]["kind"] == "folder" and rows["dense_zara_v2_asset"]["judge_sets"] == ["sets/dense_zara_v2_asset.json"]
    assert "zara_v2-000019.safetensors" in rows and "zara_v2-000018.safetensors" not in rows
    assert sum(1 for r in all_rows if r["path"].endswith("zara_v2-000019.safetensors")) == 2   # training + ComfyUI
    assert "selfie_ab" in rows and "ab_cat_desc" not in rows          # 30 days vs fresh
    assert "dense_mei_v2_asset_nodesc" not in rows                    # mei is not locked
    assert all(r["action"] == "delete" for r in rows.values())


def test_prune_apply_deletes_retires_and_keeps_the_lock(locked_world, tmp_path):
    cfg, out, judge, ck, stray = locked_world
    rows = L.prune_plan(cfg, out, judge)
    dry = L.prune_apply(cfg, rows, judge, dry_run=True)
    assert all(l.startswith("delete") for l in dry) and (out / "dense_zara_v2_asset").is_dir()
    log = L.prune_apply(cfg, rows, judge)
    assert not (out / "dense_zara_v2_asset").exists() and not (out / "selfie_ab").exists()
    assert not (ck / "zara_v2-000019.safetensors").exists() and not stray.exists()
    assert (ck / "zara_v2-000018.safetensors").is_file()
    assert (judge / "retired" / "dense_zara_v2_asset.set.json").is_file()
    assert not (judge / "sets" / "dense_zara_v2_asset.json").exists()
    assert (out / "dense_mei_v2_asset_nodesc").is_dir()
    assert any("retired dense_zara_v2_asset.set.json" in l for l in log)
    pj, pm = L.write_prune(rows, tmp_path / "library")
    assert "nothing has been deleted" in pm.read_text(encoding="utf-8")


def test_prune_refuses_while_a_lock_does_not_verify(locked_world):
    cfg, out, judge, ck, stray = locked_world
    vault = Path(cfg["paths"]["library"]) / "loras" / "zara" / "zara_v2-000018.safetensors"
    vault.write_bytes(b"tampered")
    log = L.prune_apply(cfg, L.prune_plan(cfg, out, judge), judge)
    assert log and log[0].startswith("REFUSED: zara")
    assert (ck / "zara_v2-000019.safetensors").is_file() and (out / "dense_zara_v2_asset").is_dir()
