"""Captions for a staged set that has NO shot plan behind it (sunny, priyanka,
priya, maya): measurement for framing and angle, the vision model for everything
else, one clause per attribute, identity never described.

    python caption_from_vl.py <char>          e.g. priya  -> outputs/lora-datasets/priya_v2

Assembles:
  <char>, <framing measured>, <angle measured>[, pitch], <hair>, <outfit>,
  <expression>, <lighting>, <setting>
then goes through `sourcemode train preview` for Jeremy's read and approval.
"""
import json
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

from PIL import Image

# gaze.py sits beside this script, so running this file by path puts it on sys.path
# Geometric gaze is retired: the darkest region inside the eye opening is the
# eyelash line, not the iris, so the offset was noise. Gaze is now a binary VL
# question, run separately by vl_gaze.py.

CHAR = sys.argv[1]
DS = Path(f"outputs/lora-datasets/{CHAR}_v2"); IMG = DS / "image_src"
M = Path("C:/dev/e2egen/vendor/musubi-tuner")
VL = M / ".venv/Scripts/python.exe"
CAPTIONER = M / "src/musubi_tuner/caption_images_by_qwen_vl.py"
VL_MODEL = "C:/ComfyUI/models/text_encoders/qwen_2.5_vl_7b.safetensors"
VL_OUT = DS / "vl_clauses.jsonl"
TEETH_OUT = DS / "vl_teeth.jsonl"
HAIR_OUT = DS / "vl_hair.jsonl"
HAIR_CONFIRM = DS / "vl_hair_confirm.jsonl"
GAZE_OUT = DS / "vl_gaze.jsonl"   # written by vl_gaze.py

PROMPT = (
    "Describe this photo of a woman as five short comma-free phrases, one per line, "
    "in exactly this order and format:\n"
    "hair: <how her hair is worn - loose, in a ponytail, in a bun, braided, tucked back - "
    "and nothing about its colour or length>\n"
    "outfit: <the visible clothing as ONE phrase and no commas - give each garment "
    "its colour and put 'and' between separate garments, e.g. "
    "'a grey crew-neck sweatshirt' or 'a purple top and a denim skirt'; or 'nothing visible'>\n"
    "expression: <her expression, e.g. a soft smile, a broad smile, a neutral expression>\n"
    "lighting: <the light, e.g. soft window daylight, warm lamp light, flat overcast daylight>\n"
    "setting: <the background, e.g. a plain grey studio backdrop, a softly blurred kitchen>\n"
    "Do not describe her face, eyes, skin, age, body, or hair colour or length. "
    "Keep each phrase under 10 words."
)

# Jeremy corrected several captions that called teeth-showing smiles "closed-mouth".
# The model cannot make that call in a multiple choice: with a forcing rule it
# answered "open" on 12/12 including clearly closed mouths, and without one it
# mislabelled open ones as closed. Asked as a single yes/no it scored 12/12, so
# teeth are their own binary pass and that answer decides the wording.
TEETH_Q = "Are this person's teeth visible in her mouth? Answer with exactly one word: yes or no."
# "open" must not be stripped out of "open-mouthed", which left two of priyanka's
# captions reading "-mouthed surprise" and "-mouthed speaking".
SMILE_WORDS = re.compile(r"\b(closed[- ]mouth|open(?![- ]mouth)|broad|toothy)\b", re.I)


def yaw_caption(y):
    a = abs(y); side = "her left" if y > 0 else "her right"
    if a < 10: return "facing the camera"
    if a < 25: return f"turned slightly toward {side}"
    if a < 45: return f"in a three-quarter view toward {side}"
    if a < 70: return f"turned almost to profile toward {side}"
    return f"in full profile toward {side}"


def framing_word(fh):
    if fh >= 0.58: return "a tight head portrait"
    if fh >= 0.46: return "a head-and-shoulders portrait"
    if fh >= 0.36: return "a head-and-chest portrait"
    return "a waist-up portrait"


