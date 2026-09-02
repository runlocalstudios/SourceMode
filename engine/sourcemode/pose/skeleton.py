"""Render an OpenPose-style stick figure from MediaPipe landmarks.

A skeleton is the only pose conditioning with ZERO identity in it: no face, no
hair, no body type, no skin. That is its whole appeal — the reference photo is a
picture of a different woman, and everything about her that is not "where the
limbs are" is contamination.

The catch, and the reason AnyPose exists at all: a stick figure has no depth. Its
author's stated rationale for skipping OpenPose is that it "can still result in
depth being incorrect or the pose not fully matching the character". A photo
carries foreshortening, limb thickness and how a body actually folds; a skeleton
carries none of it. 2511 also regressed the skeleton conditioning that 2509 had.

So this is built to be used ALONGSIDE the masked photo as image3, not instead of
it: the photo supplies depth and form, the skeleton pins the joints, and the
mask removes the identity. Whether that beats the photo alone is an empirical
question, which is why it is a flag and not a rewrite.

MediaPipe (Apache-2.0) and PIL only; no DWPose, no ControlNet aux dependency.
"""

from __future__ import annotations

from pathlib import Path

from .metrics import landmarks

# OpenPose-ish limb colouring. The convention matters: models that have seen
# skeleton conditioning were trained on coloured limbs, not white lines.
LIMBS = [
    ((11, 12), (153, 0, 0)),      # shoulders
    ((11, 13), (153, 51, 0)),     # left upper arm
    ((13, 15), (153, 102, 0)),    # left forearm
    ((12, 14), (153, 153, 0)),    # right upper arm
    ((14, 16), (102, 153, 0)),    # right forearm
    ((11, 23), (0, 153, 0)),      # left torso
    ((12, 24), (0, 153, 51)),     # right torso
    ((23, 24), (0, 153, 102)),    # hips
    ((23, 25), (0, 153, 153)),    # left thigh
    ((25, 27), (0, 102, 153)),    # left shin
    ((24, 26), (0, 51, 153)),     # right thigh
    ((26, 28), (0, 0, 153)),      # right shin
    ((27, 31), (51, 0, 153)),     # left foot
    ((28, 32), (102, 0, 153)),    # right foot
]
JOINTS = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
HEAD_POINTS = [0, 7, 8]  # nose and ears: head position and tilt, no features


def draw_skeleton(image_path: Path, model_path: str, dest: Path,
                  *, background: tuple[int, int, int] = (0, 0, 0)) -> bool:
    """Write a stick figure of the person in image_path. False if none found."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    found = landmarks(Path(image_path), model_path)
    if found is None:
        return False
    lm, (w, h) = found
    canvas = Image.new("RGB", (w, h), background)
    dr = ImageDraw.Draw(canvas)
    thick = max(4, int(min(w, h) * 0.012))

    def px(i):
        return (lm[i].x * w, lm[i].y * h)

    for (a, b), colour in LIMBS:
        dr.line([px(a), px(b)], fill=colour, width=thick)
    r = thick * 0.9
    for i in JOINTS:
        x, y = px(i)
        dr.ellipse((x - r, y - r, x + r, y + r), fill=(200, 200, 200))
    # Head as a circle through the ears, so tilt and scale survive without
    # drawing a face — a face here would reintroduce exactly what we removed.
    (lx, ly), (rx, ry), (nx, ny) = px(7), px(8), px(0)
    head_r = max(abs(lx - rx) * 0.85, thick * 2.5)
    cx, cy = (lx + rx) / 2, (ly + ry) / 2
    dr.ellipse((cx - head_r, cy - head_r, cx + head_r, cy + head_r),
               outline=(220, 220, 220), width=max(2, thick // 2))
    dr.ellipse((nx - r, ny - r, nx + r, ny + r), fill=(255, 255, 255))

    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest)
    return True
