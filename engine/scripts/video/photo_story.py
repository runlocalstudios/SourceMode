"""Render one photo story for a character from text with her LoRA.

    python scripts/video/photo_story.py <character> <story> [--section=a,b] [--only=id,id] [--retry=id,id]
                                        [--reject=file,file] [--dry-run] [--sheet-only]

The stories live in `story_defs.STORIES` (librarian, dictation, tryon, cheer,
livingroom, massage, bar, tutor ...): each one is a room sentence, a camera
line, one look per character (hair + outfit, worded identically in every
frame) and an ordered list of shots. The machinery is hotel_story.py's,
which proved the recipe on 2026-11-10 (docs/story-recipes.md "Hotel arrival
story"): her locked LoRA alone at 1.0, 1024x1536, the viewer never named,
"the camera at seated eye level"; nude shots stack GNASS under hers.

Jeremy, 2026-11-10 evening: "recreate the Fiona librarian set, the dictation
set, the try-on set, the cheerleader tease set, and then ... the living room
tease set ... the massage set ... the closing the bar set ... the tutor set
... Audit your work as you go - if a shot doesn't work redo it one time
before moving on. Log anything you learn". So MAX_ATTEMPTS is 2 here.

An attempt is kept when her face scores against her reference and reads
adult; shots flagged face_hidden keep on sight, face_low (profile, over the
shoulder) use the lower floor. `--reject=<file stem>` marks an audited miss:
it stays on disk and on the judge board, the shot renders again.

Output: library/<character>/<date>_video_<story>-story/<id>__a<n>.png,
shots.json, sheet.jpg and judge set story_<character>_<story>.
"""

import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from story_defs import GNASS, GNASS_STRENGTH, HANDS, NEG_BASE, NEG_NOMAN, NEG_NUDE, STORIES, Shot  # noqa: E402

from sourcemode.assets.appearance import clause, negative as appearance_negative  # noqa: E402
from sourcemode.assets.judge import make_set  # noqa: E402
from sourcemode.assets.looks import reference  # noqa: E402
from sourcemode.assets.lora import resolve_lora  # noqa: E402
from sourcemode.assets.render import t2i_workflow  # noqa: E402
from sourcemode.config import load_config, outputs_dir  # noqa: E402
from sourcemode.gates.identity import _get_face_app, cosine, embed_image  # noqa: E402
from sourcemode.library import find_set, write_set_json  # noqa: E402
from sourcemode.render.client import ComfyUIClient  # noqa: E402

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
SHEET_ONLY = "--sheet-only" in sys.argv
if len(ARGS) < 2:
    raise SystemExit(__doc__ + "\nstories: " + ", ".join(STORIES))
CHAR, STORY_NAME = ARGS[0].lower(), ARGS[1].lower()
if STORY_NAME not in STORIES:
    raise SystemExit(f"no story {STORY_NAME}; stories: {', '.join(STORIES)}")
ONLY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), None)
SECTION = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--section=")), None)
RETRY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--retry=")), [])
REJECT = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--reject=")), [])
MAX_ATTEMPTS = 2      # "if a shot doesn't work redo it one time before moving on"
FACE_MIN = 0.25       # a tie-breaker between seeds, never a verdict: his eye picks from everything that passes
FACE_SIDE_MIN = 0.15  # a true profile scores 0.22-0.25 against a frontal reference and is still her
YOUNG_FLAG = 20       # Jeremy, 2026-11-10: "The floor should be like 20 because 18 is a fucking adult"
W, H = 1024, 1536

story = STORIES[STORY_NAME]
look = story.look(CHAR)
if look is None:
    raise SystemExit(f"story {STORY_NAME} has no look for {CHAR}")
SHOTS: tuple[Shot, ...] = story.shots
IDS = [s.id for s in SHOTS]
assert len(IDS) == len(set(IDS)), "duplicate shot id"
BY_ID = {s.id: s for s in SHOTS}

cfg = load_config()
OUT_ROOT = outputs_dir(cfg)
lora = resolve_lora(cfg, CHAR)
if not lora:
    raise SystemExit(f"{CHAR} has no locked LoRA")
