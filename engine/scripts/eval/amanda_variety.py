"""Can the prompt vary outfit / hair / setting while the pose token controls angle?

The angle test worked: yaw tracked the azimuth token from -68 to +51 deg, and
identity held at 0.82-0.94 frontally. But all twelve outputs wore the SAME floral
cami on the SAME stone patio - copied from the reference. That is fatal for a
training set, because a constant is not made variable by captioning it: a set where
every image shares an outfit teaches the trigger that outfit.

So this asks the one question that decides whether Codex can be replaced:

    does "<sks> <pose>" + attribute text change the attributes,
    while the pose token still controls the camera?

Pose is HELD at front-right quarter - the best identity band (0.82-0.92) - so any
change in outfit or setting is attributable to the added text and nothing else.

Measured, not judged:
  - identity against her own references, and against every other identity
  - face size at the bucket
  - whether the output still reads as the requested angle (yaw)
Whether the OUTFIT actually changed needs eyes; the judge set carries the prompt.

    python amanda_variety.py [--char amanda]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from sourcemode.assets.judge import make_set
from sourcemode.config import load_config, workflows_dir
from sourcemode.gates.identity import _get_face_app, embed_image
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.workflow import load_template, substitute

CHAR = sys.argv[sys.argv.index("--char") + 1] if "--char" in sys.argv else "amanda"
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
OUT = Path(f"outputs/variety_{CHAR}"); OUT.mkdir(parents=True, exist_ok=True)
POSE = "<sks> front-right quarter view eye-level shot medium shot"
SEED = 11

# Deliberately far from the reference (floral cami, stone patio) so a copy is
# obvious. Hair is included because the shot plan varies it and it is the attribute
# most tied to identity.
LOOKS = [
    ("control", ""),
    ("blazer_office", ", wearing a charcoal blazer over a white shirt, her hair in a low bun, "
                      "in a blurred office, composed expression"),
    ("gym_outdoor", ", wearing a black athletic crop top, her hair in a high ponytail, "
                    "on a park path with trees behind her, calm expression"),
    ("gown_ballroom", ", wearing a midnight blue velvet gown, her hair pinned into a chignon, "
                      "in a blurred ballroom, poised expression"),
    ("knit_kitchen", ", wearing a mustard knit jumper, her hair in a messy topknot, "
                     "in a blurred kitchen, faint smile"),
    ("denim_street", ", wearing a blue denim jacket over a white tee, her hair worn loose, "
                     "on a city sidewalk, relaxed expression"),
]
NEGATIVE = ("different person, different face, deformed, distorted hands, extra limbs, "
            "plastic skin, doll-like, blurry, low quality, cartoon, watermark, text")

refs = sorted(p for p in REFS.glob(f"{CHAR}_*")
              if p.stem.split("_")[0].lower() == CHAR and p.suffix.lower() in (".jpg", ".jpeg", ".png"))
comfy_in = Path("C:/ComfyUI/input")
staged = []
for p in refs[:3]:
    d = comfy_in / p.name
    if not d.exists():
        d.write_bytes(p.read_bytes())
    staged.append(p.name)
while len(staged) < 3:
    staged.append(staged[0])
print(f"{CHAR}: {len(refs)} references, pose held at '{POSE}'")

cfg = load_config()
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
rows = []
for name, extra in LOOKS:
    dest = OUT / f"{name}.png"
    prompt = POSE + extra
    if not dest.exists():
        wf = substitute(load_template(workflows_dir(cfg), "qwen_multiangle_ref"), {
            "REF1": staged[0], "REF2": staged[1], "REF3": staged[2],
            "POSITIVE": prompt, "NEGATIVE": NEGATIVE, "SEED": SEED,
            "FILENAME_PREFIX": f"variety_{CHAR}/{name}"})
        files = client.outputs(client.wait(client.submit(wf), timeout_s=1800))
        if not files:
            print(f"  {name}: NO OUTPUT"); continue
        client.fetch(files[0], dest)
    rows.append({"look": name, "prompt": prompt, "file": str(dest)})
    print(f"  rendered {name}")

if not rows:
    raise SystemExit("nothing rendered - refusing to write an empty judge set")

app = _get_face_app()
banks = {}
for p in sorted(REFS.glob("*")):
    if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"): continue
    who = p.stem.split("_")[0].lower()
    if who == "universal": continue
    e = embed_image(p)
    if e is not None: banks.setdefault(who, []).append(e)

print(f"\n{'look':<16}{'yaw':>7}{'face':>7}{'self':>7}  best")
for r in rows:
    im = Image.open(r["file"]).convert("RGB")
    fs = app.get(np.asarray(im)[:, :, ::-1])
    if not fs:
        r["yaw"] = r["face_px"] = r["self"] = None; r["best"] = None
        print(f"{r['look']:<16}{'no face':>7}"); continue
    f = max(fs, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
    r["yaw"] = round(float(f.pose[1]), 1)
    r["face_px"] = int(f.bbox[3] - f.bbox[1])
    sc = {n: max(float(x @ f.normed_embedding) for x in b) for n, b in banks.items()}
    top = max(sc.items(), key=lambda kv: kv[1])
    r["self"] = round(sc.get(CHAR, 0.0), 3); r["best"] = top[0]
    print(f"{r['look']:<16}{r['yaw']:>7}{r['face_px']:>7}{r['self']:>7}  {top[0]}")

(OUT / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
items = [{"id": r["look"], "path": r["file"], "arm": r["look"], "group": "0"} for r in rows]
make_set(Path("outputs/judge"), f"variety_{CHAR}",
         f"{CHAR.title()}: does the prompt change outfit and setting, or is it copying the reference?",
         items, question="Did the outfit and setting actually change to what was asked?", priority=1)
print(f"\njudge set variety_{CHAR}: {len(items)} images")
print("VARIETYDONE")
