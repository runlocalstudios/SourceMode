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
  door    just inside the street door, walking diagonally away from the player
          toward the back left - a rear three-quarter view from their right -
          both heads turned left toward Mei
  stairs  at the foot of the stairs, backs square to the camera, heads up as
          they are about to climb
Both by T2I on the pack's grey studio, no LoRA, with the same hair and clothes
named in both prompts so the seeds pair up; he picks a matching pair. In both
views the opening of her coat faces away from the camera.

Four rounds, 2026-11-09: "walking toward the left of the frame" is a sideways
walk, which T2I snaps to full back or full front whatever the view is called
("three-quarter rear view", "angled three-quarters away", a placed camera);
the Edit pass turned a pair a half turn cleanly but kept the source's head
turn, and a quarter turn left the bodies back-on or facing each other. The
door view is them walking AWAY diagonally, and that is the word that places
the camera. Sunday night: she is in a coat (Mei's closer is "Different
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
# Fourth round: "walking toward the left of the frame" is a sideways walk, which T2I
# snaps to full back or full front. The shot is them walking diagonally AWAY from the
# player toward the back left - a rear three-quarter view - so that is what it says.
DOOR = ("a full-length picture of a young man and a young woman walking arm in arm, side by side, "
        "walking away from the camera diagonally toward the back left of the frame, seen from behind "
        "and from their right in a rear three-quarter view, so we see their backs and the right side of "
        "each body, both of their heads turned to the left as if looking at someone across the room, "
        "only the right edge of each face visible, late on a Sunday night: he is nearest the camera and "
        "half a step ahead, in a dark navy bomber jacket over a plain white t-shirt, dark jeans and white "
        "sneakers, short dark hair; she holds his arm on his far side, in a long camel wool coat over a "
        "short black dress and black heels, long dark hair down her back, the plain smooth back of her "
        "coat toward the camera, the coat's open front, lapels and buttons on her far side facing away "
        "from the camera, mid-stride, both figures fully in frame from head to feet, "
        f"{STUDIO_BACKDROP}. Photorealistic, natural skin texture, sharp focus.")
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


log(f"lobby couple: {SEEDS} seeds, door and stairs by T2I -> {d}")
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
        wf = t2i_workflow(cfg, DOOR, seed, "sourcemode/extras_lobby_couple", lora_path="",
                          negative=NEGATIVE, width=W, height=H)
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
