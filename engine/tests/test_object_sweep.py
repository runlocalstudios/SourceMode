"""The object LoRA sweep: its scenes and its preflight (the torso toy, 2026-10-15)."""

import sys

from collections import Counter

from sourcemode.assets.object_scenes import RANDOM_WOMEN, SCENES, TIEBREAKER, object_prompts, object_tiebreaker_prompts
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


def test_the_tiebreaker_is_his_twenty_acts_split_between_a_stranger_and_her():
    """Jeremy, 2026-10-16: 4 handjob, 4 blowjob, 2 footjob, 4 vaginal, 2 anal,
    2 hovering, 2 against her ass cheeks; every shot has a girl; each act half
    with a random 20-year-old and half with the Amanda LoRA."""
    rows = object_tiebreaker_prompts("torsotoy", "amanda", "a young woman with long dark brown hair")
    assert len(rows) == len(TIEBREAKER) == 20
    by_act = Counter(r["tag"].replace("POV ", "").split(" riding")[0] for r in rows)
    assert by_act == {"handjob": 4, "blowjob": 4, "footjob": 2, "vaginal": 4, "anal": 2,
                      "hovering above": 2, "pressed against her ass": 2}
    # half and half WITHIN each act, not just overall
    for act in by_act:
        hers = [r["character"] for r in rows if r["tag"].replace("POV ", "").startswith(act)]
        assert hers.count(True) == hers.count(False), act
    randoms = [r for r in rows if not r["character"]]
    assert len(randoms) == len(RANDOM_WOMEN) == 10 and len(set(RANDOM_WOMEN)) == 10
    for r, woman in zip(randoms, RANDOM_WOMEN):
        assert r["prompt"].startswith(f"torsotoy, {r['tag']}, {woman} "), r["prompt"]
        assert "amanda" not in r["prompt"]
    for r in rows:
        if r["character"]:
            assert r["prompt"].startswith("amanda, a young woman with long dark brown hair, torsotoy, " + r["tag"] + ", amanda ")
        assert "{t}" not in r["prompt"] and "torsotoy" in r["prompt"].split(r["tag"], 1)[1]
    # POV shots say so in the toy's own words, so the tag teaches what the captions taught
    for r in rows:
        assert ("seen from the toy's own viewpoint" in r["prompt"]) == r["tag"].startswith("POV"), r["prompt"]
    # the two "not inside her" acts say so
    for r in rows:
        if r["tag"] in ("hovering above", "pressed against her ass"):
            assert "not inside her" in r["prompt"] or "not touching her" in r["prompt"]


def test_the_six_handjobs_are_all_hers_and_each_places_the_toy_and_her_body():
    """Jeremy, 2026-10-16: "clarify the location of the toy and her body
    relative to it in the picture"."""
    from sourcemode.assets.object_scenes import HANDJOB_CLARITY, handjob_clarity_prompts
    rows = handjob_clarity_prompts("torsotoy", "amanda", "a young woman")
    assert len(rows) == len(HANDJOB_CLARITY) == 6 and all(r["character"] for r in rows)
    for r in rows:
        p = r["prompt"]
        assert p.startswith(f"amanda, a young woman, torsotoy, {r['tag']}, amanda ")
        assert "handjob" in r["tag"] and "{t}" not in p
        # where the toy is in the frame, and where she is relative to it
        assert "frame" in p or "nearest the camera" in p or "pointing at the camera" in p, p
        assert any(w in p for w in ("beside", "behind", "at the right side", "beyond", "in front of")), p
        assert ("seen from the toy's own viewpoint" in p) == r["tag"].startswith("POV"), p
