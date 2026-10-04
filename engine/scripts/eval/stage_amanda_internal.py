"""Stage the keepers of cull_amanda_internal as amanda_internal_v2.

Captions start from each shot's plan `training_caption` but the plan's head-tilt
and gaze clauses are STRIPPED: Jeremy removed "her head tilted to one side" and
"looking just off camera" 14 times from the seeded set, because the plan says what
was asked, not what came out. Gaze is re-added only where gaze_mp measures it.
Hair is checked by eye on a contact sheet before approval. ASCII only.
"""
import json
import re
import shutil
from pathlib import Path

SRC = Path("outputs/loragen_local/amanda_internal")
CODEX = Path("outputs/lora-datasets/amanda_v2")
DS = Path("outputs/lora-datasets/amanda_internal_v2")
IMG = DS / "image_src"
J = Path("outputs/judge")
STRIP = [r",\s*her head tilted to one side", r",\s*looking just off camera", r",\s*looking off camera"]

rows = json.loads((SRC / "scores.json").read_text(encoding="utf-8"))
v = json.loads((J / "verdicts" / "cull_amanda_internal.json").read_text(encoding="utf-8"))
v = v.get("verdicts", v)
keep_ids = {k for k, x in v.items() if x == "keep"}
IMG.mkdir(parents=True, exist_ok=True)
manifest, geom, n = [], {}, 0
for r in rows:
    if f"shot_{r['n']:03d}" not in keep_ids:
        continue
    name = f"src_{n:03d}.png"
    shutil.copy2(r["file"], IMG / name)
    cap = r["training_caption"].replace("<trigger>", "amanda").strip()
    for pat in STRIP:
        cap = re.sub(pat, "", cap)
    (IMG / name.replace(".png", ".txt")).write_text(cap + "\n", encoding="utf-8")
    manifest.append({"file": name, "original": str(Path(r["file"]).resolve()), "batch": "loragen_local internal",
                     "sim": r.get("self"), "bucket_px": r.get("bucket_px"), "hair": r.get("hair")})
    geom[name] = {"face_px": r.get("bucket_px"), "yaw": r.get("yaw"), "w": 1024, "h": 1536}
    n += 1
gen = n
cg = json.loads((CODEX / "geometry.json").read_text(encoding="utf-8"))
for m in json.loads((CODEX / "manifest.json").read_text(encoding="utf-8")):
    if "lora-gen" in m["batch"]:
        continue
    src = CODEX / "image_src" / m["file"]; cap = src.with_suffix(".txt")
    if not (src.is_file() and cap.is_file()):
        continue
    name = f"src_{n:03d}.png"
    shutil.copy2(src, IMG / name); shutil.copy2(cap, IMG / name.replace(".png", ".txt"))
    manifest.append(dict(m, file=name))
    if m["file"] in cg:
        geom[name] = cg[m["file"]]
    n += 1
(DS / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
(DS / "geometry.json").write_text(json.dumps(geom, indent=1), encoding="utf-8")
print(f"amanda_internal_v2: {gen} internal keepers + {n - gen} real photos = {n} images")
