"""Which LoRA is a character's approved one, and is there one at all.

Two things count as approved, and the order matters:

1. an epoch-choice record - she was swept, judged, and an epoch was picked
2. a lora directory pruned to ONE checkpoint - the prune IS the choice, made
   by hand before the epoch board existed

Anything else - nine checkpoints and no record - is not approved, it is
undecided, and the shoots tab must not offer it. Picking silently would be
guessing at the one decision the whole sweep exists to make.
"""

from __future__ import annotations

from pathlib import Path


def resolve_lora(cfg: dict, character: str) -> dict | None:
    """Her approved checkpoint as ComfyUI needs it, or None.

    Returns `{dataset, name, path, why}` - `path` relative to ComfyUI's loras
    dir, which is what every workflow template expects.
    """
    from ..config import outputs_dir  # noqa: PLC0415
    from ..train.epochs import checkpoint_dirs, load_choice  # noqa: PLC0415

    out = outputs_dir(cfg)
    c = character.lower()

    rec = load_choice(out, c)
    if rec and rec.get("lora") and Path(rec["lora"]).is_file():
        p = Path(rec["lora"])
        return {"dataset": rec["dataset"], "name": p.name, "epoch": rec.get("epoch"),
                "path": str(Path("sourcemode") / rec["dataset"] / p.name),
                "why": f"epoch {rec.get('epoch')} chosen on the judge page"}

    base = out / "lora-datasets"
    if not base.is_dir():
        return None
    # `<char>_v2` is the convention; fall back to any dataset whose name starts
    # with her, so a `_curated` or `_v3` set is still found.
    for ds in sorted(base.glob(f"{c}_*"), key=lambda p: (p.name != f"{c}_v2", p.name)):
        if not ds.is_dir():
            continue
        ckpts = [k for sub in checkpoint_dirs(out, ds.name) for k in sub.glob("*.safetensors")]
        if len(ckpts) == 1:
            return {"dataset": ds.name, "name": ckpts[0].name, "epoch": None,
                    "path": str(Path("sourcemode") / ds.name / ckpts[0].name),
                    "why": "pruned to one checkpoint - the prune was the choice"}
    return None


def approved_characters(cfg: dict) -> list[dict]:
    """Everyone the shoots tab may offer, with why she qualifies and whether her
    appearance record is ready. Sorted by name."""
    from ..assets.appearance import check  # noqa: PLC0415
    from ..config import outputs_dir  # noqa: PLC0415
    from ..monitor.queue_page import character_of  # noqa: PLC0415

    out = outputs_dir(cfg)
    base = out / "lora-datasets"
    seen, rows = set(), []
    for ds in sorted(base.glob("*")) if base.is_dir() else []:
        if not ds.is_dir():
            continue
        c = character_of(ds.name).replace("_curated", "").replace("_internal", "")
        if c in seen:
            continue
        lora = resolve_lora(cfg, c)
        if not lora:
            continue
        seen.add(c)
        ap = check(c)
        rows.append({"character": c, "who": c.replace("_", " ").title(),
                     "lora": lora["name"], "why": lora["why"],
                     "appearance_ok": ap["ok"],
                     "appearance_missing": [m.split(" - ")[0] for m in ap["missing"]]})
    return sorted(rows, key=lambda r: r["character"])
