"""Sort a folder of LoRA candidate photos into coverage groups for a manual pick.

    python scripts/prep/sort_candidates.py <character> <folder> [--total=80]

Jeremy, 2026-11-11: "create subfolders with defined descriptions of the final
assets needed here. So if frontal is one of the subgroups, create a folder for
that with the number of examples that I likely need, and then drop all of the
assets into that folder. Create another folder for the selected winners".

Nadia's v2 set had zero frontal faces and 87% turned to her left (docs: the
2026-11-11 dataset review), so the groups are head angle, the thing that broke
her. Every image is scored with InsightFace against her reference and MOVED
(inside this folder only - these are copies) into:

    1_frontal/           |yaw| <= 10        need ~35
    2_slight_turn/       10 < |yaw| <= 25   need ~20
    3_three_quarter/     25 < |yaw| <= 45   need ~15
    4_profile/           |yaw| > 45         need ~10
    x_small_face/        face under 300 px tall at 1024x1536 - not usable as is
    x_no_face/           nothing detected
    x_not_her/           cosine to her reference under 0.30

Each group has a `_selected/` for his winners and a README with what to vary
inside it (framing, hair, expression, outfit). Files are renamed
`<facepx>_<cos>_<framing>__<original>` so a name sort puts the biggest,
closest faces first. geometry.json keeps every measurement.
"""

import json
import shutil
import sys
from pathlib import Path

import cv2

from sourcemode.assets.looks import reference
from sourcemode.gates.identity import _get_face_app, cosine, embed_image

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
CHAR, ROOT = ARGS[0].lower(), Path(ARGS[1])
TOTAL = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--total=")), 80)
IMG = {".png", ".jpg", ".jpeg", ".webp"}
MIN_FACE = 300
MIN_COS = 0.30
GROUPS = [
    ("1_frontal", 0, 10, 0.44),
    ("2_slight_turn", 10, 25, 0.25),
    ("3_three_quarter", 25, 45, 0.19),
    ("4_profile", 45, 999, 0.12),
]
HOW = """Within this group vary, as evenly as you can:
- framing: about a third each of head-and-shoulders (hs), head-and-chest (hc) and waist-up (wu);
  the framing is in the filename after the cosine
- hair: loose, ponytail, bun, braid, half-up, pigtails - no one style on more than half
- expression: neutral, closed-lip smile, smile with teeth, laughing, speaking
- outfit: no outfit twice if you can help it
- lighting and setting: a mix of daylight, lamplight, indoors and out
Prefer the biggest face you can (the first number in the name is the face height in px;
400+ is the target, 300 is the floor). The second number is the cosine to her reference
photo - a tie-breaker, not a verdict; your eye decides.
Put the winners in _selected/.
"""

ref = reference(CHAR)
app = _get_face_app()
ref_emb = embed_image(ref)
files = sorted(p for p in ROOT.iterdir() if p.is_file() and p.suffix.lower() in IMG)
print(f"{len(files)} images in {ROOT}", flush=True)

for name, *_ in GROUPS:
    (ROOT / name / "_selected").mkdir(parents=True, exist_ok=True)
for name in ("x_small_face", "x_no_face", "x_not_her"):
    (ROOT / name).mkdir(exist_ok=True)

geom = {}
counts: dict[str, int] = {}
for i, p in enumerate(files, 1):
    img = cv2.imread(str(p))
    if img is None:
        continue
    h_img, w_img = img.shape[:2]
    faces = app.get(img)
    rec = {"source_name": p.name, "image": [w_img, h_img]}
    if not faces:
        dest, new = ROOT / "x_no_face", p.name
    else:
        f = max(faces, key=lambda x: float(cosine(ref_emb, x.normed_embedding)))
        cos = float(cosine(ref_emb, f.normed_embedding))
        x1, y1, x2, y2 = [float(v) for v in f.bbox]
        face_px = y2 - y1
        # scale the face to what it would be at the training bucket (1024 wide)
        scale = 1024 / w_img
        face_px_bucket = face_px * scale
        yaw = float(f.pose[1]) if f.pose is not None else 0.0
        frac = face_px / h_img
        framing = "hs" if frac > 0.30 else ("hc" if frac > 0.20 else "wu")
        rec.update({"cos": round(cos, 3), "yaw": round(yaw, 1), "pitch": round(float(f.pose[0]), 1),
                    "face_px": int(face_px), "face_px_at_1024": int(face_px_bucket), "framing": framing,
                    "age": int(round(float(f.age))) if getattr(f, "age", None) is not None else None})
        if cos < MIN_COS:
            dest = ROOT / "x_not_her"
        elif face_px_bucket < MIN_FACE:
            dest = ROOT / "x_small_face"
        else:
            dest = ROOT / next(n for n, lo, hi, _ in GROUPS if lo < abs(yaw) <= hi or (lo == 0 and abs(yaw) <= hi))
        new = f"{int(face_px_bucket):04d}_{cos:.2f}_{framing}__{p.name}"
    shutil.move(str(p), str(dest / new))
    rec["dest"] = f"{dest.name}/{new}"
    geom[new] = rec
    counts[dest.name] = counts.get(dest.name, 0) + 1
    if i % 100 == 0:
        print(f"  {i}/{len(files)}", flush=True)

(ROOT / "geometry.json").write_text(json.dumps(geom, indent=1), encoding="utf-8")
for name, lo, hi, share in GROUPS:
    need = round(TOTAL * share)
    have = counts.get(name, 0)
    rng = f"|yaw| <= {hi}" if lo == 0 else (f"|yaw| > {lo}" if hi == 999 else f"{lo} < |yaw| <= {hi}")
    (ROOT / name / "README.md").write_text(
        f"# {name}: head turned {rng} degrees\n\nNEED about {need} of a {TOTAL}-image set. "
        f"{have} candidates here.\n\n{HOW}", encoding="utf-8")
(ROOT / "README.md").write_text(
    f"# {CHAR} LoRA candidates, sorted {len(files)} images by head angle\n\n"
    + "\n".join(f"- {n}: {counts.get(n, 0)} candidates, need ~{round(TOTAL * s)}" for n, _, _, s in GROUPS)
    + "\n" + "\n".join(f"- {n}: {counts.get(n, 0)}" for n in ("x_small_face", "x_no_face", "x_not_her"))
    + f"\n\nTarget set: ~{TOTAL} images, faces 300 px+ tall at the 1024-wide bucket (400 target), angles spread as "
      f"above, no hair style / outfit / expression on more than half.\nWinners go in each group's _selected/. "
      f"geometry.json has every measurement; filenames are <face px>_<cosine>_<framing>__<original>.\n",
    encoding="utf-8")
print("counts:", counts, flush=True)
print("SORTDONE", flush=True)
