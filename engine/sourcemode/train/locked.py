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
2. **A vault copy**, `library/loras/<character>/<character>.safetensors`,
   outside the training folder the sweeps and prunes work in. ComfyUI is
   re-staged from it.
3. **A verify** that walks the registry and says, per character, whether the
   vault file and the ComfyUI file are present and hash-identical to what was
   locked. `sourcemode lora verify` exits non-zero on any miss; it belongs in
   the pre-flight of anything that renders.

**One name per character.** Jeremy, 2026-10-15: "I would prefer all final named
LoRAs just be the model's name so Priyanka.safetensors." The lock is her LoRA,
whatever epoch of whatever run it came from, so every copy outside the training
folder is `<character>.safetensors`:

    library/loras/<character>/<character>.safetensors     the vault
    <comfy loras>/sourcemode/<character>.safetensors       what renders load
    <backup>/<character>.safetensors                       Google Drive mirror

The training folder keeps the trainer's own name (`vivienne_v2b.safetensors`,
`gabi_v2-000022.safetensors`): that is provenance, the sweep arms refer to it,
and the registry's `file` records it. `sourcemode/<output name>/` stays the
sweep's staging area for candidate epochs; the lock does not live in it.

**A relock never destroys bytes.** Choosing a new epoch on the judge page locks
again under the same name. The old vault file moves to
`library/loras/<character>/_previous/<its trainer name>` first, and the registry
row it replaces is in git. Nothing here deletes a LoRA, ever.

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
PREVIOUS = "_previous"


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
        "`file` is the trainer's name for the checkpoint (provenance). Every copy outside the",
        "training folder is `<character>.safetensors`: library/loras/<character>/, ComfyUI's",
        "loras/sourcemode/, and the backup dir. `sourcemode lora verify` checks them all.",
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


def backup_dir(cfg: dict) -> Path | None:
    """Where a second copy of every lock goes, or None when nothing is configured.
    `[paths] lora_backup` - his Google Drive folder, so Drive for Desktop carries
    the file off the machine. Only the directory is asked for; a missing drive is
    a `verify` problem, not a reason a lock cannot be made."""
    p = (cfg.get("paths") or {}).get("lora_backup")
    return Path(p) if p else None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _output_name(filename: str) -> str:
    import re  # noqa: PLC0415
    return re.sub(r"-\d{6}$", "", Path(filename).stem)


def lock_name(character: str) -> str:
    """`<character>.safetensors` - the one name her lock has everywhere."""
    return f"{_check_character(character)}.safetensors"


def comfy_target(cfg: dict, character: str) -> Path:
    """`<loras>/sourcemode/<character>.safetensors`. Flat: the per-output-name
    subfolders are the sweep's staging area, and a prune empties those."""
    return comfy_loras_dir(cfg) / "sourcemode" / lock_name(character)


def comfy_rel(character: str) -> str:
    """The same path as ComfyUI's LoraLoader wants it, relative to its loras dir."""
    return str(Path("sourcemode") / lock_name(character))


def vault_target(cfg: dict, character: str) -> Path:
    return vault_dir(cfg) / _check_character(character) / lock_name(character)


def backup_target(cfg: dict, character: str) -> Path | None:
    b = backup_dir(cfg)
    return (b / lock_name(character)) if b else None


def _check_character(character: str) -> str:
    c = (character or "").strip().lower()
    if not c or "/" in c or "\\" in c or ".." in c:
        raise LockError("a character id is required")
    return c


def _copy_verified(src: Path, dst: Path, digest: str) -> None:
    """Copy through a .part file and refuse to leave a wrong-hash file behind."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    shutil.copy2(src, tmp)
    if sha256(tmp) != digest:
        tmp.unlink(missing_ok=True)
        raise LockError(f"copy of {src.name} to {dst} did not verify")
    tmp.replace(dst)


def _set_aside(vt: Path, provenance: str, log) -> Path:
    """Move the vault file that is about to be replaced into _previous/ under
    the trainer's name for it. Never overwrites: a name clash gets the hash."""
    prev = vt.parent / PREVIOUS
    prev.mkdir(parents=True, exist_ok=True)
    dst = prev / (provenance or vt.name)
    if dst.exists():
        dst = prev / f"{dst.stem}.{sha256(vt)[:12]}{dst.suffix}"
    shutil.move(str(vt), str(dst))
    log(f"vault: previous lock kept as {dst}")
    return dst


