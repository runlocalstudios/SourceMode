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
best kept attempt is the shot's tile, every kept attempt goes to the judge; a shot with no kept attempt after four is
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
FACE_MIN = 0.30       # only a tie-breaker: her kneeling looking-up shots scored 0.34-0.48 and were all her (j1351)
FACE_SIDE_MIN = 0.30  # a profile scores low against a frontal reference: a02_side a1 was her at 0.464
YOUNG_FLAG = 20       # Jeremy, 2026-11-10: "The floor should be like 20 because 18 is a fucking adult"

GNASS = "nsfw\\qimage2512_gnass.safetensors"
GNASS_MAX = 0.6  # the composition rule caps a second LoRA at 0.6 (render.workflow.MAX_OTHER_STRENGTH); 0.8 raised on j1349
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
# every facing-him render of j1351 kept his trousers ON under her: the sex shots say so outright
HIM_BARE = f"{HIM}, naked from the waist down with his trousers off"
COCK = "his thick eight-inch erect penis, large and prominent"
PHOTOG = "picture by a photographer shooting the set"
SIDE = "picture by a photographer shooting the set from the side at her eye level, her face in profile"
POV = "POV picture from the man's eyes looking down"
KNEEL = f"she kneels on the cream wool rug in front of {HIM}, who stands by the desk with his trousers down"
# From his eyes, as the office pov shoot frames it (shoots._POV / _HIS): his own thighs along the
# bottom of the frame put the camera in his head, and his face stays out of frame.
POV_SEAT = ("close point-of-view photo looking down from the eyes of a man sitting in the big leather office "
            "chair with his knees spread, his own thighs along both sides of the bottom of the frame, his face "
            "out of frame")
