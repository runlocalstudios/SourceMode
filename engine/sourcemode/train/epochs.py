"""Which checkpoint is the live one for a character, and why.

The epoch sweep's judge set already answers "which epoch is her best": its arms
ARE the epochs (`ash_v2 epoch 16` ... `ash_v2 epoch 24`), and `judge.summary()`
already returns the keep rate per arm plus a per-scene cross-tab. What was
missing was a *record*. Without one:

- the last step of a 7-hour chain is retyping
  `...\\lora\\ash_v2-000021.safetensors` into an asset plan by hand,
- nothing downstream can tell which epoch is live, and
- a prune takes the answer with it. `outputs/lora-datasets/ash_v2/lora/` holds
  exactly one file today; the losers are gone, and so is any memory of why that
  one survived.

One file per character, written atomically, carrying the evidence it was chosen
on so the choice can be argued with later.

    outputs/epoch-choices/<character>.json

    GET  /epochs                 every choice, newest first
    GET  /epochs/{character}     one, or 404
    POST /epochs/{character}     {dataset, output_name, epoch, from_set, keep, n, low}

Nothing in this module starts, copies or loads anything. It writes one JSON file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def choices_dir(outputs_root: Path) -> Path:
    return Path(outputs_root) / "epoch-choices"


def checkpoint_dirs(outputs_root: Path, dataset: str, output_name: str = "") -> list[Path]:
    """Every directory that may hold this dataset's checkpoints.

    NOT just `lora/`. On disk `bianca_v2/` has `lora/`, `lora_bianca_lr2/` and
    `lora_bianca_lr2b/` side by side, and the sweep's ARM says which one it means
    (`bianca_lr2b epoch 25`). `queue_page.candidates()` and `_rate()` both assume
    `lora/` alone, so a run whose checkpoints landed in a sibling reads as
    approved-and-untrained forever. One helper, so every surface agrees about
    what "trained" means.
    """
    root = Path(outputs_root) / "lora-datasets"
    base = root / dataset
    want = [base / "lora"]
    if output_name:
        want.append(base / f"lora_{output_name}")
    if base.is_dir():
        want += sorted(p for p in base.glob("lora*") if p.is_dir())
    elif output_name and root.is_dir():
        # The sweep's prefix is an OUTPUT NAME, and it is not always a dataset:
        # `dense_bianca_lr2b_fav` resolves to a dataset "bianca_lr2b" that has no
        # directory, because those checkpoints live in
        # bianca_v2/lora_bianca_lr2b/. Rather than record `lora: null` for a file
        # that is on disk, look for the sibling that owns this output name.
        want += sorted(root.glob(f"*/lora_{output_name}"))
    seen: set[Path] = set()
    out: list[Path] = []
    for p in want:
        if p not in seen and p.is_dir():
            seen.add(p)
            out.append(p)
    return out


def checkpoint_for(outputs_root: Path, dataset: str, output_name: str,
                   epoch: int) -> str | None:
    """Resolve the .safetensors for one epoch, or None.

    Globbed rather than formatted, because of one thing the obvious glob misses:
    **the final epoch has no numeric suffix.** On disk,
    `amanda_internal_v2/lora/` holds `-000001` .. `-000023` plus a bare
    `amanda_internal_v2.safetensors` - that bare file IS epoch 24. A
    `*-{epoch:06d}` glob alone returns None for the final epoch, which is often
    the winner, and would record `lora: null` for the one checkpoint that
    matters most.

    The bare file is accepted ONLY when nothing numbered in that directory is
    higher. That is the exact test and it needs no caller-supplied epoch count:
    on a 16-19 sweep, epoch 19 is the sweep's top arm but not the run's last
    epoch, and the bare file there belongs to a later epoch entirely.
    """
    tail = f"-{int(epoch):06d}.safetensors"
    subs = checkpoint_dirs(outputs_root, dataset, output_name)
    for sub in subs:
        hit = sorted(sub.glob("*" + tail))
        if hit:
            return str(hit[0])
    for sub in subs:
        numbered = [int(q.stem.rsplit("-", 1)[-1]) for q in sub.glob("*-*.safetensors")
                    if q.stem.rsplit("-", 1)[-1].isdigit()]
        for bare in (sub / f"{output_name}.safetensors", sub / f"{dataset}.safetensors"):
            if bare.is_file() and (not numbered or int(epoch) > max(numbered)):
                return str(bare)
    return None


def record_choice(outputs_root: Path, character: str, *, dataset: str,
                  output_name: str = "", epoch: int, from_set: str = "",
                  keep: int | None = None, n: int | None = None,
                  low: float | None = None) -> dict:
    """Write the choice. Atomic, one file, and it saves even with no checkpoint.

    `"lora": null` when the file is not on disk: a choice is a judgement, and a
    missing file is not a reason to refuse to record it. The page says
    "checkpoint missing (pruned?)" rather than losing the answer - which is the
    ash_v2 case, where 23 of 24 checkpoints are already gone.
    """
    if not character or "/" in character or "\\" in character or ".." in character:
        raise ValueError("a character id is required")
    out_name = output_name or dataset
    rec = {"character": character, "dataset": dataset, "output_name": out_name,
           "epoch": int(epoch),
           "lora": checkpoint_for(outputs_root, dataset, out_name, int(epoch)),
           "keep": keep, "n": n,
           "rate": round(keep / n, 3) if (keep is not None and n) else None,
           "low": low, "from_set": from_set,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    d = choices_dir(outputs_root)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (character + ".json.tmp")
    tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    tmp.replace(d / (character + ".json"))
    return rec


def load_choice(outputs_root: Path, character: str) -> dict | None:
    if not character or "/" in character or "\\" in character or ".." in character:
        return None
    p = choices_dir(outputs_root) / (character + ".json")
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_choices(outputs_root: Path) -> list[dict]:
    d = choices_dir(outputs_root)
    out: list[dict] = []
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue   # a half-written file is not a reason to lose the rest
    return sorted(out, key=lambda r: r.get("at") or "", reverse=True)


def epochs_router(cfg: dict):
    from fastapi import APIRouter, Body, HTTPException  # noqa: PLC0415

    from ..config import outputs_dir  # noqa: PLC0415

    r, out = APIRouter(), outputs_dir(cfg)

    @r.get("/epochs")
    def _all() -> list[dict]:
        return list_choices(out)

    @r.get("/epochs/{character}")
    def _one(character: str) -> dict:
        rec = load_choice(out, character)
        if rec is None:
            raise HTTPException(404, f"no epoch choice recorded for {character}")
        return rec

    @r.post("/epochs/{character}")
    def _set(character: str, body: dict = Body(...)) -> dict:
        try:
            rec = record_choice(
                out, character, dataset=str(body["dataset"]),
                output_name=str(body.get("output_name") or ""),
                epoch=int(body["epoch"]), from_set=str(body.get("from_set") or ""),
                keep=body.get("keep"), n=body.get("n"), low=body.get("low"))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        # The choice IS the lock. A record alone was how sunny's and bianca's
        # best checkpoints went missing: chosen on the page, pruned from disk.
        from .locked import LockError, lock  # noqa: PLC0415

        if rec.get("lora"):
            basis = f"{rec['from_set']} {rec.get('keep')}/{rec.get('n')} at epoch {rec['epoch']}"
            try:
                rec["locked"] = lock(cfg, character, Path(rec["lora"]), epoch=rec["epoch"],
                                     dataset=rec["dataset"], basis=basis)
            except LockError as exc:
                rec["locked"] = None
                rec["lock_error"] = str(exc)
        else:
            rec["locked"] = None
            rec["lock_error"] = "checkpoint not on disk - nothing to lock"
        return rec

    return r
