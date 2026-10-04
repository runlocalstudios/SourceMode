"""Stage the keepers of cull_amanda_seeded as a training set, amanda_seeded_v2.

Jeremy culled the 80-shot run from the four real hair seeds blind (67 of 79 kept,
2026-09-30). Captions come from each shot's `training_caption` in scores.json -
NOT a plan lookup, because ten braid/pigtail shots were remapped onto seeded
styles at generation time and only scores.json carries the rewritten text.
Geometry (face px, yaw) also comes from scores.json, so no InsightFace pass is
needed. The six Grok photos and three references are copied from amanda_v2 with
the captions he already approved there. ASCII only.
"""
import json
import shutil
from pathlib import Path

SRC = Path("outputs/loragen_local/amanda")
CODEX = Path("outputs/lora-datasets/amanda_v2")
DS = Path("outputs/lora-datasets/amanda_seeded_v2")
IMG = DS / "image_src"
J = Path("outputs/judge")

rows = json.loads((SRC / "scores.json").read_text(encoding="utf-8"))
v = json.loads((J / "verdicts" / "cull_amanda_seeded.json").read_text(encoding="utf-8"))
v = v.get("verdicts", v)
keep_ids = {k for k, x in v.items() if x == "keep"}
IMG.mkdir(parents=True, exist_ok=True)
manifest, geom = [], {}
n = 0
for r in rows:
    if f"shot_{r['n']:03d}" not in keep_ids:
        continue
    name = f"src_{n:03d}.png"
    shutil.copy2(r["file"], IMG / name)
    (IMG / name.replace(".png", ".txt")).write_text(r["training_caption"].strip() + "\n", encoding="utf-8")
    manifest.append({"file": name, "original": str(Path(r["file"]).resolve()),
                     "batch": "loragen_local seeded", "sim": r.get("self"), "bucket_px": r.get("bucket_px")})
    geom[name] = {"face_px": r.get("bucket_px"), "yaw": r.get("yaw"), "w": 1024, "h": 1536}
    n += 1
gen = n
cg = json.loads((CODEX / "geometry.json").read_text(encoding="utf-8"))
for m in json.loads((CODEX / "manifest.json").read_text(encoding="utf-8")):
    if "lora-gen" in m["batch"]:
        continue
    src = CODEX / "image_src" / m["file"]
    cap = src.with_suffix(".txt")
    if not (src.is_file() and cap.is_file()):
        continue
    name = f"src_{n:03d}.png"
    shutil.copy2(src, IMG / name)
    shutil.copy2(cap, IMG / name.replace(".png", ".txt"))
    manifest.append(dict(m, file=name))
    if m["file"] in cg:
        geom[name] = cg[m["file"]]
    n += 1
(DS / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
(DS / "geometry.json").write_text(json.dumps(geom, indent=1), encoding="utf-8")
print(f"amanda_seeded_v2: {gen} seeded keepers + {n - gen} real photos = {n} images")