TROUSERS_DOWN = "his suit trousers and boxer briefs pushed down around his ankles"
KNEEL_POV = "she kneels on the cream wool rug right between his spread knees, close, facing the camera"
COCK_POV = "his thick eight-inch erect penis rising from between his thighs at the bottom of the frame"
SEATED_SIDE = (f"{HIM} sits in the big leather office chair with his trousers down around his ankles and his "
               f"knees spread, she kneels on the cream wool rug between his knees, both seen from the side")
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
    # a1 kept the bralette on and put her tongue out: the bralette is gone now and the vest hangs open on bare skin
    ("a04_vest_open", 0.6, f"{PHOTOG}: she sits on the edge of the desk facing the camera, waist up, her black "
                           f"vest unbuttoned and hanging open over her bare breasts with nothing beneath it, "
                           f"her nipples showing between the open sides, biting her lower lip with her mouth "
                           f"closed, a tight red pencil mini skirt and sheer black stockings"),
    ("a05_topless_front", 0.6, f"{PHOTOG}: she stands facing the camera, three-quarter length, {TOPLESS}, her "
                               f"hands sliding up her sides, smiling at the camera"),
    ("a06_topless_side", 0.6, f"{SIDE}: she stands in profile, waist up, {TOPLESS}, her back arched, turning "
                              f"her face to the camera"),
    ("a07_topless_back", 0.6, f"{PHOTOG}: seen from behind, three-quarter length, {TOPLESS}, lifting her hair "
                              f"with both hands, looking back over her shoulder at the camera"),
    # --- his pants come off, from his eyes ---
    # Jeremy, 2026-11-10: "this is supposed to be POV, so like he should be either sitting in
    # a chair or sitting on the desk, and she undoes his pants there, and then all of the hand
    # job and blow job shots except for the side view ones are all supposed to be POV."
    ("b01_belt_pov", 0.6, f"{POV_SEAT}, his suit trousers still on, {KNEEL_POV}, {TOPLESS}, her hands undoing "
                          f"his belt buckle, a large bulge straining in his trousers, looking up into the "
                          f"camera with a grin"),
    ("b02_unzip_pov", 0.6, f"{POV_SEAT}, {KNEEL_POV}, {TOPLESS}, her hands tugging his unzipped suit trousers "
                           f"down his thighs, his erection straining against his black boxer briefs, looking "
                           f"up into the camera with a grin"),
    ("b03_release_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, her hands pulling the "
                             f"waistband of his black boxer briefs down as {COCK} springs up between his "
                             f"thighs right in front of her face, her eyes wide, grinning up at the camera"),
    # --- handjob, from his eyes, two side views by the photographer ---
    ("c01_grab_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, wrapping one hand around "
                          f"{COCK_POV}, looking up into the camera with a hungry smile"),
    ("c02_spit_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, holding {COCK_POV} in one hand "
                          f"and spitting onto the head of it, a string of saliva running from her lips to the "
                          f"penis, her eyes on the camera"),
    ("c03_stroke_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, stroking {COCK_POV} with one "
                            f"hand, the shaft glistening with saliva, looking up into the camera"),
    ("c04_stroke_side", 0.6, f"{SIDE}: {SEATED_SIDE}, {TOPLESS}, stroking {COCK} with one hand, the penis seen "
                             f"from the side pointing up at her face"),
    ("c05_balls_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, stroking the shaft of "
                           f"{COCK_POV} with one hand while her other hand cups and rubs his balls, looking up "
                           f"into the camera"),
    ("c06_squeeze_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, her hand gently squeezing "
                             f"his balls, the head of {COCK_POV} resting against her cheek, smiling up at the "
                             f"camera"),
    ("c07_two_hands_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, both of her hands wrapped "
                               f"around {COCK_POV} one above the other, stroking it, the head still showing "
                               f"above her top hand, looking up into the camera"),
    ("c08_two_hands_side", 0.6, f"{SIDE}: {SEATED_SIDE}, {TOPLESS}, both hands wrapped around {COCK} stroking "
                                f"it, the penis seen from the side"),
    ("c09_pov", 0.6, f"{POV}: she kneels between his legs {RUG}, {TOPLESS}, stroking {COCK} with both hands, "
                     f"looking up into the camera"),
    # --- blowjob, from his eyes, two side views by the photographer ---
    ("d01_tip_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, just the head of {COCK_POV} "
                         f"between her lips, her lips closed around the tip only, her eyes looking up into "
                         f"the camera"),
    ("d02_lick_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, her tongue out licking the "
                          f"head of {COCK_POV}, one hand holding it at the base, her eyes on the camera"),
    ("d03_hands_on_legs_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, sucking {COCK_POV} "
                                   f"with the shaft halfway in her mouth, both of her hands resting on his "
                                   f"thighs, no hands on the penis, looking up into the camera"),
    ("d04_one_hand_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, sucking the head of "
                              f"{COCK_POV} with one hand wrapped around the base of the shaft, looking up "
                              f"into the camera"),
    ("d05_two_hands_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, sucking the head of "
                               f"{COCK_POV} with both hands wrapped around the shaft, looking up into the "
                               f"camera"),
    ("d06_side", 0.6, f"{SIDE}: {SEATED_SIDE}, {TOPLESS}, {COCK} halfway into her mouth, her lips stretched "
                      f"around the shaft, seen from the side"),
    ("d07_deep_pov", 0.6, f"{POV_SEAT}, {TROUSERS_DOWN}, {KNEEL_POV}, {TOPLESS}, most of {COCK_POV} inside her "
                          f"mouth, her lips near the base, her cheeks hollowed, her eyes heavy-lidded with pleasure, looking up "
                          f"into the camera"),
    ("d08_deep_side", 0.6, f"{SIDE}: {SEATED_SIDE}, {TOPLESS}, {COCK} all the way in her mouth, her lips at "
                           f"the base, her nose against his body, seen from the side"),
    ("d09_pov", 0.6, f"{POV}: she kneels between his legs {RUG}, {TOPLESS}, her lips wrapped around {COCK}, "
                     f"one hand at the base, looking up into the camera"),
    # --- sex: she faces him on every shot, legs spread and planted, her pussy in his view ---
    # Jeremy, 2026-11-10: "All anal and vaginal she is to be facing him - meaning no bent
    # over shots. So she needs to have her legs spread and planted on the desk or floor
    # and she brings her pussy or ass down onto his cock, he can always see her pussy in
    # all those shots. Before he finishes, her back is on the desk and he is standing next
    # to the desk ... add some poses where she is really looking pleasured. Try to add a
    # few of her squirting while he is deep in her ass too"
    ("s01_rug_tip", 0.6, f"{PHOTOG} from beside his head: {HIM_BARE} lies on his back {RUG}, she squats over his hips "
                         f"facing him with her feet planted flat on the rug either side of him and her knees "
                         f"spread wide, {SKIRT_UP}, one hand guiding just the head of {COCK} into her vagina, "
                         f"her vagina fully visible between her spread thighs, her face turned to the camera"),
    ("s02_rug_deep", 0.6, f"{PHOTOG} from beside his head: {HIM_BARE} lies on his back {RUG}, she squats over his hips "
                          f"facing him, feet planted flat on the rug, knees spread wide, {SKIRT_UP}, lowered all "
                          f"the way down with his thick penis deep inside her vagina, her stretched labia fully "
                          f"visible, her face to the camera flushed with pleasure, eyes heavy-lidded, lips parted in a soft moan"),
    ("s03_rug_pov", 0.6, f"{POV} from his eyes as he lies on his back {RUG}: she squats over his hips facing "
                         f"him, feet planted flat on the rug, knees spread wide, {SKIRT_UP}, {COCK} deep inside "
                         f"her vagina, her vagina stretched around it in full view, her face flushed, biting "
                         f"her lip and looking into the camera"),
    ("s04_rug_pleasure", 0.6, f"{PHOTOG} from beside his head: {HIM_BARE} lies on his back {RUG}, she squats over him "
                              f"facing him, feet planted, knees wide, {SKIRT_UP}, riding his thick penis deep "
                              f"in her vagina, her eyes half closed in pleasure, lips parted in a soft moan, her face flushed, "
                              f"her hands squeezing her own breasts, her face to the camera"),
    ("s05_desk_tip", 0.6, f"{PHOTOG} from beside the desk: {HIM_BARE} lies on his back on the big walnut desk, she "
                          f"squats over his hips on the desk facing him with her feet planted flat on the "
                          f"desktop and her knees spread wide, {SKIRT_UP}, guiding just the head of {COCK} into "
                          f"her vagina, her vagina fully visible, her face turned to the camera"),
    ("s06_desk_deep", 0.6, f"{PHOTOG} from beside the desk: {HIM_BARE} lies on his back on the big walnut desk, she "
                           f"squats over him on the desk facing him, feet planted on the desktop, knees wide, "
                           f"{SKIRT_UP}, his thick penis deep inside her vagina, her stretched labia visible, "
                           f"bouncing on it, her face to the camera flushed with pleasure, eyes heavy-lidded, lips parted"),
    ("s07_desk_pov", 0.6, f"{POV} from his eyes as he lies on his back on the big walnut desk: she squats over "
                          f"his hips facing him, feet planted on the desktop, knees spread wide, {SKIRT_UP}, "
                          f"{COCK} deep inside her vagina in full view, her face flushed with pleasure, looking "
                          f"into the camera"),
    ("s08_rug_anal_tip", 0.6, f"{PHOTOG} from beside his head: {HIM_BARE} lies on his back {RUG}, she squats over his "
                              f"hips facing him, feet planted flat on the rug, knees spread wide, {SKIRT_UP}, "
                              f"one hand guiding just the head of {COCK} against her anus, her wet vagina fully "
                              f"visible just above it, her face turned to the camera"),
    ("s09_rug_anal_deep", 0.6, f"{PHOTOG} from beside his head: {HIM_BARE} lies on his back {RUG}, she squats over "
                               f"him facing him, feet planted, knees wide, {SKIRT_UP}, lowered all the way down "
                               f"with his thick penis deep inside her anus, her wet vagina fully visible above "
                               f"it, her face to the camera flushed with pleasure, eyes heavy-lidded, lips parted in a soft moan"),
    ("s10_rug_anal_pov", 0.6, f"{POV} from his eyes as he lies on his back {RUG}: she squats over his hips "
                              f"facing him, feet planted flat on the rug, knees spread wide, {SKIRT_UP}, "
                              f"{COCK} deep inside her anus, her wet vagina in full view above it, her eyes "
                              f"rolling back with pleasure, looking into the camera"),
    ("s11_rug_anal_squirt", 0.6, f"{PHOTOG} from beside his head: {HIM_BARE} lies on his back {RUG}, she squats over "
                                 f"him facing him, feet planted, knees wide, {SKIRT_UP}, his thick penis deep "
                                 f"inside her anus, a clear stream of fluid squirting from her vagina, her head "
                                 f"thrown back and her lips parted in a cry of pleasure, her face to the camera"),
    ("s12_desk_anal_deep", 0.6, f"{PHOTOG} from beside the desk: {HIM_BARE} lies on his back on the big walnut desk, "
                                f"she squats over him on the desk facing him, feet planted on the desktop, "
                                f"knees wide, {SKIRT_UP}, his thick penis deep inside her anus, her wet vagina "
                                f"fully visible above it, her face to the camera flushed with pleasure, lips parted in a soft moan"),
    ("s13_desk_anal_squirt", 0.6, f"{PHOTOG} from beside the desk: {HIM_BARE} lies on his back on the big walnut "
                                  f"desk, she squats over him facing him, feet planted on the desktop, knees "
                                  f"wide, {SKIRT_UP}, his thick penis deep inside her anus, a clear stream of "
                                  f"fluid squirting from her vagina, her eyes rolling back, her face to the "
                                  f"camera"),
    # --- her back on the desk, him standing beside it, before he finishes ---
    ("e01_desk_tip", 0.6, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs spread wide with her "
                          f"feet planted on the edge of the desk, {HIM_BARE} standing at the edge of the desk "
                          f"between her legs with just the head of {COCK} pressing into her vagina, her vagina "
                          f"in full view, her face turned to the camera"),
    ("e02_desk_deep", 0.6, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs spread wide and "
                           f"held up, {HIM_BARE} standing between her legs with his thick penis deep inside her "
                           f"vagina, thrusting, her labia stretched around the shaft, her head back and her "
                           f"mouth open in pleasure, her face turned to the camera"),
    ("e09_desk_anal_tip", 0.6, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs raised and held "
                               f"open, {HIM_BARE} standing at the edge of the desk with just the head of {COCK} "
                               f"entering her anus, her wet vagina in full view above it, her face turned to "
                               f"the camera"),
    ("e10_desk_anal_deep", 0.6, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs raised and "
                                f"held open, {HIM_BARE} standing at the edge of the desk with his thick penis deep "
                                f"inside her anus, thrusting, her wet vagina visible above it, her face turned "
                                f"to the camera with her lips parted"),
    ("e11_desk_anal_pleasure", 0.6, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs raised and "
                                    f"held open, {HIM_BARE} standing at the edge of the desk with his thick penis "
                                    f"deep inside her anus, her wet vagina visible above it, her eyes rolling "
                                    f"back and her lips parted in a soft moan, gripping the edge of the desk, her "
                                    f"face to the camera"),
    ("e12_desk_anal_squirt", 0.6, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs raised and "
                                  f"held open, {HIM_BARE} standing at the edge of the desk with his thick penis deep "
                                  f"inside her anus, a clear stream of fluid squirting from her vagina, her "
                                  f"head thrown back in a cry of pleasure, her face to the camera"),
    # --- the finish: he stands beside the desk, his penis held just above her pussy ---
    ("f01_pullout", 0.6, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs spread, {HIM} "
                         f"standing beside the desk having just pulled {COCK} out of her anus and holding it "
                         f"just above her vagina, she reaches down and wraps her hand around it, looking at "
                         f"the camera"),
    ("f02_cum", 0.6, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs spread, {HIM_BARE} standing "
                     f"beside the desk, she jerks {COCK} held just above her vagina as he ejaculates, a massive "
                     f"load of thick white cum spraying across her stomach, chest and face, her eyes on the "
                     f"camera"),
    ("f03_covered", 0.6, f"{PHOTOG} from beside the desk: {ON_DESK}, {SKIRT_UP}, her legs spread, {HIM_BARE} standing "
                         f"beside the desk, her stomach, breasts and face covered in thick white cum, {COCK} "
                         f"still in her hand just above her vagina, smiling at the camera"),
)
IDS = [s[0] for s in STORY]
assert len(IDS) == len(set(IDS)), "duplicate shot id"

