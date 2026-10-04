"""Prompt adherence, measured: did the render do what the prompt asked?

Jeremy, 2026-10-02, after a full-body render was placed over a correct mid-thigh
one: a face-size threshold "is not the right generalized rule. There could be
examples later where I do add full body shots." So the rule is relative to the
ASK. The render records what it asked for (crop class, body family and degrees,
head family and degrees, expression type) and this module measures what came
back, deterministically, with tools already in use:

  crop        MediaPipe pose landmarks - which of hips / knees / ankles are in frame
  body turn   shoulder depth from the same landmarks - which shoulder is nearer
  head turn   nose tip against the eye midpoint from the face landmarks
  expression  face blendshapes - smile, asymmetry, mouth opening

`check()` returns the list of asks the render broke; `place` ranks by that count
before identity. Everything here annotates; nothing blocks.
"""
from __future__ import annotations

from pathlib import Path

MODELS = Path(__file__).resolve().parents[2] / "models" / "mediapipe"
POSE_MODEL = MODELS / "pose_landmarker_full.task"
FACE_MODEL = MODELS / "face_landmarker.task"

# MediaPipe pose landmark indices
L_SHOULDER, R_SHOULDER = 11, 12       # "left" is the SUBJECT's left = image-right
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
# face mesh indices
NOSE_TIP, L_EYE_OUTER, R_EYE_OUTER = 1, 263, 33

CROP_ORDER = ["chest-up", "waist-up", "mid-thigh-up", "knee-up", "full-body"]
VIS = 0.5

_pose = None
_face = None


def _landmarkers():
    global _pose, _face
    if _pose is None:
        import mediapipe as mp  # noqa: PLC0415
        from mediapipe.tasks import python as mpp  # noqa: PLC0415
        from mediapipe.tasks.python import vision  # noqa: PLC0415
        _pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=str(POSE_MODEL)),
            num_poses=1, running_mode=vision.RunningMode.IMAGE))
        _face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mpp.BaseOptions(model_asset_path=str(FACE_MODEL)),
            output_face_blendshapes=True, num_faces=1, running_mode=vision.RunningMode.IMAGE))
    return _pose, _face


def _in_frame(lm) -> bool:
    return getattr(lm, "visibility", 1.0) >= VIS and 0.0 <= lm.y <= 1.0 and 0.0 <= lm.x <= 1.0


def measure(path: Path) -> dict:
    """What the image shows: crop class, body side, head side, expression type.
    Any field can be None when the landmarker finds nothing."""
    import mediapipe as mp  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    pose, face = _landmarkers()
    rgb = np.asarray(Image.open(path).convert("RGB"))
    img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    got: dict = {"crop": None, "body_side": None, "body_depth": None, "head_side": None,
                 "head_offset": None, "expression": None, "smile": None, "jaw": None,
                 "gaze": None, "eyes_on_lens": None}

    pr = pose.detect(img)
    if pr.pose_landmarks:
        lm = pr.pose_landmarks[0]
        ankles = _in_frame(lm[L_ANKLE]) or _in_frame(lm[R_ANKLE])
        knees = _in_frame(lm[L_KNEE]) or _in_frame(lm[R_KNEE])
        hips = _in_frame(lm[L_HIP]) or _in_frame(lm[R_HIP])
        shoulders = _in_frame(lm[L_SHOULDER]) and _in_frame(lm[R_SHOULDER])
        if ankles:
            got["crop"] = "full-body"
        elif knees:
            got["crop"] = "knee-up"
        elif hips:
            got["crop"] = "mid-thigh-up"       # hips in frame, knees out: mid-thigh or waist
        elif shoulders:
            got["crop"] = "chest-up"
        if shoulders:
            # z is depth, smaller = nearer the camera. Subject-left shoulder sits on
            # IMAGE-RIGHT. If it is nearer, the torso faces image-left.
            depth = float(lm[L_SHOULDER].z - lm[R_SHOULDER].z)
            got["body_depth"] = round(depth, 3)
            got["body_side"] = "front" if abs(depth) < 0.08 else ("image-left" if depth < 0 else "image-right")

    fr = face.detect(img)
    if fr.face_landmarks:
        f = fr.face_landmarks[0]
        mid = (f[L_EYE_OUTER].x + f[R_EYE_OUTER].x) / 2
        width = abs(f[L_EYE_OUTER].x - f[R_EYE_OUTER].x) or 1e-6
        off = (f[NOSE_TIP].x - mid) / width          # negative = nose toward image-left
        got["head_offset"] = round(float(off), 3)
        got["head_side"] = "front" if abs(off) < 0.12 else ("image-left" if off < 0 else "image-right")
    if fr.face_blendshapes:
        b = {c.category_name: c.score for c in fr.face_blendshapes[0]}
        sl, sr = b.get("mouthSmileLeft", 0.0), b.get("mouthSmileRight", 0.0)
        smile, jaw = (sl + sr) / 2, b.get("jawOpen", 0.0)
        got["smile"], got["jaw"] = round(smile, 3), round(jaw, 3)
        # gaze, as gaze_mp.py scores it: (inLeft + outRight) - (outLeft + inRight);
        # large magnitude = eyes off the lens. Jeremy: she must ALWAYS look at the camera.
        gaze = ((b.get("eyeLookInLeft", 0) + b.get("eyeLookOutRight", 0))
                - (b.get("eyeLookOutLeft", 0) + b.get("eyeLookInRight", 0)))
        got["gaze"] = round(float(gaze), 3)
        got["eyes_on_lens"] = abs(gaze) < 1.0
        if smile >= 0.35 and jaw >= 0.06:
            got["expression"] = "teeth"
        elif smile >= 0.3:
            got["expression"] = "closed-lip"
        elif smile >= 0.12 and abs(sl - sr) >= 0.12:
            got["expression"] = "flirty"
        else:
            got["expression"] = "neutral"
    return got


def check(asked: dict, got: dict) -> dict:
    """The asks the render broke. Hard: crop, head side, neutral-vs-smile. Soft: body
    side (uncalibrated depth signal) and which kind of smile."""
    failed, soft = [], []
    if asked.get("crop") and got.get("crop"):
        want, have = asked["crop"], got["crop"]
        ok = have == want or (want in ("waist-up", "mid-thigh-up", "upper-thigh-up") and have == "mid-thigh-up")
        if not ok:
            failed.append(f"crop: asked {want}, got {have}")
    # Body side comes from MediaPipe shoulder DEPTH, which is the noisiest of these
    # signals (the seated, near-frontal plate reads -0.35), so until it is
    # calibrated against judged images it is a soft miss, not a hard one.
    if asked.get("body_side") and got.get("body_side") and got["body_side"] != asked["body_side"]:
        soft.append(f"body: asked {asked['body_side']}, got {got['body_side']}")
    if asked.get("head_side") and got.get("head_side") and got["head_side"] != asked["head_side"]:
        failed.append(f"head: asked {asked['head_side']}, got {got['head_side']}")
    if got.get("eyes_on_lens") is False:
        failed.append(f"gaze: eyes off the lens ({got.get('gaze')})")
    if asked.get("expression") and got.get("expression"):
        want, have = asked["expression"], got["expression"]
        smiling = {"closed-lip", "teeth", "flirty"}
        if (want == "neutral") != (have == "neutral"):
            failed.append(f"expression: asked {want}, got {have}")
        elif want in smiling and have in smiling and want != have:
            soft.append(f"expression: asked {want}, got {have}")
    return {"failed": failed, "soft": soft, "got": got}
