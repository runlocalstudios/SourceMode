"""Can the edit path draw the office story's POV acts? One plate, a chain of edits.

    python scripts/video/pov_edit_probe.py <character> <plate.png> [--arms=a,b] [--keys=a,b] [--seeds=N] [--dry-run]

Small batches: Jeremy, 2026-11-10, "Don't run tons of photos. Run like 4 and see if what
you created works or not" - one seed, two arms, the chain to the first act, then look.

Jeremy, 2026-11-10: "If generating the assets from scratch is too problematic
with the 2 characters, then I suggest you feel free to start with a photo more
like the office POV ones and then edit to get what we're looking for ... The
thing that's most important here is the facial identity, hair, and body of the
girl. Second most important is the reality of the photo shoots."

Text-to-image with the GNASS LoRA at the 0.6 cap drew the standing-man handjob
and blowjob shots with the penis attached nowhere (j1351): the plate path is
the alternative, because Qwen-Image-Edit keeps the plate's face. This renders
the chain on an office POV plate of her between his knees:

  topless  her blazer and bra gone, skirt red (the desk set's colours)
  free     his shorts gone, his erect penis up between his thighs, her hand on it
  tip      the head between her lips           (from `free`)
  deep     the shaft deep in her mouth         (from `free`)
  hands    both hands stroking it              (from `free`)

Arms are the two NSFW edit LoRAs at 0.8 spliced after her LoRA, as
nsfw_lora_test.py did on 2026-11-09 (mcnl_char scored 0.63-0.65, sexgod_char
0.50-0.67 on nude edits of her):
  mcnl     MCNL NSFW edit LoRA + her LoRA
  sexgod   SexGod nudes 2511 edit LoRA + her LoRA
  allin    "Qwen Image Edit 2511 All included" act LoRA + her LoRA (its words: fellatio, handjob, throating)
  couples  SexGod Couples Nudity (Edit 2511) + her LoRA

Output: library/<character>/<date>_video_pov-edit-probe/<arm>__<key>__s<seed>.png,
keys.json (face score and age per render) and sheet.jpg (rows = arm x seed,
columns = plate, topless, free, tip, deep, hands).
"""

import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
from PIL import Image, ImageDraw

from sourcemode.assets.looks import reference
from sourcemode.assets.lora import resolve_lora
from sourcemode.config import load_config
from sourcemode.gates.identity import _get_face_app, cosine, embed_image
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.passes import build_edit_workflow

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
if len(ARGS) != 2:
    raise SystemExit(__doc__)
CHAR, PLATE = ARGS[0].lower(), Path(ARGS[1])
if not PLATE.is_file():
    raise SystemExit(f"no plate {PLATE}")
SEEDS = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--seeds=")), 2))
ONLY_ARMS = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--arms=")), None)
ONLY_KEYS = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--keys=")), None)

NSFW = "nsfw\\"
ARMS = {"mcnl": NSFW + "qedit_mcnl_nsfw.safetensors", "sexgod": NSFW + "qedit_sexgod_nudes_2511.safetensors",
        # act-trained Edit-2511 LoRAs found 2026-11-10 (Hugging Face mirrors): the "all included" one lists
        # fellatio, handjob, throating, semen, anal among its words; SexGod Couples is two-person nudity
        "allin": NSFW + "qedit2511_all_included_v2.safetensors",
        "couples": NSFW + "qedit2511_sexgod_couples_v1.safetensors"}
if ONLY_ARMS:
    ARMS = {k: v for k, v in ARMS.items() if k in ONLY_ARMS}
STRENGTH = 0.8