def expression_clause(claimed, teeth_visible):
    """The teeth answer decides; the model's own adjective is only a stem."""
    stem = " ".join(SMILE_WORDS.sub("", claimed or "").split()) or "a smile"
    if "smile" not in stem:
        # The VL hands back a bare adjective - "neutral", "surprised", "thoughtful" -
        # and a lone adjective in a caption does not say what it describes. Every
        # other clause is a noun phrase; make this one match.
        low = stem.lower()
        if low in ("neutral", "serious", "thoughtful", "calm", "relaxed", "surprised",
                   "playful", "pensive", "focused", "curious", "confident"):
            return f"a {stem} expression"
        if "expression" not in low and not low.startswith(("a ", "an ", "her ")):
            return f"a {stem} expression"
        return stem
    if teeth_visible:
        return stem.replace("smile", "smile showing her teeth", 1)
    return stem.replace("smile", "closed-mouth smile", 1)


# The free-form pass called 99 of priyanka's 121 images "loose" when her shot plan
# asked for fourteen styles, which is the same failure the teeth question had: asked
# to describe, the model reaches for the commonest answer. Asked to pick from a
# closed list of visually distinct states, it did 12/12. So hairstyle is its own
# constrained pass and its answer overrides the free-form clause.
HAIR_OPTIONS = {
    "loose": "her hair worn loose",
    "ponytail": "her hair in a ponytail",
    "bun": "her hair in a bun",
    "braid": "her hair in a braid",
    "pigtails": "her hair in pigtails",
    "halfup": "her hair half pinned up",
    "tucked": "her hair tucked behind her ears",
}
HAIR_Q = ("How is this person's hair worn? Answer with exactly one word from this list: "
          "loose, ponytail, bun, braid, pigtails, halfup, tucked. "
          "Use 'loose' only if her hair hangs free and is not gathered, tied or pinned "
          "anywhere. Use 'halfup' if the top is pinned back and the rest hangs free.")

# A bare noun phrase at the end of a caption reads as an object in the scene rather
# than the place. The shot-plan captions say "against a plain grey seamless"; this
# pass had been appending "plain grey backdrop" with no preposition, so the setting
# was genuinely stated but unreadable as such - and the dataset check scored it
# missing on 43% of the set.
_BACKDROP = ("backdrop", "background", "wall", "seamless", "screen", "curtain")


def hair_clause(answer):
    w = re.sub(r"[^a-z]", "", (answer or "").strip().lower())
    return HAIR_OPTIONS.get(w)


def setting_clause(s):
    t = s.strip().rstrip(".")
    if not t:
        return None
    low = t.lower()
    if low.startswith(("in ", "on ", "at ", "against ", "a ", "an ", "the ")):
        return t if low.startswith(("in ", "on ", "at ", "against ")) else f"in {t}"
    prep = "against" if any(w in low for w in _BACKDROP) else "in"
    article = "an" if low[0] in "aeiou" else "a"
    return f"{prep} {article} {t}"


def run_vl(out_path, prompt, max_new, only=None):
    """Ask the VL. `only` restricts it to a subset of image_src, via a temp folder,
    which is how the hair pass is skipped for images the shot plan already describes.
    A GPU pass is the only step in dataset prep that needs the card, so not spending
    it on 80 images whose hair is already known is the whole point."""
    if out_path.exists():
        # Incremental, never all-or-nothing: an existing file used to mean "done",
        # so images added to a staged set after the first pass were never
        # described - gabi's 33 adopted face crops, 2026-10-08. Ask only for the
        # ones it lacks and append them.
        have = set(read_jsonl(out_path))
        want = set(only) if only is not None else {p.name for p in IMG.glob("src_*.png")}
        missing = sorted(want - have)
        if not missing:
            return
        part = out_path.with_suffix(".part.jsonl")
        if part.exists():
            part.unlink()
        run_vl(part, prompt, max_new, only=missing)
        with out_path.open("a", encoding="utf-8") as f:
            f.write(part.read_text(encoding="utf-8"))
        part.unlink()
        return
    src = IMG
    tmp = None
    if only is not None:
        if not only:
            out_path.write_text("", encoding="utf-8")   # nothing to ask
            return
        tmp = DS / "_vlsubset"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        for n in only:
            shutil.copy2(IMG / n, tmp / n)
        src = tmp
    try:
        subprocess.run([str(VL), str(CAPTIONER), "--image_dir", str(src), "--model_path", VL_MODEL,
                        "--output_file", str(out_path), "--prompt", prompt,
                        "--max_new_tokens", str(max_new), "--fp8_vl"], check=True)
    finally:
        if tmp is not None and tmp.exists():
            shutil.rmtree(tmp)


