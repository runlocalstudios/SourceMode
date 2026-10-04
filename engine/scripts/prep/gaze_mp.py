"""Gaze from MediaPipe FaceLandmarker blendshapes - a real gaze signal, not pixels.

The model emits eyeLookIn/Out/Up/Down per eye. Looking at the lens, the two eyes
counter-rotate together (inLeft with outRight, or the mirror); looking away, the
pattern inverts. Validated on Jeremy's seven labelled raven images: 7/7 with the
classes separated by more than a full point of score.

Everything before this failed because it tried to find the pupil in pixels: the
darkest thing inside an eye opening is the eyelash line, not the iris.

    python gaze_mp.py <char> [--apply] [--sheet]
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import mediapipe as mp
from mediapipe.tasks import python as mpp
from mediapipe.tasks.python import vision

MODEL = "models/mediapipe/face_landmarker.task"
# The blendshapes are HEAD-RELATIVE, so a raw score cannot decide this on its own:
# eyes centred in their sockets means "looking where the head points", which is at
# the lens only when the head is frontal. Holding the lens with a turned head
# requires the eyes to counter-rotate, and they do so at about 0.057 per degree of
# yaw - fitted on Jeremy's four at-camera labels. What separates the classes is the
# RESIDUAL from that line, not the score.
#   at camera : residual -0.22 .. +0.18
#   off camera: residual -1.02 .. -1.99
# 7/7 on the labelled set with a 4.6x margin.
EYE_PER_YAW = 0.057
# 0.62 was the midpoint of raven's gap (at-camera max 0.23, off-camera min 1.03) and
# it caught three of mira's at-camera frames at 0.62-0.68. Mira's own gap runs
# 0.76 -> 1.49, so 0.85 sits inside both gaps and still scores 7/7 on raven.
THRESHOLD = 0.85
CLAUSE = "looking off camera"
GAZE_RE = re.compile(r"^(looking off camera|looking (?:slightly )?off[- ]camera"
                     r"|looking just off camera|her eyes turned slightly toward her (?:left|right)"
                     r"|looking away from the camera toward her (?:left|right)"
                     r"|her eyes (?:lowered|raised))$", re.I)

_L = None


# jawOpen is a direct mouth-open signal from the same model. Over 138 captioned
# images the 90th percentile was 0.04; everything at 0.10 or above was a mouth open
# mid-speech, and the VL had captioned every one of those "neutral". 0.07 was an
# open-mouthed smile, which the smile clause already covers.
JAW_OPEN = 0.10


def features(img: Image.Image):
    """(gaze score, jawOpen) or None. Score = (inLeft+outRight)-(outLeft+inRight)."""
    global _L
    if _L is None:
        _L = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=MODEL),
            output_face_blendshapes=True, num_faces=1,
            running_mode=vision.RunningMode.IMAGE))
    res = _L.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(img.convert("RGB"))))
    if not res.face_blendshapes:
        return None
    b = {c.category_name: c.score for c in res.face_blendshapes[0]}
    gaze = ((b.get("eyeLookInLeft", 0) + b.get("eyeLookOutRight", 0))
            - (b.get("eyeLookOutLeft", 0) + b.get("eyeLookInRight", 0)))
    return gaze, b.get("jawOpen", 0.0)


def score(img: Image.Image):
    """(inLeft + outRight) - (outLeft + inRight). Positive = eyes on the lens."""
    global _L
    if _L is None:
        _L = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=MODEL),
            output_face_blendshapes=True, num_faces=1,
            running_mode=vision.RunningMode.IMAGE))
    res = _L.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(img.convert("RGB"))))
    if not res.face_blendshapes:
        return None
    b = {c.category_name: c.score for c in res.face_blendshapes[0]}
    return ((b.get("eyeLookInLeft", 0) + b.get("eyeLookOutRight", 0))
            - (b.get("eyeLookOutLeft", 0) + b.get("eyeLookInRight", 0)))


if __name__ == "__main__":
    char = sys.argv[1].lower()
    apply_ = "--apply" in sys.argv
    sheet = "--sheet" in sys.argv
    DS = Path(f"outputs/lora-datasets/{char}_v2")
    IMG = DS / "image_src"
    geom = json.loads((DS / "geometry.json").read_text(encoding="utf-8"))
    vals, jaws = {}, {}
    for p in sorted(IMG.glob("*.png")):
        f = features(Image.open(p))
        gy = (geom.get(p.name) or {}).get("yaw")
        if f is not None and gy is not None:
            vals[p.name] = f[0] - EYE_PER_YAW * gy        # residual
            jaws[p.name] = f[1]
    off = {k for k, v in vals.items() if abs(v) >= THRESHOLD}
    talking = {k for k, j in jaws.items() if j >= JAW_OPEN}
    print(f"  mouth open (jawOpen >= {JAW_OPEN}): {len(talking)} of {len(jaws)}")
    xs = sorted(vals.values())
    print(f"{char}: {len(vals)} measured, threshold {THRESHOLD}")
    print(f"  residual deciles: " + " ".join(f"{xs[int(len(xs)*q/10)]:+.2f}" for q in range(10)))
    print(f"  off camera: {len(off)} of {len(vals)} = {100*len(off)/len(vals):.0f}%")
    (DS / "gaze_mp.json").write_text(json.dumps(
        {k: {"resid": round(v, 3), "jaw": round(jaws.get(k, 0.0), 3),
             "off_camera": abs(v) >= THRESHOLD, "mouth_open": jaws.get(k, 0.0) >= JAW_OPEN}
         for k, v in sorted(vals.items())}, indent=1), encoding="utf-8")

    if sheet:
        order = sorted(vals.items(), key=lambda kv: kv[1])
        # the most negative, the most positive, and the boundary either side
        picks = order[:6] + order[-6:]
        near = sorted(vals.items(), key=lambda kv: abs(abs(kv[1]) - THRESHOLD))[:6]
        picks = picks + near
        tiles = []
        for n, v in picks:
            im = Image.open(IMG / n).convert("RGB")
            im = im.crop((0, int(im.height*0.10), im.width, int(im.height*0.42)))
            im.thumbnail((360, 200), Image.LANCZOS)
            tiles.append((f"{n[-11:]} {v:+.2f} {'OFF' if abs(v) >= THRESHOLD else 'at cam'}", im))
        cols = 6; w = max(t.width for _, t in tiles); h = max(t.height for _, t in tiles)
        rn = (len(tiles)+cols-1)//cols
        sh = Image.new("RGB", (cols*w, rn*(h+18)), (20, 20, 20)); d = ImageDraw.Draw(sh)
        for i, (l, t) in enumerate(tiles):
            x, y = (i % cols)*w, (i//cols)*(h+18)
            sh.paste(t, (x, y)); d.text((x+3, y+h+3), l, fill=(255, 220, 120))
        # outputs/, not a session scratchpad: this wrote the check sheet into one
        # Claude session's temp directory, so the debug branch would throw the
        # moment that directory was gone.
        o = Path("outputs/qc/gaze_mp_check.png")
        o.parent.mkdir(parents=True, exist_ok=True)
        sh.save(o); print("  sheet:", o)

    if apply_:
        n_add = n_rm = 0
        for p in sorted(IMG.glob("*.png")):
            t = p.with_suffix(".txt")
            if not t.exists():
                continue
            parts = [c.strip() for c in t.read_text(encoding="utf-8").strip().split(",")]
            has = next((i for i, c in enumerate(parts) if GAZE_RE.match(c)), None)
            want = p.name in off
            if want and has is None:
                hair = next((i for i, c in enumerate(parts)
                             if c.lower().startswith("her hair")), None)
                parts.insert(hair if hair is not None else min(3, len(parts)), CLAUSE)
                n_add += 1
            elif not want and has is not None:
                parts.pop(has); n_rm += 1
            else:
                continue
            t.write_text(", ".join(parts), encoding="utf-8")
        print(f"  applied: +{n_add} clauses, -{n_rm}")
