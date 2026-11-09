"""Which Wan nudity LoRA, if any, the undressing legs need: the same three FLF2V
legs between the same chosen stills, once per Wan LoRA arm.

    python scripts/video/nsfw_flf_test.py <character> <dressed> <topless> <nude> <end> [--dry-run]

The stills come from nsfw_lora_test.py (her body made naked where her own LoRA
or photo carries identity). Here every leg starts AND lands on a fixed still,
so the video model only fills the motion between them - it never has to invent
her over 80 frames, which is what lost her in the chained try-on keys.

Legs: dressed -> topless -> nude -> end (her next outfit, or back to dressed).
Arms (Wan 2.2 I2V high/low pair, capped at 0.6 by the composition rule):
  none     no nudity LoRA - Wan alone between two naked stills
  general  lopi999 Wan2.2-I2V General NSFW (e8), 0.5
  pussy    the Pussyv1 pair the try-on keys used, 0.5 - re-tested before it goes

Output: library/<character>/<date>_video_nsfw-flf-test/<arm>__<leg>.mp4, and
sheet.jpg (rows = arm x leg; first, middle, last frame; the middle frame's face
score against her reference - QC only, his eye is final).
"""

import json
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from sourcemode.assets.looks import reference
from sourcemode.config import load_config
from sourcemode.gates.identity import cosine, embed_image
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.passes import build_video_workflow
from sourcemode.video import NEGATIVE as VIDEO_NEGATIVE
from sourcemode.video import ffmpeg_exe, video_output

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
if len(ARGS) != 5:
    raise SystemExit(__doc__)
CHAR = ARGS[0].lower()
STILLS = {k: Path(p) for k, p in zip(("dressed", "topless", "nude", "end"), ARGS[1:])}
for k, p in STILLS.items():
    if not p.is_file():
        raise SystemExit(f"{k}: no image at {p}")

ARMS = {
    "none": ("", "", 0.0),
    # ComfyUI on Windows lists subfolder LoRAs with a backslash
    "general": ("nsfw\\wan22_general_nsfw_high.safetensors", "nsfw\\wan22_general_nsfw_low.safetensors", 0.5),
    "pussy": ("WAN2.2-HighNoise_Pussyv1-I2V_T2V.safetensors", "WAN2.2-LowNoise_Pussyv1-I2V_T2V.safetensors", 0.5),
}
LEGS = (
    ("undress_top", "dressed", "topless",
     "she slowly pulls her top down to her waist, revealing her bare breasts, smiling at the camera, "
     "the camera holds still"),
    ("undress_all", "topless", "nude",
     "she slides the rest of her clothes down her legs and steps out of them, standing naked, smiling "
     "at the camera, the camera holds still"),
    ("dress", "nude", "end",
     "she gets dressed again, pulling her outfit on and smoothing it down, smiling at the camera, "
     "the camera holds still"),
)
NEG = VIDEO_NEGATIVE + ", different person, changing face, blurry, morphing, extra limbs"

cfg = load_config()
face_ref = reference(CHAR)
d = find_set(cfg, CHAR, "video", "nsfw-flf-test", create=True)
write_set_json(d, character=CHAR, kind="video", name="nsfw-flf-test", date=d.name[:10])
LOG = d / "run.log"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def arm_cfg(high: str, low: str, strength: float) -> dict:
    video = dict(cfg["video"], lora_high=high, lora_low=low, lora_strength=strength)
    return {**cfg, "video": video}


plan = [(arm, leg) for arm in ARMS for leg in LEGS]
log(f"{CHAR}: {len(plan)} legs -> {d}")
if DRY:
    for arm, leg in plan:
        log(f"  would render {arm} {leg[0]}: {leg[1]} -> {leg[2]}")
    raise SystemExit(0)

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
names = {k: client.upload_image(p) for k, p in STILLS.items()}
w, h = Image.open(STILLS["dressed"]).size
scale = 1440 / max(w, h)
W, H = int(w * scale) // 16 * 16, int(h * scale) // 16 * 16
ref_emb = embed_image(face_ref) if face_ref else None
rng = random.SystemRandom()
record = json.loads((d / "legs.json").read_text(encoding="utf-8")) if (d / "legs.json").is_file() else {}
record["_stills"] = {k: str(p) for k, p in STILLS.items()}


def frames(mp4: Path) -> list[Path]:
    out = []
    for tag, seek in (("first", ["-ss", "0"]), ("mid", ["-ss", "2.5"]), ("last", ["-sseof", "-0.2"])):
        p = mp4.with_name(f"{mp4.stem}_{tag}.png")
        subprocess.run([ffmpeg_exe(), "-y", "-v", "error", *seek, "-i", str(mp4), "-vframes", "1", str(p)],
                       check=True)
        out.append(p)
    return out


for arm, (leg, a, b, motion) in plan:
    mp4 = d / f"{arm}__{leg}.mp4"
    if not mp4.is_file():
        seed = rng.randrange(1, 2**31)
        t0 = time.monotonic()
        wf, _ = build_video_workflow(arm_cfg(*ARMS[arm]), CHAR, positive=motion, negative=NEG,
                                     image_name=names[a], end_image_name=names[b], seed=seed,
                                     render_pass="medium", duration_s=5.0, width=W, height=H)
        vid = video_output(client.outputs(client.wait(client.submit(wf), timeout_s=4 * 3600)))
        if not vid:
            raise SystemExit(f"{arm}/{leg}: ComfyUI returned no video")
        client.fetch(vid, mp4)
        record[mp4.stem] = {"seed": seed, "lora": ARMS[arm][0], "strength": ARMS[arm][2]}
        log(f"  {mp4.name}: {time.monotonic() - t0:.0f}s")
    shots = frames(mp4)
    e = embed_image(shots[1])
    record.setdefault(mp4.stem, {})["mid_face"] = (round(float(cosine(ref_emb, e)), 3)
                                                    if e is not None and ref_emb is not None else None)
    (d / "legs.json").write_text(json.dumps(record, indent=1), encoding="utf-8")

TW, TH = 240, 360
sheet = Image.new("RGB", (TW * 3, TH * len(plan)), "black")
dr = ImageDraw.Draw(sheet)
for r, (arm, (leg, *_)) in enumerate(plan):
    stem = f"{arm}__{leg}"
    for c, tag in enumerate(("first", "mid", "last")):
        im = Image.open(d / f"{stem}_{tag}.png").convert("RGB")
        im.thumbnail((TW, TH))
        sheet.paste(im, (c * TW, r * TH))
    dr.rectangle([0, r * TH, TW * 3, r * TH + 16], fill="black")
    dr.text((4, r * TH + 2), f"{arm} / {leg} / mid face {record[stem].get('mid_face')}", fill="yellow")
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")
log("LEGSDONE")
