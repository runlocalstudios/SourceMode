"""Apparent age and sex across a character's pipeline, measured, per group.

    python scripts/eval/age_compare.py <char> [<extra folder> ...]

Groups: her reference photos, her staged training images, and every epoch-sweep
folder outputs/dense_<char>_v2*. Prints median / quartiles of InsightFace's
age estimate and the share read as male, per group. Jeremy, 2026-10-07, on
cat: "her pics look like shit" - old and masculine. The question it answers is
WHERE in the chain she gets older: references -> generated training set ->
LoRA renders. InsightFace is QC-only (non-commercial weights) and loads a model,
so this runs through the GPU queue.
"""
import json
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from sourcemode.gates.identity import _get_face_app

CHAR = sys.argv[1].lower()
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
groups = {
    "references": sorted(p for p in REFS.glob(f"{CHAR}_*") if p.stem.split("_")[0].lower() == CHAR),
    "training set": sorted(Path(f"outputs/lora-datasets/{CHAR}_v2/image_src").glob("*.png")),
}
for d in sorted(Path("outputs").glob(f"dense_{CHAR}_v2*")):
    if d.is_dir():
        groups[d.name] = sorted(p for p in d.rglob("scene_*.png") if "_web" not in p.parts)
for extra in sys.argv[2:]:
    groups[extra] = sorted(Path(extra).rglob("*.png"))

app = _get_face_app()
out = {}
for name, paths in groups.items():
    ages, male, none = [], 0, 0
    for p in paths:
        fs = app.get(np.asarray(Image.open(p).convert("RGB"))[:, :, ::-1])
        if not fs:
            none += 1
            continue
        f = max(fs, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        ages.append(float(f.age))
        male += int(getattr(f, "gender", 0) == 1)
    if ages:
        q = statistics.quantiles(ages, n=4) if len(ages) > 1 else [ages[0]] * 3
        out[name] = {"n": len(ages), "no_face": none, "age_median": round(statistics.median(ages), 1),
                     "age_q1": round(q[0], 1), "age_q3": round(q[2], 1),
                     "male_share": round(male / len(ages), 2)}
    else:
        out[name] = {"n": 0, "no_face": none}
    print(f"{name:34s} {out[name]}", flush=True)

Path("outputs/qc").mkdir(parents=True, exist_ok=True)
Path(f"outputs/qc/age_compare_{CHAR}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("AGECOMPAREDONE")
