"""FastAPI app: localhost only, the key stays here."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import config, manifest, pricing, refs, runs
from .client import MockClient, RealClient
from .worker import Worker

app = FastAPI(title="imagegen")
STATIC = config.ROOT / "static"

_client = None
worker: Worker | None = None


def get_worker() -> Worker:
    global _client, worker
    if worker is None:
        if config.mock_mode():
            _client = MockClient(delay_s=0.5)
        else:
            key = config.api_key()
            if not key:
                raise HTTPException(400, "OPENAI_API_KEY is not set - see README (or run with IMAGEGEN_MOCK=1)")
            _client = RealClient(key)
        worker = Worker(_client, config.OUTPUTS_DIR, config.PRICING_PATH)
    return worker


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/app.js")
def app_js():
    return FileResponse(STATIC / "app.js", media_type="application/javascript")


@app.get("/api/status")
def status():
    w = worker
    return {"mock": config.mock_mode(), "key_present": bool(config.api_key()),
            "references_dir": str(config.REFERENCES_DIR), "references_dir_exists": config.REFERENCES_DIR.is_dir(),
            "manifest": str(config.MANIFEST_PATH), "manifest_exists": config.MANIFEST_PATH.is_file(),
            "codex_outputs": str(config.CODEX_OUTPUTS_DIR), "outputs": str(config.OUTPUTS_DIR),
            "models": config.MODELS, "sizes": config.SIZES, "qualities": config.QUALITIES,
            "input_fidelity": config.INPUT_FIDELITY, "moderation": config.MODERATION,
            "no_input_fidelity": config.NO_INPUT_FIDELITY,
            "defaults": config.DEFAULT_SETTINGS,
            "active_run": (w.run["run_id"] if w and w.run else None), "active": bool(w and w.active()),
            "log": (w.log[-30:] if w else [])}


@app.get("/api/characters")
def characters():
    return {"characters": refs.list_characters(), "dir": str(config.REFERENCES_DIR)}


@app.get("/api/references/{character}")
def references(character: str):
    rs = refs.references_for(character)
    codex = config.CODEX_OUTPUTS_DIR / character.lower()
    return {"character": character.lower(),
            "references": [{"name": p.name, "path": str(p), "size": p.stat().st_size} for p in rs],
            "codex_outputs": sorted(p.name for p in codex.iterdir()) if codex.is_dir() else []}


@app.get("/api/file")
def file(p: str):
    """Serve an image from an allowed root only."""
    path = Path(p).resolve()
    allowed = [config.REFERENCES_DIR.resolve(), config.CODEX_OUTPUTS_DIR.resolve(), config.OUTPUTS_DIR.resolve()]
    if not any(str(path).lower().startswith(str(a).lower()) for a in allowed) or not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path)


@app.post("/api/manifest/{character}/import")
def manifest_import(character: str, force: bool = False):
    try:
        return manifest.import_manifest(character, force=force)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/manifest/{character}")
def manifest_get(character: str):
    doc = manifest.load_working(character)
    if doc is None:
        raise HTTPException(404, "not imported")
    return doc


class PromptEdit(BaseModel):
    shot_id: str
    prompt: str


@app.post("/api/manifest/{character}/prompt")
def manifest_edit(character: str, body: PromptEdit):
    return manifest.edit_prompt(character, body.shot_id, body.prompt)


class EstimateReq(BaseModel):
    model: str
    size: str
    quality: str
    n_refs: int
    n_shots: int


@app.post("/api/estimate")
def estimate(body: EstimateReq):
    pr = pricing.load()
    e = pricing.estimate(pr, body.model, body.size, body.quality, body.n_refs)
    per = e.get("per_image_usd")
    return {**e, "n_shots": body.n_shots, "run_usd": round(per * body.n_shots, 4) if per else None,
            "batch80_usd": round(per * 80, 2) if per else None, "verified": pr["verified"], "source": pr["source"]}


class RunReq(BaseModel):
    character: str
    label: str = "pilot"
    shot_ids: list[str]
    reference_names: list[str]
    settings: dict
    spend_ceiling_usd: float | None = None


@app.post("/api/runs")
def create_run(body: RunReq):
    """Creates the run folder and record. Does NOT send anything."""
    doc = manifest.load_working(body.character)
    if doc is None:
        raise HTTPException(400, "import the manifest first")
    shots = [s for s in doc["shots"] if s["id"] in set(body.shot_ids)]
    if not shots:
        raise HTTPException(400, "no shots selected")
    available = {p.name: p for p in refs.references_for(body.character)}
    chosen = [available[n] for n in body.reference_names if n in available]
    if not chosen:
        raise HTTPException(400, "no references selected")
    settings = {**config.DEFAULT_SETTINGS, **body.settings}
    for k, allowed in (("model", config.MODELS), ("size", config.SIZES), ("quality", config.QUALITIES),
                       ("input_fidelity", config.INPUT_FIDELITY), ("moderation", config.MODERATION)):
        if settings.get(k) not in allowed:
            raise HTTPException(400, f"bad {k}: {settings.get(k)}")
    pr = pricing.load()
    est = pricing.estimate(pr, settings["model"], settings["size"], settings["quality"], len(chosen))
    run = runs.create_run(body.character, body.label, settings, chosen, shots, body.spend_ceiling_usd, est)
    return run


@app.get("/api/runs")
def list_runs():
    return {"runs": runs.list_runs()}


@app.get("/api/runs/{character}/{run_id}")
def get_run(character: str, run_id: str):
    w = worker
    if w and w.run and w.run["run_id"] == run_id:
        return w.run
    try:
        return runs.reconcile(runs.load_run(character, run_id))
    except FileNotFoundError as e:
        raise HTTPException(404, "no such run") from e


@app.post("/api/runs/{character}/{run_id}/generate")
def generate(character: str, run_id: str):
    """The deliberate click. Loads the run, reconciles, starts the queue."""
    w = get_worker()
    if w.active():
        raise HTTPException(409, f"run {w.run['run_id']} is still active - pause it first")
    run = runs.reconcile(runs.load_run(character, run_id))
    w.start(run)
    return {"started": run_id}


@app.post("/api/runs/{character}/{run_id}/pause")
def pause(character: str, run_id: str):
    w = get_worker()
    if not w.run or w.run["run_id"] != run_id:
        raise HTTPException(409, "that run is not active")
    w.pause()
    return {"paused": run_id}


@app.post("/api/runs/{character}/{run_id}/resume")
def resume(character: str, run_id: str):
    w = get_worker()
    if not w.run or w.run["run_id"] != run_id:
        run = runs.reconcile(runs.load_run(character, run_id))
        w.run = run
    w.resume()
    return {"resumed": run_id}


@app.post("/api/runs/{character}/{run_id}/retry/{shot_id}")
def retry(character: str, run_id: str, shot_id: str):
    w = get_worker()
    if not w.run or w.run["run_id"] != run_id:
        w.run = runs.reconcile(runs.load_run(character, run_id))
    w.retry_shot(shot_id)
    if not w.active():
        w.start(w.run, only=[shot_id])
    return {"retrying": shot_id}


class Review(BaseModel):
    shot_id: str
    verdict: str | None = None      # keep | reject | None
    note: str | None = None
    codex_compare: str | None = None


@app.post("/api/runs/{character}/{run_id}/review")
def review(character: str, run_id: str, body: Review):
    d = runs.run_dir(character, run_id)
    p = d / "review.json"
    doc = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    entry = doc.get(body.shot_id, {})
    if body.verdict is not None:
        entry["verdict"] = body.verdict or None
    if body.note is not None:
        entry["note"] = body.note
    if body.codex_compare is not None:
        entry["codex_compare"] = body.codex_compare
    doc[body.shot_id] = entry
    p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


@app.get("/api/runs/{character}/{run_id}/review")
def get_review(character: str, run_id: str):
    p = runs.run_dir(character, run_id) / "review.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


class Billing(BaseModel):
    billing_actual_usd: float | None


@app.post("/api/runs/{character}/{run_id}/billing")
def billing(character: str, run_id: str, body: Billing):
    run = runs.load_run(character, run_id)
    run["billing_actual_usd"] = body.billing_actual_usd
    runs.save_run(run)
    return {"ok": True}


@app.get("/api/pricing")
def get_pricing():
    return pricing.load()


@app.get("/api/costs")
def costs():
    """Across all local runs: estimated spend, unknown attempts, saved images."""
    total, unknown, saved, per_run = 0.0, 0, 0, []
    for r in runs.list_runs():
        total += r["totals"]["spent_estimate_usd"]; unknown += r["totals"]["unknown_cost_attempts"]; saved += r["totals"]["saved"]
        per_run.append({"run_id": r["run_id"], "character": r["character"], **r["totals"]})
    return {"spent_estimate_usd": round(total, 4), "unknown_cost_attempts": unknown, "saved": saved, "runs": per_run}


def serve():
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    serve()
