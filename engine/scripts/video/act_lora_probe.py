"""Which text-to-image sex LoRA draws the office story's POV and facing-him acts?

    python scripts/video/act_lora_probe.py <character> [--arms=a,b] [--shots=a,b] [--seeds=N] [--dry-run]

Small batches: Jeremy, 2026-11-10, "Don't run tons of photos. Run like 4 and see if what
you created works or not" - so one seed, two arms, two shots, then look.

Jeremy, 2026-11-10: "Sometimes you need specific LORAs for each sex act, have
you researched that." GNASS (s3x_2512_qwen, no trigger words) at the 0.6 cap
attached the penis nowhere on j1351's handjob and blowjob shots. Found the same
day on Hugging Face mirrors, for Qwen-Image 2512:

  qwen4play    QWEN 4 PLAY 2512 v2 by DR34MSC4PE - the all-in-one with position
               triggers: pov, bl0wj0b, c0wg1rl, r3v3rs3_c0wg1rl, m15510n4ry,
               d0gg13; the author runs it at 1.0 and says penises are hit or miss
  anatomy      Qwen-Image-2512 Penis LoRA v2 (+blowjob, +cumshot) on the POV shots,
               qwen_2512_pussy_anus_v2 on the cowgirl and anal shots
  q4p_anatomy  QWEN 4 PLAY at 1.0 with that anatomy LoRA spliced after it at 0.8
  gnass        s3x_2512_qwen as the control, at 0.6 - j1351's facing-him renders
               held her face and the pose but put the penis between her thighs
               attached to nothing (Jeremy: "the penis isn't really in her properly")

Six shots, the story's own wording: his pants freed, one-hand stroke, the tip
between her lips, deep, cowgirl facing him deep, anal facing him deep. Several
seeds each, her face (closest to her reference) and age guess logged.

The act LoRA is spliced after her LoRA at the author's strength. That is above
the shoot composition cap (0.6 for a second LoRA) on purpose and for this probe
only: the cap protects identity in production shoots, and the probe exists to
measure what the cap costs against what the act needs. The face score says.

Output: library/<character>/<date>_video_act-lora-probe/<arm>__<shot>__s<seed>.png,
shots.json and sheet.jpg (rows = arm x seed, columns = shot).
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
from sourcemode.assets.shoots import OFFICE_IN
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
ONLY_SHOTS = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--shots=")), None)
TAG = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--tag=")), "")   # round name in the file name
W, H = 1024, 1536

NSFW = "nsfw\\"
# arm -> (lora file, strength, trigger words put first in the prompt)
Q4P, PENIS, PUSSY, GNASS = (NSFW + "qimage2512_qwen4play_v2.safetensors", NSFW + "qimage2512_penis_v2.safetensors",
                            NSFW + "qimage2512_pussy_anus_v2.safetensors", NSFW + "qimage2512_gnass.safetensors")
# arm -> (first lora, strength, trigger words put first in the prompt, second lora or None, its strength)
ARMS: dict[str, tuple[str, float, str, str | None, float]] = {
    "qwen4play": (Q4P, 1.0, "pov, ", None, 0.0),
    "anatomy": (PENIS, 1.0, "", None, 0.0),          # the Penis LoRA on his shots, pussy/anus on hers
    "q4p_anatomy": (Q4P, 1.0, "pov, ", PENIS, 0.8),  # the all-rounder plus the anatomy LoRA
    "gnass": (GNASS, 0.6, "", None, 0.0),
}
SEX_SHOTS = ("cowgirl", "anal")   # the anatomy LoRA for these is the pussy/anus one, not the penis one
if ONLY_ARMS:
    ARMS = {k: v for k, v in ARMS.items() if k in ONLY_ARMS}

# the story's continuity and wording (office_story.py)
HAIR = "her hair worn down with wavy curls throughout"
TOPLESS = ("topless with her bare breasts showing, wearing only the tight red pencil mini skirt and sheer "
           "black stockings")
SKIRT_UP = ("topless with her bare breasts showing, her red mini skirt pushed up around her waist, her sheer "
            "black stockings still on, otherwise naked")
HIM = "a fit man in a white dress shirt with the sleeves rolled up, naked from the waist down"
COCK = "his thick erect penis"
PHOTOG = "picture by a photographer shooting the set"
RUG = "on the cream wool rug"
POV_SEAT = ("close point-of-view photo looking down from the eyes of a man sitting in the big leather office "
            "chair with his knees spread, his own thighs along both sides of the bottom of the frame, his face "
            "out of frame")
TROUSERS_DOWN = "he is naked from the waist down, his bare thighs spread"
KNEEL_POV = "she kneels on the cream wool rug right between his spread knees, close, facing the camera"
COCK_POV = "his thick erect penis rising from between his bare thighs at the bottom of the frame"

# shot -> (qwen4play trigger, body)
SHOTS: dict[str, tuple[str, str]] = {
    "release": ("", f"{POV_SEAT}, {KNEEL_POV}, {TOPLESS}, her hands pulling his black boxer briefs down his thighs "
                    f"as {COCK} springs up right in front of her face, her eyes wide, grinning up at the camera"),
    "stroke": ("", f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, stroking {COCK_POV} with one hand, the "
                   f"shaft glistening with saliva, looking up into the camera"),
    "tip": ("bl0wj0b, ", f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, just the head of {COCK_POV} "
                         f"between her lips, her lips closed around the tip only, her eyes looking up into the "
                         f"camera"),
    "deep": ("bl0wj0b, ", f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, deepthroat: {COCK_POV} all the "
                          f"way inside her mouth and throat, her lips pressed to its base, her nose touching his "
                          f"belly, her cheeks hollowed, her eyes heavy-lidded with pleasure looking up into the camera, loving it"),
    "cowgirl": ("c0wg1rl, ", f"{PHOTOG} from beside his head: {HIM} lies on his back {RUG}, she squats over his "
                             f"hips facing him, feet planted flat on the rug, knees spread wide, {SKIRT_UP}, "
                             f"lowered all the way down with his thick penis deep inside her vagina, her "
                             f"stretched labia fully visible, her head tilted back and her lips parted in "
                             f"pleasure, her face to the camera"),
    "anal": ("c0wg1rl, ", f"{PHOTOG} from beside his head: {HIM} lies on his back {RUG}, she squats over him "
                          f"facing him, feet planted, knees wide, {SKIRT_UP}, lowered all the way down with his "
                          f"thick penis deep inside her anus, her wet vagina fully visible above it, her head "
                          f"back and her lips parted in pleasure, her face to the camera"),
}
if ONLY_SHOTS:
    SHOTS = {k: v for k, v in SHOTS.items() if k in ONLY_SHOTS}
NEG = ("different person, different face, changed hair, bra, bralette, vest, blouse, shirt on her, top on her, "
       "extra penis, extra hands, extra limbs, deformed genitals, deformed hands, blurry, low quality, cartoon, "
       "anime, watermark, text, condom, tears, crying, watering eyes, toothy grin, childlike, child, underage")
NEG_POV = ", the man's face, his face, far away, distant, standing, office chair behind her, a second man"

cfg = load_config()
lora = resolve_lora(cfg, CHAR)
if not lora:
    raise SystemExit(f"{CHAR} has no locked LoRA")
face_ref = reference(CHAR)
if face_ref is None:
    raise SystemExit(f"{CHAR} has no face reference to score against")
d = find_set(cfg, CHAR, "video", "act-lora-probe", create=True)
write_set_json(d, character=CHAR, kind="video", name="act-lora-probe", date=d.name[:10])
LOG = d / "run.log"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def arm_loras(arm: str, shot: str) -> list[tuple[str, float]]:
    path, strength, _, second, s2 = ARMS[arm]
    out = [(PUSSY if (path == PENIS and shot in SEX_SHOTS) else path, strength)]
    if second:
        out.append((PUSSY if (second == PENIS and shot in SEX_SHOTS) else second, s2))
    return out


def prompt_for(arm: str, shot: str) -> str:
    trig = lora.get("trigger") or CHAR
    arm_trigger = ARMS[arm][2]
    shot_trigger, body = SHOTS[shot]
    lead = (arm_trigger + shot_trigger) if ARMS[arm][0] == Q4P else ""
    return (f"{lead}{trig}, {clause(CHAR)}, {HAIR}, {body}. {OFFICE_IN}. Photorealistic, natural skin texture, "
            f"sharp focus.")


def splice_lora(wf: dict, after: str, path: str, strength: float, new: str) -> dict:
    """One more LoraLoaderModelOnly between node `after` and whatever read its model."""
    nodes = wf["nodes"] if "nodes" in wf else wf
    for node in nodes.values():
        for k, v in node.get("inputs", {}).items():
            if k == "model" and v == [after, 0]:
                node["inputs"][k] = [new, 0]
    nodes[new] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": [after, 0], "lora_name": path, "strength_model": float(strength)}}
    return wf


def workflow(arm: str, shot: str, seed: int) -> dict:
    loras = arm_loras(arm, shot)
    path, strength = loras[0]
    neg = NEG + (NEG_POV if shot in ("release", "stroke", "tip", "deep") else "")
    extra = appearance_negative(CHAR)
    # built at the cap, then the act LoRA's own strength set on its node - the probe's deliberate bypass
    wf = t2i_workflow(cfg, prompt_for(arm, shot), seed, f"sourcemode/{CHAR}_actprobe", lora_path=lora["path"],
                      negative=neg + (", " + extra if extra else ""), width=W, height=H,
                      extra_loras=((path, min(strength, 0.6)),))
    nodes = wf["nodes"] if "nodes" in wf else wf
    slot = None
    for key, node in nodes.items():
        if node.get("class_type") == "LoraLoaderModelOnly" and node["inputs"].get("lora_name") == path:
            node["inputs"]["strength_model"] = float(strength)
            slot = key
    if len(loras) > 1 and slot:
        splice_lora(wf, slot, loras[1][0], loras[1][1], "901")
    return wf


plan = [(arm, shot, s) for shot in SHOTS for arm in ARMS for s in range(SEEDS)]
log(f"{CHAR}: {len(plan)} stills ({len(SHOTS)} shots x {len(ARMS)} arms x {SEEDS} seeds) -> {d}")
if DRY:
    for p in plan:
        log(f"  would render {p}: {prompt_for(p[0], p[1])[:120]}...")
    raise SystemExit(0)

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
ref_emb = embed_image(face_ref)
app = _get_face_app()
rng = random.SystemRandom()
record = json.loads((d / "shots.json").read_text(encoding="utf-8")) if (d / "shots.json").is_file() else {}


def score(p: Path) -> tuple[float | None, int | None]:
    if app is None or ref_emb is None:
        return None, None
    img = cv2.imread(str(p))
    faces = app.get(img) if img is not None else []
    if not faces:
        return None, None
    f = max(faces, key=lambda x: float(cosine(ref_emb, x.normed_embedding)))
    return (round(float(cosine(ref_emb, f.normed_embedding)), 3),
            int(round(float(f.age))) if getattr(f, "age", None) is not None else None)


for arm, shot, s in plan:
    out = d / f"{arm}__{shot}__{TAG + '_' if TAG else ''}s{s}.png"
    if out.is_file():
        continue
    seed = rng.randrange(1, 2**31)
    t0 = time.monotonic()
    files = client.outputs(client.wait(client.submit(workflow(arm, shot, seed)), timeout_s=3600))
    if not files:
        raise SystemExit(f"{out.name}: ComfyUI returned no image")
    client.fetch(files[0], out)
    out.with_suffix(".txt").write_text(prompt_for(arm, shot), encoding="utf-8")
    face, age = score(out)
    record[out.stem] = {"arm": arm, "shot": shot, "seed": seed, "loras": arm_loras(arm, shot),
                        "face": face, "age": age}
    (d / "shots.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    log(f"  {out.name}: face {face}  age {age}  {time.monotonic() - t0:.0f}s")

TW, TH = 300, 450
rows = [(arm, s) for arm in ARMS for s in range(SEEDS)]
sheet = Image.new("RGB", (TW * len(SHOTS), TH * len(rows)), "black")
dr = ImageDraw.Draw(sheet)
for r, (arm, s) in enumerate(rows):
    for c, shot in enumerate(SHOTS):
        p = d / f"{arm}__{shot}__{TAG + '_' if TAG else ''}s{s}.png"
        if not p.is_file():
            continue
        im = Image.open(p).convert("RGB")
        im.thumbnail((TW, TH))
        sheet.paste(im, (c * TW, r * TH))
        rec = record.get(p.stem, {})
        dr.rectangle([c * TW, r * TH, c * TW + TW, r * TH + 18], fill="black")
        dr.text((c * TW + 4, r * TH + 3), f"{arm} s{s} {shot} / face {rec.get('face')} age {rec.get('age')}",
                fill="yellow")
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")
log("PROBEDONE")
