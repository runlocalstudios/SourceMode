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


# Landmark indices used to solve the graft affine. Eyes, nose and mouth give
# five well-spread correspondences; ears are excluded because their projected
# position swings hard with yaw and would shear the warp.
_ALIGN_POINTS = (0, 2, 5, 9, 10)  # nose, left eye, right eye, mouth corners


def graft_source_face(source_asset: Path, posed: Path, dest: Path, model_path: str,
                      *, feather_frac: float = 0.18):
    """Warp the SOURCE face onto the posed head, geometrically, in real pixels.

    The reference-conditioned refine had the dependency backwards: geometry sat
    in the init latent and identity had to be imported by the model — and the
    denoise strong enough to import identity (~0.85+) was also strong enough to
    re-frame the crop and turn the head, so every strong candidate failed the
    pose gate. Here the identity is in the pixels from the start — pores and
    freckles included, which no generation pass managed to reproduce — and the
    model's only job afterwards is the HEAL: perspective, lighting, seams.

    The mask is two-zone, learned in three steps. A generous face ellipse
    grafts identity at 0.82-0.88 but its rim crosses hair whose edge pixels are
    genuinely MIXED with backdrop colour, so magenta and blue halos rode in
    past both the chroma key and the heal. A skin-only ellipse killed the halos
    and the identity with them (0.65-0.75) — forehead and jaw carry face shape.
    So the inner 70% of the ellipse grafts unconditionally, the rim grafts only
    pixels that pass a strict backdrop test, and any kept pixel still tinted
    toward the backdrop is despilled toward its own luminance.

    Returns the face box on the posed image, or None when either face is
    missing; on None, dest is not written and the caller keeps the posed image.
    """
    import numpy as np  # noqa: PLC0415
    from PIL import Image, ImageChops, ImageDraw, ImageFilter  # noqa: PLC0415

    src_found = landmarks(source_asset, model_path)
    dst_found = landmarks(posed, model_path)
    if src_found is None or dst_found is None:
        return None
    (slm, (sw, sh)), (dlm, (dw, dh)) = src_found, dst_found

    src_pts = np.array([[slm[i].x * sw, slm[i].y * sh] for i in _ALIGN_POINTS])
    dst_pts = np.array([[dlm[i].x * dw, dlm[i].y * dh] for i in _ALIGN_POINTS])

    # PIL's AFFINE transform wants the DEST->SRC mapping; solve least squares.
    ones = np.ones((len(dst_pts), 1))
    A, *_ = np.linalg.lstsq(np.hstack([dst_pts, ones]), src_pts, rcond=None)
    coeffs = (A[0, 0], A[1, 0], A[2, 0], A[0, 1], A[1, 1], A[2, 1])

    src_img = Image.open(source_asset).convert("RGB")
    posed_img = Image.open(posed).convert("RGB")

    # The assets carry their chroma backdrop baked into the RGB. Key it out:
    # sample the border for the backdrop colour, mask by distance from it.
    arr = np.asarray(src_img, dtype=float)
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    bg = np.median(border, axis=0)
    dist = np.sqrt(((arr - bg) ** 2).sum(axis=2))
    subject = Image.fromarray(((dist > 60) * 255).astype("uint8"), "L")
    subject = subject.filter(ImageFilter.MinFilter(5))  # eat matte-edge slivers
    strict = Image.fromarray(((dist > 110) * 255).astype("uint8"), "L")
    strict = strict.filter(ImageFilter.MinFilter(7))

    # Despill BEFORE warping: a pixel still tinted toward the backdrop hue is
    # pulled to its own luminance, so keyed-through hair strands keep their
    # shape but lose the backdrop colour.
    spill = np.clip((150.0 - dist) / 150.0, 0.0, 1.0)[..., None] * 0.85
    luma = arr.mean(axis=2, keepdims=True)
    despilled = Image.fromarray(np.clip(arr * (1 - spill) + luma * spill, 0, 255).astype("uint8"))

    warped = despilled.transform((dw, dh), Image.AFFINE, coeffs, resample=Image.BICUBIC)
    subject_w = subject.transform((dw, dh), Image.AFFINE, coeffs, resample=Image.BILINEAR)
    strict_w = strict.transform((dw, dh), Image.AFFINE, coeffs, resample=Image.BILINEAR)

    box = face_box(posed, model_path, pad=0.55)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    inner = (cx - (cx - x0) * 0.70, cy - (cy - y0) * 0.70,
             cx + (x1 - cx) * 0.70, cy + (y1 - cy) * 0.70)

    mask = Image.new("L", (dw, dh), 0)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    mask = ImageChops.multiply(ImageChops.multiply(mask, subject_w), strict_w)
    ImageDraw.Draw(mask).ellipse(inner, fill=255)
    mask = ImageChops.multiply(mask, subject_w)  # inner zone still never grafts pure backdrop
    mask = mask.filter(ImageFilter.GaussianBlur(max(4, int((x1 - x0) * feather_frac))))

    posed_img.paste(warped, (0, 0), mask)
    dest.parent.mkdir(parents=True, exist_ok=True)
    posed_img.save(dest)
    return box


def match_exposure(patch, base_region):
    """Rebalance a regenerated patch to the exposure of what it replaces.

    A regenerated face carries its own lighting, so pasting it leaves a visible
    brightness step at the seam — the halo left over once the warp and the
    backdrop spill were solved. Per-channel mean/std matching is enough: it is
    a compositing correction, so it must never touch the model or the identity.
    """
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    p = np.asarray(patch.convert("RGB"), dtype=float)
    b = np.asarray(base_region.convert("RGB"), dtype=float)
    out = np.empty_like(p)
    for c in range(3):
        ps, bs = p[..., c].std(), b[..., c].std()
        scale = 1.0 if ps < 1e-6 else min(max(bs / ps, 0.6), 1.6)  # clamp: no contrast blowouts
        out[..., c] = (p[..., c] - p[..., c].mean()) * scale + b[..., c].mean()
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def paste_face_oval(base_path: Path, patch, crop_box: tuple, dest: Path, model_path: str,
                    *, exposure_match: bool = True):
    """Paste only the FACE OVAL of a healed crop, exposure-matched.

    The square crop carries regenerated background and hair at its corners; a
    rectangular paste therefore drags an invented scene into the render. Taking
    the oval means only skin and features transfer, and everything the pose pass
    got right — hair, wardrobe, background — is left untouched.
    """
    from PIL import Image, ImageDraw, ImageFilter  # noqa: PLC0415

    base = Image.open(base_path).convert("RGB")
    x0, y0, x1, y1 = crop_box
    w, h = x1 - x0, y1 - y0
    patch = patch.convert("RGB").resize((w, h), Image.LANCZOS)

    tmp = dest.parent / f"{dest.stem}_probe.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    patch.save(tmp)
    fb = face_box(tmp, model_path, pad=0.65)
    tmp.unlink(missing_ok=True)
    if fb is None:
        fb = (int(w * 0.20), int(h * 0.15), int(w * 0.80), int(h * 0.85))

    if exposure_match:
        patch = match_exposure(patch, base.crop((x0, y0, x1, y1)))

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse(fb, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(6, (fb[2] - fb[0]) // 10)))
    base.paste(patch, (x0, y0), mask)
    base.save(dest)
    return dest
