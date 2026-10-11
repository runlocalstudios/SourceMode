"""Face embeddings via InsightFace (buffalo_l) + onnxruntime.

InsightFace is an OPTIONAL extra (uv sync --extra gates) and its pretrained
weights are non-commercial — internal QC tooling only, never shipped.
Imported lazily; callers check `insightface_available()` or get None back.
"""

from __future__ import annotations

from pathlib import Path

_app = None
_import_failed = False


def _get_face_app():
    """Lazy-load the InsightFace FaceAnalysis app (buffalo_l). None if unavailable."""
    global _app, _import_failed
    if _app is not None:
        return _app
    if _import_failed:
        return None
    try:
        from insightface.app import FaceAnalysis  # noqa: PLC0415

        app = FaceAnalysis(name="buffalo_l")
        app.prepare(ctx_id=0, det_size=(640, 640))
        _app = app
        return _app
    except Exception:
        _import_failed = True
        return None


def insightface_available() -> bool:
    try:
        import insightface  # noqa: F401, PLC0415
        import onnxruntime  # noqa: F401, PLC0415

        return True
    except Exception:
        return False


def embed_image(image_path: Path):
    """Return the embedding of the largest face in the image, or None."""
    app = _get_face_app()
    if app is None:
        return None
    import cv2  # noqa: PLC0415

    img = cv2.imread(str(image_path))
    if img is None:
        return None
    faces = app.get(img)
    if not faces:
        return None
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return face.normed_embedding


def cosine(a, b) -> float:
    import numpy as np  # noqa: PLC0415

    a = np.asarray(a, dtype="float32")
    b = np.asarray(b, dtype="float32")
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)
