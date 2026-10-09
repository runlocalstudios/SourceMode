"""Which LoRA is a character's approved one, and is there one at all.

Three things count as approved, and the order matters:

0. a LOCK in characters/loras.json - committed, hashed, vaulted (train.locked)
1. an epoch-choice record - she was swept, judged, and an epoch was picked
2. a lora directory pruned to ONE checkpoint - the prune IS the choice, made
   by hand before the epoch board existed

Anything else - nine checkpoints and no record - is not approved, it is
undecided, and the shoots tab must not offer it. Picking silently would be
guessing at the one decision the whole sweep exists to make.
"""

from __future__ import annotations

import re
from pathlib import Path


def comfy_path(filename: str) -> str:
    """Where ComfyUI has a checkpoint: `sourcemode/<output name>/<file>`.

    Keyed by the FILENAME, never the dataset folder. A continuation run saves
    `priyanka_v2b-000006.safetensors` into priyanka_v2's training folder, but it
    is staged in ComfyUI under `priyanka_v2b/` - its output name - so a path
    built from the dataset name failed all 14 of her influencer renders.
    """
    stem = re.sub(r"-\d{6}$", "", Path(filename).stem)
    return str(Path("sourcemode") / stem / Path(filename).name)


def resolve_lora(cfg: dict, character: str) -> dict | None:
    """Her approved checkpoint as ComfyUI needs it, or None.

    Returns `{dataset, name, path, why}` - `path` relative to ComfyUI's loras
    dir, which is what every workflow template expects.
    """
    from ..config import outputs_dir  # noqa: PLC0415
    from ..train.epochs import checkpoint_dirs, load_choice  # noqa: PLC0415
    from ..train.locked import locked  # noqa: PLC0415

    out = outputs_dir(cfg)
    c = character.lower()

    # 0. the lock. characters/loras.json is committed and the bytes sit in the
    # vault, so this answer survives a prune, a library move and a fresh
    # checkout - which is the point. A locked file that is not staged in
    # ComfyUI is still the answer; `sourcemode lora verify` is what says so.
    lk = locked(cfg, c)
    if lk:
        return {"dataset": lk["dataset"], "name": lk["file"], "epoch": lk.get("epoch"),
                "path": comfy_path(lk["file"]),
                "why": f"locked: {lk.get('basis') or 'epoch ' + str(lk.get('epoch'))}"}

    rec = load_choice(out, c)
    if rec and rec.get("lora") and Path(rec["lora"]).is_file():
        p = Path(rec["lora"])
        return {"dataset": rec["dataset"], "name": p.name, "epoch": rec.get("epoch"),
                "path": comfy_path(p.name),
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
                    "path": comfy_path(ckpts[0].name),
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
                     "appearance_missing": [m.split(" - ")[0] for m in ap["missing"]],
                     "blocked": blocked_shoots(cfg, c)})
    return sorted(rows, key=lambda r: r["character"])


def blocked_shoots(cfg: dict, character: str) -> dict[str, str]:
    """`{shoot_id: why it cannot run for her}`, so the tab can grey the box and
    say what is missing instead of letting her queue a job that dies at the
    guard an hour later.

    Today only the wardrobe pack can be blocked: its 28 outfits are a decision
    somebody makes per character, and a plan that does not exist is not a
    default to fall back on.
    """
    from ..config import outputs_dir  # noqa: PLC0415
    from .shoots import CATALOG, plan_path  # noqa: PLC0415

    out = outputs_dir(cfg)
    blocked = {}
    for sh in CATALOG:
        pp = plan_path(sh, character, out)
        if pp is not None and not pp.is_file():
            blocked[sh.id] = ("no wardrobe plan yet - the 28 outfits have to be "
                              "decided before they can be rendered")
    return blocked
