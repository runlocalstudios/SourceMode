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
the right). His staging: "Shot 1, man closest to viewer, viewed partially from
the side and from behind. Looking to the left, walking. A woman is on his arm.
She is also looking to the left ... the next photo, they are walking away from
the viewer." In both views the opening of her coat faces away from the camera.

Three stages per seed, each the step the model does reliably:
  stairs  T2I on the pack's grey studio, no LoRA: backs square to the camera,
          heads up as they are about to climb. T2I holds this every seed.
  look    Qwen-Image-Edit of stairs: both heads turned left toward Mei, bodies
          as they were. The Edit pass turns heads reliably.
  door    the Multiple Angles LoRA on Qwen-Image-Edit, applied to look: the
          camera orbits to their left, which puts him nearest the camera
          walking left with her on his far arm, seen from behind and from the
          side. This LoRA exists to move the camera; prompts cannot (below).
          "45 degrees" was nearer a full profile with her hidden behind him,
          so 30 is the door view and 15 is drawn beside it.

Why not a prompt (five rounds, 2026-11-09): T2I draws a walking pair either
back-on or front-on whatever the view is called - "three-quarter rear view",
"angled three-quarters away", a placed camera, "walking away diagonally" - and
the plain Edit pass turns heads but not bodies (a quarter turn left them
back-on or facing each other). The view between back and side is a camera
move, and only the camera LoRA makes one. Sunday night: she is in a coat
(Mei's closer is "Different coat."), he is half a step ahead with his face
away - Danny has no face yet, and this does not give him one. Cut out with
the pack's grey-studio matte. Output: library/_extras/<date>_shoot_lobby-couple/
(renders, sheet.jpg) and outputs/game-assets/_extras/lobby_couple/ (png + webp
cutouts + sidecars) for Jeremy to pick from; nothing here writes into the game
repo.
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
TURN = ("Turn both of their heads to the left so they look across the room at someone there, their "
        "faces seen only in part profile from behind. Keep everything else exactly as it is: their "
        "bodies walking away from the camera, their clothes, hair, heights and builds, the plain smooth "
        "back of her coat, the plain light grey studio background, the lighting and the full-length "
        "framing from head to feet. Photorealistic, natural skin texture, sharp focus.")
# the Multiple Angles LoRA's own command grammar - the command alone, nothing appended.
# Seen on the first renders: orbiting LEFT puts him nearest the camera walking left,
# her on his far arm, which is the shot; at "45 degrees" the move is nearer a full
# profile and she vanishes behind him, so the smaller angles are drawn.
ORBIT = {"door": "Rotate the camera 30 degrees to the left.",
         "door15": "Rotate the camera 15 degrees to the left."}
ANGLES_LORA = "qwen-image-edit-2511-multiple-angles-lora.safetensors"
NEGATIVE = (CAMERA_NEGATIVE + ", facing the camera, looking at the camera, three people, extra person, "
            "coat open at the back, dress showing through the back of the coat, lapels on the back of "
            "the coat, buttons on the back of the coat, cropped feet, cut off at the knees, close-up, "
            "blurry, deformed hands, extra limbs, cartoon, text, watermark, props, furniture, doorway, "
            "stairs, top-down view, bird's eye view, rotated image, tilted frame, lying down")

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


def splice_lora(wf: dict, path: str, strength: float = 1.0) -> dict:
    """One more LoraLoaderModelOnly on the edit graph's UNet (node 161; 222 is the
    character slot and is pruned when no character LoRA is asked for)."""
    nodes = wf["nodes"] if "nodes" in wf else wf
    after = "222" if "222" in nodes else "161"
    new = "900"
    for node in nodes.values():
        for k, v in node.get("inputs", {}).items():
            if k == "model" and v == [after, 0]:
                node["inputs"][k] = [new, 0]
    nodes[new] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": [after, 0], "lora_name": path, "strength_model": float(strength)}}
    return wf


log(f"lobby couple: {SEEDS} seeds, stairs by T2I, look by Edit, door by the camera LoRA -> {d}")
if DRY:
    for s in range(SEEDS):
        log(f"  would render stairs_{s}.png, look_{s}.png, door_{s}.png and door15_{s}.png, "
            f"then cut out door, door15 and stairs -> {CUT_DIR}")
    raise SystemExit(0)

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
rng = random.SystemRandom()


def run(wf: dict, out: Path, t0: float, seed: int) -> None:
    files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
    if not files:
        raise SystemExit(f"{out.name}: ComfyUI returned no image")
    client.fetch(files[0], out)
    log(f"  {out.name}: seed {seed}  {time.monotonic() - t0:.0f}s")


def edit(src: Path, out: Path, instruction: str, lora: str = "") -> None:
    if out.is_file():
        return
    seed = rng.randrange(1, 2**31)
    t0 = time.monotonic()
    wf, _ = build_edit_workflow(cfg, "extras", instruction=instruction, negative=NEGATIVE,
                                image_name=client.upload_image(src), seed=seed, render_pass="medium",
                                filename_prefix="sourcemode/extras_lobby_couple")
    if lora:
        wf = splice_lora(wf, lora)
    run(wf, out, t0, seed)


pngs: list[Path] = []
for s in range(SEEDS):
    back = d / f"stairs_{s}.png"
    if not back.is_file():
        seed = rng.randrange(1, 2**31)
        t0 = time.monotonic()
        run(t2i_workflow(cfg, STAIRS, seed, "sourcemode/extras_lobby_couple", lora_path="",
                         negative=NEGATIVE, width=W, height=H), back, t0, seed)
    look = d / f"look_{s}.png"
    edit(back, look, TURN)
    for tag, cmd in ORBIT.items():
        out = d / f"{tag}_{s}.png"
        edit(look, out, cmd, lora=ANGLES_LORA)
        pngs.append(out)
    pngs.append(back)

TW, TH = 300, 450
VIEWS = (*ORBIT, "look", "stairs")
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
