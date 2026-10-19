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


def test_the_characters_state_carries_the_staging_and_the_queue_hook_adds_one_cpu_job(tmp_path, monkeypatch):
    from sourcemode.assets import looks as L
    from sourcemode.monitor.queue_page import queue_process_if_ready

    out, jr = tmp_path / "out", tmp_path / "out" / "judge"
    cfg = {"paths": {"outputs": str(out), "judge": str(jr)}}
    monkeypatch.setattr("sourcemode.config.outputs_dir", lambda c: out)
    monkeypatch.setattr("sourcemode.assets.judge.judge_root", lambda c: jr)
    monkeypatch.setattr("sourcemode.assets.wardrobe.editable", lambda c: {"jobs": [], "outfits": {}})
    monkeypatch.setattr(L, "shipped", lambda c: {})
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
    assert L.sheet_path(cfg, "amanda", "compare") == sheet and L.sheet_path(cfg, "amanda", "mapping") is None
