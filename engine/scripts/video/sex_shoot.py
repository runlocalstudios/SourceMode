"""Sex-act stills for a character: handjob, blowjob, vaginal and anal, with a
well-endowed man, several seeds per shot, scored for her face and for age.

    python scripts/video/sex_shoot.py <character> [--seeds=N] [--arms=a,b] [--only=shot,shot] [--dry-run]

Jeremy, 2026-11-09: "Set up shoots that generate plenty of example angles,
poses, additions like her dripping lube from a lube bottle onto the big cock.
Go for an 8 inch, thick cock ... Try to do some anal poses too - crouching on
top of him on the bed facing forward and maybe her lying down on the bed and
him standing next to the bed."

Only characters who read as adults run through this. The character record's
age is not enough on its own: InsightFace's age estimate is logged per render
and anything that reads young is flagged on the sheet for rejection. QC only;
his eye is final. (fiona was held back on 2026-11-09 while her "18-year-old
girl" wording rendered young; her record now says "a 20-year-old young woman"
and her office set of 2026-11-10 reads early twenties, so she runs - flagged
tiles still get thrown out.)

Arms (Qwen-Image 2512 text-to-image, her locked LoRA at 1.0 plus the GNASS sex
LoRA - its training name is s3x_2512_qwen - at two strengths):
  gnass06  GNASS 0.6 (the composition rule's cap for a second LoRA)
  gnass08  GNASS 0.8 - anatomy first, identity second; the score says which

Output: library/<character>/<date>_video_sex-shoot/<arm>__<shot>__<seed>.png,
shots.json (seed, face score, age estimate) and sheet.jpg (rows = shot, columns
= arm x seed).
"""

import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
from PIL import Image, ImageDraw

from sourcemode.assets.appearance import clause, negative as appearance_negative
from sourcemode.assets.looks import reference
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.render import t2i_workflow
from sourcemode.config import load_config
from sourcemode.gates.identity import _get_face_app, cosine, embed_image
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
if len(ARGS) != 1:
    raise SystemExit(__doc__)
CHAR = ARGS[0].lower()
SEEDS = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--seeds=")), 2))
ONLY_ARMS = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--arms=")), None)
ONLY_SHOTS = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), None)
YOUNG_FLAG = 20  # Jeremy, 2026-11-10: "The floor should be like 20 because 18 is a fucking adult"

GNASS = "nsfw\\qimage2512_gnass.safetensors"  # ComfyUI on Windows lists subfolder LoRAs with a backslash
ARMS = {"gnass06": 0.6, "gnass08": 0.8}

HIM = "a man with a thick eight-inch erect penis, the penis large and prominent"
BED = "on a bed in a softly lit bedroom"
SHOTS = {
    "handjob": (f"POV picture from the man's eyes: she kneels {BED} between his legs, both of her hands wrapped "
                f"around {HIM}, stroking it, looking up into the camera with a hungry smile, her bare breasts visible"),
    "handjob_lube": (f"POV picture from the man's eyes: she kneels {BED}, one hand around the base of {HIM}, with the "
                     f"other hand tipping a clear bottle of lube so a thick stream of lube drips onto the head of the "
                     f"penis and runs down the shaft, looking up at the camera"),
    "blowjob": (f"POV picture from the man's eyes: she kneels {BED}, her lips stretched around the thick shaft of "
                f"{HIM}, the head of the penis in her mouth, one hand around the base, looking up into the camera"),
    "blowjob_deep": (f"POV picture from the man's eyes: she kneels {BED}, most of {HIM} inside her mouth, her cheeks "
                     f"hollowed, her lips at the base, her eyes watering, looking up at the camera"),
    "cowgirl_pov": (f"POV picture from the eyes of {HIM} lying on his back {BED}: she straddles his hips facing the "
                    f"camera, her knees wide apart and out to the sides, his thick penis deep inside her vagina, her "
                    f"labia stretched around the shaft, her bare breasts visible, her hands on his chest, riding him"),
    "cowgirl_rear": (f"picture from the foot of the bed: {HIM} lies on his back {BED}, she rides him facing away from "
                     f"his head, toward the camera, crouched over his hips with her feet flat on the bed and her knees "
                     f"wide, his thick penis deep inside her vagina, her stretched labia visible, her face visible "
                     f"looking into the camera"),
    "anal_crouch": (f"picture from the foot of the bed: {HIM} lies on his back {BED}, she crouches over his hips facing "
                    f"the camera with her feet flat on the bed and her knees wide apart, his thick penis deep inside "
                    f"her anus, her wet vagina fully visible just above it, her face visible looking into the camera"),
    "anal_bedside": (f"picture from beside the bed: she lies on her back across the edge of the bed with her legs "
                     f"raised and held open, {HIM} standing beside the bed with his thick penis deep inside her anus, "
                     f"her wet glistening vagina fully visible above it, her bare breasts visible, her face turned to "
                     f"the camera"),
}
if ONLY_ARMS:
    ARMS = {k: v for k, v in ARMS.items() if k in ONLY_ARMS}
