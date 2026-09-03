"""Landmark measurements used to gate pose references and rank candidates.

Everything here is a RATIO of landmark distances, never a raw pixel value, so
the numbers are comparable across image sizes and subjects. Which ratio is
meaningful depends on the pose, which is why each pose declares its own gates
rather than inheriting a global set.

Hard-won notes:
- `head` is measured against SHOULDER WIDTH, not torso. Shooting from above
  foreshortens the torso while the head keeps its size, so head/torso rises
  with camera height for real perspective reasons and is not comparable
  across camera angles. Both ear span and shoulder width are horizontal, so
  their ratio is invariant to camera pitch.
- `body_facing` exists because MediaPipe's `visibility` field is useless for
  detecting a turned-away subject: the Tasks API returns 1.0 for every
  landmark, including a back fully turned to camera. Landmarks are labelled
  ANATOMICALLY, so the left/right shoulder order in image space inverts when
  the subject turns around — that measures +1.00 front, -1.00 rear, with no
  overlap.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

# MediaPipe Pose landmark indices
NOSE, L_EAR, R_EAR = 0, 7, 8
L_SHO, R_SHO, L_ELB, R_ELB, L_WRI, R_WRI = 11, 12, 13, 14, 15, 16
L_HIP, R_HIP, L_KNE, R_KNE, L_ANK, R_ANK = 23, 24, 25, 26, 27, 28

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task"
)


class PoseModelMissing(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _landmarker(model_path: str):
    import mediapipe as mp  # noqa: PLC0415
    from mediapipe.tasks.python import BaseOptions, vision  # noqa: PLC0415

    if not Path(model_path).exists():
        raise PoseModelMissing(
            f"pose landmarker not found at {model_path}\nDownload it with:\n  curl -L -o "
            f'"{model_path}" {MODEL_URL}'
        )
    opts = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
    )
    return mp, vision.PoseLandmarker.create_from_options(opts)


def landmarks(image_path: Path, model_path: str):
    """33 landmarks for the largest detected person, or None."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    mp, lm = _landmarker(str(model_path))
    img = Image.open(image_path).convert("RGB")
    result = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.array(img)))
    if not result.pose_landmarks:
        return None
    return result.pose_landmarks[0], img.size


def _angle(a, b, c) -> float:
    v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if not n1 or not n2:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))))


def measure(image_path: Path, model_path: str) -> dict | None:
    """All pose metrics for one image. None if no person is found."""
    found = landmarks(Path(image_path), model_path)
    if found is None:
        return None
    lm, (width, height) = found

    def px(i):
        return (lm[i].x * width, lm[i].y * height)

    ear_span = math.dist(px(L_EAR), px(R_EAR))
    shoulder_w = math.dist(px(L_SHO), px(R_SHO))
    shoulder = ((px(L_SHO)[0] + px(R_SHO)[0]) / 2, (px(L_SHO)[1] + px(R_SHO)[1]) / 2)
    hip = ((px(L_HIP)[0] + px(R_HIP)[0]) / 2, (px(L_HIP)[1] + px(R_HIP)[1]) / 2)
    torso = math.dist(shoulder, hip)
    if not shoulder_w or not torso:
        return None

    eye_line = (px(L_EAR)[1] + px(R_EAR)[1]) / 2
    ear_x = abs(px(L_EAR)[0] - px(R_EAR)[0]) or 1.0
    thigh_l = math.dist(hip, px(L_KNE))
    knee_mid_y = (px(L_KNE)[1] + px(R_KNE)[1]) / 2

    return {
        # proportions, invariant to camera pitch
        "head": ear_span / shoulder_w,
        # camera height: kneeling ~0.7-1.0, standing ~1.8-2.3
        "foreshorten": torso / shoulder_w,
        # chin up/down; only meaningful when the face is toward camera
        "gaze": (eye_line - px(NOSE)[1]) / (ear_span or 1.0),
        # apparent angle between the thighs, widened by an overhead camera
        "thigh_angle": _angle(px(L_KNE), hip, px(R_KNE)),
        # shoulder-hip line off vertical: 0 upright, 90 horizontal
        "torso_bend": math.degrees(math.atan2(abs(shoulder[0] - hip[0]), abs(shoulder[1] - hip[1]))),
        # +1 facing camera, -1 facing away
        "body_facing": (px(L_SHO)[0] - px(R_SHO)[0]) / shoulder_w,
        # nose offset from the ear midpoint, in ear spans: ~0 square, 1-2.5 glancing back
        "head_turn": abs(px(NOSE)[0] - (px(L_EAR)[0] + px(R_EAR)[0]) / 2) / ear_x,
        # hips relative to knees, in thigh lengths. +ve = hips ABOVE knees
        # (shallow), <=0 = hips at or below the knees (a genuinely deep squat).
        # STRONGLY camera-dependent: from a high angle the knees project lower
        # in frame than the hips, so a genuinely deep squat still reads +0.4 to
        # +0.55. Level with the subject the same pose reads -0.06 to -0.36.
        # Recalibrate whenever a pose's camera moves.
        "squat_depth": (knee_mid_y - hip[1]) / (thigh_l or 1.0),
        # wrists relative to ankles, in thigh lengths. ~0 = hands down at floor
        # level, +ve = hands carried higher up the body. This is what separates
        # hands-on-floor from hands-on-knees; torso_bend does NOT, because
        # reaching down to the floor from a deep squat leaves the torso vertical
        # (measured 0.2-1.3 degrees, i.e. upright, in both poses).
        "hand_height": (((px(L_ANK)[1] + px(R_ANK)[1]) / 2)
                        - ((px(L_WRI)[1] + px(R_WRI)[1]) / 2)) / (thigh_l or 1.0),
    }


