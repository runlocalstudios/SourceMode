"""The GPU queue page: the state it reports and the controls it exposes.

The badge rule is the thing worth pinning down - it counts what is WAITING ON
JEREMY, never how many jobs are queued. A badge that is always lit says nothing.
"""

import pytest

from sourcemode.gpu import lease as lease_mod
from sourcemode.gpu import queue as q
from sourcemode.monitor.queue_page import queue_state


@pytest.fixture
def cfg(tmp_path):
    return {"paths": {"outputs": str(tmp_path)}}


def _queue(tmp_path, *labels, **kw):
    path = q.queue_path(tmp_path)
    doc = q.load(path)
    for label in labels:
        q.add(doc, kind="train", label=label, cmd=["x"], cwd=".", **kw)
    q.save(path, doc)
    return doc


def test_state_marks_the_next_job_and_nothing_else(cfg, tmp_path):
    _queue(tmp_path, "vivienne_v2", "zara_v2")
    st = queue_state(cfg)
    assert [j["label"] for j in st["jobs"]] == ["vivienne_v2", "zara_v2"]
    assert [j["is_next"] for j in st["jobs"]] == [True, False]


def test_finished_jobs_drop_off_the_page(cfg, tmp_path):
    doc = _queue(tmp_path, "vivienne_v2", "zara_v2")
    q.mark_finished(doc, doc["jobs"][0]["id"], 0)
    q.save(q.queue_path(tmp_path), doc)
    st = queue_state(cfg)
    assert [j["label"] for j in st["jobs"]] == ["zara_v2"]


def test_the_badge_counts_what_waits_on_him_not_the_queue_length(cfg, tmp_path):
    # Eight queued jobs and a live runner is a HEALTHY queue: badge 0.
    _queue(tmp_path, *[f"char{i}_v2" for i in range(8)])
    lease_mod.acquire(lease_mod.lease_path(tmp_path))
    assert queue_state(cfg)["attention"] == 0

    # Paused needs him.
    path = q.queue_path(tmp_path)
    doc = q.load(path)
    q.pause(doc, "fast failure")
    q.save(path, doc)
    assert queue_state(cfg)["attention"] == 1

    # A failed job needs him too, and the two add up.
    doc = q.load(path)
    q.mark_running(doc, doc["jobs"][0]["id"], 1, "log")
    q.mark_finished(doc, doc["jobs"][0]["id"], 2)
    q.save(path, doc)
    assert queue_state(cfg)["attention"] == 2


def test_a_dead_runner_with_work_waiting_is_an_attention_item(cfg, tmp_path):
    _queue(tmp_path, "zara_v2")
    assert queue_state(cfg)["lease"] is None
    assert queue_state(cfg)["attention"] == 1, "nothing will start, so say so"


def test_no_runner_and_no_work_is_not_an_attention_item(cfg, tmp_path):
    assert queue_state(cfg)["attention"] == 0


def test_only_the_head_job_is_checked_for_approval(cfg, tmp_path, monkeypatch):
    from sourcemode.gpu import runner as runner_mod

    asked = []

    def fake(ds):
        asked.append(ds)
        return False, f"{ds} is not approved"

    monkeypatch.setattr(runner_mod, "approval_ok", fake)
    _queue(tmp_path, "vivienne_v2", "zara_v2", requires_approval="ds")
    lease_mod.acquire(lease_mod.lease_path(tmp_path))   # isolate: a live runner
    st = queue_state(cfg)
    assert asked == ["ds"], "a job behind the head must not be approval-checked"
    assert st["jobs"][0]["blocked_reason"] and not st["jobs"][1]["blocked_reason"]
    assert st["attention"] == 1


def test_the_runners_own_last_line_is_what_gets_shown(cfg, tmp_path):
    log = tmp_path / "logs" / "gpu-runner.log"
    log.parent.mkdir(parents=True)
    log.write_text("earlier line\nwait: card busy - PID 30144; j001 zara_v2 is next\n", encoding="utf-8")
    assert queue_state(cfg)["runner_says"].startswith("wait: card busy - PID 30144")


# --- the controls ----------------------------------------------------------

@pytest.fixture
def client(cfg):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from fastapi import FastAPI

    from sourcemode.monitor.queue_page import queue_router

    app = FastAPI()
    app.include_router(queue_router(cfg))
    return fastapi_testclient.TestClient(app)


def test_the_page_renders(client):
    r = client.get("/queue")
    assert r.status_code == 200 and "SourceMode GPU" in r.text


def test_move_hold_and_cancel_through_the_api(client, tmp_path):
    _queue(tmp_path, "vivienne_v2", "zara_v2", "marisol_v2")
    ids = [j["id"] for j in client.get("/queue/state").json()["jobs"]]

    st = client.post(f"/queue/job/{ids[2]}/move", json={"position": 0}).json()
    assert [j["label"] for j in st["jobs"]] == ["marisol_v2", "vivienne_v2", "zara_v2"]

    st = client.post(f"/queue/job/{ids[2]}/hold", json={"hold": True}).json()
    assert st["jobs"][0]["hold"] is True
    assert st["jobs"][1]["is_next"] is True, "a held job is skipped for 'next' but keeps its place"

    # ids are stable, so ids[1] is zara wherever she now sits in the order.
    st = client.post(f"/queue/job/{ids[1]}/cancel").json()
    assert [j["label"] for j in st["jobs"]] == ["marisol_v2", "vivienne_v2"]


def test_pause_and_resume_through_the_api(client, tmp_path):
    _queue(tmp_path, "zara_v2")
    assert client.post("/queue/pause").json()["paused"] is True
    assert client.post("/queue/resume").json()["paused"] is False


def test_a_running_job_cannot_be_cancelled_from_the_page(client, tmp_path):
    doc = _queue(tmp_path, "zara_v2")
    job_id = doc["jobs"][0]["id"]
    q.mark_running(doc, job_id, 123, "log")
    q.save(q.queue_path(tmp_path), doc)
    assert client.post(f"/queue/job/{job_id}/cancel").status_code == 409


def test_an_unknown_job_is_a_404(client, tmp_path):
    _queue(tmp_path, "zara_v2")
    assert client.post("/queue/job/j999/hold", json={"hold": True}).status_code == 404
