"""Hair-conformance test on Amanda's REAL ponytail seed - 4 arms x 4 shots.

Jeremy, 2026-10-01, after the seeded set came back 58/72 loose: "try to get the
prompt conformance up before moving forward". In the seeded run the ponytail seed
sat in slot 1 beside TWO loose-hair references and the prompt carried no hair text
(loragen_local.py: hair_clause = "" when seeded). Measured: ponytail in 1 of 13.
Hypothesis: the hair follows the majority of the input images plus the text, and
the text was silent. Prediction written before the run: B >= 3/4 ponytails; D the
most ponytails but the weakest identity (one input image).

  A  seed + 2 loose refs, no hair text          (control = the seeded run)
  B  seed + 2 loose refs, "her hair in a high ponytail"
  C  seed + 1 loose ref,  "her hair in a high ponytail"
  D  seed only x3,        "her hair in a high ponytail"

Outfits are fitted on purpose (Jeremy: internal shots should show her body
proportions, unlike the moderated Codex plan). Output: a labelled sheet and
scores.json; hair conformance is judged by eye from the sheet.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from sourcemode.config import load_config, workflows_dir
from sourcemode.gates.identity import _get_face_app, embed_image
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.workflow import load_template, substitute

CHAR = "amanda"
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
SEED = Path("outputs/seeds/amanda/amanda_seed_ponytail.jpg")
COMFY_IN = Path("C:/ComfyUI/input")
OUT = Path("outputs/loragen_local/amanda_conformance"); OUT.mkdir(parents=True, exist_ok=True)
NEG = ("different person, different face, deformed, distorted hands, extra limbs, "
       "plastic skin, doll-like, blurry, low quality, cartoon, watermark, text")
HAIR = ", her hair in a high ponytail"

def stage(p):
    d = COMFY_IN / p.name
    if not d.exists(): d.write_bytes(p.read_bytes())
    return p.name

seed = stage(SEED)
face = stage(REFS / "amanda_face.jpg")
p1 = stage(REFS / "amanda_portrait1.jpg")
ARMS = {"A": ([seed, face, p1], ""), "B": ([seed, face, p1], HAIR),
        "C": ([seed, face, face], HAIR), "D": ([seed, seed, seed], HAIR)}
SHOTS = [
    ("<sks> front view eye-level shot medium shot", "a fitted black ribbed tank top", "a soft smile", "soft window daylight, against a plain light grey wall"),
    ("<sks> front-left quarter view eye-level shot medium shot", "a fitted white crop top and high-waisted jeans", "a neutral expression", "warm late-afternoon sun, on a quiet city sidewalk"),
    ("<sks> front view eye-level shot close-up", "a fitted olive green scoop-neck top", "a thoughtful expression", "even frontal studio light, against a plain charcoal backdrop"),
    ("<sks> front-right quarter view eye-level shot medium shot", "a fitted burgundy bodysuit", "a broad open smile", "flat overcast daylight, in a sunlit kitchen"),
]

cfg = load_config()
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
app = _get_face_app()
refemb = [e for e in (embed_image(REFS / n) for n in ("amanda_face.jpg", "amanda_portrait1.jpg", "amanda_portrait2.jpg")) if e is not None]

def measure(path):
    im = Image.open(path).convert("RGB")
    fs = app.get(np.asarray(im)[:, :, ::-1])
    if not fs: return {}
    f = max(fs, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
    px = round(float(f.bbox[3]-f.bbox[1]) / im.height * 1536)
    return {"self": round(max(float(e @ f.normed_embedding) for e in refemb), 3), "bucket_px": px}

rows = []
for arm, (refs3, hair) in ARMS.items():
    for k, (pose, outfit, expr, light) in enumerate(SHOTS):
        prompt = f"{pose}{hair}, wearing {outfit}, {expr}, {light}"
        dest = OUT / f"{arm}_{k}.png"
        if not dest.exists():
            wf = substitute(load_template(workflows_dir(cfg), "qwen_multiangle_ref"), {
                "REF1": refs3[0], "REF2": refs3[1], "REF3": refs3[2],
                "POSITIVE": prompt, "NEGATIVE": NEG, "SEED": 5000 + k, "FILENAME_PREFIX": f"loragen_local/amanda_conformance/{arm}_{k}"})
            files = client.outputs(client.wait(client.submit(wf), timeout_s=1800))
            if not files:
                print(f"{arm}{k}: NO OUTPUT"); continue
            client.fetch(files[0], dest)
        m = measure(dest)
        rows.append({"arm": arm, "k": k, "file": str(dest), "prompt": prompt, **m})
        print(f"{arm}{k}: self {m.get('self')} {m.get('bucket_px')}px")
(OUT / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

tw, th = 300, 450
sheet = Image.new("RGB", (4 * tw, 4 * (th + 22)), "white"); d = ImageDraw.Draw(sheet)
for r in rows:
    i, j = "ABCD".index(r["arm"]), r["k"]
    im = Image.open(r["file"]).resize((tw, th)); x, y = j * tw, i * (th + 22)
    sheet.paste(im, (x, y)); d.text((x + 4, y + th + 4), f"{r['arm']}{j} self {r.get('self')} {r.get('bucket_px')}px", fill="black")
sheet.save(OUT / "sheet.jpg", quality=85)
print("AMANDACONFDONE", OUT / "sheet.jpg")