def score_against(candidate: dict, target: dict, limits: dict, weights: dict) -> float | None:
    """Lower is better. None when any metric falls outside its hard limit."""
    total = 0.0
    for key, (lo, hi) in limits.items():
        if key not in candidate or not (lo <= candidate[key] <= hi):
            return None
        total += weights.get(key, 1.0) * abs(candidate[key] - target[key]) / (hi - lo)
    return total


def pose_similarity(candidate: dict, reference: dict, tolerance_deg: float = 45.0,
                    body_only: bool = False) -> dict:
    """How closely a rendered candidate matches the reference pose (0..1).

    Joint angles are compared rather than positions: the reference photo and
    the character have different proportions and framing, so only angles are
    comparable. Body facing and head turn are included because a candidate can
    match every joint angle while facing the wrong way.

    body_only drops the head-PROPORTION term. Use it ONLY when the head size is
    independently guaranteed. It was once switched on for the face-refine pass on
    the theory that `head` moving 0.44->0.62 was ear-detection noise; it was not.
    The refine was genuinely enlarging the head 40% and the proportion term was
    the only thing catching it. Bobbleheads shipped the moment it was disabled.
    """
    joints = ("thigh_angle", "torso_bend")
    parts = {}
    for key in joints:
        parts[key] = max(0.0, 1.0 - abs(candidate[key] - reference[key]) / tolerance_deg)
    parts["facing"] = max(0.0, 1.0 - abs(candidate["body_facing"] - reference["body_facing"]) / 2.0)
    parts["head_turn"] = max(0.0, 1.0 - abs(candidate["head_turn"] - reference["head_turn"]) / 2.0)
    parts["proportion"] = max(0.0, 1.0 - abs(candidate["head"] - reference["head"]) / 0.25)
    if body_only:
        # same weights, renormalised over the 0.90 that is not `proportion`
        score = (
            0.30 * parts["thigh_angle"] + 0.20 * parts["torso_bend"]
            + 0.25 * parts["facing"] + 0.15 * parts["head_turn"]
        ) / 0.90
    else:
        score = (
            0.30 * parts["thigh_angle"] + 0.20 * parts["torso_bend"]
            + 0.25 * parts["facing"] + 0.15 * parts["head_turn"] + 0.10 * parts["proportion"]
        )
    return {"score": round(score, 4), **{k: round(v, 4) for k, v in parts.items()}}
