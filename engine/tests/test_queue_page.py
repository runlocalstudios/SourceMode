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

# --- what is ready to train (the thing the first version could not show) ----

def _approve(tmp_path, ds, images=2, at=None):
    """An approved preview, the way the engine writes one."""
    import json
    root = tmp_path / "train-previews"
    (root / "previews").mkdir(parents=True, exist_ok=True)
    (root / "approvals").mkdir(parents=True, exist_ok=True)
    fp = f"fp-{ds}"
    (root / "previews" / f"{ds}.json").write_text(
        # "images" + "n", the keys build_preview actually writes. The first version
        # of this fixture invented "items", so it agreed with a bug that reported
        # 0 images for every candidate on the live page.
        json.dumps({"id": ds, "fingerprint": fp, "n": images,
                    "images": [{"id": f"src_{i}"} for i in range(images)]}), encoding="utf-8")
    (root / "approvals" / f"{ds}.json").write_text(
        json.dumps({"approved": True, "fingerprint": fp,
                    "at": at or "2026-09-22T17:59:07+00:00"}), encoding="utf-8")
    return root


@pytest.fixture
def cfg_full(tmp_path):
    return {"paths": {"outputs": str(tmp_path)},
            "train": {"previews": str(tmp_path / "train-previews")}}


def test_an_approved_untrained_dataset_is_offered_even_though_nobody_queued_it(cfg_full, tmp_path):
    """sunny_v2 sat approved and untrained from 2026-09-22 because the page only
    listed jobs someone had typed in. Candidates come from the approval record."""
    from sourcemode.monitor.queue_page import candidates

    _approve(tmp_path, "sunny_v2")
    rows = candidates(cfg_full)
    assert [r["dataset"] for r in rows] == ["sunny_v2"]
    assert rows[0]["who"] == "Sunny" and rows[0]["character"] == "sunny"
    assert rows[0]["images"] == 2


def test_candidates_are_in_approval_order(cfg_full, tmp_path):
    """Approval order IS the training order, so that is the order they are offered."""
    from sourcemode.monitor.queue_page import candidates

    _approve(tmp_path, "marisol_v2", at="2026-10-03T17:27:32+00:00")
    _approve(tmp_path, "sunny_v2", at="2026-09-22T17:59:07+00:00")
    _approve(tmp_path, "cici_v2", at="2026-10-02T17:39:00+00:00")
    assert [r["dataset"] for r in candidates(cfg_full)] == ["sunny_v2", "cici_v2", "marisol_v2"]


def test_a_trained_dataset_is_not_offered_again(cfg_full, tmp_path):
    """ANY checkpoint means trained - a prune deletes the losing epochs, so a count
    of one is still a finished run."""
    from sourcemode.monitor.queue_page import candidates

    _approve(tmp_path, "jojo_v2")
    lora = tmp_path / "lora-datasets" / "jojo_v2" / "lora"
    lora.mkdir(parents=True)
    (lora / "jojo_v2-000018.safetensors").write_bytes(b"x")
    assert candidates(cfg_full) == []


def test_a_queued_dataset_is_not_offered_twice(cfg_full, tmp_path):
    from sourcemode.monitor.queue_page import candidates

    _approve(tmp_path, "cici_v2")
    assert len(candidates(cfg_full)) == 1
    _queue(tmp_path, "cici_v2")
    assert candidates(cfg_full) == []


def test_an_unapproved_dataset_is_never_offered(cfg_full, tmp_path):
    import json

    from sourcemode.monitor.queue_page import candidates

    root = _approve(tmp_path, "tess_v2")
    # captions edited after approval -> the fingerprint no longer matches
    doc = json.loads((root / "previews" / "tess_v2.json").read_text(encoding="utf-8"))
    doc["fingerprint"] = "changed"
    (root / "previews" / "tess_v2.json").write_text(json.dumps(doc), encoding="utf-8")
    assert candidates(cfg_full) == []


# --- queueing a training run from the page ---------------------------------

@pytest.fixture
def client_full(cfg_full):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from fastapi import FastAPI

    from sourcemode.monitor.queue_page import queue_router

    app = FastAPI()
    app.include_router(queue_router(cfg_full))
    return fastapi_testclient.TestClient(app)


