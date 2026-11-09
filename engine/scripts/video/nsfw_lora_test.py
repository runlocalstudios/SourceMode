"""Which nudity LoRA keeps HER: undressed stills from one clothed photo, every
arm side by side, each scored against her face reference.

    python scripts/video/nsfw_lora_test.py <character> <photo> [--staged] [--arms=a,b] [--dry-run]

Jeremy, 2026-11-09, on the fiona try-on keys: "a complete disaster ... it
completely changed her identity and also looked horrible and blurry". The keys
were eight Wan I2V hops, each started from the last one's final frame, with a
Wan nudity LoRA on every clip - identity fell 0.70 -> 0.06 down the chain. His
ask: find nudity LoRAs for breasts and the lower body, test them WITH the
character LoRAs, on fiona and on bianca.

Her character LoRA is a Qwen-Image LoRA; Wan cannot load it. So she is made
naked in the STILL, where her LoRA (or her own photo) carries identity, and the
video only moves between stills (FLF2V) - never invents her body over 80 frames.

Arms (two keys - topless, nude - two seeds each):
  edit_mcnl        Qwen-Image-Edit 2511 on her photo + MCNL NSFW (edit LoRA)
  edit_mcnl_char   the same + her locked T2I LoRA in the identity slot
  edit_sexgod      Qwen-Image-Edit 2511 on her photo + SexGod female nudes 2511
  edit_sexgod_char the same + her locked T2I LoRA
  t2i_gnass        Qwen-Image 2512 text-to-image: her LoRA + GNASS nudes (0.6)

Edit keeps the photo's face, room and light; T2I keeps only what her LoRA
knows. Output: library/<character>/<date>_video_nsfw-lora-test/, keys.json and
sheet.jpg (rows = arm, columns = key x seed, each with its face score).
InsightFace scores are QC only - his eye is final.
"""

import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from sourcemode.assets.appearance import clause, negative as appearance_negative
from sourcemode.assets.looks import reference
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.render import t2i_workflow
from sourcemode.config import load_config
from sourcemode.gates.identity import cosine, embed_image
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.passes import build_edit_workflow

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
if len(ARGS) != 2:
    raise SystemExit(__doc__)
CHAR, PHOTO = ARGS[0].lower(), Path(ARGS[1])
if not PHOTO.is_file():
    raise SystemExit(f"no photo at {PHOTO}")

NSFW = "nsfw\\"  # ComfyUI on Windows lists subfolder LoRAs with a backslash
MCNL, SEXGOD, GNASS = NSFW + "qedit_mcnl_nsfw.safetensors", NSFW + "qedit_sexgod_nudes_2511.safetensors", \
    NSFW + "qimage2512_gnass.safetensors"
ARMS = {
    "edit_mcnl": ("edit", MCNL, 0.8, False),
    "edit_mcnl_char": ("edit", MCNL, 0.8, True),
    "edit_sexgod": ("edit", SEXGOD, 0.8, False),
    "edit_sexgod_char": ("edit", SEXGOD, 0.8, True),
    "t2i_gnass": ("t2i", GNASS, 0.6, True),
}
KEEP = ("Keep her face, her hair, her body shape, her pose, her shoes, the room, the camera and the "
        "lighting exactly as they are. Photorealistic, natural skin texture, sharp focus.")
EDIT = {
    "topless": ("Pull her top down to her waist: she is topless, her bare natural breasts and nipples "
                "fully visible, the rest of her outfit still on. " + KEEP),
    "nude": ("Remove all of her clothing except her shoes: she is completely naked, her bare natural "
             "breasts and nipples visible, her smooth shaved pubic area visible, no underwear. " + KEEP),
}
T2I = {
    "topless": "topless, her bare natural breasts and nipples visible, her outfit pulled down to her waist",
    "nude": "completely naked, her bare natural breasts and nipples visible, her smooth shaved pubic area visible",
}
# --staged: Jeremy, 2026-11-09, on the first keys - "half the dress just disappeared.
# It's not like she is sensually getting undressed." Each key now shows the garment
# moved, not erased, so the leg between two keys is her pulling it down.
STAGED = {
    "straps": ("Slip the straps of her dress off her shoulders: the neckline has slid down to just above "
               "her nipples, the dress still on. " + KEEP),
    "topless": ("Pull the top of her dress down: the fabric is gathered and bunched around her waist, the "
                "straps hanging loose at her sides, she is topless, her bare natural breasts and nipples "
                "fully visible, the rest of the dress still on her hips. " + KEEP),
    # "bunched at her upper thighs" alone read as a hiked-up hem (bianca, both seeds):
    # say where the dress is NOT as well as where it is
    "hips": ("Pull the whole dress down off her body to her thighs: the dress is now only a band of bunched "
             "fabric around her upper thighs, below her hips, with nothing on her shoulders, chest or "
             "stomach. Above the bunched fabric she is naked: her bare natural breasts and nipples, her "
             "stomach and her smooth shaved pubic area all visible, no underwear. " + KEEP),
    "nude": ("Her dress lies crumpled on the floor around her ankles: she is completely naked, her bare "
             "natural breasts and nipples visible, her smooth shaved pubic area visible, no underwear. "
             + KEEP),
}
if "--staged" in sys.argv:
    EDIT = STAGED
ONLY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--arms=")), None)
if ONLY:
    ARMS = {k: v for k, v in ARMS.items() if k in ONLY}
