"""Two-stage generation: hair baselines first, then outfit/background/expression.

Jeremy, 2026-09-29: "we set up a larger array of face and hair baselines, and then
we use those to generate the outfit and background variety needed."

The measurement that motivates it: asking for attributes cost about 0.10 identity,
and the cost scaled with how far the ask sat from the references - denim/street
(closest to her casual reference) held 0.794, a velvet gown and a knit jumper
dropped to 0.669 and 0.655. A closer reference should mean a smaller ask.

STAGE 1  generate a hair baseline per style from the ORIGINAL references.
         Each is gated against those originals before it may seed anything -
         stage-1 error otherwise compounds into stage 2, which is exactly how
         Keiko was aged three years without anyone noticing.

STAGE 2  three arms, same outfit/background/expression ask, so the only variable
         is what sits in the three reference slots:
           A  baseline x3                      - his proposal as stated
           B  baseline + the two originals     - baseline supplies hair, originals
                                                 anchor identity
           C  originals x3, hair asked in text - today's method, the control

If B beats A, the originals are worth keeping in the slots. If both beat C, the
two-stage idea is right. If neither does, it is not, and the control already works.

    python amanda_twostage.py [--char amanda]
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
OUT = Path(f"outputs/twostage_{CHAR}"); OUT.mkdir(parents=True, exist_ok=True)
COMFY_IN = Path("C:/ComfyUI/input")
SEED = 11
POSE = "<sks> front-right quarter view eye-level shot medium shot"
FRONT = "<sks> front view eye-level shot medium shot"
NEG = ("different person, different face, deformed, distorted hands, extra limbs, "
       "plastic skin, doll-like, blurry, low quality, cartoon, watermark, text")
# Identity floor a baseline must clear against the ORIGINAL references before it is
# allowed to seed stage 2. Well above the 0.50 gross-mismatch floor: a baseline is a
# seed, so it has to be good, not merely not-wrong.
BASELINE_FLOOR = 0.75

HAIR = {
    "loose":    "her hair worn loose",
    "ponytail": "her hair in a high ponytail",
    "bun":      "her hair in a low bun",
    "braid":    "her hair in a braid over one shoulder",
}
# held identical across all three arms in stage 2
LOOKS = [
    ("blazer_office", ", wearing a charcoal blazer over a white shirt, in a blurred office, "
                      "composed expression"),
    ("gown_ballroom", ", wearing a midnight blue velvet gown, in a blurred ballroom, "
                      "a soft closed-mouth smile"),
    ("denim_street", ", wearing a blue denim jacket over a white tee, on a city sidewalk, "
                     "a broad open smile"),
]

cfg = load_config()
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
app = _get_face_app()

orig = sorted(p for p in REFS.glob(f"{CHAR}_*")
              if p.stem.split("_")[0].lower() == CHAR and p.suffix.lower() in (".jpg", ".jpeg", ".png"))
if not orig:
    raise SystemExit(f"no references for {CHAR}")
orig_names = []
for p in orig[:3]:
    d = COMFY_IN / p.name
    if not d.exists(): d.write_bytes(p.read_bytes())
    orig_names.append(p.name)
while len(orig_names) < 3: orig_names.append(orig_names[0])

# the bank every measurement is scored against - ORIGINAL references only
orig_emb = [e for e in (embed_image(p) for p in orig) if e is not None]
others = {}
for p in sorted(REFS.glob("*")):
    if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"): continue
    who = p.stem.split("_")[0].lower()
    if who in (CHAR, "universal"): continue
    e = embed_image(p)
    if e is not None: others.setdefault(who, []).append(e)


def measure(path):
    fs = app.get(np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1])
    if not fs: return None
    f = max(fs, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
    self_ = max(float(e @ f.normed_embedding) for e in orig_emb)
    best, bs = CHAR, self_
    for n, b in others.items():
        v = max(float(x @ f.normed_embedding) for x in b)
        if v > bs: best, bs = n, v
    return {"self": round(self_, 3), "best": best, "yaw": round(float(f.pose[1]), 1),
            "face_px": int(f.bbox[3] - f.bbox[1])}


def render(dest, prompt, refs3, prefix):
    if dest.exists(): return True
    wf = substitute(load_template(workflows_dir(cfg), "qwen_multiangle_ref"), {
        "REF1": refs3[0], "REF2": refs3[1], "REF3": refs3[2],
        "POSITIVE": prompt, "NEGATIVE": NEG, "SEED": SEED, "FILENAME_PREFIX": prefix})
    files = client.outputs(client.wait(client.submit(wf), timeout_s=1800))
    if not files: return False
    client.fetch(files[0], dest); return True


# ---------- STAGE 1 -----------------------------------------------------------
print("STAGE 1: hair baselines from the original references")
baselines = {}
for style, clause in HAIR.items():
    dest = OUT / f"baseline_{style}.png"
    if not render(dest, f"{FRONT}, {clause}, wearing a plain white top, against a plain "
                        f"light grey background, a neutral expression",
                  orig_names, f"twostage_{CHAR}/baseline_{style}"):
        print(f"  {style}: NO OUTPUT"); continue
    m = measure(dest)
    if m is None:
        print(f"  {style}: no face, REJECTED"); continue
    ok = m["self"] >= BASELINE_FLOOR and m["best"] == CHAR
    print(f"  {style:<9} identity {m['self']:.3f} vs {CHAR}, best={m['best']}, "
          f"face {m['face_px']}px  -> {'GATED IN' if ok else 'REJECTED'}")
    if ok:
        n = f"{CHAR}_baseline_{style}.png"
        (COMFY_IN / n).write_bytes(dest.read_bytes())
        baselines[style] = (n, m)
if not baselines:
    raise SystemExit("no baseline cleared the gate - stage 2 would compound the error")

# ---------- STAGE 2 -----------------------------------------------------------
print(f"\nSTAGE 2: {len(baselines)} baselines x {len(LOOKS)} looks x 3 arms")
rows = []
for style, (bname, _) in baselines.items():
    for look, extra in LOOKS:
        arms = {
            "A_baseline_only": [bname, bname, bname],
            "B_baseline_plus_orig": [bname, orig_names[0], orig_names[1]],
            "C_control_text_hair": orig_names,
        }
        for arm, refs3 in arms.items():
            # only the control has to ask for hair in text; A and B get it from the seed
            prompt = POSE + (f", {HAIR[style]}" if arm.startswith("C") else "") + extra
            dest = OUT / f"{arm}__{style}__{look}.png"
            if not render(dest, prompt, refs3, f"twostage_{CHAR}/{arm}_{style}_{look}"):
                print(f"  {arm} {style} {look}: NO OUTPUT"); continue
            m = measure(dest) or {}
            rows.append({"arm": arm, "style": style, "look": look, "file": str(dest),
                         "prompt": prompt, **m})
            print(f"  {arm:<22}{style:<9}{look:<15}"
                  f"self {m.get('self')}  best {m.get('best')}  face {m.get('face_px')}px")

(OUT / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
print("\n=== identity by arm (higher is better) ===")
for arm in ("A_baseline_only", "B_baseline_plus_orig", "C_control_text_hair"):
    v = [r["self"] for r in rows if r["arm"] == arm and r.get("self") is not None]
    w = sum(1 for r in rows if r["arm"] == arm and r.get("best") not in (None, CHAR))
    if v:
        print(f"  {arm:<22} n={len(v):<3} mean {sum(v)/len(v):.3f}  "
              f"min {min(v):.3f}  max {max(v):.3f}  wrong-identity {w}")

items = [{"id": f"{r['arm']}__{r['style']}__{r['look']}", "path": r["file"],
          "arm": r["arm"], "group": f"{r['style']}_{r['look']}"} for r in rows]
if items:
    make_set(Path("outputs/judge"), f"twostage_{CHAR}",
             f"{CHAR.title()} two-stage: hair from a seed image vs hair asked in text",
             items, question="Is this her, with the right hair and outfit?", priority=1)
    print(f"\njudge set twostage_{CHAR}: {len(items)} images")
print("TWOSTAGEDONE")