NEG_BASE = ("different person, different face, changed hair, extra penis, extra hands, extra limbs, deformed "
            "genitals, deformed hands, blurry, low quality, cartoon, anime, watermark, text, condom, childlike, "
            "child, underage, tears, crying, watering eyes, toothy grin")
NEG_BARE = "bra, bralette, vest, blouse, shirt on her, top on her"   # once she is topless, nothing comes back
NEG_POV = "the man's face, his face, far away, distant, standing, office chair behind her, a second man"

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
    if strength:
        neg += ", " + NEG_BARE
    if sid.endswith("_pov"):
        neg += ", " + NEG_POV
    extra = appearance_negative(CHAR)
    return neg + (", " + extra if extra else "")


record: dict = json.loads(SHOTS.read_text(encoding="utf-8")) if SHOTS.is_file() else {}
for sid, _, _ in STORY:
    record.setdefault(sid, {"attempts": [], "kept": None})


def save() -> None:
    SHOTS.write_text(json.dumps(record, indent=1), encoding="utf-8")


def face_floor(sid: str) -> float:
    return FACE_SIDE_MIN if sid.endswith("_side") else FACE_MIN


def passes(sid: str, a: dict) -> bool:
    """Judged against the CURRENT floor, not the flag stored when it rendered: the
    side floor was lowered after a02_side's four profiles of her all failed 0.5, and
    the age floor is judged the same way."""
    young = a.get("age") is not None and a["age"] < YOUNG_FLAG
    return bool(a.get("face") is not None and a["face"] >= face_floor(sid) and not young)


