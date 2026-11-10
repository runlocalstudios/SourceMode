"""One office photo story for a character, continuing her office desk set.

    python scripts/video/office_story.py <character> [--section=a,p,q,e,f] [--only=id,id] [--retry=id,id] [--dry-run] [--sheet-only]

Jeremy, 2026-11-10: "a set starting from the set we chose that involves her
showing off her body ... followed by her taking off the man's pants ... she
first grabs it, spits on it as lube and a number of handjob pics ... Then shift
to blowjob shots ... Then the sex poses either on the desk or the floor - mix of
vaginal and anal penetration ... all pics with her face visible facing the
viewer, then at the end ... he shoots a massive cum load all over her stomach,
chest and face ... retry only 3 times for each shot before moving on."
Later the same day: "this is supposed to be POV ... all of the hand job and
blow job shots except for the side view ones are all supposed to be POV";
"All anal and vaginal she is to be facing him"; "Run like 4 and see if what
you created works or not"; "start a list of those combinations".

Built on the recipes that were proven by eye on 2026-11-10 (docs/story-recipes.md):

  a  showing off          text-to-image, her LoRA (GNASS 0.6 once she is topless)
  p  pants, handjob,      the EDIT CHAIN from an office POV plate of her between his
     blowjob from his     knees: Qwen-Image-Edit 2511, her LoRA + the "all included"
     eyes                 act LoRA at 0.8, each step editing the previous step's kept
                          render, so her face and the room carry through (0.63-0.71)
  q  sex facing him,      text-to-image with QWEN 4 PLAY at 1.0 and its position
     rug and desk         triggers - the only LoRA that attaches him and draws penetration
  e  her back on the      text-to-image, QWEN 4 PLAY, from his eyes standing between her
     desk                 raised legs (her face upright), and the side view of the desk
  f  the finish           text-to-image, QWEN 4 PLAY, same two framings

Each shot gets at most MAX_ATTEMPTS renders (the first plus three retries). An
attempt is kept when her face scores and reads adult; every kept attempt goes to
the judge; the best kept one is the shot's tile, and the parent of the next edit
step. `--section` runs one section at a time so each batch is small enough to
look at in full. `--retry` spends another attempt on a shot whose kept render
missed the content.

QWEN 4 PLAY at 1.0 is above the shoot composition cap (0.6 for a second LoRA):
its strength is set on its own node after the graph is built, as the probe did,
and only for this story.

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
from sourcemode.render.passes import build_edit_workflow

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
SHEET_ONLY = "--sheet-only" in sys.argv
if len(ARGS) != 1:
    raise SystemExit(__doc__)
CHAR = ARGS[0].lower()
ONLY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), None)
SECTION = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--section=")), None)
RETRY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--retry=")), [])
MAX_ATTEMPTS = 4      # the first render plus three retries
FACE_MIN = 0.30       # a tie-breaker between seeds, never a verdict: his eye picks from everything that passes
FACE_SIDE_MIN = 0.30
YOUNG_FLAG = 20       # Jeremy, 2026-11-10: "The floor should be like 20 because 18 is a fucking adult"
W, H = 1024, 1536

NSFW = "nsfw\\"
GNASS = NSFW + "qimage2512_gnass.safetensors"           # nudity on the show-off shots, at the cap
Q4P = NSFW + "qimage2512_qwen4play_v2.safetensors"       # QWEN 4 PLAY 2512 v2: the act LoRA, at 1.0
ALLIN = NSFW + "qedit2511_all_included_v2.safetensors"   # the Edit-2511 act LoRA for the chain, at 0.8
# the office POV plate the chain starts from: her between his knees, his shorts at the bottom of the frame
PLATE = Path("C:/dev/sourcemode/library") / CHAR / "2026-11-10_shoot_office-pov" / "office_pov_01.png"

# --- the set's continuity ---------------------------------------------------
HAIR = "her hair worn down with wavy curls throughout"
OUTFIT = ("a black tailored vest buttoned over a lace bralette, a tight red pencil mini skirt and "
          "sheer black stockings")
TOPLESS = ("topless with her bare breasts showing, wearing only the tight red pencil mini skirt and sheer "
           "black stockings")
SKIRT_UP = ("topless with her bare breasts showing, her red mini skirt pushed up around her waist, her sheer "
            "black stockings still on, otherwise naked")
HIM = "a fit man in a white dress shirt with the sleeves rolled up, naked from the waist down"
COCK = "his thick erect penis"
PHOTOG = "picture by a photographer shooting the set"
SIDE = "picture by a photographer shooting the set from the side at her eye level, her face in profile"
RUG = "on the cream wool rug"
PLEASURE = "her face flushed with pleasure, eyes heavy-lidded, lips parted in a soft moan"
# from above his head, him lying on his back (the rug and desk squats)
OVER_HIM = "picture from above his head looking at her"
DESK_POV = ("close point-of-view photo from the eyes of the man standing at the end of the desk between her "
            "raised legs, looking down the length of her body at her, his bare thighs at the bottom of the "
            "frame, his face out of frame; she lies on her back on the big walnut desk, her legs spread wide "
            "and held up, her face looking up at the camera")
DESK_SIDE = (f"picture from the side of the desk, the desk running left to right across the frame: she lies on "
             f"her back along the desk with her head on the left and her legs raised and spread on the right, "
             f"her face turned toward the camera; {HIM} stands at the right end of the desk between her legs")
KEEP = "Keep her face, her hair, her bare breasts, the room and the framing exactly as they are."
CUM = ("her hand jerking {cock} held just above her vagina as he ejaculates, ropes of thick white semen landing "
       "across her stomach, her breasts and her face, {eyes}, loving it")

# A shot is (id, kind, lora, text):
#   kind "t2i":  lora is None (hers alone), "gnass" (0.6) or "q4p" (1.0, text starts with its triggers)
#   kind "edit": lora is the parent shot id (None = the plate); text is the instruction
STORY: tuple[tuple[str, str, str | None, str], ...] = (
    # --- a: showing off her body -------------------------------------------------
    ("a01_front", "t2i", None, f"{PHOTOG}: she stands beside the big desk facing the camera, three-quarter "
                               f"length, hands on her hips, one hip cocked, a teasing smile, in {OUTFIT}"),
    ("a02_side", "t2i", None, f"{SIDE}: she stands beside the desk in profile, waist up, her back arched and "
                              f"chest out, turning her face to smile at the camera, in {OUTFIT}"),
    ("a03_back", "t2i", None, f"{PHOTOG}: seen from behind, three-quarter length, standing at the desk with her "
                              f"back to the camera, the tight red skirt hugging her bottom, looking back over "
                              f"her shoulder at the camera, in {OUTFIT}"),
    ("a04_vest_open", "t2i", "gnass", f"{PHOTOG}: she sits on the edge of the desk facing the camera, waist up, "
                                      f"her black vest unbuttoned and hanging open over her bare breasts with "
                                      f"nothing beneath it, her nipples showing between the open sides, biting "
                                      f"her lower lip with her mouth closed, a tight red pencil mini skirt and "
                                      f"sheer black stockings"),
    ("a05_topless_front", "t2i", "gnass", f"{PHOTOG}: she stands facing the camera, three-quarter length, "
                                          f"{TOPLESS}, her hands sliding up her sides, smiling at the camera"),
    ("a06_topless_side", "t2i", "gnass", f"{SIDE}: she stands in profile, waist up, {TOPLESS}, her back arched, "
                                         f"turning her face to the camera"),
    ("a07_topless_back", "t2i", "gnass", f"{PHOTOG}: seen from behind, three-quarter length, {TOPLESS}, lifting "
                                         f"her hair with both hands, looking back over her shoulder at the "
                                         f"camera"),
    # --- p: from his eyes, the edit chain -----------------------------------------
    ("p01_topless", "edit", None, "Remove her blazer and her bra so she is topless with her bare breasts showing, "
                                  "and change her skirt to red. Keep her face, her hair, her pose, the room and "
                                  "the man's legs exactly as they are."),
    ("p02_free", "edit", "p01_topless", f"Remove the man's navy shorts. His erect penis, proportionate to his body "
                                        f"and of realistic size, stands up from between his thighs at the bottom "
                                        f"of the frame, and she wraps one hand around it, looking up into the "
                                        f"camera. {KEEP}"),
    ("p03_spit", "edit", "p02_free", f"She holds {COCK} in one hand and spits onto the head of it, a string of "
                                     f"saliva running from her lips to the penis, her eyes on the camera. {KEEP}"),
    ("p04_stroke", "edit", "p02_free", f"handjob: she strokes {COCK} with one hand, the shaft glistening wet with "
                                       f"saliva, looking up into the camera and loving it. {KEEP}"),
    ("p05_balls", "edit", "p02_free", f"Add his testicles, visible below the base of {COCK}; she holds the penis up "
                                      f"with one hand and cups his testicles in the palm of her other hand, "
                                      f"looking up into the camera. {KEEP}"),
    ("p06_two_hands", "edit", "p02_free", f"handjob: two hands - both of her hands grip the shaft of {COCK}, "
                                          f"stacked one above the other, the head showing above her top hand, "
                                          f"looking up into the camera with a hungry smile. {KEEP}"),
    ("p07_lick", "edit", "p02_free", f"Her tongue is out, licking the head of {COCK}, one hand holding it at the "
                                     f"base, her eyes heavy-lidded looking up into the camera. {KEEP}"),
    ("p08_tip", "edit", "p02_free", f"She leans in and takes just the head of {COCK} between her lips, her eyes "
                                    f"looking up into the camera. {KEEP}"),
    # a1 of both kept one hand on the shaft: the hands are placed first, then the mouth
    ("p09_suck_hands_on_legs", "edit", "p08_tip", f"Move both of her hands onto the tops of his thighs, palms flat "
                                                  f"on his thighs, no hand touching the penis; the head of {COCK} "
                                                  f"stays in her mouth, her eyes looking up into the camera. "
                                                  f"{KEEP}"),
    ("p10_suck_two_hands", "edit", "p06_two_hands", f"She keeps both hands stacked on the shaft and lowers her "
                                                    f"mouth onto it, the head of {COCK} between her lips above "
                                                    f"her top hand, her eyes looking up into the camera. {KEEP}"),
    # --- q: sex facing him, squatting over him, rug and desk ----------------------
    ("q01_rug_tip", "t2i", "q4p", f"c0wg1rl, {OVER_HIM}: {HIM} lies on his back {RUG}, she squats over his hips "
                                  f"facing him with her feet planted flat on the rug either side of him and her "
                                  f"knees spread wide, {SKIRT_UP}, one hand guiding just the head of {COCK} into "
                                  f"her vagina, her vagina fully visible between her spread thighs, her face to "
                                  f"the camera flushed with anticipation, lips parted"),
    ("q02_rug_deep", "t2i", "q4p", f"c0wg1rl, {OVER_HIM}: {HIM} lies on his back {RUG}, she squats over his hips "
                                   f"facing him, feet planted flat on the rug, knees spread wide, {SKIRT_UP}, "
                                   f"lowered all the way down with {COCK} deep inside her vagina, her stretched "
                                   f"labia fully visible, {PLEASURE}, her face to the camera"),
    ("q03_rug_pleasure", "t2i", "q4p", f"c0wg1rl, {OVER_HIM}: {HIM} lies on his back {RUG}, she squats over him "
                                       f"facing him, feet planted, knees wide, {SKIRT_UP}, riding {COCK} deep in "
                                       f"her vagina, her eyes half closed in pleasure, lips parted in a soft "
                                       f"moan, her face flushed, her hands squeezing her own breasts, her face to "
                                       f"the camera"),
    ("q04_desk_tip", "t2i", "q4p", f"c0wg1rl, picture from beside the desk: {HIM} lies on his back on the big "
                                   f"walnut desk, she squats over his hips on the desk facing him with her feet "
                                   f"planted flat on the desktop and her knees spread wide, {SKIRT_UP}, guiding "
                                   f"just the head of {COCK} into her vagina, her vagina fully visible, her face "
                                   f"turned to the camera"),
    ("q05_desk_deep", "t2i", "q4p", f"c0wg1rl, picture from beside the desk: {HIM} lies on his back on the big "
                                    f"walnut desk, she squats over him on the desk facing him, feet planted on "
                                    f"the desktop, knees wide, {SKIRT_UP}, {COCK} deep inside her vagina, her "
                                    f"stretched labia visible, bouncing on it, {PLEASURE}, her face to the "
                                    f"camera"),
    ("q06_rug_anal_tip", "t2i", "q4p", f"c0wg1rl, {OVER_HIM}: {HIM} lies on his back {RUG}, she squats over his "
                                       f"hips facing him, feet planted flat on the rug, knees spread wide, "
                                       f"{SKIRT_UP}, one hand guiding just the head of {COCK} against her anus, "
                                       f"her wet vagina fully visible just above it, her face turned to the "
                                       f"camera, lips parted"),
    ("q07_rug_anal_deep", "t2i", "q4p", f"c0wg1rl, {OVER_HIM}: {HIM} lies on his back {RUG}, she squats over him "
                                        f"facing him, feet planted, knees wide, {SKIRT_UP}, lowered all the way "
                                        f"down with {COCK} deep inside her anus, her wet vagina fully visible "
                                        f"above it, {PLEASURE}, her face to the camera"),
    ("q08_rug_anal_squirt", "t2i", "q4p", f"c0wg1rl, {OVER_HIM}: {HIM} lies on his back {RUG}, she squats over "
                                          f"him facing him, feet planted, knees wide, {SKIRT_UP}, {COCK} deep "
                                          f"inside her anus, a clear stream of fluid squirting from her vagina, "
                                          f"her face to the camera flushed and lost in pleasure, eyes "
                                          f"heavy-lidded, lips parted"),
    ("q09_desk_anal_deep", "t2i", "q4p", f"c0wg1rl, picture from beside the desk: {HIM} lies on his back on the "
                                         f"big walnut desk, she squats over him on the desk facing him, feet "
                                         f"planted on the desktop, knees wide, {SKIRT_UP}, {COCK} deep inside "
                                         f"her anus, her wet vagina fully visible above it, {PLEASURE}, her face "
                                         f"to the camera"),
    ("q10_desk_anal_squirt", "t2i", "q4p", f"c0wg1rl, picture from beside the desk: {HIM} lies on his back on the "
                                           f"big walnut desk, she squats over him facing him, feet planted on "
                                           f"the desktop, knees wide, {SKIRT_UP}, {COCK} deep inside her anus, a "
                                           f"clear stream of fluid squirting from her vagina, her face to the "
                                           f"camera flushed with pleasure, eyes heavy-lidded, lips parted"),
    # --- e: her back on the desk, him standing beside it ----------------------------
    ("e01_desk_tip_pov", "t2i", "q4p", f"pov, m15510n4ry, {DESK_POV}, {SKIRT_UP}, just the head of {COCK} pressing "
                                       f"into her vagina, her vagina in full view, her face flushed with "
                                       f"anticipation, lips parted"),
    ("e02_desk_deep_pov", "t2i", "q4p", f"pov, m15510n4ry, {DESK_POV}, {SKIRT_UP}, {COCK} deep inside her vagina, "
                                        f"her labia stretched around the shaft, {PLEASURE}"),
    ("e03_desk_deep_side", "t2i", "q4p", f"m15510n4ry, {DESK_SIDE}, {SKIRT_UP}, {COCK} deep inside her vagina, "
                                         f"thrusting, her face turned to the camera flushed with pleasure, lips "
                                         f"parted"),
    ("e04_desk_anal_tip_pov", "t2i", "q4p", f"pov, {DESK_POV}, {SKIRT_UP}, just the head of {COCK} entering her "
                                            f"anus, her wet vagina in full view above it, her face turned up to "
                                            f"the camera, lips parted"),
    ("e05_desk_anal_deep_pov", "t2i", "q4p", f"pov, {DESK_POV}, {SKIRT_UP}, {COCK} deep inside her anus, her wet "
                                             f"vagina in full view above it, {PLEASURE}"),
    ("e06_desk_anal_side", "t2i", "q4p", f"m15510n4ry, {DESK_SIDE}, {SKIRT_UP}, {COCK} deep inside her anus, her "
                                         f"wet vagina visible above it, her face turned to the camera flushed "
                                         f"with pleasure, eyes heavy-lidded, lips parted in a soft moan"),
    ("e07_desk_anal_squirt_pov", "t2i", "q4p", f"pov, {DESK_POV}, {SKIRT_UP}, {COCK} deep inside her anus, a clear "
                                               f"stream of fluid squirting from her vagina, her face flushed and "
                                               f"lost in pleasure, eyes heavy-lidded, lips parted"),
    # --- f: the finish -----------------------------------------------------------------
    ("f01_pullout_pov", "t2i", "q4p", f"pov, {DESK_POV}, {SKIRT_UP}, he has just pulled {COCK} out of her anus and "
                                      f"holds it just above her vagina, her hand reaching down to wrap around it, "
                                      f"her eyes on the camera, lips parted"),
    ("f02_cum_pov", "t2i", "q4p", f"pov, {DESK_POV}, {SKIRT_UP}, {CUM.format(cock=COCK, eyes='her eyes on the camera')}"),
    ("f03_cum_side", "t2i", "q4p", f"{DESK_SIDE}, {SKIRT_UP}, "
                                   f"{CUM.format(cock=COCK, eyes='her face turned to the camera')}"),
    ("f04_covered_pov", "t2i", "q4p", f"pov, {DESK_POV}, {SKIRT_UP}, her stomach, her breasts and her face "
                                      f"streaked with thick white semen, {COCK} still in her hand just above her "
                                      f"vagina, smiling up at the camera"),
)
IDS = [s[0] for s in STORY]
assert len(IDS) == len(set(IDS)), "duplicate shot id"
BY_ID = {s[0]: s for s in STORY}

NEG_BASE = ("different person, different face, changed hair, extra penis, extra hands, extra limbs, deformed "
            "genitals, deformed hands, blurry, low quality, cartoon, anime, watermark, text, condom, tears, "
            "crying, watering eyes, toothy grin, childlike, child, underage")
NEG_BARE = "bra, bralette, vest, blouse, shirt on her, top on her"   # once she is topless, nothing comes back
NEG_POV = "the man's face, his face, far away, distant, standing, office chair behind her, a second man"
NEG_EDIT = ("different person, different face, changed hair, bra, blazer, clothes on her chest, condom, "
            "deformed genitals, deformed hands, extra hands, extra limbs, blurry, low quality, cartoon, "
            "watermark, text, tears, crying, watering eyes, childlike, child, underage")

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
               outfit=OUTFIT, hair=HAIR, plate=str(PLATE))
LOG = d / "run.log"
SHOTS = d / "shots.json"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def prompt_for(text: str) -> str:
    trig = lora.get("trigger") or CHAR
    return f"{trig}, {clause(CHAR)}, {HAIR}, {text}. {OFFICE_IN}. Photorealistic, natural skin texture, sharp focus."


def negative_for(sid: str, lk: str | None) -> str:
    neg = NEG_BASE
    if lk and not sid.startswith("a04"):
        neg += ", " + NEG_BARE
    if "_pov" in sid:
        neg += ", " + NEG_POV
    extra = appearance_negative(CHAR)
    return neg + (", " + extra if extra else "")


def splice_lora(wf: dict, after: str, path: str, strength: float, new: str = "900") -> dict:
    """One more LoraLoaderModelOnly between node `after` and whatever read its model."""
    nodes = wf["nodes"] if "nodes" in wf else wf
    for node in nodes.values():
        for k, v in node.get("inputs", {}).items():
            if k == "model" and v == [after, 0]:
                node["inputs"][k] = [new, 0]
    nodes[new] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": [after, 0], "lora_name": path, "strength_model": float(strength)}}
    return wf


def t2i_wf(sid: str, lk: str | None, text: str, seed: int) -> dict:
    path, strength = {None: ("", 0.0), "gnass": (GNASS, 0.6), "q4p": (Q4P, 1.0)}[lk]
    wf = t2i_workflow(cfg, prompt_for(text), seed, f"sourcemode/{CHAR}_story", lora_path=lora["path"],
                      negative=negative_for(sid, lk), width=W, height=H,
                      extra_loras=((path, min(strength, 0.6)),) if path else ())
    if strength > 0.6:
        # the act LoRA at its author's strength, set on its own node after the cap was checked
        nodes = wf["nodes"] if "nodes" in wf else wf
        for node in nodes.values():
            if node.get("class_type") == "LoraLoaderModelOnly" and node["inputs"].get("lora_name") == path:
                node["inputs"]["strength_model"] = float(strength)
    return wf


def edit_wf(instr: str, seed: int, image: str) -> dict:
    wf, _ = build_edit_workflow(cfg, CHAR, instruction=instr, negative=NEG_EDIT, image_name=image,
                                image_lora=lora["path"], seed=seed, render_pass="medium",
                                filename_prefix=f"sourcemode/{CHAR}_story_edit")
    nodes = wf["nodes"] if "nodes" in wf else wf
    after = "222" if "222" in nodes else "161"
    return splice_lora(wf, after, ALLIN, 0.8)


record: dict = json.loads(SHOTS.read_text(encoding="utf-8")) if SHOTS.is_file() else {}
for sid, _, _, _ in STORY:
    record.setdefault(sid, {"attempts": [], "kept": None})


def save() -> None:
    SHOTS.write_text(json.dumps(record, indent=1), encoding="utf-8")


def face_floor(sid: str) -> float:
    return FACE_SIDE_MIN if sid.endswith("_side") else FACE_MIN


def passes(sid: str, a: dict) -> bool:
    """Judged against the CURRENT floors, not the flag stored when it rendered."""
    young = a.get("age") is not None and a["age"] < YOUNG_FLAG
    return bool(a.get("face") is not None and a["face"] >= face_floor(sid) and not young)


def kept_of(sid: str) -> dict | None:
    ok = [a for a in record[sid]["attempts"] if passes(sid, a)]
    return max(ok, key=lambda a: a["face"]) if ok else None


def selected(sid: str) -> bool:
    if ONLY is not None:
        return sid in ONLY
    if SECTION is not None:
        return sid[0] in SECTION
    return True


todo = [s for s in STORY if selected(s[0])]
if not SHEET_ONLY:
    plan = []
    for sid, kind, lk, text in todo:
        n = len(record[sid]["attempts"])
        if sid in RETRY:
            if n >= MAX_ATTEMPTS:
                log(f"  {sid}: already {n} attempts, no retry left")
                continue
            plan.append((sid, kind, lk, text, 1))
        elif kept_of(sid) is None and n < MAX_ATTEMPTS:
            plan.append((sid, kind, lk, text, MAX_ATTEMPTS - n))
    log(f"{CHAR}: {len(plan)} shots to render (up to {sum(p[4] for p in plan)} renders), of {len(STORY)} in the "
        f"story -> {d}")
    if DRY:
        for sid, kind, lk, text, budget in plan:
            src = (text if kind == "edit" else prompt_for(text))[:150]
            log(f"  would render {sid} x{budget} ({kind} {lk}): {src}...")
        raise SystemExit(0)
    if any(kind == "edit" for _, kind, _, _, _ in plan) and not PLATE.is_file():
        raise SystemExit(f"no plate {PLATE}")

    client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    ref_emb = embed_image(face_ref)
    app = _get_face_app()
    rng = random.SystemRandom()
    uploaded: dict[str, str] = {}

    def upload(p: Path) -> str:
        if str(p) not in uploaded:
            uploaded[str(p)] = client.upload_image(p)
        return uploaded[str(p)]

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

    for sid, kind, lk, text, budget in plan:
        for _ in range(budget):
            n = len(record[sid]["attempts"]) + 1
            out = d / f"{sid}__a{n}.png"
            seed = rng.randrange(1, 2**31)
            t0 = time.monotonic()
            src = None
            if kind == "edit":
                parent = kept_of(lk) if lk else None
                if lk and parent is None:
                    log(f"  {sid}: nothing kept for {lk} to edit from")
                    break
                src = (d / parent["file"]) if parent else PLATE
                wf = edit_wf(text, seed, upload(src))
            else:
                wf = t2i_wf(sid, lk, text, seed)
            files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
            if not files:
                log(f"  {sid} a{n}: ComfyUI returned no image")
                record[sid]["attempts"].append({"file": out.name, "seed": seed, "face": None, "age": None,
                                                "young": False, "ok": False, "why": "no image"})
                save()
                continue
            client.fetch(files[0], out)
            out.with_suffix(".txt").write_text(text if kind == "edit" else prompt_for(text), encoding="utf-8")
            face, age = score(out)
            young = bool(age is not None and age < YOUNG_FLAG)
            ok = bool(face is not None and face >= face_floor(sid) and not young)
            why = "" if ok else ("no face" if face is None else "YOUNG" if young else f"face {face} < {face_floor(sid)}")
            record[sid]["attempts"].append({"file": out.name, "seed": seed, "face": face, "age": age,
                                            "young": young, "ok": ok, "why": why, "kind": kind, "lora": lk,
                                            "from": (src.name if src else None)})
            k = kept_of(sid)
            record[sid]["kept"] = k["file"] if k else None
            save()
            log(f"  {sid} a{n}: face {face}  age {age}  {'kept' if ok else why}  {time.monotonic() - t0:.0f}s")
            if ok and sid not in RETRY:
                break
        if kept_of(sid) is None:
            log(f"  {sid}: GAVE UP after {len(record[sid]['attempts'])} attempts")

# --- the sheet and the judge set: one tile per shot, every passing attempt to the judge ----
TW, TH, COLS = 300, 450, 6
rows = (len(STORY) + COLS - 1) // COLS
sheet = Image.new("RGB", (TW * COLS, TH * rows), "black")
dr = ImageDraw.Draw(sheet)
items = []
for i, (sid, _, _, _) in enumerate(STORY):
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
    # every attempt that passes goes to the judge: "I don't want you throwing out good images for no reason"
    for a in att:
        if passes(sid, a) and (d / a["file"]).is_file():
            items.append({"id": a["file"][:-4], "path": d / a["file"], "arm": "story", "group": sid})
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")
if items and not DRY:
    make_set(OUT_ROOT / "judge", f"story_{CHAR}_office", f"{CHAR.title()} - office story", items,
             question="Keep this one? K = yes, X = re-roll it.", priority=5,
             meta={"character": CHAR, "renders_dir": d})
    log(f"{sum(1 for s in STORY if kept_of(s[0]))} of {len(STORY)} shots kept -> judge set story_{CHAR}_office")
log("STORYDONE")
