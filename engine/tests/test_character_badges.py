import json
import os
import time
from datetime import datetime, timezone

from sourcemode.assets.selfies import pack_state
from sourcemode.monitor.appearance_page import todo


def row(confirmed=True, jobs=("server at The Sandbar",), shipped=28, awaiting=False,
        looks="approved", looks_at="2026-10-22T10:00:00+00:00", selfies="new"):
    s = {"new": {"wardrobe": True, "rendered": 24, "total": 24, "at": "2026-10-22T12:00:00+00:00"},
         "old": {"wardrobe": False, "rendered": 24, "total": 24, "at": "2026-10-21T12:00:00+00:00"},
         "partial": {"wardrobe": True, "rendered": 9, "total": 24, "at": "2026-10-22T12:00:00+00:00"},
         "stale": {"wardrobe": True, "rendered": 24, "total": 24, "at": "2026-10-22T09:00:00+00:00"},
         None: None}[selfies]
    return {"confirmed": confirmed,
            "wardrobe": {"jobs": [{"job": j, "outfit": "", "places": []} for j in jobs]},
            "packs": {"shipped": shipped, "awaiting": awaiting, "shoots": [],
                      "looks": looks, "looks_at": looks_at, "selfies": s}}


def test_a_finished_character_has_no_badges():
    assert todo(row()) == []


def test_each_missing_thing_is_one_short_badge():
    assert todo(row(confirmed=False)) == ["DESC"]
    assert todo(row(jobs=("", "  "))) == ["JOB"]
    assert todo(row(shipped=0)) == ["NOT IN GAME"]
    assert todo(row(awaiting=True)) == ["APPROVE WARDROBE"]


def test_a_staged_pack_waiting_on_him_replaces_no_wardrobe():
    assert todo(row(shipped=0, awaiting=True)) == ["APPROVE WARDROBE"]
    assert todo(row(confirmed=False, jobs=(), shipped=0)) == ["DESC", "JOB", "NOT IN GAME"]


def test_the_looks_plan_and_the_selfies_shot_against_it_each_get_a_badge():
    # Jeremy, 2026-10-23: which characters have no 28-look plan yet, and whose
    # selfies were shot before the selfies wore the plan
    assert todo(row(looks="none", looks_at=None, selfies=None)) == ["NO LOOKS"]
    assert todo(row(looks="draft", looks_at=None, selfies=None)) == ["APPROVE LOOKS"]
    assert todo(row(selfies=None)) == ["NO SELFIES"]
    assert todo(row(selfies="old")) == ["NEEDS NEW SELFIES"]
    assert todo(row(selfies="partial")) == ["NEEDS NEW SELFIES"]
    # the looks were re-approved after the selfies were shot
    assert todo(row(selfies="stale")) == ["NEEDS NEW SELFIES"]
    # an old pack with no plan is a plan problem, not a selfie problem
    assert todo(row(looks="none", looks_at=None, selfies="old")) == ["NO LOOKS"]
    # an older approved plan carries no time; the new selfies count
    assert todo(row(looks_at=None)) == []


def test_pack_state_tells_a_wardrobe_pack_from_an_older_one(tmp_path):
    lib = tmp_path / "library"
    assert pack_state("ash", lib) is None
    d = lib / "ash" / "2026-10-21_selfies_selfies"
    d.mkdir(parents=True)
    # the folder alone is nothing - run_shoots makes it before the first render
    (d / "set.json").write_text(json.dumps({"name": "selfies"}), encoding="utf-8")
    assert pack_state("ash", lib) is None
    for i in range(1, 25):
        (d / f"selfie_{i:02d}.png").write_bytes(b"x")
    s = pack_state("ash", lib)
    assert (s["wardrobe"], s["rendered"], s["total"]) == (False, 24, 24)
    assert s["at"].endswith("+00:00")
    # the same folder re-used by the wardrobe pack: the manifest wins, and it
    # counts only the manifest's files - partial while the queue is on it
    man = [{"file": f"selfie_casual_{i:02d}.png"} for i in range(1, 8)]
    (d / "set.json").write_text(json.dumps({"name": "selfies", "selfies": man}), encoding="utf-8")
    assert pack_state("ash", lib) == {"set": d.name, "wardrobe": True, "rendered": 0, "total": 7, "at": None}
    for m in man[:3]:
        (d / m["file"]).write_bytes(b"x")
    # `at` is the newest render, not the folder or the manifest
    late = d / man[2]["file"]
    os.utime(late, (time.time() + 100, time.time() + 100))
    s = pack_state("ash", lib)
    assert (s["wardrobe"], s["rendered"], s["total"]) == (True, 3, 7)
    assert s["at"] == datetime.fromtimestamp(late.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
