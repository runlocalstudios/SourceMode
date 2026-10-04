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
