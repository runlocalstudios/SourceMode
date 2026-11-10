"""The Willow lobby's walk-through: Danny and "Danny's friend" as ONE cutout.

    python scripts/eval/lobby_couple.py [--seeds N] [--dry-run]

Jeremy, 2026-11-09, on the prologue's P4 beat: "right now it's just text and
it's hard to follow" - Mei at the desk in work_01 (her own cutout, already in
the game) while a man and a woman cross the lobby to the stairs. The game
renders its rooms empty and layers people on as cutouts (CharacterOverlay), so
the pair is a cutout too - and one cutout, not two: arm in arm they overlap,
and two cutouts seam at the linked arms and drift apart at other window shapes.

Two views of the SAME pair, for the two positions in the beat (the lobby is
seen from where the player stands, Mei at the desk on the left, the pair on
the right):
  stairs  at the foot of the stairs, backs square to the camera, heads up as
          they are about to climb - T2I on the pack's grey studio, no LoRA
  door    just inside the street door, seen from their side at an angle, both
          looking across at Mei - Qwen-Image-Edit of the stairs render, so
          clothes, hair and build carry over (his ask: "generate one and then
          edit it for the different angles")
In both views the opening of her coat faces away from the camera.

Why this way round (three rounds, 2026-11-09): T2I would not hold the door
angle - "three-quarter rear view", "angled three-quarters away" and a placed
camera each drew back-on and front-on seeds and never the side - while the
Edit pass turned a pair a full half turn cleanly but kept the source's head
turn every time. So the view T2I draws reliably (a straight back view) is the
source, and the Edit pass, which keeps heads turned, makes the view where
heads ARE turned. Sunday night: she is in a coat (Mei's closer is "Different
coat."), he is half a step ahead with his face away - Danny has no face yet,
and this does not give him one. Cut out with the pack's grey-studio matte.
Output: library/_extras/<date>_shoot_lobby-couple/ (renders, sheet.jpg) and
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

STAIRS = ("a full-length picture of a young man and a young woman walking arm in arm, side by side, "
          "seen directly from behind, both backs square to the camera: we see only the backs of both "
          "heads and no part of either face, their heads tilted up a little as they look toward the "
          "top left of the frame, as if about to climb a staircase just ahead of them, late on a "
          "Sunday night: he is on the left in a dark navy bomber jacket over a plain white t-shirt, "
          "dark jeans and white sneakers, short dark hair; she is on the right holding his arm, in a "
          "long camel wool coat over a short black dress and black heels, long dark hair down her "
          "back, the plain smooth back of her coat toward the camera, one continuous panel of camel "
          "wool with no opening, lapels or buttons, mid-stride, both figures fully in frame from head "
          f"to feet, {STUDIO_BACKDROP}. Photorealistic, natural skin texture, sharp focus.")
DOOR = ("Move the camera a quarter turn around to their right side, so we now see the two of them from "
        "the side and a little behind, at an angle: they walk from the right of the frame toward the "
        "left, his right shoulder and the right side of his back toward the camera, she on his far side "
        "holding his arm, and both of them turn their heads to the left as if looking at someone across "
        "the room, so only the right edge of each face is seen. Keep their clothes, hair, heights and "
        "builds exactly the same: his navy bomber jacket, white t-shirt, dark jeans and white sneakers; "
        "her long camel coat, short black dress and black heels, with the plain back and right side of "
        "her coat toward the camera and the coat's open front, lapels and buttons on her far side, away "
        "from the camera. Keep the plain light grey studio background, the soft even lighting and the "
        "full-length framing from head to feet. Photorealistic, natural skin texture, sharp focus.")
NEGATIVE = (CAMERA_NEGATIVE + ", facing the camera, looking at the camera, three people, extra person, "
            "coat open at the back, dress showing through the back of the coat, lapels on the back of "
            "the coat, buttons on the back of the coat, cropped feet, cut off at the knees, close-up, "
            "blurry, deformed hands, extra limbs, cartoon, text, watermark, props, furniture, doorway, "
            "stairs")

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


log(f"lobby couple: {SEEDS} seeds, stairs by T2I then door by Edit -> {d}")
if DRY:
    for s in range(SEEDS):
        log(f"  would render stairs_{s}.png then door_{s}.png, then cut both out -> {CUT_DIR}")
    raise SystemExit(0)

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
rng = random.SystemRandom()
pngs: list[Path] = []
for s in range(SEEDS):
    back = d / f"stairs_{s}.png"
    if not back.is_file():
        seed = rng.randrange(1, 2**31)
        t0 = time.monotonic()
        wf = t2i_workflow(cfg, STAIRS, seed, "sourcemode/extras_lobby_couple", lora_path="",
                          negative=NEGATIVE, width=W, height=H)
        files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
        if not files:
            raise SystemExit(f"stairs_{s}: ComfyUI returned no image")
        client.fetch(files[0], back)
        log(f"  {back.name}: seed {seed}  {time.monotonic() - t0:.0f}s")
    pngs.append(back)
    front = d / f"door_{s}.png"
    if not front.is_file():
        seed = rng.randrange(1, 2**31)
        t0 = time.monotonic()
        wf, _ = build_edit_workflow(cfg, "extras", instruction=DOOR, negative=NEGATIVE,
                                    image_name=client.upload_image(back), seed=seed,
                                    render_pass="medium", filename_prefix="sourcemode/extras_lobby_couple")
        files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
        if not files:
            raise SystemExit(f"door_{s}: ComfyUI returned no image")
        client.fetch(files[0], front)
        log(f"  {front.name}: seed {seed}  {time.monotonic() - t0:.0f}s")
    pngs.append(front)

TW, TH = 300, 450
VIEWS = ("door", "stairs")
sheet = Image.new("RGB", (TW * len(VIEWS), TH * SEEDS), "black")
dr = ImageDraw.Draw(sheet)
for s in range(SEEDS):
    for c, tag in enumerate(VIEWS):
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
