from sourcemode.monitor.appearance_page import todo


def row(confirmed=True, jobs=("server at The Sandbar",), shipped=28, awaiting=False):
    return {"confirmed": confirmed,
            "wardrobe": {"jobs": [{"job": j, "outfit": "", "places": []} for j in jobs]},
            "packs": {"shipped": shipped, "awaiting": awaiting}}


def test_a_finished_character_has_no_badges():
    assert todo(row()) == []


def test_each_missing_thing_is_one_short_badge():
    assert todo(row(confirmed=False)) == ["DESC"]
    assert todo(row(jobs=("", "  "))) == ["JOB"]
    assert todo(row(shipped=0)) == ["NO WARDROBE"]
    assert todo(row(awaiting=True)) == ["APPROVE WARDROBE"]


def test_a_staged_pack_waiting_on_him_replaces_no_wardrobe():
    assert todo(row(shipped=0, awaiting=True)) == ["APPROVE WARDROBE"]
    assert todo(row(confirmed=False, jobs=(), shipped=0)) == ["DESC", "JOB", "NO WARDROBE"]
