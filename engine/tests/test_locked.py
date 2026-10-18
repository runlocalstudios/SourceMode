"""The lock: decided once, written in the repo, vaulted, verified by hash.

Jeremy, 2026-10-09: "ENSURE the LoRAs we have trained and decided are best are
LOCKED AND LOADED ... I DO NOT HAVE TO RETELL YOU WHICH ARE BEST OR RETRAIN."
Sunny's and Bianca's best checkpoints were already gone when this was written.

Jeremy, 2026-10-15: "I would prefer all final named LoRAs just be the model's
name so Priyanka.safetensors." One name per character everywhere outside the
training folder, a relock never destroys bytes, and a Google Drive mirror.
"""

import json
from pathlib import Path

import pytest

from sourcemode.train import locked as L


@pytest.fixture
def world(tmp_path, monkeypatch):
    out = tmp_path / "engine" / "outputs"
    ck = out / "lora-datasets" / "zara_v2" / "lora"
    ck.mkdir(parents=True)
    (ck / "zara_v2-000018.safetensors").write_bytes(b"epoch-18-bytes")
    (ck / "zara_v2-000019.safetensors").write_bytes(b"epoch-19-bytes")
    cfg = {"paths": {"outputs": str(out), "library": str(tmp_path / "library"),
                     "lora_backup": str(tmp_path / "drive" / "loras")},
           "comfyui": {"loras_dir": str(tmp_path / "comfy" / "loras")}}
    reg = tmp_path / "characters" / "loras.json"
    return cfg, out, ck, reg


def _paths(cfg):
    vault = Path(cfg["paths"]["library"]) / "loras" / "zara" / "zara.safetensors"
    comfy = Path(cfg["comfyui"]["loras_dir"]) / "sourcemode" / "zara.safetensors"
    backup = Path(cfg["paths"]["lora_backup"]) / "zara.safetensors"
    return vault, comfy, backup


def test_lock_vaults_stages_mirrors_and_records_under_her_name(world):
    cfg, out, ck, reg = world
    row = L.lock(cfg, "Zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2",
                 basis="dense_zara_v2_asset 9/10", registry=reg)
    vault, comfy, backup = _paths(cfg)
    assert vault.read_bytes() == comfy.read_bytes() == backup.read_bytes() == b"epoch-18-bytes"
    assert row["sha256"] == L.sha256(vault)
    assert row["name"] == "zara.safetensors" and row["file"] == "zara_v2-000018.safetensors"
    assert Path(row["comfy"]).parts == ("sourcemode", "zara.safetensors")
    doc = json.loads(reg.read_text(encoding="utf-8"))
    assert doc["zara"]["epoch"] == 18 and doc["zara"]["basis"] == "dense_zara_v2_asset 9/10"
    assert not list(reg.parent.glob("*.tmp")) and not list(vault.parent.glob("*.part"))


def test_a_relock_sets_the_old_file_aside_and_never_deletes_it(world):
    """Choosing a new epoch on the judge page locks again under the same name.
    The old bytes move to _previous/ under the trainer's name for them."""
    cfg, out, ck, reg = world
    L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
    L.lock(cfg, "zara", ck / "zara_v2-000019.safetensors", epoch=19, dataset="zara_v2", registry=reg)
    vault, comfy, backup = _paths(cfg)
    assert vault.read_bytes() == comfy.read_bytes() == backup.read_bytes() == b"epoch-19-bytes"
    prev = vault.parent / "_previous" / "zara_v2-000018.safetensors"
    assert prev.read_bytes() == b"epoch-18-bytes"
    assert L.locked(cfg, "zara", registry=reg)["epoch"] == 19
    assert all(r["ok"] for r in L.verify(cfg, registry=reg))
    # the set-aside file is something a prune must leave alone
    assert prev.resolve() in L.locked_files(cfg, registry=reg)


def test_verify_names_what_is_wrong_and_restage_repairs_comfy(world):
    cfg, out, ck, reg = world
    L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
    vault, comfy, backup = _paths(cfg)
    comfy.write_bytes(b"corrupted")
    (r,) = L.verify(cfg, registry=reg)
    assert not r["ok"] and r["problems"] == ["ComfyUI copy differs from the locked hash"]
    L.restage(cfg, "zara", registry=reg)
    assert L.verify(cfg, registry=reg)[0]["ok"]
    comfy.unlink()
    assert L.verify(cfg, registry=reg)[0]["problems"] == ["not staged in ComfyUI"]
    backup.unlink()
    assert "backup copy missing" in L.verify(cfg, registry=reg)[0]["problems"]
    vault.write_bytes(b"tampered")
    assert "vault copy differs from the locked hash" in L.verify(cfg, registry=reg)[0]["problems"]
    with pytest.raises(L.LockError, match="nothing to restage"):
        L.restage(cfg, "zara", registry=reg)


