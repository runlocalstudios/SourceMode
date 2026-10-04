"""Generate a character's full training set LOCALLY - the Codex replacement.

Three reference photos in, the v4 shot plan's 80 shots out, with no character LoRA
and no cloud API. Everything measured on Amanda on 2026-09-29 feeds into this:

  - Qwen-Image-Edit-2511 + the fal multiple-angles LoRA (both Apache-2.0).
  - Pose comes from the `<sks> [azimuth] [elevation] [distance]` vocabulary, which
    genuinely steers the camera (yaw tracked -68 to +51). This REPLACES the
    over-asking trick, which stopped working past three-quarter.
  - Attributes come from the shot plan as text, which works alongside the pose token.
  - Arm B: the hair baseline PLUS the two original references in the three slots.
    Jeremy's judging put B at 6/12 against the control's 3/12 and baseline-only's
    1/12. Never fill all three slots with a generated image.

Hard limits taken from the measurements, not guessed:
  - BACK VIEWS ARE DROPPED. Identity collapsed to 0.23-0.42 there and one frame
    matched a different character better. The plan has 8 such shots; they are
    re-pointed at the nearest working band rather than generated and thrown away.
  - Every output is gated against ALL reference identities, not a floor. That is the
    check that caught 35 Hannah frames inside Ash's set.
  - Faces under MIN_BUCKET_PX are dropped rather than flagged.

    python loragen_local.py <char> [--limit N] [--dry-run] [--seeds <dir>]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from sourcemode.config import load_config, workflows_dir
from sourcemode.gates.identity import _get_face_app, embed_image
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.workflow import load_template, substitute

CHAR = sys.argv[1].lower()
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 80
DRY = "--dry-run" in sys.argv
SEEDS = Path(sys.argv[sys.argv.index("--seeds") + 1]) if "--seeds" in sys.argv else None
# Jeremy, 2026-10-01: the INTERNAL plan differs from the Codex plan. Fitted outfits
# on every head-and-chest / waist-up frame so the LoRA can learn her build (loose
# tops teach nothing), the character's appearance clause in every generation
# prompt (never in a caption), and the hair recipe that won the conformance test:
# seed + ONE reference + the hair named in text (arm C, 4/4 ponytails, identity
# 0.71-0.78; the seeded run's seed + two loose refs + no text gave 1/13).
INTERNAL = "--internal" in sys.argv
OUT_SUFFIX = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else ("internal" if INTERNAL else "")
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
COMFY_IN = Path("C:/ComfyUI/input")
OUT = Path(f"outputs/loragen_local/{CHAR}" + (f"_{OUT_SUFFIX}" if OUT_SUFFIX else "")); OUT.mkdir(parents=True, exist_ok=True)
APPEARANCE = ""
if INTERNAL:
    # age + body text from the one place that knows both; the age is stated in every
    # generation (Jeremy, 2026-10-03) and never in a caption.
    from sourcemode.assets.appearance import clause as _clause
    APPEARANCE = _clause(CHAR)
    print(f"appearance clause: {APPEARANCE or '(none in characters/appearance.json)'}")
# fitted garments, rotated per shot, keeping the plan's colour. Only for the frames
# that show the body; tight head portraits keep the plan's outfit.
FITTED = ["fitted ribbed tank top", "fitted scoop-neck top", "fitted crop top", "fitted bodysuit",
          "fitted short-sleeve t-shirt", "fitted camisole", "fitted long-sleeve top", "halter top",
          "fitted knit top", "off-the-shoulder fitted top", "fitted v-neck top", "fitted square-neck top"]
BODY_FRAMES = {"a head-and-chest portrait", "a waist-up portrait", "a head-and-shoulders portrait"}
PLAN = Path("outputs/shot_plans/v4/shot_plan_80_main_v4.json")
MIN_BUCKET_PX = 250
BASELINE_FLOOR = 0.75

# yaw_target -> azimuth token. near_profile and profile stay at side: measured
# identity there was 0.68-0.78, usable. There is deliberately no back mapping.
# The pose token REQUIRES a direction, but the plan only sets `side` on the 8
# near-profile/profile shots - the other 72 deliberately omit left/right so the old
# pipeline could let her turn naturally. Picking one direction for all of them would
# turn the whole set the same way, which is the homogeneity the plan exists to avoid.
# So: honour `side` where it is set, otherwise alternate on the shot number.
def azimuth_for(r):
    y = r["yaw_target"]
    if y == "straight":
        return "front"
    side = r.get("side") or ("left" if r["n"] % 2 == 0 else "right")
    if y in ("near_profile", "profile"):
        return f"{side} side"
    return f"front-{side} quarter"
# framing -> distance token
DISTANCE = {"a tight head portrait": "close-up",
            "a head-and-shoulders portrait": "close-up",
            "a head-and-chest portrait": "medium shot",
            "a waist-up portrait": "medium shot"}
PITCH = {"level": "eye-level shot", "down": "high-angle shot", "up": "low-angle shot"}
NEG = ("different person, different face, deformed, distorted hands, extra limbs, "
       "plastic skin, doll-like, blurry, low quality, cartoon, watermark, text")

# hair clause -> the baseline seed that supplies it
def hair_kind(h):
    h = (h or "").lower()
    if "braid" in h or "plait" in h: return "braid"
    if "pigtail" in h: return "pigtails"
    if "bun" in h or "knot" in h or "chignon" in h: return "bun"
    if "ponytail" in h: return "ponytail"
    if any(w in h for w in ("half", "pinned", "clip", "gathered back", "pushed back",
                            "swept back", "held back", "off her neck", "off her face")):
        return "halfup"
    return "loose"

plan = json.loads(PLAN.read_text(encoding="utf-8"))[:LIMIT]
orig = sorted(p for p in REFS.glob(f"{CHAR}_*")
              if p.stem.split("_")[0].lower() == CHAR and p.suffix.lower() in (".jpg", ".jpeg", ".png"))
if not orig:
    raise SystemExit(f"no references for {CHAR} in {REFS}")
orig_names = []
for p in orig[:3]:
    d = COMFY_IN / p.name
    if not d.exists(): d.write_bytes(p.read_bytes())
    orig_names.append(p.name)
while len(orig_names) < 2: orig_names.append(orig_names[0])

styles = sorted({hair_kind(r["hair"]) for r in plan})
print(f"{CHAR}: {len(orig)} references, {len(plan)} shots, {len(styles)} hair baselines needed: {styles}")
if DRY:
    from collections import Counter
    print("  azimuth:", dict(Counter(azimuth_for(r) for r in plan)))
    print("  distance:", dict(Counter(DISTANCE.get(r['framing'], 'medium shot') for r in plan)))
    raise SystemExit("dry run")

cfg = load_config()
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
app = _get_face_app()
orig_emb = [e for e in (embed_image(p) for p in orig) if e is not None]
others = {}
for p in sorted(REFS.glob("*")):
    if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"): continue
    who = p.stem.split("_")[0].lower()
    if who in (CHAR, "universal"): continue
    e = embed_image(p)
    if e is not None: others.setdefault(who, []).append(e)


def measure(path):
    im = Image.open(path).convert("RGB")
    fs = app.get(np.asarray(im)[:, :, ::-1])
    if not fs: return None
    f = max(fs, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
    fh = float(f.bbox[3] - f.bbox[1])
    bucket = round(fh / im.height * (1536 if im.height > im.width else 1024))
    self_ = max(float(e @ f.normed_embedding) for e in orig_emb)
    best, bs = CHAR, self_
    for n, b in others.items():
        v = max(float(x @ f.normed_embedding) for x in b)
        if v > bs: best, bs = n, v
    return {"self": round(self_, 3), "best": best, "bucket_px": bucket,
            "yaw": round(float(f.pose[1]), 1)}


def render(dest, prompt, refs3, prefix, seed):
    if dest.exists(): return True
    wf = substitute(load_template(workflows_dir(cfg), "qwen_multiangle_ref"), {
        "REF1": refs3[0], "REF2": refs3[1], "REF3": refs3[2],
        "POSITIVE": prompt, "NEGATIVE": NEG, "SEED": seed, "FILENAME_PREFIX": prefix})
    files = client.outputs(client.wait(client.submit(wf), timeout_s=1800))
    if not files: return False
    client.fetch(files[0], dest); return True


# ---- stage 1: one gated hair baseline per style ------------------------------
HAIR_TEXT = {"loose": "her hair worn loose", "ponytail": "her hair in a high ponytail",
             "bun": "her hair in a low bun", "braid": "her hair in a braid over one shoulder",
             "pigtails": "her hair in two pigtails", "halfup": "her hair half pinned back",
             "tucked": "her hair tucked behind both ears"}
print()
print("stage 1: hair baselines" + (f" from REAL seeds in {SEEDS}" if SEEDS else " (generated)"))
seeds = {}
# Jeremy, 2026-09-30: real high-fidelity seeds, one per hairstyle, each with its
# own outfit and background, so every generated image is ONE step from a real
# photo. Every seed is identity-gated against ALL reference identities first.
if SEEDS:
    for st in styles:
        cands = sorted(SEEDS.glob(f"{CHAR}_seed_{st}.*"))
        if not cands:
            print(f"  {st:<9} no real seed -> hair asked in text"); continue
        p = cands[0]; m = measure(p)
        good = m and m["self"] >= BASELINE_FLOOR and m["best"] == CHAR
        sv = m["self"] if m else "-"; bv = m["best"] if m else "-"; px = m["bucket_px"] if m else "-"
        print(f"  {st:<9} {p.name:<28} identity {sv}  best {bv}  face {px}px -> " + ("in" if good else "REJECTED"))
        if good:
            n = f"{CHAR}_bl_{st}{p.suffix}"; (COMFY_IN / n).write_bytes(p.read_bytes()); seeds[st] = n
for st in ([] if SEEDS else styles):
    dest = OUT / f"_baseline_{st}.png"
    ok = render(dest, f"<sks> front view eye-level shot medium shot, {HAIR_TEXT.get(st, 'her hair worn loose')}, "
                      f"wearing a plain white top, against a plain light grey background, a neutral expression",
                orig_names[:3] if len(orig_names) >= 3 else orig_names * 2, f"loragen_local/{CHAR}/_baseline_{st}", 7)
    if not ok: print(f"  {st}: NO OUTPUT"); continue
    m = measure(dest)
    good = m and m["self"] >= BASELINE_FLOOR and m["best"] == CHAR
    print(f"  {st:<9} identity {m['self'] if m else '-'}  best {m['best'] if m else '-'}  "
          f"-> {'in' if good else 'REJECTED, falls back to text'}")
    if good:
        n = f"{CHAR}_bl_{st}.png"
        (COMFY_IN / n).write_bytes(dest.read_bytes())
        seeds[st] = n

# ---- stage 2: the 80 shots ---------------------------------------------------
print(f"\nstage 2: {len(plan)} shots")
rows = []
# Jeremy, 2026-09-30: only the four seeded styles. A plan shot asking for a braid
# or pigtails is remapped onto a seeded style, rotating so the balance holds, and
# its caption is rewritten to match - the plan's own hair clause would otherwise
# describe hair the image does not have.
SEEDED = [st for st in ('loose', 'ponytail', 'halfup', 'bun') if st in seeds]
_rot = 0
for r in plan:
    st = hair_kind(r["hair"])
    if SEEDS and st not in seeds and SEEDED:
        st_new = SEEDED[_rot % len(SEEDED)]; _rot += 1
        r = dict(r, hair=HAIR_TEXT[st_new],
                 training_caption=r["training_caption"].replace(r["hair"], HAIR_TEXT[st_new]))
        st = st_new
    if INTERNAL and r["framing"] in BODY_FRAMES:
        colour = (r.get("colour") or "").strip()
        new_outfit = f"a {colour + ' ' if colour else ''}{FITTED[r['n'] % len(FITTED)]}"
        r = dict(r, outfit=new_outfit,
                 training_caption=r["training_caption"].replace(r["outfit"], new_outfit))
    az = azimuth_for(r)
    dist = DISTANCE.get(r["framing"], "medium shot")
    elev = PITCH.get(r.get("pitch", "level"), "eye-level shot")
    pose = f"<sks> {az} view {elev} {dist}"
    # a gated baseline supplies the hair; if none, ask for it in text
    if st in seeds and INTERNAL:
        refs3 = [seeds[st], orig_names[0], orig_names[0]]      # arm C
        hair_clause = f", {r['hair']}"
    elif st in seeds:
        refs3 = [seeds[st], orig_names[0], orig_names[1 % len(orig_names)]]
        hair_clause = ""
    else:
        refs3 = (orig_names * 3)[:3]
        hair_clause = f", {r['hair']}"
    prompt = (f"{pose}{', ' + APPEARANCE if APPEARANCE else ''}{hair_clause}, wearing {r['outfit']}, {r['expression']}, "
              f"{r['lighting']}, {r['background']}")
    dest = OUT / f"{CHAR}_shot_{r['n']:03d}.png"
    if not render(dest, prompt, refs3, f"loragen_local/{CHAR}/shot_{r['n']:03d}", 1000 + r["n"]):
        print(f"  shot {r['n']:03d}: NO OUTPUT"); continue
    m = measure(dest) or {}
    keep = bool(m) and m.get("best") == CHAR and m.get("bucket_px", 0) >= MIN_BUCKET_PX
    rows.append({"n": r["n"], "file": str(dest), "hair": st, "azimuth": az,
                 "prompt": prompt, "training_caption": r["training_caption"],
                 "keep": keep, **m})
    if r["n"] % 10 == 0 or not keep:
        print(f"  shot {r['n']:03d} {st:<8} {az:<20} self {m.get('self')} "
              f"{m.get('bucket_px')}px {'' if keep else '  DROPPED'}")

(OUT / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
kept = [r for r in rows if r["keep"]]
print(f"\n{len(kept)}/{len(rows)} passed the gates")
if kept:
    px = sorted(r["bucket_px"] for r in kept); sim = sorted(r["self"] for r in kept)
    print(f"  face at bucket: median {px[len(px)//2]}px, min {px[0]}")
    print(f"  identity: median {sim[len(sim)//2]:.3f}, min {sim[0]:.3f}")
    wrong = sum(1 for r in rows if r.get("best") not in (None, CHAR))
    print(f"  matched another identity: {wrong}")
print("LORAGENLOCALDONE")