face_ref = reference(CHAR)
if face_ref is None:
    raise SystemExit(f"{CHAR} has no face reference to score against")
d = find_set(cfg, CHAR, "video", f"{STORY_NAME}-story", create=True)
write_set_json(d, character=CHAR, kind="video", name=f"{STORY_NAME}-story", date=d.name[:10],
               outfit=look.outfit, hair=look.hair)
LOG = d / "run.log"
SHOTS_JSON = d / "shots.json"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def text_of(shot: Shot) -> str:
    return story.render(shot, look)


def prompt_for(shot: Shot) -> str:
    trig = lora.get("trigger") or CHAR
    room = story.close_room if "close" in shot.flags else story.room
    hair, _ = story.hair_outfit(shot, look)
    return (f"{trig}, {clause(CHAR)}, {hair}, {text_of(shot)}, {HANDS}. {room}. Photorealistic, natural skin "
            f"texture, sharp focus.")


def negative_for(shot: Shot) -> str:
    neg = NEG_BASE
    if "him" not in shot.flags:
        neg += ", " + NEG_NOMAN
    if story.negative:
        neg += ", " + story.negative
    if look.negative:
        neg += ", " + look.negative
    if "nude" in shot.flags:
        neg += ", " + NEG_NUDE
    if "close" in shot.flags:
        neg += ", full body, full length, wide shot, her legs, her shoes"
    if shot.negative:
        neg += ", " + shot.negative
    extra = appearance_negative(CHAR)
    return neg + (", " + extra if extra else "")


def t2i_wf(shot: Shot, seed: int) -> dict:
    return t2i_workflow(cfg, prompt_for(shot), seed, f"sourcemode/{CHAR}_{STORY_NAME}", lora_path=lora["path"],
                        negative=negative_for(shot), width=W, height=H,
                        extra_loras=((GNASS, GNASS_STRENGTH),) if "nude" in shot.flags and GNASS_STRENGTH else ())


record: dict = json.loads(SHOTS_JSON.read_text(encoding="utf-8")) if SHOTS_JSON.is_file() else {}
for s in SHOTS:
    record.setdefault(s.id, {"attempts": [], "kept": None})


def save() -> None:
    SHOTS_JSON.write_text(json.dumps(record, indent=1), encoding="utf-8")


def face_floor(sid: str) -> float:
    fl = BY_ID[sid].flags
    if "face_hidden" in fl:
        return -1.0
    return FACE_SIDE_MIN if "face_low" in fl else FACE_MIN


def passes(sid: str, a: dict) -> bool:
    """Her face and age pass, judged against the CURRENT floors, not the flag stored when it rendered."""
    if a.get("why") == "no image":
        return False
    if "face_hidden" in BY_ID[sid].flags:
        return True
    young = a.get("age") is not None and a["age"] < YOUNG_FLAG
    return bool(a.get("face") is not None and a["face"] >= face_floor(sid) and not young)


def on_story(sid: str, a: dict) -> bool:
    """Passes AND was not rejected by eye after the audit."""
    return passes(sid, a) and not a.get("reject")


def kept_of(sid: str) -> dict | None:
    ok = [a for a in record[sid]["attempts"] if on_story(sid, a)]
    return max(ok, key=lambda a: a.get("face") or 0.0) if ok else None


for s in SHOTS:
    for a in record[s.id]["attempts"]:
        if a["file"][:-4] in REJECT and not a.get("reject"):
            a["reject"] = True
            a["ok"] = False
            a["why"] = "rejected by eye"
    k = kept_of(s.id)
    record[s.id]["kept"] = k["file"] if k else None
save()


def selected(sid: str) -> bool:
    if ONLY is not None:
        return sid in ONLY
    if SECTION is not None:
        return sid[0] in SECTION
    return True