COCK = "his thick erect penis"
# key -> (parent key or None, instruction). Everything else in the picture stays as it is.
CHAIN: dict[str, tuple[str | None, str]] = {
    "topless": (None, "Remove her blazer and her bra so she is topless with her bare breasts showing, and "
                      "change her skirt to red. Keep her face, her hair, her pose, the room and the man's "
                      "legs exactly as they are."),
    "free": ("topless", f"Remove the man's navy shorts. {COCK} stands up from between his thighs at the bottom "
                        f"of the frame, and she wraps one hand around it, looking up into the camera. Keep her "
                        f"face, her hair, her bare breasts, the room and the man's legs exactly as they are."),
    "tip": ("free", f"She leans in and takes just the head of {COCK} between her lips, her eyes looking up "
                    f"into the camera. Keep her face, her hair, her bare breasts and the room as they are."),
    "deep": ("free", f"Deepthroat: she takes {COCK} all the way into her mouth and throat, her lips pressed to its "
                     f"base, her nose touching his belly, her cheeks hollowed, her eyes heavy-lidded looking up "
                     f"into the camera and loving it. Keep her face, her hair, her bare breasts and the room as "
                     f"they are."),
    "hands": ("free", f"She strokes {COCK} with both of her hands wrapped around it one above the other, "
                      f"looking up into the camera with a hungry smile. Keep her face, her hair, her bare "
                      f"breasts and the room as they are."),
    # round 2 (2026-11-10): the chain to `free` and `tip` held her face at 0.68-0.70 and 0.48-0.54; these
    # continue from `free`
    "spit": ("free", f"She holds {COCK} in one hand and spits onto the head of it, a string of saliva running "
                     f"from her lips to the penis, her eyes on the camera. Keep her face, her hair, her bare "
                     f"breasts and the room as they are."),
    "balls": ("free", f"She strokes the shaft of {COCK} with one hand while her other hand cups and gently "
                      f"squeezes his balls, looking up into the camera and loving it. Keep her face, her hair, "
                      f"her bare breasts and the room as they are."),
    "lick": ("free", f"Her tongue is out, licking the head of {COCK}, one hand holding it at the base, her eyes "
                     f"heavy-lidded looking up into the camera. Keep her face, her hair, her bare breasts and "
                     f"the room as they are."),
    # round 3 (2026-11-10): spit worked; hands drew one hand, balls drew none, deep stayed at the tip and
    # zoomed in; every step ballooned the penis. The LoRA's own words (throating, handjob) and plainer
    # geometry this time, and a size clause on a second `free`.
    "free2": ("topless", "Remove the man's navy shorts. His erect penis, proportionate to his body and of "
                         "realistic size, stands up from between his thighs at the bottom of the frame, and she "
                         "wraps one hand around it, looking up into the camera. Keep her face, her hair, her bare "
                         "breasts, the room, the framing and the man's legs exactly as they are."),
    "deep2": ("free", "throating: she has half of the shaft of his erect penis inside her mouth, her lips "
                      "stretched around the middle of the shaft, her cheeks hollowed, her eyes heavy-lidded "
                      "looking up into the camera. Keep her face, her hair, her bare breasts, the room and the "
                      "framing exactly as they are, do not zoom in."),
    "hands2": ("free", "handjob: two hands - both of her hands grip the shaft of his erect penis, stacked one "
                       "above the other, the head showing above her top hand, looking up into the camera with "
                       "a hungry smile. Keep her face, her hair, her bare breasts and the room as they are."),
    "balls2": ("free", "handjob: one of her hands strokes the shaft of his erect penis while her other hand "
                       "cups his balls, which hang visible below the shaft, looking up into the camera and "
                       "loving it. Keep her face, her hair, her bare breasts and the room as they are."),
    # round 4 (2026-11-10): free2 (realistic size) and hands2 (two hands stacked) worked; "throating" drew a
    # second penis head at her lips with his still at his lap, because her face is a foot from his lap in
    # this plate; balls twice not drawn. So deep moves her down to his lap, or starts from the text-to-image
    # tip render where her mouth is already on it; balls get the plain word once more, then stop.
    "deep3": ("free2", "She bends down with her face at his lap and takes his erect penis all the way into her "
                       "mouth, her lips at the base of the shaft and her nose in his pubic hair, her eyes "
                       "heavy-lidded looking up at the camera. There is only one penis. Keep her hair, her "
                       "bare breasts, the room and the framing as they are."),
    "balls3": ("free2", "She holds his erect penis up with one hand so his testicles are visible below it, and "
                        "cups his testicles in her other hand, looking up into the camera. Keep her face, her "
                        "hair, her bare breasts and the room as they are."),
    "deep_tip": (None, "She pushes her head down, taking the whole shaft of his erect penis into her mouth, her "
                       "lips at the base of the shaft and her nose in his pubic hair, her eyes heavy-lidded "
                       "looking up at the camera. Keep her face, her hair, the room and the framing as they are."),
}
if ONLY_KEYS:
    CHAIN = {k: v for k, v in CHAIN.items() if k in ONLY_KEYS}
NEGATIVE = ("different person, different face, changed hair, bra, blazer, clothes on her chest, condom, "
            "deformed genitals, deformed hands, extra hands, extra limbs, blurry, low quality, cartoon, "
            "watermark, text, tears, crying, watering eyes, childlike, child, underage")

cfg = load_config()
lora = resolve_lora(cfg, CHAR)
if not lora:
    raise SystemExit(f"{CHAR} has no locked LoRA")
face_ref = reference(CHAR)
if face_ref is None:
    raise SystemExit(f"{CHAR} has no face reference to score against")