if ONLY_SHOTS:
    SHOTS = {k: v for k, v in SHOTS.items() if k in ONLY_SHOTS}
NEGATIVE = ("different person, different face, changed hair, clothes, underwear, condom, extra penis, extra hands, "
            "extra limbs, deformed genitals, deformed hands, blurry, low quality, cartoon, anime, watermark, text, "
            "childlike, child, underage")

cfg = load_config()
lora = resolve_lora(cfg, CHAR)
if not lora:
    raise SystemExit(f"{CHAR} has no locked LoRA")
face_ref = reference(CHAR)
if face_ref is None:
    raise SystemExit(f"{CHAR} has no face reference to score against")
d = find_set(cfg, CHAR, "video", "sex-shoot", create=True)
write_set_json(d, character=CHAR, kind="video", name="sex-shoot", date=d.name[:10])
LOG = d / "run.log"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def prompt_for(shot: str) -> str:
    trig = lora.get("trigger") or CHAR
    return (f"{trig}, {clause(CHAR)}, an adult woman, {SHOTS[shot]}, completely naked. Photorealistic, "
            f"natural skin texture, sharp focus.")


plan = [(arm, shot, s) for shot in SHOTS for arm in ARMS for s in range(SEEDS)]
log(f"{CHAR}: {len(plan)} stills ({len(SHOTS)} shots x {len(ARMS)} arms x {SEEDS} seeds) -> {d}")
if DRY:
    for p in plan:
        log(f"  would render {p}")
    raise SystemExit(0)

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
ref_emb = embed_image(face_ref)
app = _get_face_app()
rng = random.SystemRandom()
record = json.loads((d / "shots.json").read_text(encoding="utf-8")) if (d / "shots.json").is_file() else {}


def score(p: Path) -> tuple[float | None, int | None]:
    """Her face score against the reference and InsightFace's age estimate of the largest face."""
    if app is None:
        return None, None
    img = cv2.imread(str(p))
    faces = app.get(img) if img is not None else []
    if not faces:
        return None, None
    f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    face = round(float(cosine(ref_emb, f.normed_embedding)), 3) if ref_emb is not None else None
    age = int(round(float(f.age))) if getattr(f, "age", None) is not None else None
    return face, age


for arm, shot, s in plan:
    out = d / f"{arm}__{shot}__{s}.png"
    if not out.is_file():
        seed = rng.randrange(1, 2**31)
        t0 = time.monotonic()
        wf = t2i_workflow(cfg, prompt_for(shot), seed, f"sourcemode/{CHAR}_sexshoot", lora_path=lora["path"],
                          negative=NEGATIVE + ", " + (appearance_negative(CHAR) or ""),
                          extra_loras=((GNASS, ARMS[arm]),))
        files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
        if not files:
            raise SystemExit(f"{arm}/{shot}/{s}: ComfyUI returned no image")
        client.fetch(files[0], out)
        face, age = score(out)
        record[out.stem] = {"arm": arm, "shot": shot, "seed": seed, "strength": ARMS[arm], "face": face, "age": age,
                            "young": bool(age is not None and age < YOUNG_FLAG)}
        (d / "shots.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
        log(f"  {out.name}: face {face}  age {age}{'  YOUNG' if record[out.stem]['young'] else ''}  "
            f"{time.monotonic() - t0:.0f}s")

TW, TH = 300, 450
cols = len(ARMS) * SEEDS
sheet = Image.new("RGB", (TW * cols, TH * len(SHOTS)), "black")
dr = ImageDraw.Draw(sheet)
for r, shot in enumerate(SHOTS):
    tiles = [(arm, s, d / f"{arm}__{shot}__{s}.png") for arm in ARMS for s in range(SEEDS)]
    for c, (arm, s, p) in enumerate(tiles):
        im = Image.open(p).convert("RGB")
        im.thumbnail((TW, TH))
        sheet.paste(im, (c * TW, r * TH))
        rec = record.get(p.stem, {})
        dr.rectangle([c * TW, r * TH, c * TW + TW, r * TH + 18], fill="red" if rec.get("young") else "black")
        dr.text((c * TW + 4, r * TH + 3), f"{shot} / {arm} s{s} / face {rec.get('face')} age {rec.get('age')}",
                fill="yellow")
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")
log("SHOTSDONE")
