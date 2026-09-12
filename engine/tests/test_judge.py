"""Blind judge: manifests hide the arm, verdicts persist, the tally is per arm."""

import json
from pathlib import Path

import pytest
from PIL import Image

from sourcemode.assets.judge import (
    item_path, list_sets, load_set, make_set, record_verdict, set_payload, summary,
)


def make_items(tmp_path: Path, arms=("A", "B"), n=3):
    items = []
    for a in arms:
        for i in range(n):
            p = tmp_path / "img" / f"{a}_{i}.png"; p.parent.mkdir(exist_ok=True)
            Image.new("RGB", (8, 8), (10, 20, 30)).save(p)
            items.append({"id": f"{a}_{i}", "path": p, "arm": a, "group": str(i)})
    return items


def test_make_set_shuffles_deterministically_and_payload_hides_arms(tmp_path: Path):
    items = make_items(tmp_path)
    make_set(tmp_path, "exp", "An experiment", items, seed=3, question="her?")
    s = load_set(tmp_path, "exp")
    assert sorted(s["order"]) == sorted(it["id"] for it in items) and s["order"] != [it["id"] for it in items]
    make_set(tmp_path, "exp", "An experiment", items, seed=3)
    assert load_set(tmp_path, "exp")["order"] == s["order"]                      # same seed, same blind order
    p = set_payload(tmp_path, "exp")
    assert [i["id"] for i in p["items"]] == s["order"] and p["has_reference"] is False
    assert all(set(i) == {"id"} for i in p["items"])                            # no arm, no path
    with pytest.raises(ValueError):
        make_set(tmp_path, "dup", "x", items + [items[0]])


def test_item_path_only_from_manifest(tmp_path: Path):
    items = make_items(tmp_path)
    make_set(tmp_path, "exp", "t", items)
    assert item_path(tmp_path, "exp", "A_0") == items[0]["path"]
    assert item_path(tmp_path, "exp", "../secret") is None
    assert item_path(tmp_path, "../exp", "A_0") is None and load_set(tmp_path, "nope") is None


def test_verdicts_persist_and_summarise_per_arm(tmp_path: Path):
    items = make_items(tmp_path)
    make_set(tmp_path, "exp", "t", items, priority=1)
    record_verdict(tmp_path, "exp", "A_0", "keep"); record_verdict(tmp_path, "exp", "A_1", "reject")
    record_verdict(tmp_path, "exp", "B_0", "reject"); record_verdict(tmp_path, "exp", "B_1", "keep")
    record_verdict(tmp_path, "exp", "B_1", None)                                  # undo
    v = json.loads((tmp_path / "verdicts" / "exp.json").read_text())
    assert v == {"A_0": "keep", "A_1": "reject", "B_0": "reject"}
    s = summary(tmp_path, "exp")
    assert s["arms"] == [{"arm": "A", "n": 3, "judged": 2, "keep": 1, "rate": 0.5},
                         {"arm": "B", "n": 3, "judged": 1, "keep": 0, "rate": 0.0}]
    assert s["groups"]["0"] == {"A": "keep", "B": "reject"}
    assert list_sets(tmp_path) == [{"id": "exp", "title": "t", "question": "", "priority": 1, "n": 6, "judged": 3}]
    with pytest.raises(ValueError):
        record_verdict(tmp_path, "exp", "A_0", "meh")
    with pytest.raises(KeyError):
        record_verdict(tmp_path, "exp", "Z_9", "keep")


def test_router_serves_page_files_and_verdicts(tmp_path: Path):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from sourcemode.assets.judge import judge_router

    items = make_items(tmp_path); make_set(tmp_path, "exp", "t", items, reference=items[0]["path"])
    app = FastAPI(); app.include_router(judge_router({"assets": {"judge": str(tmp_path)}}))
    c = TestClient(app)
    assert "SourceMode judge" in c.get("/judge").text
    assert c.get("/judge/sets").json()[0]["n"] == 6
    assert c.get("/judge/file", params={"set": "exp", "id": "A_0"}).status_code == 200
    assert c.get("/judge/file", params={"set": "exp", "id": "nope"}).status_code == 404
    assert c.get("/judge/ref", params={"set": "exp"}).status_code == 200
    assert c.post("/judge/set/exp/verdict", json={"item": "A_0", "verdict": "keep"}).json() == {"A_0": "keep"}
    assert c.post("/judge/set/exp/verdict", json={"item": "A_0", "verdict": "meh"}).status_code == 400
    assert c.get("/judge/set/exp/summary").json()["arms"][0]["keep"] == 1
