"""The hotel-arrival photo story for a character, rendered from text with her LoRA.

    python scripts/video/hotel_story.py <character> [--section=d,c,w,g,n,o,k,p,l] [--only=id,id] [--retry=id,id] [--reject=file,file] [--dry-run] [--sheet-only]

Jeremy, 2026-11-10: the Codex photo stories ("her coming into the viewer's hotel
room, taking off her fur coat, pouring a glass of champagne, dancing sexy for the
viewer, sitting in front of him") were made by OpenAI image generation from a
reference library and it "won't even do anything like have the girl kneeling in
front of the viewer". Recreate the same shot plan with her LoRA instead:
"facial identity, and the identity of her hairstyle and body be very, very high
fidelity. The second priority is the fidelity to the outfit ... The third is the
fidelity of the room". ~30 images; "run a few, audit the work, and then if things
are looking good, you can go ahead and finish the whole set".

The storyboard follows the Codex hotel stories (Nadia 2026-10-30_nadia_26_1,
Fiona 2026-11-08_fiona_29_2): door, coat, window, champagne, ottoman, the
kneeling beats OpenAI refused, close portraits, the last look - plus the dance
he asked for. Every frame is from the eyes of the viewer in the armchair.

Every shot is text-to-image through `render.t2i_workflow` with her locked LoRA
at 1.0 and no other LoRA: identity first. The outfit and the room are one fixed
sentence each so they are worded identically in every frame; the room is the
loosest of the three and he said so.

Each shot gets at most MAX_ATTEMPTS renders (the first plus three retries). An
attempt is kept when her face scores against her reference and reads adult;
`_back` shots (face hidden by design) keep on sight. Every kept attempt goes to
the judge; the best kept one is the shot's tile. `--reject=<file stem>,...`
marks an attempt off-story after the audit (she sat in a chair instead of
kneeling): it stays on disk and on the judge board, but the shot renders again.

Lesson from the first probe (j1374): "from the eyes of the man seated in a tan
leather armchair" painted the armchair into three of four frames and sat her
in it twice. Then "from the eyes of a seated man" (j1375) painted the man's own
suit shoulder into the corner. The viewer is never named at all now: the camera
is "at seated eye level", and armchair, man and suit are in the negative.

Output: library/<character>/<date>_video_hotel-story/<id>__a<n>.png, shots.json,
sheet.jpg and judge set story_<character>_hotel.
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
from sourcemode.config import load_config, outputs_dir
from sourcemode.gates.identity import _get_face_app, cosine, embed_image
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
SHEET_ONLY = "--sheet-only" in sys.argv
if not ARGS:
    raise SystemExit(__doc__)
CHAR = ARGS[0].lower()
ONLY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), None)
SECTION = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--section=")), None)
RETRY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--retry=")), [])
REJECT = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--reject=")), [])
MAX_ATTEMPTS = 4      # the first render plus three retries
FACE_MIN = 0.25       # a tie-breaker between seeds, never a verdict: his eye picks from everything that passes
                      # (0.30 held back an over-the-shoulder look at 0.291 that was plainly her, j1377)
FACE_SIDE_MIN = 0.15  # a true profile scores 0.22-0.25 against a frontal reference and is still her (w02, j1377)
YOUNG_FLAG = 20       # Jeremy, 2026-11-10: "The floor should be like 20 because 18 is a fucking adult"
W, H = 1024, 1536

# --- what she wears and where she is: one sentence each, identical in every frame ----
LOOKS = {
    "nadia": {
        "hair": "her hair worn loose",
        "outfit": ("a tight sky-blue satin sleeveless mini dress with a draped cowl neckline, black leather "
                   "knee-high stiletto boots and diamond stud earrings"),
        "coat": "a knee-length black fur coat",
    },
    "fiona": {
        "hair": "her hair worn loose",
        "outfit": ("a fitted amethyst-purple velour mini dress with short sleeves and a high round neckline, "
                   "matching purple velour opera gloves reaching above her elbows, a narrow purple velour "
                   "choker, silver hoop earrings and purple velour pumps"),
        "coat": "a long white fur coat",
    },
}
if CHAR not in LOOKS:
    raise SystemExit(f"no hotel look for {CHAR}; add one to LOOKS")
HAIR, OUTFIT, COAT = LOOKS[CHAR]["hair"], LOOKS[CHAR]["outfit"], LOOKS[CHAR]["coat"]
CLUTCH = "a small black clutch purse"
ROOM = ("Inside a luxury hotel suite at night, warm lamplight, beige walls with walnut trim, a king bed with a "
        "white duvet on the left, a floor-to-ceiling window full of city lights at night on the right, a low "
        "oatmeal upholstered ottoman in the middle of the room, a small round walnut side table with a silver "
        "champagne bucket and two champagne flutes beside the window, a walnut entry door at the far end")
POV = "point-of-view photo, the camera at seated eye level"
CLOSE = "a close-up portrait photo, head and shoulders only, her face filling the frame"
CLOSE_ROOM = "Soft out-of-focus hotel suite behind her at night, warm lamplight, city lights in the window"
COAT_ON = f"wearing {COAT} open over {OUTFIT}"
COAT_OFF = f"in {OUTFIT}, the black clutch and {COAT} lying on the bed"

# A shot is (id, text). Section = first letter of the id.
STORY: tuple[tuple[str, str], ...] = (
    # --- d: the door -------------------------------------------------------------
    ("d01_doorway", f"{POV}: she pauses just inside the open hotel room door, full length, facing the camera, "
                    f"a white keycard in one hand and {CLUTCH} in the other, the hotel corridor behind her, a "
                    f"small welcoming smile, {COAT_ON}"),
    ("d02_closing", f"{POV}: she pushes the hotel room door shut behind her with one hand, {CLUTCH} in the "
                    f"other, looking back over her shoulder at the camera with a raised brow, full length, "
                    f"{COAT_ON}"),
    ("d03_against_door", f"{POV}: she leans her back against the closed walnut door facing the camera, "
                         f"three-quarter length, chin tipped down, a relaxed teasing smile, {CLUTCH} held at "
                         f"her hip, {COAT_ON}"),
    # --- c: the coat -------------------------------------------------------------
    ("c01_to_bed", f"{POV}: she walks toward the bed on the left in a three-quarter view, full length, the "
                   f"fur coat open and swinging, {CLUTCH} in her hand, glancing at the camera, {COAT_ON}"),
    ("c02_coat_off", f"{POV}: standing beside the bed, three-quarter length, the fur coat slipped down off her "
                     f"bare shoulders and hanging from her elbows as she takes it off, eyes on the camera with "
                     f"a knowing smile, {COAT_ON}"),
    ("c03_reveal", f"{POV}: a full-length photo, her whole standing figure in frame, standing on the carpet "
                   f"beside the bed facing the camera, one foot forward, arms relaxed at her sides, lifting "
                   f"her gaze with a quiet smile, {COAT_OFF}"),
    # --- w: the window -----------------------------------------------------------
    ("w01_back", f"{POV}: seen from behind, full length, she walks toward the city window, her long hair "
                 f"hanging down her back, mid-step, {COAT_OFF}"),
    ("w02_side", f"{POV}: she stands beside the floor-to-ceiling window in profile, waist up, one hand on "
                 f"the window frame, gazing at the city lights with a faint smile, {COAT_OFF}"),
    ("w03_turn", f"{POV}: she stands right at the floor-to-ceiling window with her back against the glass "
                 f"and the city lights directly behind her, facing the camera, three-quarter length, hands "
                 f"clasped loosely at her waist, a soft friendly smile, {COAT_OFF}"),
    # --- g: the champagne --------------------------------------------------------
    ("g01_pour", f"{POV}: she stands at the walnut side table pouring champagne from the bottle into a "
                 f"flute, eyes on the pour, waist up, {COAT_OFF}"),
    ("g02_offer", f"{POV}: she holds a full champagne flute out toward the camera by its stem, arm extended, "
                  f"another flute in her other hand, eyes up at the camera with a quiet smile, waist up, "
                  f"{COAT_OFF}"),
    ("g03_sip", f"{POV}: she stands sipping from a champagne flute, eyes on the camera over the rim, waist "
                f"up, {COAT_OFF}"),
    # --- n: the dance ------------------------------------------------------------
    ("n01_sway", f"{POV}: she dances slowly for the camera in the middle of the room, full length, hips "
                 f"swaying to one side, one hand lifted into her hair, eyes locked on the camera, {COAT_OFF}"),
    ("n02_over_shoulder", f"{POV}: she dances with her back to the camera, hands on her hips, looking back "
                          f"over her shoulder with a teasing smile, full length, {COAT_OFF}"),
    ("n03_lean_in", f"{POV}: dancing close to the camera, she bends forward toward it with her hands on her "
                    f"knees, a teasing smile, waist up, {COAT_OFF}"),
    ("n04_spin", f"{POV}: she spins slowly with her long hair swinging out, laughing, full length, "
                 f"{COAT_OFF}"),
    ("n05_hands_down", f"{POV}: she stands close, running both hands slowly down her sides over the dress, "
                       f"lips parted in a sly smile, eyes on the camera, three-quarter length, {COAT_OFF}"),
    # --- o: the ottoman ----------------------------------------------------------
    ("o01_seated", f"{POV}: a full-length photo, her whole seated figure in frame, sitting on the oatmeal "
                   f"ottoman in the middle of the room facing the camera, the bed behind her on the left, knees "
                   f"together, a champagne flute held low in one hand, eye contact with a knowing little "
                   f"smile, {COAT_OFF}"),
    ("o02_toast", f"{POV}: seated on the ottoman in front of the camera she lifts her champagne flute to "
                  f"chest height, one eyebrow raised, lips together, waist up, {COAT_OFF}"),
    ("o03_lean", f"{POV}: seated on the ottoman she leans toward the camera with her elbows on her knees "
                 f"and her chin resting on her hands, a playful smile, waist up, {COAT_OFF}"),
    ("o04_laugh", f"{POV}: sitting on the oatmeal ottoman in the middle of the room with her legs crossed, "
                  f"the bed behind her on the left, leaning back on one hand, laughing with her head tilted, "
                  f"three-quarter length, {COAT_OFF}"),
    ("o05_hair_up", f"{POV}: seated sideways on the ottoman she gathers all her long hair up behind her "
                    f"head in both hands, giving the camera a playful sidelong glance, waist up, {COAT_OFF}"),
    # --- k: kneeling in front of him ------------------------------------------------
    ("k01_kneel", f"{POV}: a full-length photo from slightly above, her whole kneeling figure in frame, "
                  f"kneeling on the carpet right in front of the camera, sitting back on her heels, hands "
                  f"resting on her thighs, her face tilted up toward the camera, looking up into the lens "
                  f"with a teasing smile, {COAT_OFF}"),
    ("k02_kneel_close", f"{POV}: she kneels up tall on the carpet very close to the camera, looking up into "
                        f"it with parted lips, her hands resting on the knees of the man in the armchair, "
                        f"{COAT_OFF}"),
    ("k03_crawl", f"{POV}: she crawls toward the camera on her hands and knees across the carpet, looking "
                  f"up at it with a sly smile, her long hair falling forward, {COAT_OFF}"),
    ("k04_kneel_chin", f"{POV}: kneeling close in front of the camera she raises her chin and pushes her hair "
                       f"back with one hand, eyes half closed, lips parted, {COAT_OFF}"),
    # --- p: close portraits ------------------------------------------------------
    ("p01_half_smile", f"{CLOSE}, she looks straight into the camera with a playful asymmetric half-smile, "
                       f"chin dipped a little, in {OUTFIT}"),
    ("p02_laugh", f"{CLOSE}, she laughs warmly with her head tilted, eyes creased, in {OUTFIT}"),
    # --- l: the last look --------------------------------------------------------
    ("l01_leaving", f"{POV}: at the walnut door with one hand on the handle, {COAT} folded over her "
                    f"other forearm and {CLUTCH} in that hand, she looks back at the camera with a warm "
                    f"farewell smile, three-quarter length, in {OUTFIT}"),
    ("l02_last_look", f"{POV}: she stands in the hotel corridor just outside the door, giving the camera a "
                      f"last playful smile through the half-closed doorway, the corridor lights behind her, "
                      f"waist up, {COAT_ON}"),
)
IDS = [s[0] for s in STORY]
assert len(IDS) == len(set(IDS)), "duplicate shot id"

NEG_BASE = ("different person, different face, changed hair, extra hands, extra limbs, deformed hands, "
            "blurry, low quality, cartoon, anime, watermark, text, a second woman, the man's face, his face, "
            "armchair, sofa, couch, sitting in a chair, a man, man's shoulder, his knee, suit jacket, another "
            "person, tongue out, childlike, child, underage")
NEG_CLOTHES = {
    "nadia": "long dress, gown, pants, sneakers, bare feet",
    "fiona": "bare arms, bare hands, long dress, gown, boots, bare feet",
}

cfg = load_config()
OUT_ROOT = outputs_dir(cfg)
lora = resolve_lora(cfg, CHAR)
if not lora:
    raise SystemExit(f"{CHAR} has no locked LoRA")
face_ref = reference(CHAR)
if face_ref is None:
    raise SystemExit(f"{CHAR} has no face reference to score against")
d = find_set(cfg, CHAR, "video", "hotel-story", create=True)
write_set_json(d, character=CHAR, kind="video", name="hotel-story", date=d.name[:10],
               outfit=OUTFIT, hair=HAIR, coat=COAT)
LOG = d / "run.log"
SHOTS = d / "shots.json"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def prompt_for(text: str) -> str:
    trig = lora.get("trigger") or CHAR
    room = CLOSE_ROOM if text.startswith(CLOSE) else ROOM
    return f"{trig}, {clause(CHAR)}, {HAIR}, {text}. {room}. Photorealistic, natural skin texture, sharp focus."


def negative_for(sid: str) -> str:
    neg = NEG_BASE + ", " + NEG_CLOTHES.get(CHAR, "")
    if sid.startswith(("d0", "l02")):
        neg += ", coat on the bed"
    else:
        neg += ", wearing the fur coat, fur coat on her"
    if sid.startswith("o0"):
        neg += ", sitting on the bed"
    if sid.startswith(("c03", "n0", "g0", "w03")):
        neg += ", sitting, sitting on the bed, seated"
    if sid.startswith("p0"):
        neg += ", full body, full length, wide shot, her legs, her boots, her shoes"
    extra = appearance_negative(CHAR)
    return neg + (", " + extra if extra else "")


def t2i_wf(sid: str, text: str, seed: int) -> dict:
    return t2i_workflow(cfg, prompt_for(text), seed, f"sourcemode/{CHAR}_hotel", lora_path=lora["path"],
                        negative=negative_for(sid), width=W, height=H)


record: dict = json.loads(SHOTS.read_text(encoding="utf-8")) if SHOTS.is_file() else {}
for sid, _ in STORY:
    record.setdefault(sid, {"attempts": [], "kept": None})


def save() -> None:
    SHOTS.write_text(json.dumps(record, indent=1), encoding="utf-8")


def face_floor(sid: str) -> float:
    if sid.endswith("_back"):
        return -1.0          # her face is hidden by design; kept on sight
    return FACE_SIDE_MIN if sid.endswith("_side") else FACE_MIN


def passes(sid: str, a: dict) -> bool:
    """Her face and age pass, judged against the CURRENT floors, not the flag stored when it rendered."""
    if a.get("why") == "no image":
        return False
    if sid.endswith("_back"):
        return True
    young = a.get("age") is not None and a["age"] < YOUNG_FLAG
    return bool(a.get("face") is not None and a["face"] >= face_floor(sid) and not young)


def on_story(sid: str, a: dict) -> bool:
    """Passes AND was not rejected by eye after the audit."""
    return passes(sid, a) and not a.get("reject")


def kept_of(sid: str) -> dict | None:
    ok = [a for a in record[sid]["attempts"] if on_story(sid, a)]
    return max(ok, key=lambda a: a.get("face") or 0.0) if ok else None


for sid, _ in STORY:
    for a in record[sid]["attempts"]:
        if a["file"][:-4] in REJECT and not a.get("reject"):
            a["reject"] = True
            a["ok"] = False
            a["why"] = "rejected by eye"
    k = kept_of(sid)
    record[sid]["kept"] = k["file"] if k else None
save()


def selected(sid: str) -> bool:
    if ONLY is not None:
        return sid in ONLY
    if SECTION is not None:
        return sid[0] in SECTION
    return True


todo = [s for s in STORY if selected(s[0])]
if not SHEET_ONLY:
    plan = []
    for sid, text in todo:
        n = len(record[sid]["attempts"])
        if sid in RETRY:
            if n >= MAX_ATTEMPTS:
                log(f"  {sid}: already {n} attempts, no retry left")
                continue
            plan.append((sid, text, 1))
        elif kept_of(sid) is None and n < MAX_ATTEMPTS:
            plan.append((sid, text, MAX_ATTEMPTS - n))
    log(f"{CHAR}: {len(plan)} shots to render (up to {sum(p[2] for p in plan)} renders), of {len(STORY)} in the "
        f"story -> {d}")
    if DRY:
        for sid, text, budget in plan:
            log(f"  would render {sid} x{budget}: {prompt_for(text)}")
        raise SystemExit(0)

    client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    ref_emb = embed_image(face_ref)
    app = _get_face_app()
    rng = random.SystemRandom()

    def score(p: Path) -> tuple[float | None, int | None]:
        """HER face: the one closest to her reference, not the largest in frame."""
        if app is None:
            return None, None
        img = cv2.imread(str(p))
        faces = app.get(img) if img is not None else []
        if not faces:
            return None, None
        if ref_emb is not None:
            f = max(faces, key=lambda x: float(cosine(ref_emb, x.normed_embedding)))
        else:
            f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        face = round(float(cosine(ref_emb, f.normed_embedding)), 3) if ref_emb is not None else None
        age = int(round(float(f.age))) if getattr(f, "age", None) is not None else None
        return face, age

    for sid, text, budget in plan:
        for _ in range(budget):
            n = len(record[sid]["attempts"]) + 1
            out = d / f"{sid}__a{n}.png"
            seed = rng.randrange(1, 2**31)
            t0 = time.monotonic()
            wf = t2i_wf(sid, text, seed)
            files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
            if not files:
                log(f"  {sid} a{n}: ComfyUI returned no image")
                record[sid]["attempts"].append({"file": out.name, "seed": seed, "face": None, "age": None,
                                                "young": False, "ok": False, "why": "no image"})
                save()
                continue
            client.fetch(files[0], out)
            out.with_suffix(".txt").write_text(prompt_for(text), encoding="utf-8")
            face, age = score(out)
            a = {"file": out.name, "seed": seed, "face": face, "age": age, "young": False, "ok": False, "why": ""}
            a["young"] = bool(age is not None and age < YOUNG_FLAG)
            a["ok"] = on_story(sid, a)
            a["why"] = "" if a["ok"] else ("no face" if face is None else "YOUNG" if a["young"]
                                           else f"face {face} < {face_floor(sid)}")
            record[sid]["attempts"].append(a)
            k = kept_of(sid)
            record[sid]["kept"] = k["file"] if k else None
            save()
            log(f"  {sid} a{n}: face {face}  age {age}  {'kept' if a['ok'] else a['why']}  "
                f"{time.monotonic() - t0:.0f}s")
            if a["ok"] and sid not in RETRY:
                break
        if kept_of(sid) is None:
            log(f"  {sid}: GAVE UP after {len(record[sid]['attempts'])} attempts")

# --- the sheet and the judge set: one tile per shot, every passing attempt to the judge ----
TW, TH, COLS = 300, 450, 6
rows = (len(STORY) + COLS - 1) // COLS
sheet = Image.new("RGB", (TW * COLS, TH * rows), "black")
dr = ImageDraw.Draw(sheet)
items = []
for i, (sid, _) in enumerate(STORY):
    k = kept_of(sid)
    att = record[sid]["attempts"]
    best = k or (max((a for a in att if a.get("face") is not None), key=lambda a: a["face"], default=None))
    x, y = (i % COLS) * TW, (i // COLS) * TH
    if best and (d / best["file"]).is_file():
        im = Image.open(d / best["file"]).convert("RGB")
        im.thumbnail((TW, TH))
        sheet.paste(im, (x, y))
    colour = "black" if k else ("red" if any(a.get("young") for a in att) else "gray")
    rejected = sum(1 for a in att if a.get("reject"))
    dr.rectangle([x, y, x + TW, y + 18], fill=colour)
    dr.text((x + 4, y + 3), f"{sid} / {len(att)} tries{f' ({rejected} rej)' if rejected else ''} / face "
                            f"{best['face'] if best else None} age {best['age'] if best else None}"
                            f"{'' if k else ' NO KEEP'}", fill="yellow")
    # every attempt that passes goes to the judge: "I don't want you throwing out good images for no reason"
    for a in att:
        if passes(sid, a) and (d / a["file"]).is_file():
            items.append({"id": a["file"][:-4], "path": d / a["file"], "arm": "story", "group": sid})
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")
if items and not DRY:
    make_set(OUT_ROOT / "judge", f"story_{CHAR}_hotel", f"{CHAR.title()} - hotel story", items,
             question="Keep this one? K = yes, X = re-roll it.", priority=5,
             meta={"character": CHAR, "renders_dir": d})
    log(f"{sum(1 for s in STORY if kept_of(s[0]))} of {len(STORY)} shots kept -> judge set story_{CHAR}_hotel")
log("STORYDONE")
