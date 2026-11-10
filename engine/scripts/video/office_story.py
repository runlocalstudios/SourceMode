"""One office photo story for a character, continuing her office desk set.

    python scripts/video/office_story.py <character> [--only=id,id] [--retry=id,id] [--dry-run] [--sheet-only]

Jeremy, 2026-11-10: "a set starting from the set we chose that involves her
showing off her body (front, side and back pics of 3/4 or waist up) followed by
her taking off the man's pants over a few pics ... she first grabs it, spits on
it as lube and a number of handjob pics including rubbing his balls, squeezing
them gently and a few using both hands ... Then shift to blowjob shots - just
the tip, licking the head, sucking with her hands on his legs, sucking while
holding it with one hand, and then 2 hands, a few deepthroat shots. Infuse some
side angles ... as would be viewed by a photographer shooting the set. Then the
sex poses either on the desk or the floor - mix of vaginal and anal penetration,
just the tip at first then deep and thrusting, all pics with her face visible
facing the viewer, then at the end ... he pulls out and she jerks him off as he
shoots a massive cum load all over her stomach, chest and face ... if you run
into issues creating the shot you want retry only 3 times for each shot before
moving on."

Continuity is the office desk set's: its outfit, its hair, the OFFICE_IN room.
Every shot is her locked LoRA at 1.0 through Qwen-Image 2512; the explicit shots
add the GNASS sex LoRA. A shot gets at most MAX_ATTEMPTS renders (the first plus
three retries): an attempt is kept when her face scores and reads adult, and the
best kept attempt is the shot's tile; a shot with no kept attempt after four is
logged GAVE UP and left out of the judge set. `--retry` spends another attempt
on a shot whose kept render missed the content (my audit by eye, prompt revised
in STORY first); `--only` limits a run to some shots.

Adults only: InsightFace's age estimate is logged per render and anything that
reads young is never kept. QC only; his eye is final.

Output: library/<character>/<date>_video_office-story/<id>__a<n>.png, shots.json,
sheet.jpg (one tile per shot) and judge set story_<character>_office.
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
from sourcemode.assets.judge import make_set
from sourcemode.assets.looks import reference
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.render import t2i_workflow
from sourcemode.assets.shoots import OFFICE_IN
from sourcemode.config import load_config, outputs_dir
from sourcemode.gates.identity import _get_face_app, cosine, embed_image
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
SHEET_ONLY = "--sheet-only" in sys.argv
if len(ARGS) != 1:
    raise SystemExit(__doc__)
CHAR = ARGS[0].lower()
ONLY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), None)
RETRY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--retry=")), [])
MAX_ATTEMPTS = 4      # the first render plus three retries
FACE_MIN = 0.50       # her face against the reference; GNASS renders of her ran 0.68-0.70 on 2026-11-09
FACE_SIDE_MIN = 0.35  # a profile scores low against a frontal reference: a02_side a1 was her at 0.464
YOUNG_FLAG = 23       # InsightFace runs a few years low on young adults; below this is never kept

GNASS = "nsfw\\qimage2512_gnass.safetensors"
W, H = 1024, 1536

# --- the set's continuity ---------------------------------------------------
HAIR = "her hair worn down with wavy curls throughout"
OUTFIT = ("a black tailored vest buttoned over a lace bralette, a tight red pencil mini skirt and "
          "sheer black stockings")
TOPLESS = ("topless with her bare breasts showing, wearing only the tight red pencil mini skirt and sheer "
           "black stockings")
SKIRT_UP = ("topless with her bare breasts showing, her red mini skirt pushed up around her waist, her sheer "
            "black stockings still on, otherwise naked")
HIM = "a fit man in a white dress shirt with the sleeves rolled up"
COCK = "his thick eight-inch erect penis, large and prominent"
PHOTOG = "picture by a photographer shooting the set"
SIDE = "picture by a photographer shooting the set from the side at her eye level, her face in profile"
POV = "POV picture from the man's eyes looking down"
KNEEL = f"she kneels on the cream wool rug in front of {HIM}, who stands by the desk with his trousers down"
ON_DESK = "she lies on her back on the big walnut desk"
RUG = "on the cream wool rug"

# id, GNASS strength (0 = her LoRA alone), the shot. Order is the story's order.
STORY: tuple[tuple[str, float, str], ...] = (
    # --- showing off her body ---
    ("a01_front", 0.0, f"{PHOTOG}: she stands beside the big desk facing the camera, three-quarter length, "
                       f"hands on her hips, one hip cocked, a teasing smile, in {OUTFIT}"),
    ("a02_side", 0.0, f"{SIDE}: she stands beside the desk in profile, waist up, her back arched and chest "
                      f"out, turning her face to smile at the camera, in {OUTFIT}"),
    ("a03_back", 0.0, f"{PHOTOG}: seen from behind, three-quarter length, standing at the desk with her back "
                      f"to the camera, the tight red skirt hugging her bottom, looking back over her shoulder "
                      f"at the camera, in {OUTFIT}"),
    ("a04_vest_open", 0.6, f"{PHOTOG}: she sits on the edge of the desk facing the camera, waist up, her black "
                           f"vest unbuttoned and hanging open, her lace bralette pulled down beneath her bare "
                           f"breasts, biting her lip, a tight red pencil mini skirt and sheer black stockings"),
    ("a05_topless_front", 0.6, f"{PHOTOG}: she stands facing the camera, three-quarter length, {TOPLESS}, her "
                               f"hands sliding up her sides, smiling at the camera"),
    ("a06_topless_side", 0.6, f"{SIDE}: she stands in profile, waist up, {TOPLESS}, her back arched, turning "
                              f"her face to the camera"),
    ("a07_topless_back", 0.6, f"{PHOTOG}: seen from behind, three-quarter length, {TOPLESS}, lifting her hair "
                              f"with both hands, looking back over her shoulder at the camera"),
    # --- his pants come off ---
    ("b01_belt", 0.6, f"{PHOTOG}: she kneels on the cream wool rug in front of {HIM} standing by the desk, "
                      f"{TOPLESS}, her hands undoing his belt buckle, a large bulge straining in his suit "
                      f"trousers, she looks up at him with a grin"),
    ("b02_unzip", 0.6, f"{PHOTOG}: she kneels on the cream wool rug, {TOPLESS}, pulling his unzipped suit "
                       f"trousers down over his hips, his erection straining against his black boxer briefs, "
                       f"she looks at the camera with a grin"),
    ("b03_release", 0.8, f"{PHOTOG}: she kneels on the cream wool rug, {TOPLESS}, pulling his boxer briefs down "
                         f"as {COCK} springs free right in front of her face, her eyes wide, grinning at the "
                         f"camera"),
    # --- handjob ---
    ("c01_grab", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, wrapping one hand around {COCK}, looking up at the camera "
                      f"with a hungry smile"),
    ("c02_spit", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, holding {COCK} in one hand and spitting onto the head of "
                      f"it, a string of saliva running from her lips to the penis"),
    ("c03_stroke", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, stroking {COCK} with one hand, the shaft glistening "
                        f"with saliva, looking up at the camera"),
    ("c04_stroke_side", 0.8, f"{SIDE}: {KNEEL}, {TOPLESS}, stroking {COCK} with one hand, the penis seen from "
                             f"the side pointing at her face"),
    ("c05_balls", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, stroking the shaft of {COCK} with one hand while her "
                       f"other hand cups and rubs his balls, looking up at the camera"),
    ("c06_squeeze", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, her hand gently squeezing his balls, the head of "
                         f"{COCK} resting against her cheek, smiling at the camera"),
    ("c07_two_hands", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, both of her hands wrapped around {COCK} one above "
                           f"the other, stroking it, the head still showing above her top hand, looking up at "
                           f"the camera"),
    ("c08_two_hands_side", 0.8, f"{SIDE}: {KNEEL}, {TOPLESS}, both hands wrapped around {COCK} stroking it, "
                                f"the penis seen from the side"),
    ("c09_pov", 0.8, f"{POV}: she kneels between his legs {RUG}, {TOPLESS}, stroking {COCK} with both hands, "
                     f"looking up into the camera"),
    # --- blowjob ---
    ("d01_tip", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, just the head of {COCK} between her lips, her lips closed "
                     f"around the tip only, her eyes looking up at the camera"),
    ("d02_lick", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, her tongue out licking the head of {COCK}, one hand "
                      f"holding it at the base, her eyes on the camera"),
    ("d03_hands_on_legs", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, sucking {COCK} with the shaft halfway in her "
                               f"mouth, both of her hands resting on his thighs, no hands on the penis, looking "
                               f"up at the camera"),
    ("d04_one_hand", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, sucking the head of {COCK} with one hand wrapped "
                          f"around the base of the shaft, looking up at the camera"),
    ("d05_two_hands", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, sucking the head of {COCK} with both hands wrapped "
                           f"around the shaft, looking up at the camera"),
    ("d06_side", 0.8, f"{SIDE}: {KNEEL}, {TOPLESS}, {COCK} halfway into her mouth, her lips stretched around "
                      f"the shaft, seen from the side"),
    ("d07_deep", 0.8, f"{PHOTOG}: {KNEEL}, {TOPLESS}, most of {COCK} inside her mouth, her lips near the base, "
                      f"her cheeks hollowed, her eyes watering, looking up at the camera"),
    ("d08_deep_side", 0.8, f"{SIDE}: {KNEEL}, {TOPLESS}, {COCK} all the way in her mouth, her lips at the "
                           f"base, her nose against his body, seen from the side"),
    ("d09_pov", 0.8, f"{POV}: she kneels between his legs {RUG}, {TOPLESS}, her lips wrapped around {COCK}, "
                     f"one hand at the base, looking up into the camera"),
    # --- sex: she faces him on every shot, legs spread and planted, her pussy in his view ---
    # Jeremy, 2026-11-10: "All anal and vaginal she is to be facing him - meaning no bent
    # over shots. So she needs to have her legs spread and planted on the desk or floor
    # and she brings her pussy or ass down onto his cock, he can always see her pussy in
    # all those shots. Before he finishes, her back is on the desk and he is standing next
    # to the desk ... add some poses where she is really looking pleasured. Try to add a
    # few of her squirting while he is deep in her ass too"
    ("s01_rug_tip", 0.8, f"{PHOTOG} from beside his head: {HIM} lies on his back {RUG}, she squats over his hips "
                         f"facing him with her feet planted flat on the rug either side of him and her knees "
                         f"spread wide, {SKIRT_UP}, one hand guiding just the head of {COCK} into her vagina, "
                         f"her vagina fully visible between her spread thighs, her face turned to the camera"),
    ("s02_rug_deep", 0.8, f"{PHOTOG} from beside his head: {HIM} lies on his back {RUG}, she squats over his hips "
                          f"facing him, feet planted flat on the rug, knees spread wide, {SKIRT_UP}, lowered all "
                          f"the way down with his thick penis deep inside her vagina, her stretched labia fully "
                          f"visible, her head tilted back and her mouth open in pleasure, her face to the camera"),
    ("s03_rug_pov", 0.8, f"{POV} from his eyes as he lies on his back {RUG}: she squats over his hips facing "
                         f"him, feet planted flat on the rug, knees spread wide, {SKIRT_UP}, {COCK} deep inside "
                         f"her vagina, her vagina stretched around it in full view, her face flushed, biting "
                         f"her lip and looking into the camera"),
    ("s04_rug_pleasure", 0.8, f"{PHOTOG} from beside his head: {HIM} lies on his back {RUG}, she squats over him "
                              f"facing him, feet planted, knees wide, {SKIRT_UP}, riding his thick penis deep "
                              f"in her vagina, her eyes half closed and rolling back, her mouth open in a moan, "
                              f"her hands squeezing her own breasts, her face to the camera"),
    ("s05_desk_tip", 0.8, f"{PHOTOG} from beside the desk: {HIM} lies on his back on the big walnut desk, she "
                          f"squats over his hips on the desk facing him with her feet planted flat on the "
                          f"desktop and her knees spread wide, {SKIRT_UP}, guiding just the head of {COCK} into "
                          f"her vagina, her vagina fully visible, her face turned to the camera"),
    ("s06_desk_deep", 0.8, f"{PHOTOG} from beside the desk: {HIM} lies on his back on the big walnut desk, she "
                           f"squats over him on the desk facing him, feet planted on the desktop, knees wide, "
                           f"{SKIRT_UP}, his thick penis deep inside her vagina, her stretched labia visible, "
                           f"bouncing on it, her face to the camera with her mouth open in pleasure"),
    ("s07_desk_pov", 0.8, f"{POV} from his eyes as he lies on his back on the big walnut desk: she squats over "
                          f"his hips facing him, feet planted on the desktop, knees spread wide, {SKIRT_UP}, "
                          f"{COCK} deep inside her vagina in full view, her face flushed with pleasure, looking "
                          f"into the camera"),
    ("s08_rug_anal_tip", 0.8, f"{PHOTOG} from beside his head: {HIM} lies on his back {RUG}, she squats over his "
                              f"hips facing him, feet planted flat on the rug, knees spread wide, {SKIRT_UP}, "
                              f"one hand guiding just the head of {COCK} against her anus, her wet vagina fully "
                              f"visible just above it, her face turned to the camera"),
    ("s09_rug_anal_deep", 0.8, f"{PHOTOG} from beside his head: {HIM} lies on his back {RUG}, she squats over "
                               f"him facing him, feet planted, knees wide, {SKIRT_UP}, lowered all the way down "
                               f"with his thick penis deep inside her anus, her wet vagina fully visible above "
                               f"it, her head back and her mouth open in pleasure, her face to the camera"),
    ("s10_rug_anal_pov", 0.8, f"{POV} from his eyes as he lies on his back {RUG}: she squats over his hips "
                              f"facing him, feet planted flat on the rug, knees spread wide, {SKIRT_UP}, "
                              f"{COCK} deep inside her anus, her wet vagina in full view above it, her eyes "
                              f"rolling back with pleasure, looking into the camera"),
    ("s11_rug_anal_squirt", 0.8, f"{PHOTOG} from beside his head: {HIM} lies on his back {RUG}, she squats over "
                                 f"him facing him, feet planted, knees wide, {SKIRT_UP}, his thick penis deep "
                                 f"inside her anus, a clear stream of fluid squirting from her vagina, her head "
                                 f"thrown back and her mouth open in a cry of pleasure, her face to the camera"),
    ("s12_desk_anal_deep", 0.8, f"{PHOTOG} from beside the desk: {HIM} lies on his back on the big walnut desk, "
                                f"she squats over him on the desk facing him, feet planted on the desktop, "
                                f"knees wide, {SKIRT_UP}, his thick penis deep inside her anus, her wet vagina "
                                f"fully visible above it, her face to the camera, moaning"),
    ("s13_desk_anal_squirt", 0.8, f"{PHOTOG} from beside the desk: {HIM} lies on his back on the big walnut "
                                  f"desk, she squats over him facing him, feet planted on the desktop, knees "
                                  f"wide, {SKIRT_UP}, his thick penis deep inside her anus, a clear stream of "
                                  f"fluid squirting from her vagina, her eyes rolling back, her face to the "
                                  f"camera"),
    # --- her back on the desk, him standing beside it, before he finishes ---
    ("e01_desk_tip", 0.8, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs spread wide with her "
                          f"feet planted on the edge of the desk, {HIM} standing at the edge of the desk "
                          f"between her legs with just the head of {COCK} pressing into her vagina, her vagina "
                          f"in full view, her face turned to the camera"),
    ("e02_desk_deep", 0.8, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs spread wide and "
                           f"held up, {HIM} standing between her legs with his thick penis deep inside her "
                           f"vagina, thrusting, her labia stretched around the shaft, her head back and her "
                           f"mouth open in pleasure, her face turned to the camera"),
    ("e09_desk_anal_tip", 0.8, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs raised and held "
                               f"open, {HIM} standing at the edge of the desk with just the head of {COCK} "
                               f"entering her anus, her wet vagina in full view above it, her face turned to "
                               f"the camera"),
    ("e10_desk_anal_deep", 0.8, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs raised and "
                                f"held open, {HIM} standing at the edge of the desk with his thick penis deep "
                                f"inside her anus, thrusting, her wet vagina visible above it, her face turned "
                                f"to the camera with her mouth open"),
    ("e11_desk_anal_pleasure", 0.8, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs raised and "
                                    f"held open, {HIM} standing at the edge of the desk with his thick penis "
                                    f"deep inside her anus, her wet vagina visible above it, her eyes rolling "
                                    f"back and her mouth open in a moan, gripping the edge of the desk, her "
                                    f"face to the camera"),
    ("e12_desk_anal_squirt", 0.8, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs raised and "
                                  f"held open, {HIM} standing at the edge of the desk with his thick penis deep "
                                  f"inside her anus, a clear stream of fluid squirting from her vagina, her "
                                  f"head thrown back in a cry of pleasure, her face to the camera"),
    # --- the finish: he stands beside the desk, his penis held just above her pussy ---
    ("f01_pullout", 0.8, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs spread, {HIM} "
                         f"standing beside the desk having just pulled {COCK} out of her anus and holding it "
                         f"just above her vagina, she reaches down and wraps her hand around it, looking at "
                         f"the camera"),
    ("f02_cum", 0.8, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs spread, {HIM} standing "
                     f"beside the desk, she jerks {COCK} held just above her vagina as he ejaculates, a massive "
                     f"load of thick white cum spraying across her stomach, chest and face, her eyes on the "
                     f"camera"),
    ("f03_covered", 0.8, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs spread, {HIM} standing "
                         f"beside the desk, her stomach, breasts and face covered in thick white cum, {COCK} "
                         f"still in her hand just above her vagina, smiling at the camera"),
)
IDS = [s[0] for s in STORY]
assert len(IDS) == len(set(IDS)), "duplicate shot id"

NEG_BASE = ("different person, different face, changed hair, extra penis, extra hands, extra limbs, deformed "
            "genitals, deformed hands, blurry, low quality, cartoon, anime, watermark, text, condom, childlike, "
            "child, underage")
NEG_BARE = "bra, bralette, vest, blouse, shirt on her, top on her"   # once she is topless, nothing comes back

cfg = load_config()
OUT_ROOT = outputs_dir(cfg)
lora = resolve_lora(cfg, CHAR)
if not lora:
    raise SystemExit(f"{CHAR} has no locked LoRA")
face_ref = reference(CHAR)
if face_ref is None:
    raise SystemExit(f"{CHAR} has no face reference to score against")
d = find_set(cfg, CHAR, "video", "office-story", create=True)
write_set_json(d, character=CHAR, kind="video", name="office-story", date=d.name[:10],
               outfit=OUTFIT, hair=HAIR)
LOG = d / "run.log"
SHOTS = d / "shots.json"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def prompt_for(body: str) -> str:
    trig = lora.get("trigger") or CHAR
    return f"{trig}, {clause(CHAR)}, {HAIR}, {body}. {OFFICE_IN}. Photorealistic, natural skin texture, sharp focus."


def negative_for(sid: str, strength: float) -> str:
    neg = NEG_BASE
    if strength and not sid.startswith("a04"):
        neg += ", " + NEG_BARE
    extra = appearance_negative(CHAR)
    return neg + (", " + extra if extra else "")


record: dict = json.loads(SHOTS.read_text(encoding="utf-8")) if SHOTS.is_file() else {}
for sid, _, _ in STORY:
    record.setdefault(sid, {"attempts": [], "kept": None})


def save() -> None:
    SHOTS.write_text(json.dumps(record, indent=1), encoding="utf-8")


def kept_of(sid: str) -> dict | None:
    ok = [a for a in record[sid]["attempts"] if a.get("ok")]
    return max(ok, key=lambda a: a["face"]) if ok else None


todo = [s for s in STORY if (ONLY is None or s[0] in ONLY)]
if not SHEET_ONLY:
    plan = []
    for sid, strength, body in todo:
        n = len(record[sid]["attempts"])
        if sid in RETRY:
            if n >= MAX_ATTEMPTS:
                log(f"  {sid}: already {n} attempts, no retry left")
                continue
            plan.append((sid, strength, body, 1))
        elif kept_of(sid) is None and n < MAX_ATTEMPTS:
            plan.append((sid, strength, body, MAX_ATTEMPTS - n))
    log(f"{CHAR}: {len(plan)} shots to render (up to {sum(p[3] for p in plan)} renders), of {len(STORY)} in the "
        f"story -> {d}")
    if DRY:
        for sid, strength, body, budget in plan:
            log(f"  would render {sid} x{budget} (gnass {strength}): {prompt_for(body)[:160]}...")
        raise SystemExit(0)

    client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    ref_emb = embed_image(face_ref)
    app = _get_face_app()
    rng = random.SystemRandom()

    def score(p: Path) -> tuple[float | None, int | None]:
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

    for sid, strength, body, budget in plan:
        for _ in range(budget):
            n = len(record[sid]["attempts"]) + 1
            out = d / f"{sid}__a{n}.png"
            seed = rng.randrange(1, 2**31)
            t0 = time.monotonic()
            wf = t2i_workflow(cfg, prompt_for(body), seed, f"sourcemode/{CHAR}_story", lora_path=lora["path"],
                              negative=negative_for(sid, strength), width=W, height=H,
                              extra_loras=((GNASS, strength),) if strength else ())
            files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
            if not files:
                log(f"  {sid} a{n}: ComfyUI returned no image")
                record[sid]["attempts"].append({"file": out.name, "seed": seed, "face": None, "age": None,
                                                "young": False, "ok": False, "why": "no image"})
                save()
                continue
            client.fetch(files[0], out)
            out.with_suffix(".txt").write_text(prompt_for(body), encoding="utf-8")
            face, age = score(out)
            young = bool(age is not None and age < YOUNG_FLAG)
            fmin = FACE_SIDE_MIN if sid.endswith("_side") else FACE_MIN
            ok = bool(face is not None and face >= fmin and not young)
            why = "" if ok else ("no face" if face is None else "YOUNG" if young else f"face {face} < {fmin}")
            record[sid]["attempts"].append({"file": out.name, "seed": seed, "face": face, "age": age,
                                            "young": young, "ok": ok, "why": why, "gnass": strength})
            k = kept_of(sid)
            record[sid]["kept"] = k["file"] if k else None
            save()
            log(f"  {sid} a{n}: face {face}  age {age}  {'kept' if ok else why}  {time.monotonic() - t0:.0f}s")
            if ok and sid not in RETRY:
                break
        if kept_of(sid) is None:
            log(f"  {sid}: GAVE UP after {len(record[sid]['attempts'])} attempts")

# --- the sheet and the judge set: one tile per shot, the best kept attempt ----
TW, TH, COLS = 300, 450, 6
rows = (len(STORY) + COLS - 1) // COLS
sheet = Image.new("RGB", (TW * COLS, TH * rows), "black")
dr = ImageDraw.Draw(sheet)
items = []
for i, (sid, strength, _) in enumerate(STORY):
    k = kept_of(sid)
    att = record[sid]["attempts"]
    best = k or (max((a for a in att if a.get("face") is not None), key=lambda a: a["face"], default=None))
    x, y = (i % COLS) * TW, (i // COLS) * TH
    if best and (d / best["file"]).is_file():
        im = Image.open(d / best["file"]).convert("RGB")
        im.thumbnail((TW, TH))
        sheet.paste(im, (x, y))
    colour = "black" if k else ("red" if any(a.get("young") for a in att) else "gray")
    dr.rectangle([x, y, x + TW, y + 18], fill=colour)
    dr.text((x + 4, y + 3), f"{sid} / {len(att)} tries / face {best['face'] if best else None} "
                            f"age {best['age'] if best else None}{'' if k else ' NO KEEP'}", fill="yellow")
    if k:
        items.append({"id": sid, "path": d / k["file"], "arm": "story", "group": sid[0]})
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")
if items and not DRY:
    make_set(OUT_ROOT / "judge", f"story_{CHAR}_office", f"{CHAR.title()} - office story", items,
             question="Keep this one? K = yes, X = re-roll it.", priority=5,
             meta={"character": CHAR, "renders_dir": d})
    log(f"{len(items)} of {len(STORY)} shots kept -> judge set story_{CHAR}_office")
log("STORYDONE")