todo = [s for s in SHOTS if selected(s.id)]
if not SHEET_ONLY:
    plan = []
    for s in todo:
        n = len(record[s.id]["attempts"])
        if s.id in RETRY:
            if n >= MAX_ATTEMPTS + 2:
                log(f"  {s.id}: already {n} attempts, no retry left")
                continue
            plan.append((s, 1))
        elif kept_of(s.id) is None and n < MAX_ATTEMPTS:
            plan.append((s, MAX_ATTEMPTS - n))
    log(f"{CHAR} {STORY_NAME}: {len(plan)} shots to render (up to {sum(p[1] for p in plan)} renders), of "
        f"{len(SHOTS)} in the story -> {d}")
    if DRY:
        for s, budget in plan:
            log(f"  would render {s.id} x{budget}: {prompt_for(s)}")
            log(f"    negative: {negative_for(s)}")
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

    for s, budget in plan:
        for _ in range(budget):
            n = len(record[s.id]["attempts"]) + 1
            out = d / f"{s.id}__a{n}.png"
            seed = rng.randrange(1, 2**31)
            t0 = time.monotonic()
            wf = t2i_wf(s, seed)
            files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
            if not files:
                log(f"  {s.id} a{n}: ComfyUI returned no image")
                record[s.id]["attempts"].append({"file": out.name, "seed": seed, "face": None, "age": None,
                                                 "young": False, "ok": False, "why": "no image"})
                save()
                continue
            client.fetch(files[0], out)
            out.with_suffix(".txt").write_text(prompt_for(s), encoding="utf-8")
            face, age = score(out)
            a = {"file": out.name, "seed": seed, "face": face, "age": age, "young": False, "ok": False, "why": ""}
            a["young"] = bool(age is not None and age < YOUNG_FLAG)
            a["ok"] = on_story(s.id, a)
            a["why"] = "" if a["ok"] else ("no face" if face is None else "YOUNG" if a["young"]
                                           else f"face {face} < {face_floor(s.id)}")
            record[s.id]["attempts"].append(a)
            k = kept_of(s.id)
            record[s.id]["kept"] = k["file"] if k else None
            save()
            log(f"  {s.id} a{n}: face {face}  age {age}  {'kept' if a['ok'] else a['why']}  "
                f"{time.monotonic() - t0:.0f}s")
            if a["ok"] and s.id not in RETRY:
                break
        if kept_of(s.id) is None:
            log(f"  {s.id}: GAVE UP after {len(record[s.id]['attempts'])} attempts")

# --- the sheet and the judge set: one tile per shot, every passing attempt to the judge ----
TW, TH, COLS = 300, 450, 6
rows = (len(SHOTS) + COLS - 1) // COLS
sheet = Image.new("RGB", (TW * COLS, TH * rows), "black")
dr = ImageDraw.Draw(sheet)
items = []
for i, s in enumerate(SHOTS):
    k = kept_of(s.id)
    att = record[s.id]["attempts"]
    best = k or (max((a for a in att if a.get("face") is not None), key=lambda a: a["face"], default=None))
    x, y = (i % COLS) * TW, (i // COLS) * TH
    if best and (d / best["file"]).is_file():
        im = Image.open(d / best["file"]).convert("RGB")
        im.thumbnail((TW, TH))
        sheet.paste(im, (x, y))
    colour = "black" if k else ("red" if any(a.get("young") for a in att) else "gray")
    rejected = sum(1 for a in att if a.get("reject"))
    dr.rectangle([x, y, x + TW, y + 18], fill=colour)
    dr.text((x + 4, y + 3), f"{s.id} / {len(att)} tries{f' ({rejected} rej)' if rejected else ''} / face "
                            f"{best['face'] if best else None} age {best['age'] if best else None}"
                            f"{'' if k else ' NO KEEP'}", fill="yellow")
    for a in att:
        if passes(s.id, a) and (d / a["file"]).is_file():
            items.append({"id": a["file"][:-4], "path": d / a["file"], "arm": "story", "group": s.id})
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")
if items and not DRY:
    make_set(OUT_ROOT / "judge", f"story_{CHAR}_{STORY_NAME}", f"{CHAR.title()} - {story.title}", items,
             question="Keep this one? K = yes, X = re-roll it.", priority=5,
             meta={"character": CHAR, "renders_dir": d})
    log(f"{sum(1 for s in SHOTS if kept_of(s.id))} of {len(SHOTS)} shots kept -> judge set "
        f"story_{CHAR}_{STORY_NAME}")
log("STORYDONE")
