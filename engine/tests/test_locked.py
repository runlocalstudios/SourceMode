"""The lock: decided once, written in the repo, vaulted, verified by hash.

Jeremy, 2026-10-09: "ENSURE the LoRAs we have trained and decided are best are
LOCKED AND LOADED ... I DO NOT HAVE TO RETELL YOU WHICH ARE BEST OR RETRAIN."
Sunny's and Bianca's best checkpoints were already gone when this was written.
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
    cfg = {"paths": {"outputs": str(out), "library": str(tmp_path / "library")},
           "comfyui": {"loras_dir": str(tmp_path / "comfy" / "loras")}}
    reg = tmp_path / "characters" / "loras.json"
    return cfg, out, ck, reg


def test_lock_vaults_stages_and_records(world):
    cfg, out, ck, reg = world
    row = L.lock(cfg, "Zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2",
                 basis="dense_zara_v2_asset 9/10", registry=reg)
    vault = Path(cfg["paths"]["library"]) / "loras" / "zara" / "zara_v2-000018.safetensors"
    comfy = Path(cfg["comfyui"]["loras_dir"]) / "sourcemode" / "zara_v2" / "zara_v2-000018.safetensors"
    assert vault.read_bytes() == b"epoch-18-bytes" and comfy.read_bytes() == b"epoch-18-bytes"
    assert row["sha256"] == L.sha256(vault)
    assert Path(row["comfy"]).parts == ("sourcemode", "zara_v2", "zara_v2-000018.safetensors")
    doc = json.loads(reg.read_text(encoding="utf-8"))
    assert doc["zara"]["epoch"] == 18 and doc["zara"]["basis"] == "dense_zara_v2_asset 9/10"
    assert not list(reg.parent.glob("*.tmp"))
    got = L.locked(cfg, "zara", registry=reg)
    assert got["vault_present"] and got["comfy_present"]
    assert all(r["ok"] for r in L.verify(cfg, registry=reg))


def test_a_lock_never_silently_changes_its_bytes(world):
    cfg, out, ck, reg = world
    L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
    other = ck / "other"
    other.mkdir()
    (other / "zara_v2-000018.safetensors").write_bytes(b"different")
    with pytest.raises(L.LockError, match="different bytes"):
        L.lock(cfg, "zara", other / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
    assert L.locked(cfg, "zara", registry=reg)["sha256"] == L.sha256(ck / "zara_v2-000018.safetensors")


def test_verify_names_what_is_wrong_and_restage_repairs_comfy(world):
    cfg, out, ck, reg = world
    L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
    comfy = Path(cfg["comfyui"]["loras_dir"]) / "sourcemode" / "zara_v2" / "zara_v2-000018.safetensors"
    comfy.write_bytes(b"corrupted")
    (r,) = L.verify(cfg, registry=reg)
    assert not r["ok"] and r["problems"] == ["ComfyUI copy differs from the locked hash"]
    L.restage(cfg, "zara", registry=reg)
    assert L.verify(cfg, registry=reg)[0]["ok"]
    comfy.unlink()
    assert L.verify(cfg, registry=reg)[0]["problems"] == ["not staged in ComfyUI"]
    vault = Path(cfg["paths"]["library"]) / "loras" / "zara" / "zara_v2-000018.safetensors"
    vault.write_bytes(b"tampered")
    assert "vault copy differs from the locked hash" in L.verify(cfg, registry=reg)[0]["problems"]
    with pytest.raises(L.LockError, match="nothing to restage"):
        L.restage(cfg, "zara", registry=reg)


def test_resolve_lora_prefers_the_lock_over_the_training_folder(world, monkeypatch):
    from sourcemode.assets import lora as A
    cfg, out, ck, reg = world
    monkeypatch.setattr(L, "REGISTRY", reg)
    assert A.resolve_lora(cfg, "zara") is None            # two checkpoints, no record: undecided
    L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2",
           basis="dense_zara_v2_asset 9/10", registry=reg)
    got = A.resolve_lora(cfg, "zara")
    assert got["name"] == "zara_v2-000018.safetensors" and got["path"].endswith("zara_v2-000018.safetensors")
    assert got["why"].startswith("locked: dense_zara_v2_asset")
    # the training folder can vanish; the answer does not
    for p in ck.glob("*.safetensors"):
        p.unlink()
    assert A.resolve_lora(cfg, "zara")["name"] == "zara_v2-000018.safetensors"


def test_locked_files_is_what_a_prune_must_keep(world):
    cfg, out, ck, reg = world
    L.lock(cfg, "zara", ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
    keep = L.locked_files(cfg, registry=reg)
    assert (ck / "zara_v2-000018.safetensors").resolve() in keep
    assert (ck / "zara_v2-000019.safetensors").resolve() not in keep
    assert any(p.parts[-3:] == ("loras", "zara", "zara_v2-000018.safetensors") for p in keep)


@pytest.mark.parametrize("bad", ["", "../x", "a/b"])
def test_a_character_id_that_escapes_is_refused(world, bad):
    cfg, out, ck, reg = world
    with pytest.raises(L.LockError):
        L.lock(cfg, bad, ck / "zara_v2-000018.safetensors", epoch=18, dataset="zara_v2", registry=reg)
