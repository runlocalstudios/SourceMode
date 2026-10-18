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


def test_a_writer_finds_the_set_it_started_on_an_earlier_day(tmp_path):
    """A sweep resumes and a redo writes back into its shoot - so the writer must
    land in the folder that already exists, not a fresh one dated today."""
    cfg = {"paths": {"library": str(tmp_path / "lib")}}
    old = tmp_path / "lib" / "daisy" / "2026-10-01_sweep_tb-tiebreaker"
    old.mkdir(parents=True)
    (tmp_path / "lib" / "daisy" / "2026-10-01_sweep_tb-tiebreaker-x").mkdir()  # a longer name is another set
    name = L.set_name("dense_daisy_tb_tiebreaker", "dense_", "daisy", "v2")
    assert name == "tb_tiebreaker"
    assert L.find_set(cfg, "daisy", "sweep", name) == old
    fresh = L.find_set(cfg, "daisy", "ab", "hair")
    assert fresh.name == f"{time.strftime('%Y-%m-%d')}_ab_hair" and not fresh.exists()
    assert L.find_set(cfg, "daisy", "ab", "hair", create=True).is_dir()


def test_set_names_match_what_plan_filed_the_moved_folders_under():
    for folder, char in (("dense_gabi_v2_asset_confirm", "gabi"), ("ab_cat_desc", "cat")):
        prefix = folder.split("_")[0] + "_"
        kind = "sweep" if prefix == "dense_" else "ab"
        _c, k, n, _e = L._classify(folder, {char})
        assert (k, n) == (kind, L.set_name(folder, prefix, char, "v2" if kind == "sweep" else "ab"))
    assert L.shoot_kind("selfies") == "selfies" and L.shoot_kind("boudoir") == "shoot"


def test_influencer_batches_count_in_the_library_and_the_old_tree(tmp_path):
    from sourcemode.assets.influencer import next_batch

    _png(tmp_path / "2026-10-01_shoot_influencer-b03" / "a.png")
    _png(tmp_path / "influencer_b01" / "a.png")
    (tmp_path / "2026-10-02_shoot_influencer-b07").mkdir()      # failed before rendering
    assert next_batch(tmp_path) == 4


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
    # a sweep candidate staged where sweeps stage them; the lock is flat beside that folder
    stray = Path(cfg["comfyui"]["loras_dir"]) / "sourcemode" / "zara_v2" / "zara_v2-000019.safetensors"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"19")
    _png(out / "dense_zara_v2_asset" / "ep18" / "scene_00.png")
    _png(out / "dense_zara_v2_asset" / "ep19" / "scene_00.png")
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
    assert "zara_v2-000019.safetensors" in rows
    assert sum(1 for r in all_rows if r["path"].endswith("zara_v2-000019.safetensors")) == 2   # training + ComfyUI
    # the lock's training-folder copy is a third local copy and goes too;
    # the vault and ComfyUI copies never appear (Jeremy, 2026-10-18)
    assert [r["path"] for r in all_rows if r["path"].endswith("zara_v2-000018.safetensors")] == \
        [str(ck / "zara_v2-000018.safetensors")]
    assert not any(r["path"].endswith("zara.safetensors") for r in all_rows)
    assert "selfie_ab" in rows and "ab_cat_desc" not in rows          # 30 days vs fresh
    assert "dense_mei_v2_asset_nodesc" not in rows                    # mei is not locked
    assert all(r["action"] == "delete" for r in rows.values())


def test_prune_apply_deletes_retires_and_keeps_the_lock(locked_world, tmp_path):
    cfg, out, judge, ck, stray = locked_world
    rows = L.prune_plan(cfg, out, judge)
    dry = L.prune_apply(cfg, rows, judge, dry_run=True)
    assert all(l.startswith("delete") for l in dry) and (out / "dense_zara_v2_asset").is_dir()
    log = L.prune_apply(cfg, rows, judge)
    # the sweep keeps the lock's own renders (ep18) and loses the rest
    assert (out / "dense_zara_v2_asset" / "ep18" / "scene_00.png").is_file()
    assert sorted(p.name for p in (out / "dense_zara_v2_asset").iterdir()) == ["ep18"]
    assert not (out / "selfie_ab").exists()
    assert not (ck / "zara_v2-000019.safetensors").exists() and not stray.exists()
    assert not (ck / "zara_v2-000018.safetensors").exists()
    assert (Path(cfg["paths"]["library"]) / "loras" / "zara" / "zara.safetensors").is_file()
    assert (Path(cfg["comfyui"]["loras_dir"]) / "sourcemode" / "zara.safetensors").is_file()
    assert (judge / "retired" / "dense_zara_v2_asset.set.json").is_file()
    assert not (judge / "sets" / "dense_zara_v2_asset.json").exists()
    assert (out / "dense_mei_v2_asset_nodesc").is_dir()
    assert any("retired dense_zara_v2_asset.set.json" in l for l in log)
    pj, pm = L.write_prune(rows, tmp_path / "library")
    assert "nothing has been deleted" in pm.read_text(encoding="utf-8")