def read_jsonl(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[Path(r["image_path"]).name] = r["caption"]
    return out


# Expression, lighting and setting still come from the VL for every image: audited
# against Hannah's approved captions the plan matches expression only 69% and
# lighting 31% - the generator has real latitude there and a caption has to describe
# what is IN the frame, or the trigger absorbs the difference. Hair is the exception
# at 92%, so the hair questions are asked only about images with no plan entry.
# --- the shot plan knows what it asked for ------------------------------------
# Jeremy, 2026-09-22: "Can the Lora-gen skill manifest / shot plan help you better
# caption hair styles if there is confusion?" It can, and by a wide margin.
#
# Audited against Hannah's 71 shots AFTER he reviewed and signed off her captions:
# the plan's hair agrees 92% of the time (counting "tucked behind one ear" as loose,
# which it is). The 6 that disagree are all inside the halfup/ponytail/bun cluster -
# the same distinction six VL wordings could not make. The plan is also more
# specific: "her hair held back with a clip" beats "half pinned up".
#
# So for a Lora-Gen image the plan supplies hair and outfit, and the VL is demoted
# to a disagreement detector: where the two differ, the image is flagged rather than
# silently resolved. Everything measurable - framing, angle, gaze, mouth - still
# comes from measurement, because the generator does not always comply with what it
# was asked for. Images that did not come from a shot plan are unaffected.
PLAN_DIR = Path("outputs/shot_plans/v4")
SHOT_RE = re.compile(rf"{CHAR}_shot_(\d+)", re.I)


def load_plan():
    """shot number -> plan entry, from whichever v4 plan exists. The age variants are
    the same 80 shots with one sentence added, so any of them carries the same hair
    and outfit."""
    for name in ("shot_plan_80_main_v4.json", *(f"shot_plan_80_main_v4_age{a}.json"
                                                for a in range(18, 24))):
        f = PLAN_DIR / name
        if f.is_file():
            return {r["n"]: r for r in json.loads(f.read_text(encoding="utf-8"))}
    return {}


def plan_by_image():
    """image_src name -> plan entry, via the provenance recorded at gather time."""
    mf = DS / "manifest.json"
    if not mf.is_file():
        return {}
    plan = load_plan()
    if not plan:
        return {}
    out = {}
    for r in json.loads(mf.read_text(encoding="utf-8")):
        m = SHOT_RE.search(Path(r.get("original", "")).name)
        if m and int(m.group(1)) in plan:
            out[r["file"]] = plan[int(m.group(1))]
    return out


def _hair_kind(h):
    """Coarse style, so the plan's richer wording and the closed list compare fairly:
    "her hair held back with a clip" and "half pinned up" are the same style."""
    h = (h or "").lower()
    if "braid" in h or "plait" in h:
        return "braid"
    if "pigtail" in h:
        return "pigtails"
    if "bun" in h or "knot" in h or "chignon" in h:
        return "bun"
    if "ponytail" in h:
        return "ponytail"
    if any(w in h for w in ("half", "pinned", "clip", "gathered back", "pushed back",
                            "swept back", "held back", "off her neck", "off her face")):
        return "halfup"
    return "loose"          # tucked behind an ear is loose hair


plan_conflict = {}


# --no-plan: the filename -> shot mapping is not always trustworthy. Ash's run was
# interrupted during the save pass and the last 76 images were numbered afterwards,
# so ash_shot_052.png is not shot 52: its plan entry asks for a lilac short-sleeve
# top and the photograph is a camel wool coat in a cafe. Nothing in a picture records
# which prompt produced it, so a shuffled mapping cannot be recovered - caption what
# is actually in the frame instead, which is what a caption is supposed to say.
PLAN = {} if "--no-plan" in sys.argv else plan_by_image()
if "--no-plan" in sys.argv:
    print("  --no-plan: ignoring the shot plan, every attribute comes from the image")

no_plan = sorted(p.name for p in IMG.glob("src_*.png") if p.name not in PLAN)
print(f"  {len(PLAN)} images described by the shot plan, {len(no_plan)} need the VL for hair")
run_vl(TEETH_OUT, TEETH_Q, 6)
run_vl(HAIR_OUT, HAIR_Q, 8, only=no_plan)
run_vl(VL_OUT, PROMPT, 120)

teeth = {k: v.strip().lower().startswith("yes") for k, v in read_jsonl(TEETH_OUT).items()}
hair_fix = {k: hair_clause(v) for k, v in read_jsonl(HAIR_OUT).items()}
# braid and halfup were re-asked as a yes/no because the closed list was not
# trustworthy on them; that answer wins. (Checked by eye afterwards: all 7 braids
# were real - the first look missed them because the crop cut the braid off.)
confirmed_hair: set[str] = set()
if HAIR_CONFIRM.exists():
    for k, v in json.loads(HAIR_CONFIRM.read_text(encoding="utf-8")).items():
        hair_fix[k] = HAIR_OPTIONS.get(v, hair_fix.get(k))
        if v in HAIR_OPTIONS:
            confirmed_hair.add(k)
# A garment noun means a separate item of clothing; anything else in a comma list
# describes the garment before it (a neckline, a sleeve, a colour).
GARMENTS = ("top", "shirt", "blouse", "sweater", "sweatshirt", "hoodie", "jumper",
            "cardigan", "jacket", "coat", "blazer", "vest", "tank", "camisole", "tee",
            "turtleneck", "dress", "gown", "skirt", "jeans", "trousers", "pants",
            "shorts", "leggings", "bodysuit", "romper", "jumpsuit", "bra", "bralette",
            "bikini", "swimsuit", "robe", "kimono", "overalls")


COLOURS = ("black", "white", "grey", "gray", "navy", "blue", "red", "maroon", "burgundy",
           "pink", "purple", "lilac", "lavender", "green", "olive", "teal", "turquoise",
           "yellow", "mustard", "gold", "orange", "rust", "brown", "tan", "beige", "cream",
           "ivory", "charcoal", "silver", "peach", "coral", "mint", "khaki", "denim")


def is_garment(phrase):
    words = re.findall(r"[a-z-]+", phrase.lower())
    return any(g in words or any(w.endswith(g) for w in words) for g in GARMENTS)


def is_colour(phrase):
    words = re.findall(r"[a-z-]+", phrase.lower())
    return bool(words) and all(w in COLOURS or w in ("dark", "light", "pale", "deep", "bright")
                               for w in words)


def with_article(phrase):
    """"wearing grey sweatshirt" reads as a typo; "a grey sweatshirt" reads as English."""
    t = phrase.strip()
    words = re.findall(r"[a-z-]+", t.lower())
    if not t or not words:
        return t
    head = words[0]
    if head in ("a", "an", "the", "her", "his", "their", "no", "nothing", "two", "three"):
        return t
    if head.endswith("s") and not head.endswith("ss"):
        return t                      # plural garments: jeans, shorts, leggings
    art = "an" if head[0] in "aeiou" and not head.startswith(("one", "uni")) else "a"
    return art + " " + t




vl = {}
for name, raw in read_jsonl(VL_OUT).items():
    clauses = {}
    for ln in raw.splitlines():
        m = re.match(r"\s*(hair|outfit|expression|lighting|setting)\s*:\s*(.+?)\s*$", ln, re.I)
        if m:
            key, val = m.group(1).lower(), m.group(2).strip().rstrip(".")
            if key == "outfit" and "," in val:
                # A comma here is ambiguous, and the old prompt made it so: it asked for
                # "garment type, colour, neckline", so the VL answered "grey sweatshirt,
                # crew neck" - ONE garment - while "purple top, denim skirt" is two.
                # Joining every comma with "and" produced "wearing turtleneck sweater and
                # dark grey". Only a bit naming a garment earns an "and"; the rest
                # describes the garment before it.
                bits = [b.strip() for b in val.split(",") if b.strip()]
                # Where an attribute belongs depends on what it is. A colour and a
                # bare adjective go in FRONT of the garment ("dark grey" + "turtleneck
                # sweater" -> "dark grey turtleneck sweater"); a named feature goes
                # after it ("crew neck" -> "with a crew neck"). Appending everything
                # in order gave "a turtleneck sweater dark grey".
                head, extras, garments = bits[0], [], []
                for b in bits[1:]:
                    if is_garment(b):
                        garments.append(b)
                    elif is_colour(b) or len(b.split()) == 1:
                        head = b + " " + head
                    else:
                        extras.append(b)
                val = head + "".join(" with " + with_article(e) for e in extras)
                for g in garments:
                    val += " and " + g
            clauses[key] = val.replace(",", "")
    vl[name] = clauses

geom = json.loads((DS / "geometry.json").read_text(encoding="utf-8"))
PITCH_BASE = statistics.median(g["pitch"] for g in geom.values() if g)

# Gaze and mouth come from MediaPipe FaceLandmarker blendshapes, measured by
# gaze_mp.py (run it before this script). Gaze is the eyeLookIn/Out pattern minus
# the counter-rotation that holding the lens with a turned head requires - the raw
# blendshapes alone called a centred-eyes-in-a-turned-head "at camera". Validated
# 7/7 on labelled images. jawOpen >= 0.10 is a mouth open mid-speech; the VL had
# captioned every such frame "neutral". Neither clause is written when the signal
# is absent: looking at the lens with a closed mouth is the default.
MP = DS / "gaze_mp.json"
mpf = json.loads(MP.read_text(encoding="utf-8")) if MP.exists() else {}
if not mpf:
    print("  NOTE: no gaze_mp.json - run gaze_mp.py first for gaze and mouth clauses")
gaze = {k: "looking off camera" for k, v in mpf.items() if v.get("off_camera")}
# A shot the PLAN asked to look off camera gets the clause at a lower bar. Jeremy
# added "looking off camera" by hand 32 times (and removed it once), and the same
# plan shots kept coming back: 008, 023, 041 and 004 five times each, across five
# different characters. Measured over 1,355 images, the plan's three gaze values
# separate cleanly - median |residual| 0.20 for "camera", 0.65 for "off", 3.59 for
# "away" - so the "off" population really is averted, it just sits under the 0.85
# threshold that was tuned for "away". Gate it on the plan AND a residual above the
# camera population's own median (0.25), which captions 77% of the off shots and
# leaves the ones that measurably ARE on the lens alone. The threshold for every
# other shot is unchanged.
PLAN_OFF_MIN = 0.25
_plan_off = 0
for _name, _entry in PLAN.items():
    if (_entry or {}).get("gaze") not in ("off", "away") or _name in gaze:
        continue
    if abs((mpf.get(_name) or {}).get("resid") or 0) >= PLAN_OFF_MIN:
        gaze[_name] = "looking just off camera"
        _plan_off += 1
talking = {k for k, v in mpf.items() if v.get("mouth_open")}

written, thin, teeth_n = 0, [], 0
for p in sorted(IMG.glob("*")):
    if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        continue
    g = geom.get(p.name) or {}
    c = vl.get(p.name, {})
    out = [CHAR, framing_word(g.get("face_h_frac", 0.44)),
           yaw_caption(g["yaw"]) if g.get("yaw") is not None else "facing the camera"]
    d = (g.get("pitch") if g.get("pitch") is not None else PITCH_BASE) - PITCH_BASE
    if abs(d) > 10:
        out.append("shot from slightly above" if d < 0 else "shot from slightly below")
    if gaze.get(p.name):
        out.append(gaze[p.name])
    entry = PLAN.get(p.name)
    hair = hair_fix.get(p.name) or c.get("hair")
    # A hair answer confirmed against the IMAGE (hair_confirm2 / hair_recheck)
    # beats the plan: the plan says what was ASKED, and on a character whose hair
    # cannot hold the asked style the generator substituted. nisha 2026-10-06:
    # hair_recheck corrected 15 braid / high-ponytail captions and this step
    # wrote the plan's braids straight back over them.
    if p.name in confirmed_hair and hair:
        pass
    elif entry and entry.get("hair"):
        # the plan said what to render; record when the VL reads it differently so
        # the pair can be looked at, but write the plan's wording
        asked = entry["hair"]
        if hair and _hair_kind(asked) != _hair_kind(hair):
            plan_conflict[p.name] = {"plan": asked, "vl": hair}
        hair = asked
    if hair:
        out.append(hair if hair.lower().startswith("her hair") else f"her hair {hair}")
    o = (entry.get("outfit") if entry else None) or c.get("outfit")
    if o and "nothing visible" not in o.lower():
        if not o.lower().startswith("wearing"):
            # Splitting on " and " turns "a striped tee in navy and white" into two
            # garments and writes "in navy and A white". Only split when BOTH sides
            # actually look like garments; a trailing colour word is part of the
            # phrase before it, not a second item of clothing.
            parts = o.split(" and ")
            if len(parts) == 2 and is_garment(parts[0]) and is_garment(parts[1]):
                o = "wearing " + " and ".join(with_article(x) for x in parts)
            else:
                o = "wearing " + with_article(o)
        out.append(o)
    if p.name in talking:
        # a measured open mouth overrides whatever the VL called the expression
        out.append("mid-speech, her mouth open")
    elif c.get("expression"):
        teeth_n += bool(teeth.get(p.name))
        out.append(expression_clause(c["expression"], teeth.get(p.name)))
    if c.get("lighting"):
        out.append(c["lighting"])
    sc = setting_clause(c.get("setting", ""))
    if sc:
        out.append(sc)
    if len(out) < 6:
        thin.append(p.name)
    p.with_suffix(".txt").write_text(", ".join(out), encoding="utf-8")
    written += 1

import collections as _c
print(f"{CHAR}_v2: {written} captions; {teeth_n} say teeth showing; thin: {len(thin)} {thin[:4]}")
print("  hair:", dict(_c.Counter(v for v in hair_fix.values() if v).most_common()))
print(f"  gaze: {len(gaze)} looking off camera ({_plan_off} from the plan's own off/away shots); mouth open mid-speech: {len(talking)}")
print(f"  from the shot plan: {sum(1 for n in PLAN if (IMG / n).is_file())} of "
      f"{len(list(IMG.glob('src_*.png')))} images had a plan entry")
if plan_conflict:
    (DS / "plan_conflict.json").write_text(json.dumps(plan_conflict, indent=1), encoding="utf-8")
    print(f"  PLAN vs VL disagree on hair for {len(plan_conflict)} images (plan wording written, "
          f"rows flagged): " + ", ".join(sorted(plan_conflict)[:6]))
else:
    (DS / "plan_conflict.json").write_text("{}", encoding="utf-8")
print("  unmatched hair answers:", sum(1 for v in hair_fix.values() if not v))
for p in sorted(IMG.glob("*.txt"))[:2]:
    print("  " + p.read_text(encoding="utf-8"))
print("VLCAPTIONSDONE")