def kept_of(sid: str) -> dict | None:
    ok = [a for a in record[sid]["attempts"] if passes(sid, a)]
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
        # HER face: the one closest to her reference, not the largest - with him in frame the
        # largest face was his, and b01_belt scored 0.08-0.14 at age 29-34 four times (j1349)
        if ref_emb is not None:
            f = max(faces, key=lambda x: float(cosine(ref_emb, x.normed_embedding)))
        else:
            f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        face = round(float(cosine(ref_emb, f.normed_embedding)), 3) if ref_emb is not None else None
        age = int(round(float(f.age))) if getattr(f, "age", None) is not None else None
        return face, age

    # Re-score every attempt on disk that failed its floor: the picker changed (her face,
    # not the largest) and the floors changed, and a good render is never spent twice.
    for sid, _, _ in STORY:
        for a in record[sid]["attempts"]:
            if a.get("rescored") or passes(sid, a) or not (d / a["file"]).is_file():
                continue
            face, age = score(d / a["file"])
            a.update({"face": face, "age": age, "young": bool(age is not None and age < YOUNG_FLAG),
                      "rescored": True})
            a["ok"] = passes(sid, a)
            a["why"] = "" if a["ok"] else ("no face" if face is None else "YOUNG" if a["young"]
                                            else f"face {face} < {face_floor(sid)}")
            log(f"  {a['file'][:-4]}: re-scored face {face}  age {age}  {'kept' if a['ok'] else a['why']}")
        k = kept_of(sid)
        record[sid]["kept"] = k["file"] if k else None
    save()
    plan = [(sid, strength, body, budget) for sid, strength, body, budget in plan
            if sid in RETRY or kept_of(sid) is None]

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
            fmin = face_floor(sid)
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
    # every attempt that passes goes to the judge, not only the best-scoring one:
    # Jeremy, 2026-11-10, "I don't want you throwing out good images for no reason"
    for a in att:
        if passes(sid, a) and (d / a["file"]).is_file():
            items.append({"id": a["file"][:-4], "path": d / a["file"], "arm": "story", "group": sid})
sheet.save(d / "sheet.jpg", quality=90)
log(f"sheet -> {d / 'sheet.jpg'}")
if items and not DRY:
    make_set(OUT_ROOT / "judge", f"story_{CHAR}_office", f"{CHAR.title()} - office story", items,
             question="Keep this one? K = yes, X = re-roll it.", priority=5,
             meta={"character": CHAR, "renders_dir": d})
    log(f"{len(items)} of {len(STORY)} shots kept -> judge set story_{CHAR}_office")
log("STORYDONE")
