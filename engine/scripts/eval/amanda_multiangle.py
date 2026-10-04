"""Does the multi-angle LoRA actually control the camera, and does identity survive?

Jeremy wants off Codex for image generation: 3 reference photos in, a full varied
training set out, locally. This tests whether that is possible before anything is
built on it.

Two questions, asked in order, because the second only matters if the first is yes:

  1. DOES THE POSE TOKEN MOVE THE CAMERA? Objective and needs no judgement - render
     one azimuth sweep and measure yaw with InsightFace. If yaw does not track the
     requested azimuth, the LoRA is not steering and nothing else is worth looking at.
  2. DOES IDENTITY SURVIVE? Scored against her own references, and against every
     OTHER character's references - the relative check that caught 35 Hannah images
     in Ash's set. A face that matches somebody else better is not her.

Deliberately NOT judged by me. Numbers here shortlist; Jeremy's eye decides, and the
judge set is written at the end for exactly that.

    python amanda_multiangle.py [--char amanda] [--seeds 2]
"""
import json
import sys
from pathlib import Path

from sourcemode.assets.judge import make_set
from sourcemode.config import load_config, workflows_dir
from sourcemode.gates.identity import cosine, embed_image
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.workflow import load_template, substitute

CHAR = sys.argv[sys.argv.index("--char") + 1] if "--char" in sys.argv else "amanda"
SEEDS = [11, 22][: int(sys.argv[sys.argv.index("--seeds") + 1]) if "--seeds" in sys.argv else 2]
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
OUT = Path(f"outputs/multiangle_{CHAR}"); OUT.mkdir(parents=True, exist_ok=True)

# The azimuth sweep is the experiment: yaw should track it. Elevation and distance
# are held constant so nothing else can explain a change.
AZIMUTHS = ["front", "front-right quarter", "right side",
            "back-right quarter", "front-left quarter", "left side"]
ELEV, DIST = "eye-level shot", "medium shot"
NEGATIVE = ("different person, different face, changed hair, deformed, distorted hands, "
            "extra limbs, plastic skin, doll-like, blurry, low quality, cartoon, watermark, text")

refs = sorted(p for p in REFS.glob(f"{CHAR}_*")
              if p.stem.split("_")[0].lower() == CHAR and p.suffix.lower() in (".jpg", ".jpeg", ".png"))
if len(refs) < 1:
    raise SystemExit(f"no references for {CHAR} in {REFS}")
print(f"{CHAR}: {len(refs)} references -> {[p.name for p in refs]}")

cfg = load_config()
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])

# ComfyUI's LoadImage reads from its own input dir
comfy_in = Path("C:/ComfyUI/input")
staged = []
for p in refs[:3]:
    d = comfy_in / p.name
    if not d.exists():
        d.write_bytes(p.read_bytes())
    staged.append(p.name)
while len(staged) < 3:                      # the node takes 3; repeat the face if fewer
    staged.append(staged[0])

rows = []
for az in AZIMUTHS:
    for seed in SEEDS:
        tag = az.replace(" ", "_")
        dest = OUT / f"{tag}__{seed}.png"
        if not dest.exists():
            wf = substitute(load_template(workflows_dir(cfg), "qwen_multiangle_ref"), {
                "REF1": staged[0], "REF2": staged[1], "REF3": staged[2],
                "POSITIVE": f"<sks> {az} view {ELEV} {DIST}",
                "NEGATIVE": NEGATIVE, "SEED": seed,
                "FILENAME_PREFIX": f"multiangle_{CHAR}/{tag}",
            })
            files = client.outputs(client.wait(client.submit(wf), timeout_s=1800))
            if not files:
                print(f"  {az} seed{seed}: NO OUTPUT"); continue
            client.fetch(files[0], dest)
        rows.append({"azimuth": az, "seed": seed, "file": str(dest)})
        print(f"  rendered {az} seed{seed}")

if not rows:
    raise SystemExit("nothing rendered - refusing to write an empty judge set")

# --- question 1: did the camera move? -----------------------------------------
import numpy as np
from PIL import Image
from sourcemode.gates.identity import _get_face_app
app = _get_face_app()
for r in rows:
    im = Image.open(r["file"]).convert("RGB")
    fs = app.get(np.asarray(im)[:, :, ::-1])
    if fs:
        f = max(fs, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
        r["yaw"] = round(float(f.pose[1]), 1)            # pose is [pitch, yaw, roll]
        r["face_px"] = int(f.bbox[3] - f.bbox[1])
        r["emb"] = f.normed_embedding
    else:
        r["yaw"] = r["face_px"] = None; r["emb"] = None

print("\n=== Q1: does the pose token move the camera? ===")
for az in AZIMUTHS:
    ys = [r["yaw"] for r in rows if r["azimuth"] == az and r["yaw"] is not None]
    px = [r["face_px"] for r in rows if r["azimuth"] == az and r["face_px"]]
    print(f"  {az:<22} yaw {ys}   face {px}px")
spread = [r["yaw"] for r in rows if r["yaw"] is not None]
print(f"  yaw range across azimuths: {min(spread):.0f} to {max(spread):.0f} deg"
      if spread else "  NO FACES DETECTED")

# --- question 2: is it still her? ---------------------------------------------
banks = {}
for p in sorted(REFS.glob("*")):
    if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"): continue
    who = p.stem.split("_")[0].lower()
    if who == "universal": continue
    e = embed_image(p)
    if e is not None: banks.setdefault(who, []).append(e)
print(f"\n=== Q2: identity, against {len(banks)} reference identities ===")
wrong = 0
for r in rows:
    if r["emb"] is None: continue
    sc = {n: max(float(x @ r["emb"]) for x in b) for n, b in banks.items()}
    top = max(sc.items(), key=lambda kv: kv[1])
    r["self"] = round(sc.get(CHAR, 0.0), 3); r["best"] = top[0]
    if top[0] != CHAR: wrong += 1
    print(f"  {r['azimuth']:<22} seed{r['seed']}  {CHAR} {r['self']:.3f}  best={top[0]} {top[1]:.3f}")
print(f"\n  matches another identity better: {wrong}/{len([r for r in rows if r['emb'] is not None])}")

for r in rows: r.pop("emb", None)
(OUT / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
items = [{"id": f"{r['azimuth'].replace(' ', '_')}__{r['seed']}", "path": r["file"],
          "arm": r["azimuth"], "group": str(r["seed"])} for r in rows]
make_set(Path("outputs/judge"), f"multiangle_{CHAR}",
         f"{CHAR.title()} from 3 references, no character LoRA - is this her?",
         items, question="Is this the same woman as the references?", priority=1)
print(f"\njudge set multiangle_{CHAR}: {len(items)} images")
print("MULTIANGLEDONE")
