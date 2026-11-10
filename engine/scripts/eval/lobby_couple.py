"""The Willow lobby's walk-through: Danny and "Danny's friend" as ONE cutout.

    python scripts/eval/lobby_couple.py [--seeds N] [--dry-run]

Jeremy, 2026-11-09, on the prologue's P4 beat: "right now it's just text and
it's hard to follow" - Mei at the desk in work_01 (her own cutout, already in
the game) while a man and a woman cross the lobby to the stairs. The game
renders its rooms empty and layers people on as cutouts (CharacterOverlay), so
the pair is a cutout too - and one cutout, not two: arm in arm they overlap,
and two cutouts seam at the linked arms and drift apart at other window shapes.

Two views of the SAME pair, for the two positions in the beat:
  front  just inside the street door, three-quarter view, walking left - T2I
         on the pack's grey studio, no LoRA, one per seed
  back   at the foot of the stairs, seen from behind - Qwen-Image-Edit of the
         front render, so clothes, hair and build carry over (his ask: "generate
         one and then edit it for the different angles")
Sunday night: she is in a coat (Mei's closer is "Different coat."), he is half a
step ahead with his face turned away - Danny has no face yet, and this does not
give him one. Cut out with the pack's grey-studio matte. Output:
library/_extras/<date>_shoot_lobby-couple/ (renders, sheet.jpg) and
outputs/game-assets/_extras/lobby_couple/ (png + webp cutouts + sidecars) for
Jeremy to pick from; nothing here writes into the game repo.
"""

import random
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from sourcemode.assets.cutout import cutout_batch, hybrid_remover
from sourcemode.assets.pack import CAMERA_NEGATIVE, H, STUDIO_BACKDROP, W
from sourcemode.assets.render import t2i_workflow
from sourcemode.config import load_config, outputs_dir
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.passes import build_edit_workflow

DRY = "--dry-run" in sys.argv
SEEDS = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--seeds=")), 4))

FRONT = ("a full-length picture of a young man and a young woman walking arm in arm, side by side, "
         "in three-quarter view, walking toward the left of the frame, late on a Sunday night: he is "
         "half a step ahead in a dark navy bomber jacket over a plain white t-shirt, dark jeans and "
         "white sneakers, his head turned away from the camera toward where they are going so his face "
         "is not visible; she is in a long camel wool coat open over a short black dress and black "
         "heels, holding his arm, her face turned toward him, mid-stride, both figures fully in frame "
         f"from head to feet, {STUDIO_BACKDROP}. Photorealistic, natural skin texture, sharp focus.")
BACK = ("Show the same two people from behind, walking away from the camera toward the top left of "
        "the frame, still arm in arm, her head turned slightly toward him, his back to the camera. Keep "
        "their clothes, hair, heights and builds exactly the same: his navy bomber jacket, dark jeans "
        "and white sneakers; her long camel coat, short black dress and black heels. Keep the plain "
        "light grey studio background, the soft even lighting and the full-length framing from head to "
        "feet. Photorealistic, natural skin texture, sharp focus.")
NEGATIVE = (CAMERA_NEGATIVE + ", his face visible, looking at the camera, three people, extra person, "
            "cropped feet, cut off at the knees, close-up, blurry, deformed hands, extra limbs, "
            "cartoon, text, watermark, props, furniture, doorway, stairs")

cfg = load_config()
d = find_set(cfg, "_extras", "shoot", "lobby-couple", create=True)
write_set_json(d, character="_extras", kind="shoot", name="lobby-couple", date=d.name[:10])
LOG = d / "run.log"
CUT_DIR = outputs_dir(cfg) / "game-assets" / "_extras" / "lobby_couple"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


log(f"lobby couple: {SEEDS} seeds, front by T2I then back by Edit -> {d}")
if DRY:
    for s in range(SEEDS):
        log(f"  would render front_{s}.png then back_{s}.png, then cut both out -> {CUT_DIR}")
    raise SystemExit(0)

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
rng = random.SystemRandom()
pngs: list[Path] = []
for s in range(SEEDS):
    front = d / f"front_{s}.png"
    if not front.is_file():
        seed = rng.randrange(1, 2**31)
        t0 = time.monotonic()
        wf = t2i_workflow(cfg, FRONT, seed, "sourcemode/extras_lobby_couple", lora_path="",
                          negative=NEGATIVE, width=W, height=H)
        files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
        if not files:
            raise SystemExit(f"front_{s}: ComfyUI returned no image")
        client.fetch(files[0], front)
        log(f"  {front.name}: seed {seed}  {time.monotonic() - t0:.0f}s")
    pngs.append(front)
    back = d / f"back_{s}.png"
    if not back.is_file():
        seed = rng.randrange(1, 2**31)
        t0 = time.monotonic()
        wf, _ = build_edit_workflow(cfg, "extras", instruction=BACK, negative=NEGATIVE,
                                    image_name=client.upload_image(front), seed=seed,
                                    render_pass="medium", filename_prefix="sourcemode/extras_lobby_couple")
        files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
        if not files:
            raise SystemExit(f"back_{s}: ComfyUI returned no image")
        client.fetch(files[0], back)
        log(f"  {back.name}: seed {seed}  {time.monotonic() - t0:.0f}s")
    pngs.append(back)

TW, TH = 300, 450
sheet = Image.new("RGB", (TW * 2, TH * SEEDS), "black")
dr = ImageDraw.Draw(sheet)
for s in range(SEEDS):
    for c, tag in enumerate(("front", "back")):
        im = Image.open(d / f"{tag}_{s}.png").convert("RGB")
        im.thumbnail((TW, TH))
        sheet.paste(im, (c * TW, s * TH))
        dr.rectangle([c * TW, s * TH, c * TW + TW, s * TH + 16], fill="black")
        dr.text((c * TW + 4, s * TH + 2), f"{tag} {s}", fill="yellow")
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")

# the cutouts: the pack's grey-studio matte, the game's canvas, webp beside png
size = tuple(cfg.get("assets", {}).get("game_size", (W, H)))
cutout_batch(pngs, CUT_DIR, remover=hybrid_remover(), model="hybrid", size=size, webp=True, log=log)
log(f"cutouts -> {CUT_DIR}")
log("COUPLEDONE")
