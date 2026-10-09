"""The locked LoRA per character: decided once, written down, copied out of
harm's way, verified by hash.

Jeremy, 2026-10-09: "I absolutely need you to codify and ENSURE the LoRAs we have
trained and decided are best are LOCKED AND LOADED. You MUST ENSURE I DO NOT HAVE
TO RETELL YOU WHICH ARE BEST OR RETRAIN."

What went wrong before this existed, on disk today:

- sunny_v2/lora/ is EMPTY and so is her ComfyUI folder. Her chosen epoch 24
  (10/20) is gone from the machine. She has to be retrained.
- bianca's lr-2e-4 run read 16/20 at epoch 24 - her best - and both
  lora_bianca_lr2/ and lora_bianca_lr2b/ are empty. The 45% epoch-20 file is
  what survived.
- outputs/epoch-choices/ holds five records; the other fifteen decided
  characters are "decided" only because somebody pruned their folder to one
  file, and nothing says which epoch that was or why.

So three things, none of which the epoch-choices record did:

1. **A registry in the repo**, `characters/loras.json`, committed. It names
   the file, the epoch, the sha256 and the evidence. It is not under outputs/,
   so no prune, no library move and no fresh checkout loses it.
2. **A vault copy**, `library/loras/<character>/<file>`, outside the training
   folder the sweeps and prunes work in. ComfyUI is re-staged from it.
3. **A verify** that walks the registry and says, per character, whether the
   vault file and the ComfyUI file are present and hash-identical to what was
   locked. `sourcemode lora verify` exits non-zero on any miss; it belongs in
   the pre-flight of anything that renders.

`resolve_lora()` consults the registry first, so a shoot renders with the
locked file whatever the training folder holds. A prune that wants to delete a
checkpoint asks `locked_files()` first.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "characters" / "loras.json"
DEFAULT_COMFY_LORAS = Path("C:/ComfyUI/models/loras")


class LockError(RuntimeError):
    pass


def registry_path() -> Path:
    return REGISTRY


def load_registry(path: Path | None = None) -> dict:
    p = path or REGISTRY
    if not p.is_file():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def _write_registry(entries: dict, path: Path | None = None) -> None:
    p = path or REGISTRY
    doc = {"_comment": [
        "The locked LoRA per character: file, epoch, sha256 and the evidence it was chosen on.",
        "Written by `sourcemode lora lock` and by the epoch board; read by resolve_lora().",
        "The vault copy is library/loras/<character>/<file>; `sourcemode lora verify` checks it.",
        "Edit by hand only to unlock (delete the entry). Never retype a file name here.",
    ]}
    doc.update({k: entries[k] for k in sorted(entries)})
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    tmp.replace(p)


def vault_dir(cfg: dict) -> Path:
    from ..library import library_dir  # noqa: PLC0415
    return library_dir(cfg) / "loras"


def comfy_loras_dir(cfg: dict) -> Path:
    p = (cfg.get("comfyui") or {}).get("loras_dir")
    return Path(p) if p else DEFAULT_COMFY_LORAS


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _output_name(filename: str) -> str:
    import re  # noqa: PLC0415
    return re.sub(r"-\d{6}$", "", Path(filename).stem)


def comfy_target(cfg: dict, filename: str) -> Path:
    """`<loras>/sourcemode/<output name>/<file>` - the layout every workflow
    template and `assets.lora.comfy_path` already assume."""
    return comfy_loras_dir(cfg) / "sourcemode" / _output_name(filename) / Path(filename).name


def vault_target(cfg: dict, character: str, filename: str) -> Path:
    return vault_dir(cfg) / character / Path(filename).name


def _check_character(character: str) -> str:
    c = (character or "").strip().lower()
    if not c or "/" in c or "\\" in c or ".." in c:
        raise LockError("a character id is required")
    return c


def _same(a: Path, b: Path) -> bool:
    return a.is_file() and b.is_file() and a.stat().st_size == b.stat().st_size and sha256(a) == sha256(b)


def lock(cfg: dict, character: str, source: Path, *, epoch: int | None, dataset: str,
         basis: str = "", registry: Path | None = None, log=lambda m: None) -> dict:
    """Lock `source` as the character's LoRA: vault copy, ComfyUI copy, registry row.

    Refuses to overwrite a vault file of the same name with different bytes -
    that is the one way a lock could silently change what it points at. Unlock
    by deleting the entry (and the vault file) first.
    """
    c = _check_character(character)
    src = Path(source)
    if not src.is_file():
        raise LockError(f"{src} is not a file")
    digest = sha256(src)
    vt = vault_target(cfg, c, src.name)
    if vt.is_file():
        if sha256(vt) != digest:
            raise LockError(f"{vt} exists with different bytes; unlock {c} before locking a new file")
        log(f"vault: {vt.name} already present, hash matches")
    else:
        vt.parent.mkdir(parents=True, exist_ok=True)
        tmp = vt.with_suffix(vt.suffix + ".part")
        shutil.copy2(src, tmp)
        if sha256(tmp) != digest:
            tmp.unlink(missing_ok=True)
            raise LockError(f"vault copy of {src.name} did not verify")
        tmp.replace(vt)
        log(f"vault: copied {src.name} -> {vt}")
    ct = comfy_target(cfg, src.name)
    if ct.is_file() and sha256(ct) == digest:
        log(f"comfy: {ct} present, hash matches")
    else:
        ct.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(vt, ct)
        log(f"comfy: staged {ct}")
    entries = load_registry(registry)
    entries[c] = {
        "file": src.name, "epoch": epoch, "dataset": dataset,
        "output_name": _output_name(src.name),
        "sha256": digest, "bytes": src.stat().st_size,
        "comfy": str(Path("sourcemode") / _output_name(src.name) / src.name),
        "basis": basis, "locked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_registry(entries, registry)
    return entries[c]


def locked(cfg: dict, character: str, registry: Path | None = None) -> dict | None:
    """The registry row plus where the bytes are, or None when she is not locked."""
    c = (character or "").strip().lower()
    row = load_registry(registry).get(c)
    if not row:
        return None
    vt = vault_target(cfg, c, row["file"])
    ct = comfy_target(cfg, row["file"])
    return {**row, "character": c, "vault": str(vt), "vault_present": vt.is_file(),
            "comfy_path": str(ct), "comfy_present": ct.is_file()}


def verify(cfg: dict, registry: Path | None = None, *, hashes: bool = True) -> list[dict]:
    """One row per locked character. `ok` is False when either copy is missing
    or, with `hashes`, when either differs from the locked sha256."""
    rows = []
    for c, row in sorted(load_registry(registry).items()):
        vt = vault_target(cfg, c, row["file"])
        ct = comfy_target(cfg, row["file"])
        v_ok = vt.is_file() and (not hashes or sha256(vt) == row["sha256"])
        c_ok = ct.is_file() and (not hashes or sha256(ct) == row["sha256"])
        problems = []
        if not vt.is_file():
            problems.append("vault copy missing")
        elif not v_ok:
            problems.append("vault copy differs from the locked hash")
        if not ct.is_file():
            problems.append("not staged in ComfyUI")
        elif not c_ok:
            problems.append("ComfyUI copy differs from the locked hash")
        rows.append({"character": c, "file": row["file"], "epoch": row.get("epoch"),
                     "basis": row.get("basis", ""), "vault_ok": v_ok, "comfy_ok": c_ok,
                     "ok": v_ok and c_ok, "problems": problems})
    return rows


def restage(cfg: dict, character: str, registry: Path | None = None) -> Path:
    """Put the vault copy back into ComfyUI. The vault is the truth."""
    c = _check_character(character)
    row = load_registry(registry).get(c)
    if not row:
        raise LockError(f"{c} is not locked")
    vt = vault_target(cfg, c, row["file"])
    if not vt.is_file() or sha256(vt) != row["sha256"]:
        raise LockError(f"vault copy for {c} is missing or does not match its hash; nothing to restage from")
    ct = comfy_target(cfg, row["file"])
    ct.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(vt, ct)
    return ct


def locked_files(cfg: dict, registry: Path | None = None) -> set[Path]:
    """Every path a prune must leave alone: the vault copies, the ComfyUI copies,
    and any training-folder file with a locked name."""
    from ..config import outputs_dir  # noqa: PLC0415
    keep: set[Path] = set()
    out = outputs_dir(cfg)
    for c, row in load_registry(registry).items():
        keep.add(vault_target(cfg, c, row["file"]).resolve())
        keep.add(comfy_target(cfg, row["file"]).resolve())
        base = out / "lora-datasets"
        if base.is_dir():
            keep |= {p.resolve() for p in base.glob(f"*/lora*/{row['file']}")}
    return keep


def unlock(cfg: dict, character: str, registry: Path | None = None) -> dict | None:
    """Remove the lock and its vault copy. The ComfyUI copy stays - sweeps stage
    every epoch there anyway and the eval expects them. Returns the row removed."""
    c = _check_character(character)
    entries = load_registry(registry)
    row = entries.pop(c, None)
    if row is None:
        return None
    _write_registry(entries, registry)
    vt = vault_target(cfg, c, row["file"])
    if vt.is_file():
        vt.unlink()
    try:
        vt.parent.rmdir()
    except OSError:
        pass
    return row