def test_a_missing_backup_drive_does_not_stop_a_lock(world):
    """Drive for Desktop may be signed out or the laptop elsewhere. The lock is
    made - vault and ComfyUI are what renders need - and verify says the backup
    is missing until `lora backup` catches up."""
    cfg, out, ck, reg = world
    cfg["paths"]["lora_backup"] = str(Path(cfg["paths"]["lora_backup"]).parent / "zara.safetensors")  # a FILE, so mkdir fails
    Path(cfg["paths"]["lora_backup"]).parent.mkdir(parents=True)
    Path(cfg["paths"]["lora_backup"]).write_bytes(b"not a dir")
    said = []
    row = L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg, log=said.append)
    assert row["sha256"] == L.sha256(ck / "zara_v2-000018.safetensors")
    assert any("backup: WARNING" in s for s in said)
    (r,) = L.verify(cfg, registry=reg)
    # reported, but `ok` stays True: a prune must not refuse because a USB drive is unplugged
    assert r["vault_ok"] and r["comfy_ok"] and r["backup_ok"] is False and r["ok"]
    assert r["problems"] == ["backup copy missing"]


def test_backup_all_catches_up_every_lock(world):
    cfg, out, ck, reg = world
    L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
    vault, comfy, backup = _paths(cfg)
    backup.unlink()
    rows = L.backup_all(cfg, registry=reg)
    assert rows == [{"character": "zara", "ok": True, "problem": ""}]
    assert backup.read_bytes() == b"epoch-18-bytes"
    cfg["paths"].pop("lora_backup")
    assert L.verify(cfg, registry=reg)[0]["backup_ok"] is None and L.verify(cfg, registry=reg)[0]["ok"]
    with pytest.raises(L.LockError, match="no backup dir"):
        L.backup_all(cfg, registry=reg)


def test_resolve_lora_prefers_the_lock_over_the_training_folder(world, monkeypatch):
    from sourcemode.assets import lora as A
    cfg, out, ck, reg = world
    monkeypatch.setattr(L, "REGISTRY", reg)
    assert A.resolve_lora(cfg, "zara") is None            # two checkpoints, no record: undecided
    L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2",
           basis="dense_zara_v2_asset 9/10", registry=reg)
    got = A.resolve_lora(cfg, "zara")
    assert got["name"] == "zara.safetensors" and got["file"] == "zara_v2-000018.safetensors"
    assert Path(got["path"]).parts == ("sourcemode", "zara.safetensors")
    assert got["why"].startswith("locked: dense_zara_v2_asset")
    # the training folder can vanish; the answer does not
    for p in ck.glob("*.safetensors"):
        p.unlink()
    assert A.resolve_lora(cfg, "zara")["name"] == "zara.safetensors"


def test_locked_files_is_what_a_prune_must_keep(world):
    cfg, out, ck, reg = world
    L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
    keep = L.locked_files(cfg, registry=reg)
    vault, comfy, backup = _paths(cfg)
    # the training copy is not kept: vault + ComfyUI are the two (2026-10-18)
    assert (ck / "zara_v2-000018.safetensors").resolve() not in keep
    assert (ck / "zara_v2-000019.safetensors").resolve() not in keep
    assert {vault.resolve(), comfy.resolve(), backup.resolve()} <= keep


@pytest.mark.parametrize("bad", ["", "../x", "a/b"])
def test_a_character_id_that_escapes_is_refused(world, bad):
    cfg, out, ck, reg = world
    with pytest.raises(L.LockError):
        L.lock(cfg, bad, ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)


def test_unlock_removes_the_row_and_sets_the_vault_copy_aside(world):
    cfg, out, ck, reg = world
    L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
    vault, comfy, backup = _paths(cfg)
    row = L.unlock(cfg, "zara", registry=reg)
    assert row["file"] == "zara_v2-000018.safetensors"
    assert L.locked(cfg, "zara", registry=reg) is None and not vault.exists()
    assert (vault.parent / "_previous" / "zara_v2-000018.safetensors").read_bytes() == b"epoch-18-bytes"
    assert comfy.is_file() and (ck / "zara_v2-000018.safetensors").is_file()
    assert L.unlock(cfg, "zara", registry=reg) is None