if "--staged" in sys.argv and any(v[0] == "t2i" for v in ARMS.values()):
    raise SystemExit("--staged edits her photo; pass --arms= with edit arms only")
NEGATIVE = ("different person, different face, changed hair, clothes, underwear, bra, panties, pubic hair, "
            "deformed, distorted hands, extra limbs, blurry, low quality, cartoon, watermark, text")
SEEDS = 2

cfg = load_config()
lora = resolve_lora(cfg, CHAR)
if not lora:
    raise SystemExit(f"{CHAR} has no locked LoRA")
face_ref = reference(CHAR)
if face_ref is None:
    raise SystemExit(f"{CHAR} has no face reference to score against")
SET = "nsfw-undress-keys" if "--staged" in sys.argv else "nsfw-lora-test"
d = find_set(cfg, CHAR, "video", SET, create=True)
write_set_json(d, character=CHAR, kind="video", name=SET, date=d.name[:10])
LOG = d / "run.log"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def splice_lora(wf: dict, after: str, path: str, strength: float) -> dict:
    """One more LoraLoaderModelOnly between node `after` and whatever read its model."""
    nodes = wf["nodes"] if "nodes" in wf else wf
    new = "900"
    for node in nodes.values():
        for k, v in node.get("inputs", {}).items():
            if k == "model" and v == [after, 0]:
                node["inputs"][k] = [new, 0]
    nodes[new] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": [after, 0], "lora_name": path, "strength_model": float(strength)}}
    return wf


def edit_wf(instr: str, seed: int, image: str, nsfw: str, strength: float, with_char: bool) -> dict:
    wf, _ = build_edit_workflow(cfg, CHAR, instruction=instr, negative=NEGATIVE, image_name=image,
                                image_lora=lora["path"] if with_char else "", seed=seed,
                                render_pass="medium", filename_prefix=f"sourcemode/{CHAR}_nsfwtest")
    nodes = wf["nodes"] if "nodes" in wf else wf
    # her LoRA sits in 222 when asked for; pruned otherwise, so splice after the UNet
    after = "222" if "222" in nodes else "161"
    return splice_lora(wf, after, nsfw, strength)


def t2i_wf(key: str, seed: int, nsfw: str, strength: float) -> dict:
    trig = lora.get("trigger") or CHAR
    prompt = (f"{trig}, {clause(CHAR)}, a full-length portrait picture, standing facing the camera in a softly "
              f"lit bedroom, looking at the camera with a soft smile, {T2I[key]}. Photorealistic, natural skin "
              f"texture, sharp focus.")
    return t2i_workflow(cfg, prompt, seed, f"sourcemode/{CHAR}_nsfwtest", lora_path=lora["path"],
                        negative=NEGATIVE + ", " + (appearance_negative(CHAR) or ""),
                        extra_loras=((nsfw, strength),))


plan = [(arm, key, s) for arm in ARMS for key in EDIT for s in range(SEEDS)]
log(f"{CHAR}: {len(plan)} stills from {PHOTO.name} -> {d}")
if DRY:
    for p in plan:
        log(f"  would render {p}")
    raise SystemExit(0)

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
photo_name = client.upload_image(PHOTO)
ref_emb = embed_image(face_ref)
rng = random.SystemRandom()
keys = json.loads((d / "keys.json").read_text(encoding="utf-8")) if (d / "keys.json").is_file() else {}


def score(p: Path) -> float | None:
    e = embed_image(p)
    return round(float(cosine(ref_emb, e)), 3) if e is not None and ref_emb is not None else None


keys.setdefault("_photo", {"path": str(PHOTO), "face": score(PHOTO)})
for arm, key, s in plan:
    out = d / f"{arm}__{key}__{s}.png"
    if out.is_file():
        continue
    kind, nsfw, strength, with_char = ARMS[arm]
    seed = rng.randrange(1, 2**31)
    t0 = time.monotonic()
    wf = (edit_wf(EDIT[key], seed, photo_name, nsfw, strength, with_char) if kind == "edit"
          else t2i_wf(key, seed, nsfw, strength))
    files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
    if not files:
        raise SystemExit(f"{arm}/{key}/{s}: ComfyUI returned no image")
    client.fetch(files[0], out)
    keys[out.stem] = {"arm": arm, "key": key, "seed": seed, "lora": nsfw, "strength": strength,
                      "char_lora": with_char, "face": score(out)}
    (d / "keys.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    log(f"  {out.name}: face {keys[out.stem]['face']}  {time.monotonic() - t0:.0f}s")

# the sheet: photo first, then one row per arm
W, H = 300, 450
cols = 1 + len(EDIT) * SEEDS
sheet = Image.new("RGB", (W * cols, H * len(ARMS)), "black")
dr = ImageDraw.Draw(sheet)
for r, arm in enumerate(ARMS):
    tiles = [("photo", PHOTO, keys["_photo"]["face"])] + [
        (f"{key} s{s}", d / f"{arm}__{key}__{s}.png", keys.get(f"{arm}__{key}__{s}", {}).get("face"))
        for key in EDIT for s in range(SEEDS)]
    for c, (label, p, f) in enumerate(tiles):
        im = Image.open(p).convert("RGB")
        im.thumbnail((W, H))
        sheet.paste(im, (c * W, r * H))
        dr.rectangle([c * W, r * H, c * W + W, r * H + 18], fill="black")
        dr.text((c * W + 4, r * H + 3), f"{arm} / {label} / face {f}", fill="yellow")
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")
log("KEYSDONE")