def mirror(cfg: dict, character: str, digest: str, log=lambda m: None) -> bool:
    """Put the vault copy into the backup dir. True when the backup is present
    and verified; False when no backup dir is configured or the drive is away.
    Never raises on a missing drive - the lock is already safe in the vault."""
    bt = backup_target(cfg, character)
    if bt is None:
        return False
    if bt.is_file() and sha256(bt) == digest:
        log(f"backup: {bt} present, hash matches")
        return True
    try:
        _copy_verified(vault_target(cfg, character), bt, digest)
    except (OSError, LockError) as exc:
        log(f"backup: WARNING could not write {bt}: {exc}")
        return False
    log(f"backup: copied -> {bt}")
    return True


def lock(cfg: dict, character: str, source: Path, *, epoch: int | None, dataset: str,
         basis: str = "", registry: Path | None = None, log=lambda m: None) -> dict:
    """Lock `source` as the character's LoRA: vault copy, ComfyUI copy, backup
    copy, registry row - all named `<character>.safetensors`.

    A relock (a different checkpoint chosen later) sets the old vault file aside
    in `_previous/` under its trainer name before writing. Bytes are never lost;
    the registry row it replaces is in git history.
    """
    c = _check_character(character)
    src = Path(source)
    if not src.is_file():
        raise LockError(f"{src} is not a file")
    digest = sha256(src)
    entries = load_registry(registry)
    old = entries.get(c) or {}
    vt = vault_target(cfg, c)
    if vt.is_file():
        if sha256(vt) == digest:
            log(f"vault: {vt.name} already present, hash matches")
        else:
            _set_aside(vt, old.get("file", ""), log)
            _copy_verified(src, vt, digest)
            log(f"vault: copied {src.name} -> {vt}")
    else:
        _copy_verified(src, vt, digest)
        log(f"vault: copied {src.name} -> {vt}")
    ct = comfy_target(cfg, c)
    if ct.is_file() and sha256(ct) == digest:
        log(f"comfy: {ct} present, hash matches")
    else:
        _copy_verified(vt, ct, digest)
        log(f"comfy: staged {ct}")
    mirror(cfg, c, digest, log)
    entries[c] = {
        "name": lock_name(c), "file": src.name, "epoch": epoch, "dataset": dataset,
        "output_name": _output_name(src.name),
        "sha256": digest, "bytes": src.stat().st_size,
        "comfy": comfy_rel(c),
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
    vt = vault_target(cfg, c)
    ct = comfy_target(cfg, c)
    return {**row, "character": c, "name": lock_name(c), "comfy": comfy_rel(c),
            "vault": str(vt), "vault_present": vt.is_file(),
            "comfy_path": str(ct), "comfy_present": ct.is_file()}


def verify(cfg: dict, registry: Path | None = None, *, hashes: bool = True) -> list[dict]:
    """One row per locked character. `ok` is False when either copy is missing
    or, with `hashes`, when either differs from the locked sha256. The backup
    copy is checked too when a backup dir is configured; `backup_ok` is None
    when none is."""
    rows = []
    for c, row in sorted(load_registry(registry).items()):
        vt = vault_target(cfg, c)
        ct = comfy_target(cfg, c)
        bt = backup_target(cfg, c)

        def _ok(p: Path | None) -> bool | None:
            if p is None:
                return None
            return p.is_file() and (not hashes or sha256(p) == row["sha256"])

        v_ok, c_ok, b_ok = _ok(vt), _ok(ct), _ok(bt)
        problems = []
        if not vt.is_file():
            problems.append("vault copy missing")
        elif not v_ok:
            problems.append("vault copy differs from the locked hash")
        if not ct.is_file():
            problems.append("not staged in ComfyUI")
        elif not c_ok:
            problems.append("ComfyUI copy differs from the locked hash")
        if bt is not None:
            if not bt.is_file():
                problems.append("backup copy missing")
            elif not b_ok:
                problems.append("backup copy differs from the locked hash")
        # `ok` is what renders and prunes need: the vault and the ComfyUI copy. The
        # backup may be a USB drive that is not plugged in or a cloud folder that is
        # signed out; that is a problem to report, never a reason a prune refuses.
        rows.append({"character": c, "name": lock_name(c), "file": row["file"], "epoch": row.get("epoch"),
                     "basis": row.get("basis", ""), "vault_ok": bool(v_ok), "comfy_ok": bool(c_ok),
                     "backup_ok": b_ok, "ok": bool(v_ok and c_ok), "problems": problems})
    return rows


def restage(cfg: dict, character: str, registry: Path | None = None) -> Path:
    """Put the vault copy back into ComfyUI. The vault is the truth."""
    c = _check_character(character)
    row = load_registry(registry).get(c)
    if not row:
        raise LockError(f"{c} is not locked")
    vt = vault_target(cfg, c)
    if not vt.is_file() or sha256(vt) != row["sha256"]:
        raise LockError(f"vault copy for {c} is missing or does not match its hash; nothing to restage from")
    ct = comfy_target(cfg, c)
    _copy_verified(vt, ct, row["sha256"])
    return ct


def backup_all(cfg: dict, registry: Path | None = None, log=lambda m: None) -> list[dict]:
    """Mirror every lock into the backup dir. One row per character:
    {character, ok, problem}. Raises when no backup dir is configured."""
    if backup_dir(cfg) is None:
        raise LockError("no backup dir: set [paths] lora_backup in config.toml")
    rows = []
    for c, row in sorted(load_registry(registry).items()):
        vt = vault_target(cfg, c)
        if not vt.is_file() or sha256(vt) != row["sha256"]:
            rows.append({"character": c, "ok": False, "problem": "vault copy missing or wrong; nothing to back up"})
            continue
        ok = mirror(cfg, c, row["sha256"], log)
        rows.append({"character": c, "ok": ok, "problem": "" if ok else "backup dir not writable"})
    return rows


def locked_files(cfg: dict, registry: Path | None = None) -> set[Path]:
    """Every path a prune must leave alone: the vault copies and everything set
    aside beside them, the ComfyUI copies, the backup copies, and any
    training-folder file with a locked name."""
    from ..config import outputs_dir  # noqa: PLC0415
    keep: set[Path] = set()
    out = outputs_dir(cfg)
    for c, row in load_registry(registry).items():
        vt = vault_target(cfg, c)
        keep.add(vt.resolve())
        keep |= {p.resolve() for p in vt.parent.glob("*") if p.is_file()}
        keep |= {p.resolve() for p in (vt.parent / PREVIOUS).glob("*") if p.is_file()}
        keep.add(comfy_target(cfg, c).resolve())
        bt = backup_target(cfg, c)
        if bt is not None:
            keep.add(bt.resolve())
        base = out / "lora-datasets"
        if base.is_dir():
            keep |= {p.resolve() for p in base.glob(f"*/lora*/{row['file']}")}
    return keep


def unlock(cfg: dict, character: str, registry: Path | None = None) -> dict | None:
    """Remove the lock from the registry and set its vault copy aside in
    _previous/ - an unlock is a decision to choose again, not to lose the
    file. The ComfyUI copy stays. Returns the row removed."""
    c = _check_character(character)
    entries = load_registry(registry)
    row = entries.pop(c, None)
    if row is None:
        return None
    _write_registry(entries, registry)
    vt = vault_target(cfg, c)
    if vt.is_file():
        _set_aside(vt, row.get("file", ""), lambda m: None)
    return row


# --- the one-time move to one name per character -----------------------------------

def rename_plan(cfg: dict, registry: Path | None = None) -> list[dict]:
    """What `sourcemode lora rename` would do, per locked character. Reads only.

    Each row: {character, moves: [(what, from, to)], deletes: [path], problem}.
    A character whose current copies do not match her locked hash gets a problem
    and no moves - nothing is renamed on a file we cannot vouch for.
    """
    rows = []
    vault = vault_dir(cfg)
    comfy = comfy_loras_dir(cfg) / "sourcemode"
    for c, row in sorted(load_registry(registry).items()):
        moves, deletes, problem = [], [], ""
        want_v = vault_target(cfg, c)
        want_c = comfy_target(cfg, c)
        digest = row["sha256"]
        # where her bytes are now, by the trainer's name
        old_v = vault / c / row["file"]
        old_c = comfy / _output_name(row["file"]) / row["file"]
        src = None
        for cand in (want_v, old_v, want_c, old_c):
            if cand.is_file() and sha256(cand) == digest:
                src = cand
                break
        if src is None:
            rows.append({"character": c, "moves": [], "deletes": [], "problem": "no copy on disk matches the locked hash"})
            continue
        if not (want_v.is_file() and sha256(want_v) == digest):
            moves.append(("vault", str(src), str(want_v)))
        if old_v.is_file() and old_v != want_v:
            if sha256(old_v) == digest:
                deletes.append(str(old_v))          # the same bytes under the old name
            else:
                moves.append(("previous", str(old_v), str(old_v.parent / PREVIOUS / old_v.name)))
        for stray in sorted((vault / c).glob("*.safetensors")) if (vault / c).is_dir() else []:
            if stray not in (want_v, old_v):
                moves.append(("previous", str(stray), str(stray.parent / PREVIOUS / stray.name)))
        if not (want_c.is_file() and sha256(want_c) == digest):
            moves.append(("comfy", str(src), str(want_c)))
        if old_c.is_file() and old_c != want_c:
            deletes.append(str(old_c))
        bt = backup_target(cfg, c)
        if bt is not None and not (bt.is_file() and sha256(bt) == digest):
            moves.append(("backup", str(src), str(bt)))
        rows.append({"character": c, "moves": moves, "deletes": deletes, "problem": problem})
    return rows


def rename_apply(cfg: dict, registry: Path | None = None, log=lambda m: None) -> list[str]:
    """Carry out `rename_plan`: copy-verify to the new names, set strays aside,
    delete the old-named copies only after the new copy verified, rewrite the
    registry rows. Idempotent - a second run finds nothing to do."""
    entries = load_registry(registry)
    done = []
    for r in rename_plan(cfg, registry):
        c = r["character"]
        if r["problem"]:
            done.append(f"SKIP {c}: {r['problem']}")
            continue
        digest = entries[c]["sha256"]
        for what, src, dst in r["moves"]:
            s, d = Path(src), Path(dst)
            if what == "previous":
                d.parent.mkdir(parents=True, exist_ok=True)
                if d.exists():
                    d = d.parent / f"{d.stem}.{sha256(s)[:12]}{d.suffix}"
                shutil.move(str(s), str(d))
                done.append(f"{c}: set aside {s.name} -> {d}")
                continue
            try:
                _copy_verified(s, d, digest)
            except (OSError, LockError) as exc:
                done.append(f"{c}: WARNING {what} copy failed: {exc}")
                continue
            done.append(f"{c}: {what} {d}")
        # old-named copies go only once BOTH new-named copies verify
        new_ok = all(t.is_file() and sha256(t) == digest for t in (vault_target(cfg, c), comfy_target(cfg, c)))
        for p in r["deletes"]:
            p = Path(p)
            if new_ok and p.is_file():
                p.unlink()
                done.append(f"{c}: removed old-named copy {p}")
                try:
                    p.parent.rmdir()        # the empty sourcemode/<output name>/ folder
                except OSError:
                    pass
        entries[c] = {**entries[c], "name": lock_name(c), "comfy": comfy_rel(c)}
    _write_registry(entries, registry)
    return done
