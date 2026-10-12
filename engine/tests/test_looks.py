"""The 28-look plan drafted and approved from the Characters tab (2026-10-12).

Ash had a job, a style and a locked LoRA and the asset pack was still greyed
out, because the plan file it needs had no way to come into being from the
monitor. The draft must give 28 editable lines in the pack's categories, the
work looks must be HER job outfit, and approving must produce exactly the file
`blocked_shoots` looks for - and refuse while a line is blank.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sourcemode.assets import looks as L
from sourcemode.assets import wardrobe as W
from sourcemode.assets.catalog import PACK_28


@pytest.fixture
def ash(monkeypatch):
    rec = {"style": "edgy", "palette": "black and denim blue as the base, one hot accent - cobalt, burnt orange, red",
           "avoid": "", "outfits": {"everyday": "cropped tops over denim", "workout": "bright sports bra"},
           "jobs": [{"job": "Waitress at Obsidian", "outfit": "a short black shirt-dress uniform", "places": []},
                    {"job": "", "outfit": "", "places": []}],
           "hair": [], "note": "", "draft": False}
    monkeypatch.setattr(W, "editable", lambda c: rec if c == "ash" else {
        **rec, "jobs": [{"job": "", "outfit": "", "places": []}] * 2, "palette": ""})
    monkeypatch.setattr(W, "hair_options", lambda c: ("her hair worn loose", "her hair in a bun"))
    monkeypatch.setattr(L, "shipped", lambda c: {"casual": 7, "work": 5} if c == "ash" else {})
    monkeypatch.setattr(L, "reference", lambda c: None)
    return rec


def test_palette_colours_are_read_from_prose_longest_first():
    assert L.palette_colours("black and denim blue as the base, with one hot accent - cobalt, burnt orange, red") == (
        "black", "denim blue", "cobalt", "burnt orange", "red")
    assert L.palette_colours("") == L.DEFAULT_COLOURS
    assert L.palette_colours("whatever she likes") == L.DEFAULT_COLOURS


def test_draft_is_28_looks_in_the_pack_categories_coloured_from_her_palette(ash):
    d = L.draft_looks("ash")
    assert {k: len(v) for k, v in d.items()} == PACK_28
    assert sum(len(v) for v in d.values()) == 28
    colours = set(L.palette_colours(ash["palette"]))
    for cat, looks in d.items():
        if cat == "work":
            continue
        for lk in looks:
            assert any(c in lk["outfit"] for c in colours), lk
            assert lk["hair"] in ("her hair worn loose", "her hair in a bun")
    # work is her uniform, verbatim, on every work look
    assert {lk["outfit"] for lk in d["work"]} == {"a short black shirt-dress uniform"}
    # deterministic per character, different between characters
    assert L.draft_looks("ash") == d
    assert L.draft_looks("zoe")["casual"] != d["casual"]


def test_no_job_outfit_leaves_the_work_looks_blank(ash):
    assert all(lk["outfit"] == "" for lk in L.draft_looks("zoe")["work"])


def _cfg(tmp_path: Path) -> dict:
    return {"paths": {"outputs": str(tmp_path / "out"), "library": str(tmp_path / "lib")}}


def test_draft_extends_her_shipped_looks_and_approve_writes_the_pack_plan(tmp_path, ash, monkeypatch):
    cfg = _cfg(tmp_path)
    from sourcemode.assets import lora as LORA
    monkeypatch.setattr(LORA, "resolve_lora", lambda cfg, c: {
        "path": "sourcemode\\ash_v2\\ash_v2-000017.safetensors", "epoch": 17, "name": "x", "why": ""})
    src = tmp_path / "lib" / "ash" / "2026-09-25_sweep_v2" / "ep17"
    src.mkdir(parents=True)
    (src / "scene_00.png").write_bytes(b"png")

    assert L.state(cfg, "ash")["state"] == "none"
    st = L.draft(cfg, "ash")
    assert st["state"] == "draft" and st["blank"] == 0
    ids = [lk["id"] for c in st["categories"] for lk in c["looks"]]
    assert "casual_08" in ids and "casual_01" not in ids     # 7 shipped -> 8..14
    assert "work_06" in ids and "workout_01" in ids
    assert L.draft_path(Path(cfg["paths"]["outputs"]), "ash").is_file()
    assert not L.approved_path(Path(cfg["paths"]["outputs"]), "ash").is_file()
    # the guide line shows what her record says for that category
    casual = next(c for c in st["categories"] if c["key"] == "casual")
    assert casual["guide"] == "cropped tops over denim"
    assert next(c for c in st["categories"] if c["key"] == "work")["guide"] == "a short black shirt-dress uniform"

    # his edit lands in the draft
    st = L.save(cfg, "ash", {"all": [{"id": "casual_08", "outfit": "a cobalt moto jacket over a black cami",
                                      "hair": "her hair worn loose"}]})
    got = next(lk for c in st["categories"] for lk in c["looks"] if lk["id"] == "casual_08")
    assert got["outfit"] == "a cobalt moto jacket over a black cami"

    # a blank refuses approval, by name
    L.save(cfg, "ash", {"all": [{"id": "work_06", "outfit": "", "hair": "her hair worn loose"}]})
    with pytest.raises(ValueError, match="work_06"):
        L.approve(cfg, "ash")
    L.save(cfg, "ash", {"all": [{"id": "work_06", "outfit": "the uniform", "hair": "her hair worn loose"}]})

    st = L.approve(cfg, "ash")
    assert st["state"] == "approved" and st["approved_at"]
    plan_file = Path(cfg["paths"]["outputs"]) / "game-assets" / "ash" / "plan_28.json"
    assert plan_file.is_file()
    assert not L.draft_path(Path(cfg["paths"]["outputs"]), "ash").is_file()
    doc = json.loads(plan_file.read_text(encoding="utf-8"))
    assert doc["lora"].endswith("ash_v2-000017.safetensors")
    assert doc["source_asset"].endswith("scene_00.png")
    assert sum(b["lookCount"] for b in doc["categories"].values()) == 28

    # and that is the exact file the shoots tab's guard looks for
    from sourcemode.assets.lora import blocked_shoots
    assert "pack28" not in blocked_shoots(cfg, "ash")


def test_approve_refuses_without_a_render_to_condition_on(tmp_path, ash, monkeypatch):
    cfg = _cfg(tmp_path)
    from sourcemode.assets import lora as LORA
    monkeypatch.setattr(LORA, "resolve_lora", lambda cfg, c: {"path": "x", "epoch": 17, "name": "x", "why": ""})
    L.draft(cfg, "ash")
    with pytest.raises(ValueError, match="epoch 17"):
        L.approve(cfg, "ash")
    assert L.state(cfg, "ash")["state"] == "draft"
