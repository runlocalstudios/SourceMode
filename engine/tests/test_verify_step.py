"""The prep chain writes DONE only after every step verifies its own output.

verify_step.py reads outputs/lora-datasets/<char>_v2 relative to the cwd, so a
fake set under tmp_path stands in for a real one.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prep" / "verify_step.py"


def _run(cwd: Path, char: str, step: str):
    r = subprocess.run([sys.executable, str(SCRIPT), char, step], cwd=cwd,
                       capture_output=True, text=True)
    return r.returncode, r.stdout


def _set(tmp_path: Path, n: int = 4, captions: bool = True, hair: bool = True):
    img = tmp_path / "outputs" / "lora-datasets" / "nobody_v2" / "image_src"
    img.mkdir(parents=True)
    names = [f"src_{i:03d}.png" for i in range(n)]
    for i, name in enumerate(names):
        (img / name).write_bytes(b"png")
        if captions:
            (img / f"src_{i:03d}.txt").write_text(
                "nobody, " + ("her hair worn loose, " if hair else "") + "a smile", encoding="utf-8")
    (img.parent / "manifest.json").write_text(
        json.dumps([{"file": x, "original": f"o/{x}", "batch": "references"} for x in names]), encoding="utf-8")
    (img.parent / "gaze_mp.json").write_text(json.dumps({x: {} for x in names}), encoding="utf-8")
    (img.parent / "vl_hair_confirm.jsonl").write_text("{}", encoding="utf-8")
    return img


def test_a_complete_set_verifies_every_step(tmp_path):
    _set(tmp_path)
    for step in ("gather", "gaze", "captions", "hair"):
        rc, out = _run(tmp_path, "nobody", step)
        assert rc == 0, out
        assert "ok (4 images)" in out


def test_an_uncaptioned_image_fails_the_captions_step(tmp_path):
    img = _set(tmp_path)
    (img / "src_002.txt").unlink()
    rc, out = _run(tmp_path, "nobody", "captions")
    assert rc == 1 and "1 of 4 images have no caption" in out and "src_002.png" in out


def test_an_image_the_manifest_does_not_list_fails_gather(tmp_path):
    img = _set(tmp_path)
    (img / "src_099.png").write_bytes(b"png")
    rc, out = _run(tmp_path, "nobody", "gather")
    assert rc == 1 and "not in manifest.json" in out


def test_a_missing_gaze_file_fails_gaze(tmp_path):
    img = _set(tmp_path)
    (img.parent / "gaze_mp.json").unlink()
    rc, out = _run(tmp_path, "nobody", "gaze")
    assert rc == 1 and "gaze_mp.json was not written" in out


def test_captions_silent_on_hair_fail_the_hair_step_past_a_tenth(tmp_path):
    _set(tmp_path, n=12, hair=False)
    rc, out = _run(tmp_path, "nobody", "hair")
    assert rc == 1 and "12 of 12 captions never mention hair" in out


def test_a_missing_hair_verdict_file_fails_the_hair_step(tmp_path):
    img = _set(tmp_path)
    (img.parent / "vl_hair_confirm.jsonl").unlink()
    rc, out = _run(tmp_path, "nobody", "hair")
    assert rc == 1 and "vl_hair_confirm.jsonl was not written" in out


def test_nothing_staged_fails_gather(tmp_path):
    (tmp_path / "outputs" / "lora-datasets" / "nobody_v2" / "image_src").mkdir(parents=True)
    rc, out = _run(tmp_path, "nobody", "gather")
    assert rc == 1 and "nothing staged" in out