# --- the one-time rename from the trainer's names ---------------------------------

def _old_layout(cfg, reg, ck):
    """The disk as the 2026-10-09 lock left it: vault and ComfyUI copies under
    the trainer's name, a stale earlier vault copy beside it, a registry row
    with no `name`."""
    vault_dir = Path(cfg["paths"]["library"]) / "loras" / "zara"
    vault_dir.mkdir(parents=True)
    (vault_dir / "zara_v2-000018.safetensors").write_bytes(b"epoch-18-bytes")
    (vault_dir / "zara_v2-000012.safetensors").write_bytes(b"epoch-12-bytes")      # an earlier lock, left behind
    comfy_sub = Path(cfg["comfyui"]["loras_dir"]) / "sourcemode" / "zara_v2"
    comfy_sub.mkdir(parents=True)
    (comfy_sub / "zara_v2-000018.safetensors").write_bytes(b"epoch-18-bytes")
    (comfy_sub / "zara_v2-000019.safetensors").write_bytes(b"epoch-19-bytes")      # a sweep candidate, not ours
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"zara": {
        "file": "zara_v2-000018.safetensors", "epoch": 18, "dataset": "zara_v2", "output_name": "zara_v2",
        "sha256": L.sha256(ck / "zara_v2-000018.safetensors"), "bytes": 14,
        "comfy": "sourcemode\\zara_v2\\zara_v2-000018.safetensors", "basis": "dense_zara_v2_asset 9/10"}}),
        encoding="utf-8")
    return vault_dir, comfy_sub


def test_rename_moves_every_copy_to_her_name_and_loses_nothing(world):
    cfg, out, ck, reg = world
    vault_dir, comfy_sub = _old_layout(cfg, reg, ck)
    plan = L.rename_plan(cfg, registry=reg)
    assert [r["character"] for r in plan] == ["zara"] and not plan[0]["problem"]
    assert {m[0] for m in plan[0]["moves"]} == {"vault", "comfy", "backup", "previous"}
    log = L.rename_apply(cfg, registry=reg)
    vault, comfy, backup = _paths(cfg)
    assert vault.read_bytes() == comfy.read_bytes() == backup.read_bytes() == b"epoch-18-bytes"
    assert not (vault_dir / "zara_v2-000018.safetensors").exists()              # same bytes, old name: gone
    assert (vault_dir / "_previous" / "zara_v2-000012.safetensors").read_bytes() == b"epoch-12-bytes"
    assert not (comfy_sub / "zara_v2-000018.safetensors").exists()
    assert (comfy_sub / "zara_v2-000019.safetensors").is_file()                  # the sweep's candidate is not ours to touch
    row = L.load_registry(reg)["zara"]
    assert row["name"] == "zara.safetensors" and Path(row["comfy"]).parts == ("sourcemode", "zara.safetensors")
    assert row["file"] == "zara_v2-000018.safetensors"                           # provenance kept
    assert all(r["ok"] for r in L.verify(cfg, registry=reg))
    assert any("removed old-named copy" in l for l in log)
    # idempotent
    assert L.rename_plan(cfg, registry=reg)[0]["moves"] == [] and L.rename_plan(cfg, registry=reg)[0]["deletes"] == []
    assert L.rename_apply(cfg, registry=reg) == []


def test_rename_refuses_a_character_whose_bytes_do_not_match(world):
    cfg, out, ck, reg = world
    vault_dir, comfy_sub = _old_layout(cfg, reg, ck)
    for p in (vault_dir / "zara_v2-000018.safetensors", comfy_sub / "zara_v2-000018.safetensors"):
        p.write_bytes(b"tampered")
    (plan,) = L.rename_plan(cfg, registry=reg)
    assert plan["problem"] and plan["moves"] == [] and plan["deletes"] == []
    log = L.rename_apply(cfg, registry=reg)
    assert log == ["SKIP zara: no copy on disk matches the locked hash"]
    assert (vault_dir / "zara_v2-000018.safetensors").read_bytes() == b"tampered"   # touched nothing
