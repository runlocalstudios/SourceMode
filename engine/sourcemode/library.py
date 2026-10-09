"""The library: every set Jeremy might open again, by character, dated.

Jeremy, 2026-10-09: "I don't think I'll ever be able to find or organize any of
the assets we have been creating." outputs/ had ~130 top-level folders named by
experiment (dense_mei_v2_asset_nodesc, coarse_jojo_a2, ab_vivienne_hair), with
no date and no grouping by character. The library is one tree:

    <library>/<character>/<YYYY-MM-DD>_<kind>_<name>/
        ...the set's files, exactly as they were written...
        kept/       his keepers, hard-linked from the judge verdicts
        set.json    character, kind, name, date, where it came from, judge sets

Flat under the character and date first, so Explorer shows the character's
timeline; the kind is in the name (shoot, sweep, ab, wardrobe, selfies, video,
voice, probe). One-off probes live under _experiments/<character>/ with the same
naming, so a character's folder holds only what he would open again.

Pipeline internals stay in outputs/ - lora-datasets, training, judge, logs, the
queue, the asset staging root - because tools point at them and he reaches them
from the Training sets and GPU tabs, not Explorer.

`plan` writes a table (old folder -> new folder) and moves nothing; `apply`
moves what the table says and rewrites every judge set that pointed into a moved
folder, so the Judging tab keeps working on the moved images.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

KINDS = ("shoot", "sweep", "ab", "wardrobe", "selfies", "video", "voice", "probe")
MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".wav"}

#: outputs/ folders that are pipeline internals, never library material.
STAY = {
    "judge", "logs", "gpu-queue", "lora-datasets", "training", "train-previews",
    "shot_plans", "seeds", "qc", "inventory", "epoch-choices", "assets",
    "game-assets", "game-assets-t2i", "voice", "_stage", "_quarantine",
    "_pre_revision", "_sheets", "lora-candidates", "loragen_local", "library",
}
STAY_NOTE = {
    "game-assets": "asset pipeline staging root (cutout, place, review read it); packs "
                   "land in the library once the writers are switched",
    "voice": "written per character by `sourcemode voice`; moves when the voice writer does",
}


def library_dir(cfg: dict) -> Path:
    from .config import ENGINE_ROOT  # noqa: PLC0415

    p = Path(cfg.get("paths", {}).get("library", "../library"))
    return (p if p.is_absolute() else ENGINE_ROOT / p).resolve()


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or "set"


def set_folder(date: str, kind: str, name: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
    return f"{date}_{kind}_{slug(name)}"


def set_dir(cfg: dict, character: str, kind: str, name: str, *, date: str | None = None,
            experiment: bool = False) -> Path:
    """Where a NEW set goes. Created. date defaults to today."""
    date = date or time.strftime("%Y-%m-%d")
    base = library_dir(cfg)
    if experiment:
        base = base / "_experiments"
    d = base / character.lower() / set_folder(date, kind, name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_set_json(d: Path, **meta) -> Path:
    out = d / "set.json"
    doc = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    doc.update({k: (str(v) if isinstance(v, Path) else v) for k, v in meta.items()})
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


# --- planning ------------------------------------------------------------------

def _scan(folder: Path) -> tuple[int, int, str | None]:
    """(media files, all files, date of the OLDEST media file - when the set was made)."""
    media = total = 0
    oldest = None
    for root, _dirs, files in os.walk(folder):
        for f in files:
            total += 1
            if Path(f).suffix.lower() in MEDIA:
                media += 1
                m = os.path.getmtime(os.path.join(root, f))
                oldest = m if oldest is None or m < oldest else oldest
    if oldest is None and total:
        oldest = min(os.path.getmtime(os.path.join(r, f))
                     for r, _d, fs in os.walk(folder) for f in fs)
    date = time.strftime("%Y-%m-%d", time.localtime(oldest)) if oldest else None
    return media, total, date


def _character_in(name: str, characters: set[str]) -> str | None:
    for tok in re.split(r"[_\-]", name.lower()):
        if tok in characters:
            return tok
    return None


def _classify(name: str, characters: set[str]) -> tuple[str, str, str, bool] | None:
    """(character, kind, set name, experiment?) for one top-level outputs folder."""
    low = name.lower()
    char = _character_in(low, characters)
    rest = lambda prefix: re.sub(rf"^{re.escape(prefix)}[_\-]?", "", low)  # noqa: E731
    if low.startswith("dense_") and char:
        return char, "sweep", rest(f"dense_{char}") or "v2", False
    if low.startswith("ab_") and char:
        return char, "ab", rest(f"ab_{char}") or "ab", False
    if low.startswith("coarse_") and char:
        return char, "sweep", "coarse-" + (rest(f"coarse_{char}") or "a"), True
    if low.startswith("cad_wardrobe_") and char:
        return char, "wardrobe", "cad", False
    if char and re.search(r"(intimate|outfits|poses|pack)", low):
        return char, "wardrobe", rest(char), False
    if char and "video" in low:
        v = re.sub(r"(^|[_\-])video([_\-]|$)", r"\1", rest(char)).strip("_-")
        return char, "video", v or "clips", False
    if low.startswith("t2i_eval_") and char:
        return char, "sweep", "t2i-eval", True
    if char and re.search(r"(epochs|eval|r64|r32)", low):
        return char, "sweep", rest(char), True
    kind = "ab" if re.search(r"(^|[_\-])ab([_\-]|$)", low) else "probe"
    name = (rest(char) if char else low) or low
    if kind == "ab":
        name = re.sub(r"(^|[_\-])ab([_\-]|$)", r"\1", name).strip("_-") or "ab"
    return char or "misc", kind, name, True


def plan(outputs: Path, judge_root: Path, characters: set[str]) -> list[dict]:
    """One row per outputs/ folder (per set, under shoots/ and photosets/)."""
    rows: list[dict] = []
    characters = {c.lower() for c in characters}

    def row(src: Path, character, kind, name, experiment, action="move", note=""):
        media, total, date = _scan(src)
        if action == "move" and total == 0:
            action, note = "remove-empty", "no files at all"
        rel = src.relative_to(outputs)
        dst = None
        if action == "move":
            parts = ["_experiments"] if experiment else []
            dst = str(Path(*parts, character, set_folder(date, kind, name)))
        rows.append({"src": str(rel), "dst": dst, "character": character, "kind": kind,
                     "name": name, "date": date, "experiment": experiment, "media": media,
                     "files": total, "action": action, "note": note,
                     "judge_sets": _judge_refs(judge_root, outputs, src)})

    for d in sorted(outputs.iterdir()):
        if not d.is_dir():
            continue
        if d.name in STAY:
            row(d, None, None, None, False, action="stay", note=STAY_NOTE.get(d.name, "pipeline internal"))
            continue
        if d.name in ("shoots", "photosets"):
            for c in sorted(x for x in d.iterdir() if x.is_dir()):
                if c.name == "_superseded":
                    continue
                sets = [c] if d.name == "photosets" else sorted(x for x in c.iterdir() if x.is_dir())
                for s in sets:
                    if s.name == "_superseded":
                        for old in sorted(x for x in s.iterdir() if x.is_dir()):
                            row(old, c.name.lower(), "shoot", old.name + "-superseded", True)
                        continue
                    kind = "selfies" if s.name == "selfies" else "shoot"
                    name = "photoset" if d.name == "photosets" else s.name
                    row(s, c.name.lower(), kind, name, False)
            continue
        cls = _classify(d.name, characters)
        row(d, *cls)
    return rows


def _judge_refs(judge_root: Path, outputs: Path, src: Path) -> list[str]:
    """Judge sets (live and retired) with at least one item inside `src`."""
    out = []
    for sub in ("sets", "retired"):
        for f in sorted((judge_root / sub).glob("*.json")):
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if any(_inside(it.get("path", ""), src, outputs.parent) for it in doc.get("items", [])):
                out.append(f"{sub}/{f.name}")
    return out


def _inside(path_str: str, folder: Path, engine_root: Path) -> Path | None:
    p = Path(path_str)
    if not p.is_absolute():
        p = engine_root / p
    try:
        return p.resolve().relative_to(folder.resolve())
    except (ValueError, OSError):
        return None


def write_plan(rows: list[dict], library: Path) -> tuple[Path, Path]:
    library.mkdir(parents=True, exist_ok=True)
    pj = library / "_plan.json"
    pj.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    lines = ["# Library plan - nothing has moved", "",
             "`sourcemode library apply` moves every `move` row, deletes every "
             "`remove-empty` folder, rewrites the judge sets listed, and writes set.json "
             "+ kept/ in each new folder. Edit the json to change a destination or set "
             "an action to `stay`.", "",
             "| action | from | to | files | date | judge sets |", "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["action"], r["character"] or "", r["src"])):
        lines.append(f"| {r['action']} | `{r['src']}` | {('`' + r['dst'] + '`') if r['dst'] else (r['note'] or '')} "
                     f"| {r['media']} | {r['date'] or ''} | {', '.join(r['judge_sets'])} |")
    pm = library / "_plan.md"
    pm.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pj, pm


# --- applying ------------------------------------------------------------------

def apply(rows: list[dict], outputs: Path, library: Path, judge_root: Path, *,
          dry_run: bool = False) -> list[str]:
    """Move, rewrite, link keepers. Returns a log. Refuses a destination that exists."""
    from .assets.judge import load_verdicts  # noqa: PLC0415

    log: list[str] = []
    engine_root = outputs.parent
    for r in rows:
        src = outputs / r["src"]
        if r["action"] == "remove-empty":
            if src.is_dir() and not any(src.rglob("*")):
                log.append(f"remove empty {r['src']}")
                if not dry_run:
                    shutil.rmtree(src)
            else:
                log.append(f"SKIP {r['src']}: not empty any more")
            continue
        if r["action"] != "move":
            continue
        dst = library / r["dst"]
        if not src.is_dir():
            log.append(f"SKIP {r['src']}: gone")
            continue
        if dst.exists():
            log.append(f"SKIP {r['src']}: {r['dst']} already exists")
            continue
        age = _youngest_file_age_s(src)
        if age is not None and age < SETTLE_S:
            # A sweep or shoot writing into the folder right now: moving it would
            # strand the rest of its renders. Re-run apply later; the plan keeps the row.
            log.append(f"SKIP {r['src']}: written {int(age)}s ago, still in use")
            continue
        log.append(f"move {r['src']} -> {r['dst']}")
        if dry_run:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        kept: dict[str, Path] = {}
        for ref in r["judge_sets"]:
            f = judge_root / ref
            doc = json.loads(f.read_text(encoding="utf-8"))
            n = 0
            for it in doc.get("items", []):
                rel = _rel_after_move(it.get("path", ""), src, engine_root)
                if rel is not None:
                    it["path"] = str(dst / rel)
                    n += 1
            rd = doc.get("meta", {}).get("renders_dir")
            if rd:
                rel = _rel_after_move(rd, src, engine_root)
                if rel is not None:
                    doc["meta"]["renders_dir"] = str(dst / rel) if str(rel) != "." else str(dst)
            f.write_text(json.dumps(doc, indent=1), encoding="utf-8")
            log.append(f"  rewrote {n} paths in {ref}")
            if ref.startswith("sets/"):
                verdicts = load_verdicts(judge_root, doc["id"])
                for it in doc.get("items", []):
                    p = Path(it["path"])
                    if verdicts.get(it["id"]) == "keep" and p.is_file() and _inside(str(p), dst, engine_root) is not None:
                        kept.setdefault(it["id"], p)
        if kept:
            kd = dst / "kept"
            kd.mkdir(exist_ok=True)
            for item_id, p in kept.items():
                target = kd / f"{slug(item_id)}{p.suffix.lower()}"
                if target.exists():
                    continue
                try:
                    os.link(p, target)
                except OSError:
                    shutil.copy2(p, target)
            log.append(f"  kept/ {len(kept)} keepers")
        write_set_json(dst, character=r["character"], kind=r["kind"], name=r["name"],
                       date=r["date"], moved_from=f"outputs/{r['src']}",
                       moved_at=time.strftime("%Y-%m-%dT%H:%M:%S"), files=r["files"],
                       judge_sets=[x.split("/", 1)[1].rsplit(".", 1)[0] for x in r["judge_sets"]],
                       kept=len(kept))
    return log


#: A folder with a file younger than this is being written by a running job.
SETTLE_S = 15 * 60


def _youngest_file_age_s(folder: Path) -> float | None:
    newest = None
    for root, _dirs, files in os.walk(folder):
        for f in files:
            m = os.path.getmtime(os.path.join(root, f))
            newest = m if newest is None or m > newest else newest
    return None if newest is None else time.time() - newest


def _rel_after_move(path_str: str, src: Path, engine_root: Path) -> Path | None:
    """Where a path that pointed into `src` (which no longer exists) sat inside it."""
    p = Path(path_str)
    if not p.is_absolute():
        p = engine_root / p
    try:
        return Path(os.path.normpath(p)).relative_to(Path(os.path.normpath(src)))
    except ValueError:
        return None


# --- pruning: what a locked winner makes redundant ---------------------------------
#
# Jeremy, 2026-10-09: "deleting every dense epoch eval photo set which already has
# an approved epoch winner, we don't need those ... all AB test packs that are
# older than 7 days." And the big one he did not ask for but the numbers made
# plain: 278 checkpoints, 328 GB, of which 24 are locked. A winner is a LOCK
# (train.locked) - committed, vaulted, hash-verified - and nothing here deletes
# until every lock verifies. `prune_plan` writes the table; `prune_apply` deletes
# the rows it is given, re-checking the lock set as it goes.

PRUNE_AB_DAYS = 7


def _newest_mtime(folder: Path) -> float | None:
    newest = None
    for r, _d, fs in os.walk(folder):
        for f in fs:
            m = os.path.getmtime(os.path.join(r, f))
            newest = m if newest is None or m > newest else newest
    return newest


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(os.path.getsize(os.path.join(r, f)) for r, _d, fs in os.walk(path) for f in fs)


def _is_ab(name: str) -> bool:
    low = name.lower()
    return low.startswith("ab_") or low.endswith("_ab") or "_ab_" in low


def prune_plan(cfg: dict, outputs: Path, judge_root: Path, *, ab_days: int = PRUNE_AB_DAYS,
               now: float | None = None) -> list[dict]:
    """Rows of {action, kind, path, why, bytes, character, judge_sets}. Deletes nothing."""
    from .train.locked import comfy_loras_dir, load_registry, locked_files  # noqa: PLC0415

    now = now or time.time()
    reg = load_registry()
    locked_chars = set(reg)
    keep = locked_files(cfg)
    rows: list[dict] = []

    def row(kind, path, why, char="", refs=()):
        rows.append({"action": "delete", "kind": kind, "path": str(path), "why": why,
                     "bytes": _size(path), "character": char, "judge_sets": list(refs)})

    for d in sorted(p for p in outputs.glob("dense_*") if p.is_dir()):
        char = _character_in(d.name, locked_chars)
        if char:
            row("folder", d, f"epoch sweep; {char} is locked to {reg[char]['file']}", char,
                _judge_refs(judge_root, outputs, d))
    for d in sorted(p for p in outputs.iterdir() if p.is_dir() and _is_ab(p.name)):
        newest = _newest_mtime(d)
        age = (now - newest) / 86400 if newest else None
        if age is not None and age > ab_days:
            row("folder", d, f"A/B set, {age:.0f} days old", _character_in(d.name, locked_chars) or "",
                _judge_refs(judge_root, outputs, d))
    base = outputs / "lora-datasets"
    if base.is_dir():
        for ds in sorted(p for p in base.iterdir() if p.is_dir()):
            char = _character_in(ds.name, locked_chars)
            if not char:
                continue
            for ck in sorted(ds.glob("lora*/*.safetensors")):
                if ck.resolve() not in keep:
                    row("file", ck, f"checkpoint that lost; {char} is locked to {reg[char]['file']}", char)
    comfy = comfy_loras_dir(cfg) / "sourcemode"
    if comfy.is_dir():
        for ck in sorted(comfy.glob("*/*.safetensors")):
            char = _character_in(ck.parent.name, locked_chars)
            if char and ck.resolve() not in keep:
                row("file", ck, f"staged in ComfyUI but not the lock; {char} is locked to {reg[char]['file']}", char)
    return rows


def write_prune(rows: list[dict], library: Path) -> tuple[Path, Path]:
    library.mkdir(parents=True, exist_ok=True)
    pj, pm = library / "_prune.json", library / "_prune.md"
    pj.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    total = sum(r["bytes"] for r in rows)
    lines = ["# Prune plan - nothing has been deleted", "",
             f"`sourcemode library prune --apply` deletes every row below ({total / 1e9:.1f} GB). "
             "Remove a row from the json to keep it. Every locked LoRA must verify first.", "",
             "| kind | path | GB | why | judge sets |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['kind']} | `{r['path']}` | {r['bytes'] / 1e9:.2f} | {r['why']} | "
                     f"{', '.join(r['judge_sets'])} |")
    pm.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pj, pm


def _retire_sets(judge_root: Path, refs: list[str]) -> list[str]:
    """sets/<id>.json -> retired/<id>.set.json, the convention already on disk."""
    done = []
    for ref in refs:
        src = judge_root / ref
        if src.is_file() and src.parent.name == "sets":
            dst = judge_root / "retired" / (src.stem + ".set.json")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            done.append(dst.name)
    return done


def prune_apply(cfg: dict, rows: list[dict], judge_root: Path, *, dry_run: bool = False) -> list[str]:
    """Delete the rows. Refuses outright when any lock fails to verify - the losers
    are only redundant while the winner is safe."""
    from .train.locked import locked_files, verify  # noqa: PLC0415

    bad = [r for r in verify(cfg) if not r["ok"]]
    if bad:
        return [f"REFUSED: {r['character']}: {'; '.join(r['problems'])}" for r in bad]
    keep = locked_files(cfg)
    log = []
    for r in rows:
        if r.get("action") != "delete":
            continue
        p = Path(r["path"])
        if p.resolve() in keep:
            log.append(f"SKIP {p}: locked")
            continue
        if not p.exists():
            log.append(f"SKIP {p}: already gone")
            continue
        if r["kind"] == "folder":
            age = _youngest_file_age_s(p)
            if age is not None and age < SETTLE_S:
                log.append(f"SKIP {p}: written {age:.0f}s ago - still in use")
                continue
        line = f"delete {r['kind']} {p} ({r['bytes'] / 1e9:.2f} GB)"
        if dry_run:
            log.append(line)
            continue
        if r["kind"] == "folder":
            shutil.rmtree(p)
            retired = _retire_sets(judge_root, r.get("judge_sets") or [])
            line += f"; retired {', '.join(retired)}" if retired else ""
        else:
            p.unlink()
        log.append(line)
    return log
