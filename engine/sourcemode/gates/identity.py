"""Face-identity gate via InsightFace (buffalo_l) + onnxruntime.

InsightFace is an OPTIONAL extra (uv sync --extra gates) and its pretrained
weights are non-commercial — internal QC tooling only, never shipped.
Imported lazily; when unavailable every score returns
GateResult(score=None, passed=None, details="insightface not installed").

Calibration is per-character: pairwise cosine similarity across the approved
sheet, threshold = mean - 2*std with a floor of 0.30. The mean embedding and
threshold are stored back into the CharacterSource.
"""

from __future__ import annotations

from pathlib import Path

from ..source import CharacterSource
from ..source.store import update_operational
from .base import GateResult

UNAVAILABLE_DETAILS = "insightface not installed"
THRESHOLD_FLOOR = 0.30

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


class IdentityScorer:
    """score(asset, source) -> cosine similarity vs the character's calibrated embedding."""

    def __init__(self, characters_root: Path):
        self.characters_root = characters_root

    def score(self, asset_path: Path, source: CharacterSource) -> GateResult:
        if not insightface_available():
            return GateResult(score=None, passed=None, details=UNAVAILABLE_DETAILS)
        if source.identity_embedding_path is None:
            return GateResult(score=None, passed=None, details="not calibrated — run `sourcemode gates calibrate`")

        import numpy as np  # noqa: PLC0415

        char_dir = self.characters_root / source.character_id
        reference = np.load(char_dir / source.identity_embedding_path)
        embedding = embed_image(Path(asset_path))
        if embedding is None:
            return GateResult(score=0.0, passed=False, details="no face detected")

        score = cosine(reference, embedding)
        threshold = source.identity_threshold
        passed = None if threshold is None else score >= threshold
        return GateResult(score=score, passed=passed, details="", extras={"threshold": threshold})


def calibrate_identity(characters_root: Path, source: CharacterSource) -> CharacterSource:
    """Compute pairwise similarity over the approved sheet; store embedding + threshold.

    threshold = mean(pairwise cosine) - 2*std, floored at 0.30.
    """
    if not insightface_available():
        raise RuntimeError(UNAVAILABLE_DETAILS + " — install with: uv sync --extra gates")

    import numpy as np  # noqa: PLC0415

    char_dir = characters_root / source.character_id
    embeddings = []
    skipped = []
    for rel in source.approved_sheet:
        emb = embed_image(char_dir / rel)
        if emb is None:
            skipped.append(rel)
        else:
            embeddings.append(np.asarray(emb, dtype="float32"))
    if len(embeddings) < 2:
        raise RuntimeError(
            f"need at least 2 face embeddings to calibrate, got {len(embeddings)} (no face found in: {skipped})"
        )

    sims = [
        cosine(embeddings[i], embeddings[j])
        for i in range(len(embeddings))
        for j in range(i + 1, len(embeddings))
    ]
    mean, std = float(np.mean(sims)), float(np.std(sims))
    threshold = max(mean - 2.0 * std, THRESHOLD_FLOOR)

    mean_embedding = np.mean(np.stack(embeddings), axis=0)
    mean_embedding /= np.linalg.norm(mean_embedding)
    embedding_rel = "identity_embedding.npy"
    np.save(char_dir / embedding_rel, mean_embedding)

    return update_operational(
        characters_root,
        source.character_id,
        identity_embedding_path=embedding_rel,
        identity_threshold=round(threshold, 4),
    )
