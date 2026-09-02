"""Face utilities for pose transfer: hide the reference's identity, restore the character's.

Two separate problems, both about faces, both solved here.

1. The pose reference is a PHOTOGRAPH OF A DIFFERENT WOMAN. Her face is fed to
   the model as image2 on every render, so her identity competes with the
   character's for the whole generation. Masking the reference's face is the
   cheapest identity win available: it removes the competition rather than
   trying to out-argue it in the prompt.

2. In a full-body render the face is a few hundred pixels, so it gets almost
   none of the model's capacity and drifts. Cropping the face, editing it at
   full resolution against the source face, and compositing it back gives the
   face the whole frame to itself.

Everything here is MediaPipe (Apache-2.0) and PIL. Deliberately NOT InstantID,
PuLID or IP-Adapter FaceID: all three are built on InsightFace, whose weights
are non-commercial, and this output ships in the game. InsightFace stays where
CLAUDE.md puts it — scoring candidates in QC tooling, never generating a
shipped pixel.
"""

from __future__ import annotations

from pathlib import Path

from .metrics import landmarks

# MediaPipe Pose face landmarks: 0 nose, 1-6 eyes, 7-8 ears, 9-10 mouth.
NOSE = 0
EYES = (1, 2, 3, 4, 5, 6)
EARS = (7, 8)
MOUTH = (9, 10)
IDENTITY_POINTS = (NOSE, *EYES, *MOUTH)  # ears excluded: they carry head angle


def face_box(image_path: Path, model_path: str, *, pad: float = 0.6,
             include_ears: bool = False) -> tuple[int, int, int, int] | None:
    """Bounding box around the identity-carrying part of the face, padded.

    Returns None when no person is found, which callers must treat as "leave
    the image alone" rather than as an error — a reference that cannot be
    measured is still a usable reference.
    """
    found = landmarks(Path(image_path), model_path)
    if found is None:
        return None
    lm, (w, h) = found
    idx = (*IDENTITY_POINTS, *EARS) if include_ears else IDENTITY_POINTS
    xs = [lm[i].x * w for i in idx]
    ys = [lm[i].y * h for i in idx]
    if not xs or not ys:
        return None
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    # the landmark span covers eyes-to-mouth only, so grow generously to take in
    # the forehead, jaw and cheeks that actually make a face recognisable
    px, py = bw * pad, bh * pad
    return (max(0, int(x0 - px)), max(0, int(y0 - py * 1.6)),
            min(w, int(x1 + px)), min(h, int(y1 + py * 1.3)))


def mask_reference_face(src: Path, dest: Path, model_path: str,
                        fill: tuple[int, int, int] = (128, 128, 128)) -> bool:
    """Grey out the face of the pose reference. True if a face was masked.

    Only the inner face is covered. The ears, head silhouette and hair edges are
    left alone on purpose: the prompt asks for the reference's head TILT and
    gaze direction, and those cues live in the head outline. Covering the whole
    head removes the identity but takes the head angle with it.
    """
    from PIL import Image, ImageDraw, ImageFilter  # noqa: PLC0415

    img = Image.open(src).convert("RGB")
    box = face_box(src, model_path, pad=0.55)
    if box is None:
        img.save(dest)
        return False
    # A hard-edged patch reads as an object to be reproduced; a soft one reads
    # as absence. Feather it so nothing draws a rectangle onto the character.
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(4, (box[2] - box[0]) // 12)))
    img = Image.composite(Image.new("RGB", img.size, fill), img, mask)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return True


def crop_face(image_path: Path, model_path: str, *, pad: float = 1.1,
              size: int = 768) -> tuple:
    """Square crop around the face, upscaled. Returns (image, box) or (None, None).

    Square because the edit graph rescales to roughly 1MP and a square keeps the
    face centred without the model reframing it.
    """
    from PIL import Image  # noqa: PLC0415

    box = face_box(image_path, model_path, pad=pad, include_ears=True)
    if box is None:
        return None, None
    img = Image.open(image_path).convert("RGB")
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    half = max(x1 - x0, y1 - y0) // 2
    half = max(half, 48)
    sq = (max(0, cx - half), max(0, cy - half),
          min(img.width, cx + half), min(img.height, cy + half))
    crop = img.crop(sq)
    if crop.width < size:
        crop = crop.resize((size, size), Image.LANCZOS)
    return crop, sq


def paste_face(base_path: Path, patch, box: tuple, dest: Path, *, feather: int = 24) -> None:
    """Composite an edited face crop back, feathered so there is no seam."""
    from PIL import Image, ImageDraw, ImageFilter  # noqa: PLC0415

    base = Image.open(base_path).convert("RGB")
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    patch = patch.convert("RGB").resize((w, h), Image.LANCZOS)
    mask = Image.new("L", (w, h), 0)
    inset = min(feather, w // 3, h // 3)
    ImageDraw.Draw(mask).rounded_rectangle(
        (inset, inset, w - inset, h - inset), radius=inset, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(6, inset // 2)))
    base.paste(patch, (x0, y0), mask)
    dest.parent.mkdir(parents=True, exist_ok=True)
    base.save(dest)