d = find_set(cfg, CHAR, "video", "pov-edit-probe", create=True)
write_set_json(d, character=CHAR, kind="video", name="pov-edit-probe", date=d.name[:10], plate=str(PLATE))
LOG = d / "run.log"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def splice_lora(wf: dict, after: str, path: str, strength: float) -> dict:
    """One more LoraLoaderModelOnly between node `after` and whatever read its model
    (nsfw_lora_test.splice_lora)."""
    nodes = wf["nodes"] if "nodes" in wf else wf
    new = "900"
    for node in nodes.values():
        for k, v in node.get("inputs", {}).items():
            if k == "model" and v == [after, 0]:
                node["inputs"][k] = [new, 0]
    nodes[new] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": [after, 0], "lora_name": path, "strength_model": float(strength)}}
    return wf


def edit_wf(instr: str, seed: int, image: str, nsfw: str) -> dict:
    wf, _ = build_edit_workflow(cfg, CHAR, instruction=instr, negative=NEGATIVE, image_name=image,
                                image_lora=lora["path"], seed=seed, render_pass="medium",
                                filename_prefix=f"sourcemode/{CHAR}_povedit")
    nodes = wf["nodes"] if "nodes" in wf else wf
    after = "222" if "222" in nodes else "161"
    return splice_lora(wf, after, nsfw, STRENGTH)


plan = [(arm, key, s) for arm in ARMS for s in range(SEEDS) for key in CHAIN]
log(f"{CHAR}: {len(plan)} edits from {PLATE.name} -> {d}")
if DRY:
    for p in plan:
        log(f"  would render {p}")
    raise SystemExit(0)

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
ref_emb = embed_image(face_ref)
app = _get_face_app()
rng = random.SystemRandom()
keys = json.loads((d / "keys.json").read_text(encoding="utf-8")) if (d / "keys.json").is_file() else {}
uploaded: dict[str, str] = {}


def score(p: Path) -> tuple[float | None, int | None]:
    """Her face (the one closest to her reference) against the reference, and its age guess."""
    if app is None or ref_emb is None:
        return None, None
    img = cv2.imread(str(p))
    faces = app.get(img) if img is not None else []
    if not faces:
        return None, None
    f = max(faces, key=lambda x: float(cosine(ref_emb, x.normed_embedding)))
    return (round(float(cosine(ref_emb, f.normed_embedding)), 3),
            int(round(float(f.age))) if getattr(f, "age", None) is not None else None)


def upload(p: Path) -> str:
    if str(p) not in uploaded:
        uploaded[str(p)] = client.upload_image(p)
    return uploaded[str(p)]


keys.setdefault("_plate", {"path": str(PLATE), "face": score(PLATE)[0]})
for arm, key, s in plan:
    out = d / f"{arm}__{key}__s{s}.png"
    if out.is_file():
        continue
    parent, instr = CHAIN[key]
    src = PLATE if parent is None else d / f"{arm}__{parent}__s{s}.png"
    if not src.is_file():
        log(f"  {out.name}: no {parent} to edit from")
        continue
    seed = rng.randrange(1, 2**31)
    t0 = time.monotonic()
    files = client.outputs(client.wait(client.submit(edit_wf(instr, seed, upload(src), ARMS[arm])), timeout_s=3600))
    if not files:
        raise SystemExit(f"{out.name}: ComfyUI returned no image")
    client.fetch(files[0], out)
    face, age = score(out)
    keys[out.stem] = {"arm": arm, "key": key, "seed": seed, "from": src.name, "face": face, "age": age}
    (d / "keys.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    log(f"  {out.name}: face {face}  age {age}  {time.monotonic() - t0:.0f}s")

# the sheet: one row per arm x seed, the plate first
TW, TH = 300, 450
cols = 1 + len(CHAIN)
rows = [(arm, s) for arm in ARMS for s in range(SEEDS)]
sheet = Image.new("RGB", (TW * cols, TH * len(rows)), "black")
dr = ImageDraw.Draw(sheet)
for r, (arm, s) in enumerate(rows):
    tiles = [("plate", PLATE)] + [(k, d / f"{arm}__{k}__s{s}.png") for k in CHAIN]
    for c, (k, p) in enumerate(tiles):
        if not p.is_file():
            continue
        im = Image.open(p).convert("RGB")
        im.thumbnail((TW, TH))
        sheet.paste(im, (c * TW, r * TH))
        rec = keys.get(p.stem, {})
        dr.rectangle([c * TW, r * TH, c * TW + TW, r * TH + 18], fill="black")
        dr.text((c * TW + 4, r * TH + 3), f"{arm} s{s} {k} / face {rec.get('face')} age {rec.get('age')}",
                fill="yellow")
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")
log("PROBEDONE")