def test_prune_refuses_while_a_lock_does_not_verify(locked_world):
    cfg, out, judge, ck, stray = locked_world
    vault = Path(cfg["paths"]["library"]) / "loras" / "zara" / "zara.safetensors"
    vault.write_bytes(b"tampered")
    log = L.prune_apply(cfg, L.prune_plan(cfg, out, judge), judge)
    assert log and log[0].startswith("REFUSED: zara")
    assert (ck / "zara_v2-000019.safetensors").is_file() and (out / "dense_zara_v2_asset").is_dir()


def test_prune_finds_the_same_sets_in_her_library_folder(locked_world, tmp_path):
    cfg, out, judge, ck, stray = locked_world
    lib = tmp_path / "library"
    _png(lib / "zara" / "2026-10-01_sweep_v2-asset" / "ep18" / "scene_00.png")   # her lock: kept
    _png(lib / "zara" / "2026-10-01_sweep_v2-asset" / "ep19" / "scene_00.png")   # a loser: listed
    _png(lib / "mei" / "2026-10-01_sweep_v2-asset" / "ep18" / "scene_00.png")      # no lock
    _png(lib / "zara" / "2026-09-01_ab_hair" / "A" / "scene_00.png", time.time() - 30 * 86400)
    _png(lib / "zara" / "2026-10-11_ab_skin" / "A" / "scene_00.png")                # fresh
    _png(lib / "zara" / "2026-10-01_shoot_pool" / "a.png", time.time() - 30 * 86400)
    names = {Path(r["path"]).name for r in L.prune_plan(cfg, out, judge)}
    assert {"2026-10-01_sweep_v2-asset", "2026-09-01_ab_hair"} <= names
    assert not {"2026-10-11_ab_skin", "2026-10-01_shoot_pool"} & names
    assert sum(1 for r in L.prune_plan(cfg, out, judge) if "mei" in Path(r["path"]).parts) == 0


def test_a_prune_keeps_the_locked_epochs_renders_and_the_sets_record(locked_world, tmp_path):
    """2026-10-15: the first prune deleted every sweep folder whole, and with them
    the only renders of 38 locks. Jeremy: "I thought we were keeping the locked
    epoch renders." A locked character's sweep keeps `ep<lock>/` and its
    set.json; the losing epochs and the judge set go as before."""
    cfg, out, judge, ck, stray = locked_world
    lib = tmp_path / "library"
    sweep = lib / "zara" / "2026-10-01_sweep_v2-asset"
    for ep in ("ep17", "ep18", "ep19"):
        _png(sweep / ep / "scene_00.png")
        _png(sweep / ep / "scene_01.png")
    (sweep / "set.json").write_text("{}", encoding="utf-8")
    (sweep / "sheet.jpg").write_bytes(b"jpg")
    _png(lib / "mei" / "2026-10-01_sweep_v2-asset" / "ep18" / "scene_00.png")      # no lock
    rows = L.prune_plan(cfg, out, judge)
    r = next(x for x in rows if Path(x["path"]) == sweep)
    assert r["keep"] == [str(sweep / "ep18")] and r["why"].endswith("; keeps ep18")
    assert r["bytes"] == L._size(sweep) - L._size(sweep / "ep18") - L._size(sweep / "set.json")
    pj, pm = L.write_prune(rows, lib)
    assert "keeps ep18" in pm.read_text(encoding="utf-8")

    dry = L.prune_apply(cfg, rows, judge, dry_run=True)
    assert any(l.endswith("keeping ep18") for l in dry) and (sweep / "ep17").is_dir()
    L.prune_apply(cfg, rows, judge)
    assert sorted(p.name for p in sweep.iterdir()) == ["ep18", "set.json"]
    assert (sweep / "ep18" / "scene_01.png").is_file()
    assert (lib / "mei" / "2026-10-01_sweep_v2-asset" / "ep18" / "scene_00.png").is_file()
    # and approving her looks still finds the render the prune kept
    from sourcemode.assets.looks import source_asset
    lock = {"name": "zara.safetensors", "file": "zara_v2-000018.safetensors", "epoch": 18}
    assert source_asset(cfg, "zara", 18, lock) == sweep / "ep18" / "scene_00.png"
    # a second prune has nothing left to take from her sweep, so it is not listed
    assert not [x for x in L.prune_plan(cfg, out, judge) if Path(x["path"]) == sweep]


