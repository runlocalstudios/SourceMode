"""The object LoRA sweep: its scenes and its preflight (the torso toy, 2026-10-15)."""

import sys

from sourcemode.assets.object_scenes import SCENES, object_prompts
from sourcemode.gpu.preflight import preflight

PY = sys.executable


def test_object_prompts_lead_with_the_trigger_and_turn_every_tone():
    ps = object_prompts("torsotoy")
    assert len(ps) == len(SCENES) == 10
    assert all(p.startswith("torsotoy, ") for p in ps)
    assert all("torsotoy" in p[len("torsotoy, "):] for p in ps), "the trigger names the object in the scene too"
    joined = " ".join(ps)
    for tone in ("light-toned", "tan", "dark brown"):
        assert tone in joined, tone
    # half alone, half with a woman: a weak scene reads as that, not a weak epoch
    assert sum("woman" in p for p in ps) == 5
    assert "{t}" not in joined


def test_object_sweep_preflights_like_the_character_one(tmp_path):
    s = tmp_path / "object_epoch_eval.py"
    s.write_text("", encoding="utf-8")
    ck = tmp_path / "lora"; ck.mkdir()
    (ck / "torso_v1-000020.safetensors").write_bytes(b"0")
    cmd = [PY, str(s), "torso", "torso_v1", "24", "16", "24", "torsotoy", str(ck), "10", "--dry-run",
           "--epochs", "20,22"]
    out = preflight({"cmd": cmd, "cwd": str(tmp_path)}, tmp_path)
    assert out == ["epoch 22: torso_v1-000022.safetensors is not in " + str(ck)]
    cmd[-1] = "20"
    assert preflight({"cmd": cmd, "cwd": str(tmp_path)}, tmp_path) == []
    # too few slots is named, not crashed on
    out = preflight({"cmd": [PY, str(s), "torso", "torso_v1"], "cwd": str(tmp_path)}, tmp_path)
    assert any("epoch sweep needs" in p for p in out)
