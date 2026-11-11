"""Nude identity probe: does GNASS cost her face, and how much of it do we need?

    python scripts/video/nude_face_probe.py <character> [--arms=g50,g35,g20,none] [--seed=N]

Jeremy, 2026-11-10 evening: "pick a few nude shots and see what you can do to
improve the facial accuracy ... stick to her naked body and work on improving so
that her face looks just like it looks in the pics without nudity". The hotel
story's nude frames scored 0.37-0.64 against 0.49-0.78 clothed with GNASS at
0.5 under her LoRA.

Three nude poses (no touching) x the arms, one fixed seed per pose so the arms
differ only in the nudity LoRA: GNASS at 0.5 / 0.35 / 0.2 / none at all. Output
library/<character>/<date>_video_nude-face-probe/<arm>__<shot>__s<seed>.png,
a contact sheet with the face score on each tile, and judge set
probe_<character>_nude_face.
"""

import random
import sys
import time
from pathlib import Path

import cv2
from PIL import Image, ImageDraw

from sourcemode.assets.appearance import clause, negative as appearance_negative
from sourcemode.assets.judge import make_set
from sourcemode.assets.looks import reference
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.render import t2i_workflow
from sourcemode.config import load_config, outputs_dir
from sourcemode.gates.identity import _get_face_app, cosine, embed_image
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
CHAR = ARGS[0].lower()
ARMS = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--arms=")), ["g50", "g35", "g20", "none"])
SEED = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--seed=")), None)
GNASS = "nsfw\\qimage2512_gnass.safetensors"
STRENGTH = {"g50": 0.5, "g35": 0.35, "g20": 0.2, "none": 0.0}
W, H = 1024, 1536

NUDE = ("completely naked, natural makeup, her bare breasts, bare stomach and bare vagina showing, wearing "
        "nothing but her purple velour opera gloves, her narrow purple velour choker, silver hoop earrings "
        "and purple velour pumps")
ROOM = ("Inside a luxury hotel suite at night, warm lamplight, beige walls with walnut trim, a king bed with a "
        "white duvet on the left, a floor-to-ceiling window full of city lights at night on the right, a low "
        "oatmeal upholstered ottoman in the middle of the room, a small round walnut side table with a silver "
        "champagne bucket and two champagne flutes beside the window, a walnut entry door at the far end")
POV = "point-of-view photo, the camera at seated eye level"
ON_BED = "the black clutch and a long white fur coat lying on the bed"
SHOTS = {
    "stand": f"{POV}: a full-length photo, standing beside the bed facing the camera with her legs spread wide "
             f"apart in a wide stance, {NUDE}, hands on her hips, chest out, a teasing smile, eyes on the camera, "
             f"{ON_BED}",
    "sit": f"{POV}: a full-length photo, sitting on the edge of the bed facing the camera, {NUDE}, knees "
           f"together and hands resting on her knees, lips parted in a teasing smile, eyes on the camera, {ON_BED}",
    "hair": f"{POV}: three-quarter length, standing facing the camera with her legs spread, {NUDE}, both hands "
            f"gathering all of her long hair up behind her head in a high ponytail, elbows up, chin raised and "
            f"chest out, eyes on the camera, lips parted, {ON_BED}",
}
NEG = ("different person, different face, changed hair, extra hands, extra limbs, deformed hands, blurry, low "
       "quality, cartoon, anime, watermark, text, a second woman, the man's face, his face, armchair, sofa, "
       "couch, a man, suit jacket, another person, tongue out, childlike, child, underage, dress, mini dress, "
       "velour dress, clothes on her, bra, panties, underwear, covered, censored, deformed genitals, tears, "
       "crying, toothy grin, blush circles, pink cheeks, heavy blush, bare arms, bare hands, boots, bare feet")

cfg = load_config()
lora = resolve_lora(cfg, CHAR)
face_ref = reference(CHAR)
d = find_set(cfg, CHAR, "video", "nude-face-probe", create=True)
write_set_json(d, character=CHAR, kind="video", name="nude-face-probe", date=d.name[:10])
trig = lora.get("trigger") or CHAR
neg = NEG + ((", " + appearance_negative(CHAR)) if appearance_negative(CHAR) else "")


def prompt(text: str) -> str:
    return f"{trig}, {clause(CHAR)}, her hair worn loose, {text}. {ROOM}. Photorealistic, natural skin texture, sharp focus."


client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
ref_emb = embed_image(face_ref)
app = _get_face_app()
rng = random.SystemRandom()
seeds = {k: (SEED or rng.randrange(1, 2**31)) for k in SHOTS}
results = []
for shot, text in SHOTS.items():
    for arm in ARMS:
        s = STRENGTH[arm]
        out = d / f"{arm}__{shot}__s{seeds[shot]}.png"
        t0 = time.monotonic()
        wf = t2i_workflow(cfg, prompt(text), seeds[shot], f"sourcemode/{CHAR}_nudeprobe", lora_path=lora["path"],
                          negative=neg, width=W, height=H, extra_loras=((GNASS, s),) if s else ())
        files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
        if not files:
            print(f"{arm} {shot}: no image", flush=True)
            continue
        client.fetch(files[0], out)
        out.with_suffix(".txt").write_text(prompt(text), encoding="utf-8")
        img = cv2.imread(str(out))
        faces = app.get(img) if img is not None else []
        face = age = None
        if faces:
            f = max(faces, key=lambda x: float(cosine(ref_emb, x.normed_embedding)))
            face = round(float(cosine(ref_emb, f.normed_embedding)), 3)
            age = int(round(float(f.age)))
        results.append((arm, shot, out, face, age))
        print(f"{arm} {shot}: face {face} age {age}  {time.monotonic() - t0:.0f}s", flush=True)

TW, TH = 300, 450
sheet = Image.new("RGB", (TW * len(ARMS), TH * len(SHOTS)), "black")
dr = ImageDraw.Draw(sheet)
for arm, shot, out, face, age in results:
    x, y = ARMS.index(arm) * TW, list(SHOTS).index(shot) * TH
    im = Image.open(out).convert("RGB")
    im.thumbnail((TW, TH))
    sheet.paste(im, (x, y))
    dr.rectangle([x, y, x + TW, y + 18], fill="black")
    dr.text((x + 4, y + 3), f"{arm} {shot} face {face} age {age}", fill="yellow")
sheet.save(d / "sheet.jpg", quality=90)
make_set(outputs_dir(cfg) / "judge", f"probe_{CHAR}_nude_face", f"{CHAR.title()} - nude face probe",
         [{"id": o.stem, "path": o, "arm": arm, "group": shot} for arm, shot, o, _, _ in results],
         question="Is this her? K = yes, X = no.", priority=5, meta={"character": CHAR, "renders_dir": d})
print("PROBEDONE", flush=True)
