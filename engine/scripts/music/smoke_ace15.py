"""Smoke test: two takes of one ambient prompt (turbo + sft) through ComfyUI, saved for listening."""
import json
import time
from pathlib import Path

from sourcemode.render.client import ComfyUIClient

WF = Path("C:/dev/SourceMode/workflows/ace15_music.json")
OUT = Path("C:/dev/SourceMode/library/_experiments/2026-11-02_music_ace15-smoke")
TAGS = ("instrumental, lo-fi hip hop, mellow Rhodes electric piano, soft vinyl crackle, dusty boom-bap drums, "
        "warm upright bass, late night city, steady groove, no vocals, background music, no build-ups, no drops")

RUNS = [
    {"name": "turbo", "MODEL": "acestep_v1.5_xl_turbo_bf16.safetensors", "STEPS": 8, "CFG": 1.0},
    {"name": "sft", "MODEL": "acestep_v1.5_xl_sft_bf16.safetensors", "STEPS": 50, "CFG": 7.0},
]


def build(vals):
    raw = json.loads(WF.read_text(encoding="utf-8"))
    raw.pop("_meta")

    def sub(v):
        if isinstance(v, str) and v.startswith("{{") and v.endswith("}}"):
            return vals[v[2:-2]]
        return v
    for node in raw.values():
        node["inputs"] = {k: sub(v) for k, v in node["inputs"].items()}
    return raw


c = ComfyUIClient()
OUT.mkdir(parents=True, exist_ok=True)
for r in RUNS:
    vals = {"MODEL": r["MODEL"], "TAGS": TAGS, "LYRICS": "[Instrumental]", "SEED": 1100, "BPM": 80,
            "SECONDS": 120.0, "KEYSCALE": "D minor", "TIMESIG": "4", "STEPS": r["STEPS"], "CFG": r["CFG"],
            "PREFIX": f"sourcemode/music_smoke_{r['name']}"}
    t = time.time()
    pid = c.submit(build(vals))
    entry = c.wait(pid, timeout_s=1800)
    files = c.outputs(entry)
    for f in files:
        dest = c.fetch(f, OUT / f"{r['name']}_{f['filename']}")
        print(f"{r['name']}: {dest} in {time.time() - t:.0f}s", flush=True)
(OUT / "spec.json").write_text(json.dumps({"tags": TAGS, "runs": RUNS, "seed": 1100, "bpm": 80, "seconds": 120}, indent=1), encoding="utf-8")
print("done")
