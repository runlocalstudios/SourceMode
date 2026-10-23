"""The pack through T2I, the staging, and the approval that writes into the game.

Jeremy, 2026-10-14: "We'll just move forward with T2I because it performs
better. That way, anything rejected gets regenerated and anything accepted
goes into queue for processing and placement into the game repo. I would
like a formal approval step of that final shift though."
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from sourcemode.assets import pack as P
from sourcemode.assets.judge import make_set, record_verdict


def _plan(character="amanda"):
    cats = {"casual": {"looks": [{"id": "casual_01", "look": 1, "outfit": "a red tee", "hair": "loose"},
                                 {"id": "casual_02", "look": 2, "outfit": "a blue tee", "hair": "loose"}]}}
    return {"character": character, "pose": "standing", "categories": cats, "trigger": character}


class FakeClient:
    def __init__(self):
        self.seen = []

    def submit(self, wf):
        self.seen.append(wf); return f"p{len(self.seen)}"

    def wait(self, pid, timeout_s=0):
        return {"outputs": {"9": {"images": [{"filename": f"{pid}.png", "type": "output"}]}}}

    def outputs(self, entry):
        return [f for o in entry["outputs"].values() for f in o["images"]]

    def fetch(self, desc, dest):
        Image.new("RGB", (16, 24), (200, 10, 10)).save(dest); return dest


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr("sourcemode.assets.render.shot_prompt", lambda c, s, t=None, backdrop=None: f"{c} {s['outfit']} {backdrop}")
    monkeypatch.setattr("sourcemode.assets.render.t2i_workflow",
                        lambda cfg, prompt, seed, prefix, **kw: {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "seed": seed}}})
    monkeypatch.setattr("sourcemode.assets.render.pose_fields", lambda c, s: {"asked": {"crop": "upper-thigh-up"}})
    monkeypatch.setattr("sourcemode.assets.adherence.measure", lambda p: {})
    monkeypatch.setattr("sourcemode.assets.adherence.check", lambda asked, got: {"failed": [], "soft": [], "got": {}})
    monkeypatch.setattr("sourcemode.gates.identity.embed_image", lambda p: None)


def test_the_pack_renders_every_look_once_on_the_grey_studio_and_sets_edit_renders_aside(tmp_path, quiet):
    out = tmp_path / "out"
    root = P.renders_root(out, "amanda")
    # an Edit pack's folder is there already: a plate and a sidecar with no graph
    (root / "casual_01_standing").mkdir(parents=True)
    (root / "casual_01_standing" / "shot_00_s7100.json").write_text(json.dumps({"source": "x"}))
    (root / "_plate.png").write_bytes(b"")
    assert P.is_t2i_folder(root) is False
    client = FakeClient()
    metas = P.render_pack({}, client, "amanda", _plan(), out, lora_path="l", negative="n", log=lambda s: None)
    assert [m["asset"]["look"] for m in metas] == [1, 2] and all(m["graph"] == P.GRAPH for m in metas)
    assert metas[0]["seed"] == P.SEED_BASE and metas[1]["seed"] == P.SEED_BASE + 1000
    assert all(P.STUDIO_BACKDROP in m["prompt"] for m in metas)
    assert P.is_t2i_folder(root) is True
    aside = [d for d in root.parent.iterdir() if d.name.startswith("renders_edit_")]
    assert len(aside) == 1 and (aside[0] / "_plate.png").is_file()
    assert len(P.shots(root)) == 2
    # a second run renders nothing: the shots are on disk
    n = len(client.seen)
    P.render_pack({}, client, "amanda", _plan(), out, lora_path="l", negative="n", log=lambda s: None)
    assert len(client.seen) == n
    # a look rewritten since its shot was rendered renders again; the other is kept
    plan = _plan()
    plan["categories"]["casual"]["looks"][0]["outfit"] = "a green tee"
    metas = P.render_pack({}, client, "amanda", plan, out, lora_path="l", negative="n", log=lambda s: None)
    assert len(client.seen) == n + 1 and "a green tee" in metas[0]["prompt"]
    assert P.rendered_prompt(Path(metas[0]["source"])) == metas[0]["prompt"]
    n = len(client.seen)
    # a re-roll of one look with a retry seed renders only that look on that seed
    (root / "casual_02_standing" / "shot_00_s8100.png").unlink()
    metas = P.render_pack({}, client, "amanda", _plan(), out, lora_path="l", negative="n",
                          only={"casual_02"}, seed=424242, log=lambda s: None)
    assert len(metas) == 1 and metas[0]["seed"] == 424242 and metas[0]["source"].endswith("shot_00_s424242.png")


def test_processing_is_due_only_when_every_look_is_kept_and_not_staged_since(tmp_path):
    jr, out = tmp_path / "judge", tmp_path / "out"
    imgs = []
    for i in range(2):
        p = tmp_path / f"s{i}.png"; Image.new("RGB", (8, 8)).save(p); imgs.append(p)
    items = [{"id": f"casual_0{i+1}", "path": p, "arm": "casual", "group": str(i)} for i, p in enumerate(imgs)]
    make_set(jr, "pack_amanda", "Amanda - pack", items, meta={"character": "amanda", "shoot": "pack28"})
    make_set(jr, "shoot_amanda_club", "Amanda - club", items, meta={"character": "amanda", "shoot": "club"})
    assert P.process_due(jr, out, "pack_amanda") is None                 # unjudged
    record_verdict(jr, "pack_amanda", "casual_01", "keep")
    record_verdict(jr, "pack_amanda", "casual_02", "reject")
    assert P.process_due(jr, out, "pack_amanda") is None                 # a reject is open
    record_verdict(jr, "pack_amanda", "casual_02", "keep")
    assert P.process_due(jr, out, "pack_amanda") == "all 2 looks kept"
    for i in items:
        record_verdict(jr, "shoot_amanda_club", i["id"], "keep")
    assert P.process_due(jr, out, "shoot_amanda_club") is None           # not a pack
    # staged from these verdicts: not due again until a verdict changes
    vp = jr / "verdicts" / "pack_amanda.json"
    (out / "game-assets" / "amanda").mkdir(parents=True)
    P.staged_path(out, "amanda").write_text(json.dumps({"files": ["x"], "verdicts_mtime": vp.stat().st_mtime}))
    assert P.process_due(jr, out, "pack_amanda") is None
    P.staged_path(out, "amanda").write_text(json.dumps({"files": ["x"], "verdicts_mtime": vp.stat().st_mtime - 100}))
    assert P.process_due(jr, out, "pack_amanda") == "all 2 looks kept"


def test_the_compare_sheet_counts_what_the_game_would_lose_and_ship_is_the_only_write(tmp_path):
    out, game = tmp_path / "out", tmp_path / "game"
    staged = out / "game-assets" / "amanda" / "outfits"; staged.mkdir(parents=True)
    gdir = game / "src" / "assets" / "characters" / "amanda" / "outfits"; gdir.mkdir(parents=True)
    for n in ("casual_01_standing.webp", "casual_02_standing.webp"):
        Image.new("RGBA", (16, 24), (0, 200, 0, 255)).save(staged / n, "WEBP")
    Image.new("RGBA", (16, 24), (0, 0, 200, 255)).save(gdir / "casual_01_standing.webp", "WEBP")
    mapping = {"character": "amanda", "slots": [{"id": "casual_01", "file": "casual_01_standing.webp"},
                                                {"id": "casual_02", "file": "casual_02_standing.webp"}]}
    sheet, overwrite = P.compare_sheet(mapping, staged, gdir, out / "game-assets" / "amanda" / "review" / "compare.jpg")
    assert sheet.is_file() and overwrite == 1
    with pytest.raises(ValueError):
        P.ship(out, "amanda", game)                                        # nothing staged
    P.staged_path(out, "amanda").write_text(json.dumps({"files": [s["file"] for s in mapping["slots"]], "set": "pack_amanda"}))
    (out / "game-assets" / "amanda" / "plan_28.json").write_text(json.dumps({"character": "amanda"}))
    rec = P.ship(out, "amanda", game)
    assert rec["overwrote"] == 1 and sorted(rec["files"]) == ["casual_01_standing.webp", "casual_02_standing.webp"]
    assert (gdir / "casual_02_standing.webp").is_file()
    assert Image.open(gdir / "casual_01_standing.webp").convert("RGBA").getpixel((0, 0))[1] > 150   # overwritten (lossy webp)
    assert P.read_staged(out, "amanda")["shipped"]["overwrote"] == 1
    assert json.loads((out / "game-assets" / "amanda" / "plan_28.json").read_text())["shipped"]["files"]
    assert P.discard(out, "amanda") is True and P.discard(out, "amanda") is False


def test_ship_copies_only_the_ticked_looks_and_the_pairs_say_what_each_stands_against(tmp_path):
    """Jeremy, 2026-10-22: approve all by default, "but I would like an option
    to choose which one to keep from the side-by-side sets ... whichever is not
    checked would be ignored". An unticked look leaves the game's file as it
    was; a name that is not staged, or nothing ticked, refuses."""
    out, game = tmp_path / "out", tmp_path / "game"
    staged = out / "game-assets" / "amanda" / "outfits"; staged.mkdir(parents=True)
    gdir = game / "src" / "assets" / "characters" / "amanda" / "outfits"; gdir.mkdir(parents=True)
    files = ["casual_01_standing.webp", "casual_02_standing.webp", "work_01_standing.webp"]
    for n in files:
        Image.new("RGBA", (16, 24), (0, 200, 0, 255)).save(staged / n, "WEBP")
    for n in ("casual_01_standing.webp", "casual_02_standing.webp"):
        Image.new("RGBA", (16, 24), (0, 0, 200, 255)).save(gdir / n, "WEBP")
    P.staged_path(out, "amanda").write_text(json.dumps({"files": files, "set": "pack_amanda"}))
    assert P.pairs(out, "amanda", game) == [
        {"id": "casual_01", "file": files[0], "game": files[0], "overwrites": True},
        {"id": "casual_02", "file": files[1], "game": files[1], "overwrites": True},
        {"id": "work_01", "file": files[2], "game": None, "overwrites": False}]
    with pytest.raises(ValueError):
        P.ship(out, "amanda", game, keep=["nope.webp"])
    with pytest.raises(ValueError):
        P.ship(out, "amanda", game, keep=[])
    assert not (gdir / "work_01_standing.webp").exists()                 # a refusal wrote nothing
    rec = P.ship(out, "amanda", game, keep=[files[0], files[2]])
    assert rec["files"] == [files[0], files[2]] and rec["overwrote"] == 1 and rec["skipped"] == [files[1]]
    assert Image.open(gdir / files[0]).convert("RGBA").getpixel((0, 0))[1] > 150   # ticked: the new one
    assert Image.open(gdir / files[1]).convert("RGBA").getpixel((0, 0))[2] > 150   # unticked: as the game had it
    assert (gdir / files[2]).is_file()
    assert P.read_staged(out, "amanda")["shipped"]["skipped"] == [files[1]]
    # the tile is a small RGBA copy cached under review/, never beside the game's files
    cut = Image.new("RGBA", (16, 24), (0, 0, 0, 0)); cut.putpixel((8, 12), (0, 200, 0, 255))
    cut.save(staged / "casual_03_standing.webp", "WEBP", lossless=True)
    t = P.thumb(staged / "casual_03_standing.webp", out, "amanda", "new")
    assert t.is_relative_to(out / "game-assets" / "amanda" / "review")
    assert Image.open(t).convert("RGBA").getpixel((0, 0))[3] == 0            # the transparency survives
    assert not list(gdir.glob("_*"))


def test_the_compare_sheet_shows_her_current_look_when_the_plan_numbers_on(tmp_path):
    """Jeremy, 2026-10-20, on gabi: the compare sheet "showed completely blank for
    the current game assets ... even though there are current game assets for
    her". Her plan numbered on from the 28 in the game (casual_08..), so no
    staged name matched a game file. Each new look now sits beside her look in
    the same category at the same position; a matching name still counts as an
    overwrite."""
    staged = tmp_path / "staged"; staged.mkdir()
    gdir = tmp_path / "game"; gdir.mkdir()
    for n in ("casual_08_standing.webp", "casual_09_standing.webp", "work_06_standing.webp", "work_07_standing.webp"):
        Image.new("RGBA", (16, 24), (0, 200, 0, 255)).save(staged / n, "WEBP")
    for n in ("casual_01_standing.webp", "casual_02_standing.webp", "work_06_standing.webp"):
        Image.new("RGBA", (16, 24), (0, 0, 200, 255)).save(gdir / n, "WEBP")
    slots = [{"id": i, "file": f"{i}_standing.webp"} for i in ("casual_08", "casual_09", "work_06", "work_07")]
    assert P.game_counterpart(slots[0], 0, "standing", gdir).name == "casual_01_standing.webp"
    assert P.game_counterpart(slots[1], 1, "standing", gdir).name == "casual_02_standing.webp"
    assert P.game_counterpart(slots[2], 0, "standing", gdir).name == "work_06_standing.webp"   # the same name wins
    assert P.game_counterpart(slots[3], 1, "standing", gdir).name == "work_06_standing.webp"   # her only work look
    assert P.game_counterpart({"id": "workout_05", "file": "workout_05_standing.webp"}, 0, "standing", gdir) is None
    assert P.game_counterpart(slots[0], 0, "standing", tmp_path / "nowhere") is None
    sheet, overwrite = P.compare_sheet({"character": "gabi", "pose": "standing", "slots": slots},
                                       staged, gdir, tmp_path / "review" / "compare.jpg")
    assert sheet.is_file() and overwrite == 1


def test_the_characters_state_carries_the_staging_and_the_queue_hook_adds_one_cpu_job(tmp_path, monkeypatch):
    from sourcemode.assets import looks as L
    from sourcemode.monitor.queue_page import queue_process_if_ready

    out, jr = tmp_path / "out", tmp_path / "out" / "judge"
    cfg = {"paths": {"outputs": str(out), "judge": str(jr)}}
    monkeypatch.setattr("sourcemode.config.outputs_dir", lambda c: out)
    monkeypatch.setattr("sourcemode.assets.judge.judge_root", lambda c: jr)
    monkeypatch.setattr("sourcemode.assets.wardrobe.editable", lambda c: {"jobs": [], "outfits": {}})
    monkeypatch.setattr(L, "shipped", lambda c: {})
    monkeypatch.setattr(L, "GAME_ROOT", tmp_path / "game")
    home = out / "game-assets" / "amanda"; home.mkdir(parents=True)
    (home / "plan_28.json").write_text(json.dumps({**_plan(), "approved": "2026-10-14T00:00:00"}))
    st = L.state(cfg, "amanda")
    assert st["state"] == "approved" and st["staged"] is None
    img = tmp_path / "s.png"; Image.new("RGB", (8, 8)).save(img)
    items = [{"id": "casual_01", "path": img, "arm": "casual", "group": "1"}]
    make_set(jr, "pack_amanda", "x", items, meta={"character": "amanda", "shoot": "pack28"})
    assert queue_process_if_ready(cfg, "pack_amanda") is None
    record_verdict(jr, "pack_amanda", "casual_01", "keep")
    job = queue_process_if_ready(cfg, "pack_amanda")
    assert job and job["kind"] == "process" and job["lane"] == "cpu" and "process_pack.py" in job["cmd"][1]
    assert queue_process_if_ready(cfg, "pack_amanda") is None            # already queued
    sheet = home / "review" / "compare_game.jpg"; sheet.parent.mkdir(); Image.new("RGB", (8, 8)).save(sheet)
    P.staged_path(out, "amanda").write_text(json.dumps({"at": "2026-10-14T01:00:00", "n": 1, "missing": [],
                                                       "files": ["casual_01_standing.webp"], "would_overwrite": 0,
                                                       "set": "pack_amanda", "sheets": {"compare": str(sheet)}}))
    st = L.state(cfg, "amanda")
    assert st["staged"]["n"] == 1 and st["staged"]["sheets"] == ["compare"] and st["staged"]["shipped"] is None
    assert st["staged"]["looks"] == [{"id": "casual_01", "file": "casual_01_standing.webp", "game": None, "overwrites": False}]
    assert L.look_tile(cfg, "amanda", "casual_01_standing.webp", "new") is None     # no cutout on disk yet
    assert L.look_tile(cfg, "amanda", "../plan_28.json", "new") is None
    assert L.sheet_path(cfg, "amanda", "compare") == sheet and L.sheet_path(cfg, "amanda", "mapping") is None


def test_a_key_backdrop_trial_renders_into_its_own_root_and_never_the_packs(tmp_path, quiet):
    out = tmp_path / "out"
    trial = tmp_path / "trial" / "renders"
    client = FakeClient()
    metas = P.render_pack({}, client, "amanda", _plan(), out, lora_path="l", negative="n",
                          backdrop="a flat magenta key", root=trial, log=lambda s: None)
    assert len(metas) == 2 and all("a flat magenta key" in m["prompt"] for m in metas)
    assert all(Path(m["source"]).is_relative_to(trial) for m in metas)
    assert not P.renders_root(out, "amanda").exists()
    # the pack itself is unchanged: the studio backdrop, its own root
    metas = P.render_pack({}, client, "amanda", _plan(), out, lora_path="l", negative="n", log=lambda s: None)
    assert all(P.STUDIO_BACKDROP in m["prompt"] for m in metas)
    assert all(Path(m["source"]).is_relative_to(P.renders_root(out, "amanda")) for m in metas)


def test_a_fresh_shot_framed_wrong_is_redrawn_in_the_same_job(tmp_path, quiet, monkeypatch):
    """Jeremy, 2026-10-20: "reroll those before the queue moves on to the next
    thing when they are wrong". casual_01's first draw is chest-up; its second
    seed is fine and replaces it. casual_02 never comes right and keeps its
    first draw after REROLLS tries, for him to judge."""
    bad = {P.SEED_BASE, *(P.SEED_BASE + 1000 + P.REROLL_STRIDE * k for k in range(P.REROLLS + 1))}
    monkeypatch.setattr(P, "framing_problem",
                        lambda asked, got, p: "chest-up" if int(p.stem.split("_s")[1]) in bad else None)
    out = tmp_path / "out"
    client = FakeClient()
    metas = P.render_pack({}, client, "amanda", _plan(), out, lora_path="l", negative="n", log=lambda s: None)
    assert metas[0]["seed"] == P.SEED_BASE + P.REROLL_STRIDE
    assert metas[1]["seed"] == P.SEED_BASE + 1000                 # the first draw is the fallback
    assert len(client.seen) == 2 + 1 + P.REROLLS        # casual_01 twice, casual_02 every try
    root = P.renders_root(out, "amanda")
    assert [p.name for p in sorted((root / "casual_01_standing").glob("shot_*.png"))] == [f"shot_00_s{P.SEED_BASE + P.REROLL_STRIDE}.png"]
    assert len(list((root / "casual_02_standing").glob("shot_*.png"))) == 1
    # a shot already on disk is never redrawn: it may already be judged
    n = len(client.seen)
    P.render_pack({}, client, "amanda", _plan(), out, lora_path="l", negative="n", log=lambda s: None)
    assert len(client.seen) == n


def test_touches_top_reads_a_head_cut_off_at_the_top_edge(tmp_path):
    import numpy as np
    a = np.full((60, 400, 3), 185, np.uint8)
    a[:6] = 175                                   # the studio darkens toward the top
    clean = tmp_path / "clean.png"; Image.fromarray(a).save(clean)
    a[:30, 170:240] = (90, 60, 40)                # hair running off the top
    cut = tmp_path / "cut.png"; Image.fromarray(a).save(cut)
    assert not P.touches_top(clean) and P.touches_top(cut)


def test_the_profile_pick_writes_one_rgb_webp_into_portraits_and_records_which_photo(tmp_path):
    """Jeremy, 2026-10-23: the game shows portraits/profile.webp as her profile
    picture; pick it from her reference photos, "only one". The pick converts
    the photo to an RGB WebP at its own size, replaces what is there, leaves
    nothing else in the folder, and the state names the photo it came from."""
    out, game = tmp_path / "out", tmp_path / "game"
    refs = tmp_path / "refs"; refs.mkdir()
    Image.new("RGBA", (30, 45), (200, 0, 0, 255)).save(refs / "zara_portrait1.png")
    Image.new("RGB", (32, 48), (0, 0, 200)).save(refs / "zara_portrait2.jpg")
    assert P.portrait_state(out, "zara", game) == {"game": False, "from": None, "at": None}
    with pytest.raises(ValueError):
        P.ship_portrait(out, "zara", game, refs / "missing.png")
    rec = P.ship_portrait(out, "zara", game, refs / "zara_portrait1.png")
    dest = P.portrait_path(game, "zara")
    assert rec["from"] == "zara_portrait1.png" and rec["overwrote"] is False and rec["size"] == [30, 45]
    im = Image.open(dest)
    assert im.format == "WEBP" and im.mode == "RGB" and im.size == (30, 45) and im.getpixel((0, 0))[0] > 150
    assert [p.name for p in dest.parent.iterdir()] == ["profile.webp"]       # no tmp, no cache beside it
    st = P.portrait_state(out, "zara", game)
    assert st["game"] and st["from"] == "zara_portrait1.png"
    rec = P.ship_portrait(out, "zara", game, refs / "zara_portrait2.jpg")
    assert rec["overwrote"] is True and Image.open(dest).getpixel((0, 0))[2] > 150
    assert P.portrait_state(out, "zara", game)["from"] == "zara_portrait2.jpg"
    # a file put there some other way is not the recorded pick
    Image.new("RGB", (8, 12)).save(dest, "WEBP")
    import os
    os.utime(dest, (dest.stat().st_atime, dest.stat().st_mtime + 60))
    assert P.portrait_state(out, "zara", game) == {"game": True, "from": None, "at": None}
    # the small copy for the card lives under outputs, never in the game folder
    t = P.thumb(dest, out, "zara", "portrait")
    assert t.is_relative_to(out / "game-assets" / "zara" / "review")
    assert [p.name for p in dest.parent.iterdir()] == ["profile.webp"]
