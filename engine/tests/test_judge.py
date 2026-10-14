"""Blind judge: manifests hide the arm, verdicts persist, the tally is per arm."""

import json
from pathlib import Path

import pytest
from PIL import Image

from sourcemode.assets.judge import (
    item_path, list_sets, load_set, load_verdicts, make_set, record_verdict, set_payload,
    summary,
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
    # `sub`/`status`/`group` are what the one picker shows instead of a bare
    # count; they are derived, so they are asserted alongside the counts.
    assert list_sets(tmp_path) == [{"id": "exp", "title": "t", "question": "", "priority": 1,
                                    "n": 6, "judged": 3, "done": False,
                                    "sub": "3 of 6 judged · 3 left",
                                    "status": "you", "group": "progress"}]
    with pytest.raises(ValueError):
        record_verdict(tmp_path, "exp", "A_0", "meh")
    with pytest.raises(KeyError):
        record_verdict(tmp_path, "exp", "Z_9", "keep")


def test_rebuilding_a_set_forgets_verdicts_whose_image_changed(tmp_path: Path):
    """A verdict must not survive its image being replaced under the same id.

    Verdicts are keyed by item id and sets get regenerated in place, so without
    this a re-render silently inherits the last run's judgements.
    """
    items = make_items(tmp_path)
    make_set(tmp_path, "exp", "t", items)
    record_verdict(tmp_path, "exp", "A_0", "keep")
    record_verdict(tmp_path, "exp", "A_1", "reject")
    record_verdict(tmp_path, "exp", "B_0", "keep")

    Image.new("RGB", (8, 8), "red").save(items[0]["path"])        # A_0 re-rendered
    make_set(tmp_path, "exp", "t", items)

    assert load_verdicts(tmp_path, "exp") == {"A_1": "reject", "B_0": "keep"}

    # unchanged images keep theirs across any number of rebuilds
    make_set(tmp_path, "exp", "t", items)
    assert load_verdicts(tmp_path, "exp") == {"A_1": "reject", "B_0": "keep"}


def test_legacy_manifest_without_hashes_keeps_its_verdicts(tmp_path: Path):
    """Pre-hash manifests carry no digest, so there is nothing to compare.

    Dropping those verdicts would discard real judging work on the strength of a
    guess, so absence of a prior hash means leave it alone.
    """
    items = make_items(tmp_path)
    make_set(tmp_path, "exp", "t", items)
    record_verdict(tmp_path, "exp", "A_0", "keep")
    m = tmp_path / "sets" / "exp.json"
    d = json.loads(m.read_text())
    for it in d["items"]:
        it.pop("hash")
    m.write_text(json.dumps(d))

    Image.new("RGB", (8, 8), "red").save(items[0]["path"])
    make_set(tmp_path, "exp", "t", items)
    assert load_verdicts(tmp_path, "exp") == {"A_0": "keep"}


def test_unfinished_sets_sort_above_complete_ones(tmp_path: Path):
    """The list is ordered by what still needs work, not by priority alone.

    Started-but-unfinished leads (most complete first), then untouched, then done.
    Priority only breaks ties inside a band, so a finished high-priority set can
    no longer sit above a set that still needs judging.
    """
    for sid in ("done", "half", "fresh", "nearly"):
        make_set(tmp_path, sid, sid, make_items(tmp_path), priority=1 if sid == "done" else 50)
    for i in ("A_0", "A_1", "A_2", "B_0", "B_1", "B_2"):
        record_verdict(tmp_path, "done", i, "keep")
    record_verdict(tmp_path, "half", "A_0", "keep")
    record_verdict(tmp_path, "half", "A_1", "keep")
    for i in ("A_0", "A_1", "A_2", "B_0", "B_1"):
        record_verdict(tmp_path, "nearly", i, "keep")

    assert [s["id"] for s in list_sets(tmp_path)] == ["nearly", "half", "fresh", "done"]
    assert [s["done"] for s in list_sets(tmp_path)] == [False, False, False, True]


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


# --- pair mode: two of the same look, pick the better one (2026-10-14) ------
# Jeremy: "each presented side by side and a little check mark under each to
# select which is better ... something we scaffold for future use".

def make_roots(tmp_path: Path, names=("casual_01_standing", "workout_01_standing", "fancy_01_standing")):
    a, b = tmp_path / "A", tmp_path / "B"
    for root, col in ((a, (200, 0, 0)), (b, (0, 0, 200))):
        for n in names:
            d = root / n; d.mkdir(parents=True)
            Image.new("RGB", (8, 8), col).save(d / "shot_00_s7100.png")
    (a / "_plate.png").write_bytes(b"")                     # an underscore folder-mate is ignored
    (b / "only_in_b" ).mkdir(); Image.new("RGB", (8, 8)).save(b / "only_in_b" / "x.png")
    return a, b


def test_pair_set_pairs_look_folders_by_name_and_reports_the_unpaired(tmp_path: Path):
    from sourcemode.assets.judge import pair_rows, pair_set
    a, b = make_roots(tmp_path)
    out, unpaired = pair_set(tmp_path, "pair_x", "x", a, b, arm_a="edit", arm_b="t2i")
    assert unpaired == ["only_in_b"]
    s = load_set(tmp_path, "pair_x")
    assert s["mode"] == "pair" and len(s["items"]) == 6
    rows = pair_rows(s)
    assert [r["group"] for r in rows] and len(rows) == 3
    # each pair is one item per arm, sides fixed by the set id and group, and the
    # payload hands the page pairs with no arm on them
    for r in rows:
        arms = {next(it["arm"] for it in s["items"] if it["id"] == r[k]) for k in ("left", "right")}
        assert arms == {"edit", "t2i"}
    assert pair_rows(load_set(tmp_path, "pair_x")) == rows
    assert any(r["left"].endswith(":t2i") for r in rows) or len(rows) < 4   # the flip is random per group
    p = set_payload(tmp_path, "pair_x")
    assert p["mode"] == "pair" and [x["group"] for x in p["pairs"]] == [r["group"] for r in rows]
    assert "arm" not in json.dumps(p["pairs"])
    with pytest.raises(ValueError):
        pair_set(tmp_path, "pair_none", "x", a, tmp_path / "empty_nothing", arm_a="a", arm_b="b")


def test_a_pair_set_refuses_a_group_without_two_arms(tmp_path: Path):
    items = make_items(tmp_path, arms=("A", "B"), n=2)
    items.append({**items[0], "id": "A_extra", "group": "0"})             # three in group 0
    with pytest.raises(ValueError):
        make_set(tmp_path, "bad", "x", items, mode="pair")
    with pytest.raises(ValueError):
        make_set(tmp_path, "bad", "x", items[:4], mode="triple")


def test_a_pick_keeps_the_winner_rejects_the_loser_in_one_write_and_undoes_both(tmp_path: Path):
    from sourcemode.assets.judge import pair_rows, pair_set, record_pair
    a, b = make_roots(tmp_path)
    pair_set(tmp_path, "pair_x", "x", a, b, arm_a="edit", arm_b="t2i")
    rows = pair_rows(load_set(tmp_path, "pair_x"))
    r0, r1 = rows[0], rows[1]
    v = record_pair(tmp_path, "pair_x", r0["group"], r0["right"])
    assert v == {r0["right"]: "keep", r0["left"]: "reject"}
    v = record_pair(tmp_path, "pair_x", r1["group"], None)                 # neither
    assert v[r1["left"]] == "reject" and v[r1["right"]] == "reject"
    # the set list counts pairs, not images
    row = next(s for s in list_sets(tmp_path) if s["id"] == "pair_x")
    assert row["n"] == 3 and row["judged"] == 2 and "pairs" in row["sub"]
    # the summary's cross-tab reads as wins: t2i or edit kept per group
    g = summary(tmp_path, "pair_x")["groups"]
    assert sorted(g[r0["group"]].values()) == ["keep", "reject"]
    assert set(g[r1["group"]].values()) == {"reject"}
    v = record_pair(tmp_path, "pair_x", r0["group"], None, clear=True)
    assert r0["left"] not in v and r0["right"] not in v
    with pytest.raises(ValueError):
        record_pair(tmp_path, "pair_x", r0["group"], "nobody:edit")
    with pytest.raises(KeyError):
        record_pair(tmp_path, "pair_x", "no_such_group", None)
    # a side that is not on disk cannot be picked, same rule as a single item
    gone = next(it for it in load_set(tmp_path, "pair_x")["items"] if it["id"] == r0["left"])
    Path(gone["path"]).unlink()
    assert set_payload(tmp_path, "pair_x")["pending"] == 1
    with pytest.raises(FileNotFoundError):
        record_pair(tmp_path, "pair_x", r0["group"], r0["left"])


def test_router_takes_a_pair_pick(tmp_path: Path):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from sourcemode.assets.judge import judge_router, pair_rows, pair_set

    a, b = make_roots(tmp_path)
    pair_set(tmp_path, "pair_x", "x", a, b, arm_a="edit", arm_b="t2i")
    r0 = pair_rows(load_set(tmp_path, "pair_x"))[0]
    app = FastAPI(); app.include_router(judge_router({"assets": {"judge": str(tmp_path)}}))
    c = TestClient(app)
    assert c.get("/judge/set/pair_x").json()["mode"] == "pair"
    assert c.post("/judge/set/pair_x/pair", json={"group": r0["group"], "winner": r0["left"]}).json() == {
        r0["left"]: "keep", r0["right"]: "reject"}
    assert c.post("/judge/set/pair_x/pair", json={"group": r0["group"], "winner": "x"}).status_code == 400
    assert c.post("/judge/set/pair_x/pair", json={"group": "zz", "winner": None}).status_code == 404
    assert c.post("/judge/set/pair_x/pair", json={"group": r0["group"], "clear": True}).json() == {}