def test_queueing_training_builds_the_command_so_he_never_types_a_path(client_full, tmp_path):
    _approve(tmp_path, "marisol_v2")
    r = client_full.post("/queue/training", json={"dataset": "marisol_v2"})
    assert r.status_code == 200

    doc = q.load(q.queue_path(tmp_path))
    job = doc["jobs"][0]
    assert job["kind"] == "train" and job["label"] == "marisol_v2"
    assert job["requires_approval"] == "marisol_v2", "the runner must re-check at start time"
    assert "train_character.ps1" in " ".join(job["cmd"])
    assert "-Ds" in job["cmd"] and "marisol_v2" in job["cmd"]
    assert "-Char" in job["cmd"] and "marisol" in job["cmd"]


def test_an_unapproved_dataset_cannot_be_queued_from_the_page(client_full, tmp_path):
    r = client_full.post("/queue/training", json={"dataset": "nobody_v2"})
    assert r.status_code == 409


def test_the_same_training_cannot_be_queued_twice_from_the_page(client_full, tmp_path):
    _approve(tmp_path, "cici_v2")
    assert client_full.post("/queue/training", json={"dataset": "cici_v2"}).status_code == 200
    assert client_full.post("/queue/training", json={"dataset": "cici_v2"}).status_code == 409


def test_a_dataset_id_cannot_escape_its_directory(client_full):
    for bad in ("../../etc/passwd", "a/b", "a\b", ""):
        assert client_full.post("/queue/training", json={"dataset": bad}).status_code in (400, 409)


# --- drag-and-drop reordering ----------------------------------------------

def test_a_drag_sends_the_whole_resulting_order_in_one_request(client_full, tmp_path):
    _queue(tmp_path, "vivienne_v2", "zara_v2", "marisol_v2")
    ids = [j["id"] for j in client_full.get("/queue/state").json()["jobs"]]
    st = client_full.post("/queue/order", json={"ids": [ids[2], ids[0], ids[1]]}).json()
    assert [j["label"] for j in st["jobs"]] == ["marisol_v2", "vivienne_v2", "zara_v2"]


def test_a_reorder_that_names_an_unknown_job_changes_nothing(client_full, tmp_path):
    _queue(tmp_path, "vivienne_v2", "zara_v2")
    ids = [j["id"] for j in client_full.get("/queue/state").json()["jobs"]]
    assert client_full.post("/queue/order", json={"ids": [ids[1], "j999"]}).status_code == 404
    st = client_full.get("/queue/state").json()
    assert [j["label"] for j in st["jobs"]] == ["vivienne_v2", "zara_v2"], "order untouched"


def test_a_job_left_out_of_a_reorder_keeps_its_place_at_the_end(tmp_path):
    doc = _queue(tmp_path, "a_v2", "b_v2", "c_v2")
    ids = [j["id"] for j in doc["jobs"]]
    q.reorder(doc, [ids[2]])
    assert [j["label"] for j in doc["jobs"]] == ["c_v2", "a_v2", "b_v2"]


# --- the labels a person reads ---------------------------------------------

def test_rows_are_labelled_for_a_person(cfg_full, tmp_path):
    _queue(tmp_path, "marisol_v2")
    row = queue_state(cfg_full)["jobs"][0]
    assert row["who"] == "Marisol"
    assert row["what"] == "LoRA training, then the epoch sweep"
    assert row["id"].startswith("j"), "the id stays, small, so a log line can be matched back"


# --- the time estimate -----------------------------------------------------

def test_a_candidate_carries_a_measured_time_estimate(cfg_full, tmp_path):
    """Measured, not assumed: checkpoint-to-checkpoint wall time over the steps
    between saves. 5.03-5.33 s/step across five of his runs on 2026-10-04."""
    from sourcemode.monitor.queue_page import candidates

    _approve(tmp_path, "marisol_v2", images=74)
    e = candidates(cfg_full)[0]["estimate"]
    assert e["steps"] == 74 * 3 * 24, "74 images need 3 repeats to put an epoch in range"
    assert 5 * 3600 < e["train_s"] < 12 * 3600
    assert e["total_s"] > e["train_s"], "the epoch sweep is part of what holds the card"
    assert "74 images" in e["basis"] and "s/step" in e["basis"]


def test_the_estimate_is_remeasured_from_completed_runs(cfg_full, tmp_path):
    """With real runs on disk the rate comes from them, not from the fallback."""
    from sourcemode.monitor import queue_page as qp

    qp._rate_cache.clear()
    _approve(tmp_path, "done_v2", images=50)
    lora = tmp_path / "lora-datasets" / "done_v2" / "lora"
    lora.mkdir(parents=True)
    import os, time
    t0 = time.time() - 6 * 3600
    for i in range(1, 8):                       # 7 saves = 6 gaps
        f = lora / f"done_v2-{i:06d}.safetensors"
        f.write_bytes(b"x")
        os.utime(f, (t0 + i * 1800, t0 + i * 1800))   # 30 min per epoch
    r = qp._rate(cfg_full, max_age_s=0)
    assert r["measured"] is True and r["n_runs"] == 1
    # 50 images x3 repeats = 150 steps per epoch in 1800s -> 12 s/step
    assert 11.5 < r["s_per_step"] < 12.5


