"""Normalise an asset's framing to the shipped art, by measuring - not by prompting.

Jeremy, 2026-10-03: "the girl is smaller in the picture every time, I could swear I
told you to change the prompts to be upper thigh but they are still a lot lower than
that." Measured against the Codex-generated packs already in the game:

    pack              face width   hips (fraction of frame height)
    CODEX trina         20.9%            0.77
    CODEX priyanka      18.0%            0.70
    ours (amanda v3)    19.0%            0.74

Prompt wording does not move this reliably - "upper-thigh, bottom edge just below the
hips" rendered at 0.74, the same place the older "mid-thigh" wording did. The skill's
own rule applies: match the art's framing by measuring and rescaling, not by asking.

So the cutout is cropped at the bottom until the hips sit at TARGET_HIPS, then the
canvas fit scales the subject up to fill the frame - which is what makes the face
bigger. Nothing is cropped above the hips, and a render that is already tight is left
alone. If the pose landmarker finds nothing, the image is returned untouched.
"""
from __future__ import annotations

from pathlib import Path

TARGET_HIPS = 0.80          # a little tighter than trina's 0.77; knees stay out
MIN_GAIN = 0.03             # don't bother re-cropping for less than this
MODEL = Path(__file__).resolve().parents[2] / "models" / "mediapipe" / "pose_landmarker_full.task"
L_HIP, R_HIP, L_KNEE, R_KNEE = 23, 24, 25, 26

_landmarker = None


def _get():
    global _landmarker
    if _landmarker is None:
        import mediapipe as mp  # noqa: PLC0415
        from mediapipe.tasks import python as mpp  # noqa: PLC0415
        from mediapipe.tasks.python import vision  # noqa: PLC0415
        _landmarker = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=str(MODEL)),
            num_poses=1, running_mode=vision.RunningMode.IMAGE))
    return _landmarker


def crop_to_hips(img, target: float = TARGET_HIPS):
    """RGBA in, RGBA out, bottom-cropped so the hips land at `target` of the height.

    Returns (image, note). The note records what was measured and done, for the
    sidecar - a framing change that leaves no trace is how the knee-high crops went
    unnoticed for two packs.
    """
    import numpy as np  # noqa: PLC0415
    import mediapipe as mp  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    rgba = img.convert("RGBA")
    a = np.asarray(rgba)[:, :, 3]
    rows = np.where(a.max(axis=1) > 8)[0]
    if not len(rows):
        return img, "framing: empty alpha"
    top, bottom = int(rows[0]), int(rows[-1])
    try:
        res = _get().detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                     data=np.asarray(rgba.convert("RGB"))))
    except Exception as exc:  # noqa: BLE001 - a measurement, never a blocker
        return img, f"framing: landmarker failed ({exc})"
    if not res.pose_landmarks:
        return img, "framing: no pose found, left as rendered"
    lm = res.pose_landmarks[0]
    hip_px = (lm[L_HIP].y + lm[R_HIP].y) / 2 * rgba.height
    if hip_px <= top:
        return img, "framing: hips above the subject top, left as rendered"
    want_bottom = top + (hip_px - top) / target
    if want_bottom >= bottom - 1:
        return img, f"framing: already tight (hips {(hip_px - top) / (bottom - top):.2f})"
    before = (hip_px - top) / (bottom - top)
    new_bottom = int(round(min(want_bottom, rgba.height)))
    out = rgba.crop((0, 0, rgba.width, new_bottom))
    gain = (new_bottom - top) and (bottom - top) / (new_bottom - top)
    if gain - 1 < MIN_GAIN:
        return img, f"framing: gain {gain:.2f} below threshold"
    return Image.fromarray(np.asarray(out)), (
        f"framing: hips {before:.2f} -> {target:.2f}, cropped {bottom - new_bottom}px, subject {gain:.2f}x larger")