def test_lock_render_dir_follows_a_continued_runs_numbering(tmp_path):
    lib = tmp_path / "priyanka"
    for d in ("2026-09-20_sweep_v2/ep20", "2026-09-21_sweep_v2b/ep06"):
        (lib / d).mkdir(parents=True)
    lock = {"name": "priyanka.safetensors", "file": "priyanka_v2b-000006.safetensors", "epoch": 26}
    assert L.lock_render_dir(lib / "2026-09-21_sweep_v2b", "priyanka", lock) == lib / "2026-09-21_sweep_v2b" / "ep06"
    assert L.lock_render_dir(lib / "2026-09-20_sweep_v2", "priyanka", lock) is None   # a v2 sweep holds no v2b render
    # the unnumbered final file is the continued run's last epoch
    viv = tmp_path / "vivienne"
    for d in ("2026-10-11_sweep_v2b-asset/ep00", "2026-10-11_sweep_v2b-asset/ep04", "dense_vivienne_v2b_asset/ep04"):
        (viv / d).mkdir(parents=True)
    lock = {"file": "vivienne_v2b.safetensors", "epoch": 28}
    assert L.lock_render_dir(viv / "2026-10-11_sweep_v2b-asset", "vivienne", lock) == viv / "2026-10-11_sweep_v2b-asset" / "ep04"
    assert L.lock_render_dir(viv / "dense_vivienne_v2b_asset", "vivienne", lock) == viv / "dense_vivienne_v2b_asset" / "ep04"
    assert L.lock_render_dir(viv / "2026-10-11_sweep_v2b-asset", "vivienne", {"file": "vivienne_v2-000030.safetensors", "epoch": 30}) is None


def test_a_prune_leaves_every_page_and_render_answer_unchanged(locked_world, tmp_path, monkeypatch):
    """2026-10-15: the prune ran clean and the queue page then said vivienne was
    never trained and thirteen locked characters were never swept. A prune may
    delete only what no surface needs: afterwards the page's lists, the render's
    LoRA answer and the lock verify must all read exactly as before."""
    import json

    from sourcemode.assets.lora import resolve_lora
    from sourcemode.monitor.queue_page import candidates, sweepable
    from sourcemode.train import locked as LK

    cfg, out, judge, ck, stray = locked_world
    cfg["assets"] = {"judge": str(judge)}
    cfg["train"] = {"previews": str(tmp_path / "train-previews")}
    # zara_v2 approved, the way the engine writes it; she is trained (locked), so not a candidate
    root = tmp_path / "train-previews"
    (root / "previews").mkdir(parents=True)
    (root / "approvals").mkdir()
    (root / "previews" / "zara_v2.json").write_text(json.dumps({"id": "zara_v2", "fingerprint": "fp", "n": 1, "images": [{"id": "a"}]}), encoding="utf-8")
    (root / "approvals" / "zara_v2.json").write_text(json.dumps({"approved": True, "fingerprint": "fp", "at": "2026-10-01T00:00:00+00:00"}), encoding="utf-8")
    monkeypatch.setattr("sourcemode.monitor.queue_page.character_of", lambda ds: ds.split("_")[0])

    before = (candidates(cfg), sweepable(cfg), resolve_lora(cfg, "zara"), LK.verify(cfg))
    assert before[0] == [] and before[1] == [] and before[2]["path"] == str(Path("sourcemode") / "zara.safetensors")
    log = L.prune_apply(cfg, L.prune_plan(cfg, out, judge), judge)
    after = (candidates(cfg), sweepable(cfg), resolve_lora(cfg, "zara"), LK.verify(cfg))
    assert after == before
    assert log[-1] == "AFTER: every locked LoRA verifies"
    # the sweep's emptied staging folder is gone; the flat lock is not
    assert not (Path(cfg["comfyui"]["loras_dir"]) / "sourcemode" / "zara_v2").exists()
    assert (Path(cfg["comfyui"]["loras_dir"]) / "sourcemode" / "zara.safetensors").is_file()