def test_the_estimate_falls_back_and_says_so_when_nothing_has_been_measured(cfg_full, tmp_path):
    from sourcemode.monitor import queue_page as qp

    qp._rate_cache.clear()
    r = qp._rate(cfg_full, max_age_s=0)
    assert r["measured"] is False
    assert r["s_per_step"] == qp.FALLBACK_S_PER_STEP
    assert "assumed" in qp.estimate(cfg_full, 50)["basis"]
    qp._rate_cache.clear()


def test_no_images_means_no_estimate_rather_than_a_made_up_one(cfg_full):
    from sourcemode.monitor.queue_page import estimate

    e = estimate(cfg_full, 0)
    assert e["total_s"] is None and "no estimate" in e["basis"]


def test_the_queue_total_counts_only_work_that_will_actually_run(cfg_full, tmp_path):
    """Held jobs are excluded: they are not going to start until he says so."""
    from sourcemode.monitor import queue_page as qp

    qp._rate_cache.clear()
    _approve(tmp_path, "a_v2", images=50)
    _approve(tmp_path, "b_v2", images=50)
    doc = _queue(tmp_path, "a_v2", "b_v2")
    one = queue_state(cfg_full)["queued_s"]
    q.set_hold(doc, doc["jobs"][1]["id"], True)
    q.save(q.queue_path(tmp_path), doc)
    two = queue_state(cfg_full)["queued_s"]
    assert two < one and two == pytest.approx(one / 2, rel=0.01)
    qp._rate_cache.clear()


# --- a mis-click must be repairable ----------------------------------------

def test_a_removed_job_can_be_restored_and_comes_back_held(client_full, tmp_path):
    """Jeremy clicked Remove meaning Hold, and putting it back took a hand-edit of
    queue.json. It comes back HELD so a restore can never itself start 9 hours of
    GPU work."""
    _queue(tmp_path, "tess_v2")
    jid = client_full.get("/queue/state").json()["jobs"][0]["id"]
    client_full.post(f"/queue/job/{jid}/cancel")

    st = client_full.get("/queue/state").json()
    assert st["jobs"] == [] and [r["id"] for r in st["removed"]] == [jid]
    assert st["removed"][0]["who"] == "Tess"

    st = client_full.post(f"/queue/job/{jid}/restore").json()
    assert [j["id"] for j in st["jobs"]] == [jid]
    assert st["jobs"][0]["hold"] is True, "restored held, never straight back into the run order"
    assert st["removed"] == []


def test_the_restored_job_keeps_its_original_command(client_full, tmp_path):
    _approve(tmp_path, "cici_v2")
    client_full.post("/queue/training", json={"dataset": "cici_v2"})
    jid = client_full.get("/queue/state").json()["jobs"][0]["id"]
    before = q.find(q.load(q.queue_path(tmp_path)), jid)["cmd"]
    client_full.post(f"/queue/job/{jid}/cancel")
    client_full.post(f"/queue/job/{jid}/restore")
    assert q.find(q.load(q.queue_path(tmp_path)), jid)["cmd"] == before


def test_only_a_cancelled_job_can_be_restored(client_full, tmp_path):
    _queue(tmp_path, "tess_v2")
    jid = client_full.get("/queue/state").json()["jobs"][0]["id"]
    assert client_full.post(f"/queue/job/{jid}/restore").status_code == 409
    assert client_full.post("/queue/job/j999/restore").status_code == 404


def test_a_restored_job_is_not_counted_as_waiting_work_until_released(cfg_full, tmp_path):
    from sourcemode.monitor import queue_page as qp

    qp._rate_cache.clear()
    _approve(tmp_path, "tess_v2", images=50)
    doc = _queue(tmp_path, "tess_v2")
    jid = doc["jobs"][0]["id"]
    assert queue_state(cfg_full)["queued_s"] > 0
    q.cancel(doc, jid); q.save(q.queue_path(tmp_path), doc)
    doc = q.load(q.queue_path(tmp_path))
    q.restore(doc, jid); q.save(q.queue_path(tmp_path), doc)
    assert queue_state(cfg_full)["queued_s"] is None, "held work is not waiting work"
    qp._rate_cache.clear()
