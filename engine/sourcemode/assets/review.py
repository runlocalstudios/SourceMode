"""Click-to-select review of asset candidates, served by the engine monitor.

Replaces "read a contact sheet, type the numbers": the control panel shows
every cutout on a checkerboard grouped by slot, one click picks it, and Place
writes the game's outfits folder. The HTTP layer is thin; everything that
decides anything is a pure function over the sidecars that `assets cutout`
already writes.

    GET  /assets                         characters with cutouts under the staging root
    GET  /assets/{char}                  plan + slots + candidates (+ unassigned)
    GET  /assets/file?p=<rel>&w=<px>     an image under the staging root, optionally a cached thumbnail
    POST /assets/{char}/picks            {picks: {look_id: filename}} -> picks.json
    POST /assets/{char}/place            place with the saved picks -> mapping
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from .catalog import look_id, mapping_sheet, place, plan_slots, rank_candidates

THUMB_WIDTHS = (160, 240, 360, 480)


def staging_root(cfg: dict) -> Path:
    from ..config import ENGINE_ROOT  # noqa: PLC0415

    root = Path(cfg.get("assets", {}).get("staging", "outputs/game-assets"))
    return root if root.is_absolute() else ENGINE_ROOT / root


def safe_path(root: Path, rel: str) -> Path | None:
    """A file under root, or None. Refuses traversal and absolute paths."""
    if not rel or Path(rel).is_absolute() or rel.startswith(("\\", "/")):
        return None
    root = root.resolve()
    try:
        p = (root / rel).resolve()
    except OSError:
        return None
    if root not in p.parents or not p.is_file():
        return None
    return p


def thumbnail(path: Path, width: int, cache_dir: Path) -> Path:
    """Downscaled copy, cached by mtime so a re-cut invalidates it."""
    width = min(THUMB_WIDTHS, key=lambda w: abs(w - width))
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{path.stem}_{width}_{int(path.stat().st_mtime)}.png"
    if not out.exists():
        im = Image.open(path).convert("RGBA")
        im.thumbnail((width, int(width * 3)))
        im.save(out)
    return out


def characters(root: Path) -> list[dict]:
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        n = len(list((d / "cutouts").rglob("*.json"))) if (d / "cutouts").exists() else 0
        plan = next(iter(sorted(d.glob("plan*.json"))), None)
        out.append({"character": d.name, "candidates": n, "plan": plan.name if plan else None,
                    "placed": len(list((d / "outfits").glob("*.webp"))) if (d / "outfits").exists() else 0})
    return out


def _rel(root: Path, p: str | Path) -> str | None:
    try:
        return Path(p).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def candidates(root: Path, character: str) -> dict:
    """Everything the review page needs, paths relative to the staging root."""
    cdir = root / character
    plan_path = next(iter(sorted(cdir.glob("plan*.json"))), None)
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path else None
    picks_path = cdir / "picks.json"
    picks = json.loads(picks_path.read_text(encoding="utf-8")).get("picks", {}) if picks_path.exists() else {}

    sides = []
    for f in sorted((cdir / "cutouts").rglob("*.json")) if (cdir / "cutouts").exists() else []:
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if "outputs" not in s:
            continue
        png = _rel(root, s["outputs"].get("png", ""))
        if not png:
            continue
        rep = s.get("report") or {}
        sides.append({
            "file": Path(s["outputs"]["png"]).name,
            "png": png,
            "webp": _rel(root, s["outputs"]["webp"]) if s["outputs"].get("webp") else None,
            "source": s.get("source"),
            "score": s.get("score"),
            "flags": rep.get("flags", []),
            "partial": rep.get("partial"),
            "coverage": rep.get("coverage"),
            "asset": s.get("asset"),
            "report": rep,
        })

    from .catalog import parse_runtime_name  # noqa: PLC0415

    by_slot: dict[str, list[dict]] = {}
    unassigned = []
    for c in sides:
        a = c.get("asset") or {}
        if not a.get("category"):
            # cutouts made before sidecars carried a slot: the folder name still says
            parsed = parse_runtime_name(Path(c["png"]).parent.name + ".x")
            if parsed:
                a = c["asset"] = {"character": character, **parsed}
        if a.get("category") and a.get("look") is not None:
            by_slot.setdefault(look_id(a["category"], int(a["look"])), []).append(c)
        else:
            unassigned.append(c)

    slots = []
    if plan:
        for s in plan_slots(plan):
            cands = rank_candidates(by_slot.pop(s["id"], []))
            slots.append({**s, "candidates": cands,
                          "picked": picks.get(s["id"]) or (cands[0]["file"] if cands else None),
                          "auto": s["id"] not in picks})
    for sid, cands in sorted(by_slot.items()):            # cutouts with a slot but no plan entry
        cands = rank_candidates(cands)
        slots.append({"id": sid, "category": sid.rsplit("_", 1)[0], "look": int(sid.rsplit("_", 1)[1]),
                      "outfit": "", "hair": "", "pose": (cands[0].get("asset") or {}).get("pose", "standing"),
                      "filename": None, "candidates": cands,
                      "picked": picks.get(sid) or cands[0]["file"], "auto": sid not in picks})
    return {"character": character, "plan": plan_path.name if plan_path else None,
            "slots": slots, "unassigned": rank_candidates(unassigned),
            "unassigned_picked": picks.get("_unassigned", []),
            "placed": sorted(p.name for p in (cdir / "outfits").glob("*.webp")) if (cdir / "outfits").exists() else []}


def save_picks(root: Path, character: str, picks: dict) -> Path:
    cdir = root / character
    cdir.mkdir(parents=True, exist_ok=True)
    p = cdir / "picks.json"
    p.write_text(json.dumps({"picks": picks}, indent=1), encoding="utf-8")
    return p


def place_with_picks(root: Path, character: str) -> dict:
    cdir = root / character
    plan_path = next(iter(sorted(cdir.glob("plan*.json"))), None)
    if plan_path is None:
        raise FileNotFoundError(f"no plan*.json in {cdir}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    picks_path = cdir / "picks.json"
    picks = json.loads(picks_path.read_text(encoding="utf-8")).get("picks", {}) if picks_path.exists() else {}
    picks = {k: v for k, v in picks.items() if k != "_unassigned" and isinstance(v, str)}
    sides = []
    for f in sorted((cdir / "cutouts").rglob("*.json")):
        s = json.loads(f.read_text(encoding="utf-8"))
        if "outputs" in s:
            sides.append(s)
    mapping = place(sides, plan, root, pick=picks)
    sheet = mapping_sheet(mapping, root, cdir / "review" / "mapping_checkerboard.jpg")
    mapping["sheet"] = _rel(root, sheet)
    return mapping


def review_router(cfg: dict):
    from fastapi import APIRouter, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse  # noqa: PLC0415

    root = staging_root(cfg)
    r = APIRouter()

    @r.get("/assets")
    def _characters() -> dict:
        return {"root": str(root), "characters": characters(root)}

    @r.get("/assets/file")
    def _file(p: str, w: int | None = None):
        path = safe_path(root, p)
        if path is None:
            raise HTTPException(404)
        if w:
            path = thumbnail(path, w, root / "_thumbs")
        return FileResponse(path)

    @r.get("/assets/{character}")
    def _candidates(character: str) -> dict:
        if not (root / character).is_dir():
            raise HTTPException(404, f"no such character under {root}")
        return candidates(root, character)

    @r.post("/assets/{character}/picks")
    def _picks(character: str, body: dict) -> dict:
        picks = body.get("picks") if isinstance(body, dict) else None
        if not isinstance(picks, dict):
            raise HTTPException(400, "body must be {picks: {look_id: filename}}")
        return {"saved": str(save_picks(root, character, picks))}

    @r.post("/assets/{character}/place")
    def _place(character: str) -> dict:
        try:
            return place_with_picks(root, character)
        except FileNotFoundError as e:
            raise HTTPException(409, str(e)) from e

    return r
