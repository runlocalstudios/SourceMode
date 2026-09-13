"""Gate on the TRAINING SET, not the render.

Every other gate in this package scores what comes out of the pipeline. Nothing
scored what went into it, and on 2026-09-12 that cost us five LoRAs: the datasets
carried a median face of ~180px at the training bucket (~22px once the VAE has
compressed it), boilerplate captions repeated across every image, five
self-identical control/target pairs teaching "reproduce the input face", and in
sunny's case 6 degrees of head-angle variety. No amount of inference tuning
recovers an identity the gradient never contained — nine sampler-side levers
measured flat before anyone looked at the input.

Same contract as the rest of the package: a pure scorer that annotates. It
blocks only when a caller passes block=True.

Split in two on purpose, per the repo rule that every InsightFace-dependent step
stays unit-testable without one:

    measure_dataset(...)  -> DatasetMeasurements   needs InsightFace (or an injected measurer)
    evaluate(...)         -> dict report           pure, no models, fully testable
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Defaults come from what the failed datasets looked like versus published practice
# for Qwen character LoRAs (train at the resolution you generate at; variety over
# volume; caption everything except the identity).
THRESHOLDS = {
    "min_median_face_px": 300,      # at the training bucket; 400+ is comfortable
    "min_face_px_floor": 150,       # individual images below this teach nothing
    "max_tiny_face_frac": 0.25,     # ...and no more than this share may be that small
    "min_caption_unique_frac": 0.8,  # captions should be per-image, not stock
    "min_caption_words": 8,         # excluding the trigger token
    "max_self_pairs": 0,            # control == target trains "change nothing"
    "min_yaw_range_deg": 30.0,      # a wardrobe pack needs her at an angle
    # Range alone is satisfied by two outliers: priyanka's curated 33 spanned 34 deg
    # on THREE off-axis images and would have trained a frontal-only LoRA. Require a
    # real share of the set to be turned away from camera.
    "offangle_deg": 10.0,
    "min_offangle_frac": 0.25,
    "min_centroid_cosine": 0.60,    # below this an image is a different person
    "max_pairwise_cosine": 0.92,    # above this the set is near-identical shots
    "max_duplicate_frac": 0.10,
}


@dataclass
class FaceMetrics:
    """One image's measurements. face_px is the face width AT THE TRAINING BUCKET."""

    name: str
    face_px: int
    yaw_deg: float
    embedding: object | None = None


@dataclass
class DatasetMeasurements:
    faces: list[FaceMetrics] = field(default_factory=list)
    captions: dict[str, str] = field(default_factory=dict)     # image name -> caption
    self_pair_names: list[str] = field(default_factory=list)   # control == target
    n_images: int = 0
    no_face: list[str] = field(default_factory=list)
    bucket_px: int = 1024
    render_size: tuple[int, int] | None = None
    no_upscale: bool = True          # mirrors bucket_no_upscale in the dataset TOML


def _finding(check: str, passed: bool, detail: str, value=None) -> dict:
    return {"check": check, "passed": passed, "detail": detail, "value": value}


def evaluate(m: DatasetMeasurements, trigger: str = "", thresholds: dict | None = None) -> dict:
    """Score measurements against thresholds. Pure: no models, no filesystem."""
    t = {**THRESHOLDS, **(thresholds or {})}
    out: list[dict] = []

    px = sorted(f.face_px for f in m.faces)
    if px:
        med = statistics.median(px)
        tiny = sum(1 for v in px if v < t["min_face_px_floor"])
        out.append(_finding(
            "face_resolution", med >= t["min_median_face_px"],
            f"median face {med:.0f}px at the {m.bucket_px}px bucket"
            f"{' (no upscale)' if m.no_upscale else ''} "
            f"(~{med / 8:.0f}px in latent); need >= {t['min_median_face_px']}px", med))
        out.append(_finding(
            "tiny_faces", tiny / len(px) <= t["max_tiny_face_frac"],
            f"{tiny}/{len(px)} images have a face under {t['min_face_px_floor']}px", tiny / len(px)))
    else:
        out.append(_finding("face_resolution", False, "no faces measured", None))

    if m.no_face:
        out.append(_finding("face_detected", False,
                            f"{len(m.no_face)} image(s) with no detectable face: "
                            + ", ".join(m.no_face[:5]), len(m.no_face)))

    caps = list(m.captions.values())
    # A dataset with no captions at all must fail loudly: every caption check below
    # lives inside `if caps`, so silence here would read as a pass.
    out.append(_finding(
        "caption_present", len(caps) >= m.n_images,
        f"{m.n_images - len(caps)} of {m.n_images} image(s) have no caption" if len(caps) < m.n_images
        else f"all {m.n_images} images captioned", m.n_images - len(caps)))
    if caps:
        uniq = len(set(caps)) / len(caps)
        out.append(_finding(
            "caption_variety", uniq >= t["min_caption_unique_frac"],
            f"{len(set(caps))} distinct captions across {len(caps)} images "
            f"({uniq:.0%}); stock captions force the trigger to absorb the scene", uniq))
        words = [len([w for w in c.replace(trigger, "").replace(",", " ").split() if w])
                 for c in caps]
        mean_w = statistics.mean(words)
        out.append(_finding(
            "caption_detail", mean_w >= t["min_caption_words"],
            f"mean {mean_w:.1f} words per caption beyond the trigger; describe outfit, "
            f"pose, setting and expression so only identity is left uncaptioned", mean_w))
        if trigger:
            bad = [n for n, c in m.captions.items() if not c.startswith(trigger)]
            out.append(_finding("caption_trigger", not bad,
                                f"{len(bad)} caption(s) do not start with {trigger!r}", len(bad)))

    out.append(_finding(
        "self_pairs", len(m.self_pair_names) <= t["max_self_pairs"],
        f"{len(m.self_pair_names)} pair(s) have control == target, which trains "
        f"'reproduce the input face unchanged'" +
        (": " + ", ".join(m.self_pair_names[:5]) if m.self_pair_names else ""),
        len(m.self_pair_names)))

    yaws = [f.yaw_deg for f in m.faces]
    if yaws:
        rng = max(yaws) - min(yaws)
        out.append(_finding(
            "angle_spread", rng >= t["min_yaw_range_deg"],
            f"head yaw spans {rng:.0f} deg ({min(yaws):.0f} to {max(yaws):.0f}); "
            f"need >= {t['min_yaw_range_deg']:.0f} to render her turned away from camera", rng))
        off = sum(1 for v in yaws if abs(v) > t["offangle_deg"])
        out.append(_finding(
            "angle_coverage", off / len(yaws) >= t["min_offangle_frac"],
            f"{off}/{len(yaws)} images are turned more than {t['offangle_deg']:.0f} deg off axis "
            f"({off / len(yaws):.0%}); need >= {t['min_offangle_frac']:.0%} or the LoRA only "
            f"learns her facing camera", off / len(yaws)))

    embs = [f.embedding for f in m.faces if f.embedding is not None]
    if len(embs) >= 3:
        import numpy as np  # noqa: PLC0415

        E = np.stack([np.asarray(e, dtype=float) for e in embs])
        E /= np.linalg.norm(E, axis=1, keepdims=True)
        cen = E.mean(0); cen /= np.linalg.norm(cen)
        tocen = E @ cen
        M = E @ E.T
        iu = np.triu_indices(len(E), 1)
        pw = float(M[iu].mean())
        outliers = [m.faces[i].name for i in range(len(E)) if tocen[i] < t["min_centroid_cosine"]]
        out.append(_finding(
            "identity_coherence", not outliers,
            f"{len(outliers)} image(s) below cosine {t['min_centroid_cosine']} to the set centroid"
            + (": " + ", ".join(outliers[:5]) if outliers else "; the set is one person"),
            float(tocen.min())))
        out.append(_finding(
            "identity_variety", pw <= t["max_pairwise_cosine"],
            f"mean pairwise cosine {pw:.3f}; above {t['max_pairwise_cosine']} means "
            f"near-identical shots and the LoRA learns one look, not the person", pw))
        dupes = sum(1 for i, j in zip(*iu) if M[i, j] >= 0.95)
        out.append(_finding(
            "duplicates", dupes / len(E) <= t["max_duplicate_frac"],
            f"{dupes} near-duplicate pair(s) in {len(E)} images", dupes / len(E)))

    if m.render_size:
        rw, rh = m.render_size
        matched = m.bucket_px >= max(rw, rh) * 0.95
        out.append(_finding(
            "resolution_match", matched,
            f"training bucket {m.bucket_px}px vs render {rw}x{rh}; train at the "
            f"resolution you generate at", m.bucket_px))

    failed = [f for f in out if not f["passed"]]
    return {"passed": not failed, "n_images": m.n_images,
            "score": round(1 - len(failed) / len(out), 3) if out else None,
            "findings": out, "failed": [f["check"] for f in failed]}


def measure_dataset(
    dataset_dir: Path,
    *,
    bucket_px: int = 1024,
    render_size: tuple[int, int] | None = None,
    no_upscale: bool = True,
    measure_face: Callable[[Path, int], FaceMetrics | None] | None = None,
) -> DatasetMeasurements:
    """Walk a musubi dataset dir (image*/ + optional control*/ + .txt captions).

    measure_face is injectable so this is testable without InsightFace.
    """
    dataset_dir = Path(dataset_dir)
    measure_face = measure_face or _insightface_measurer(no_upscale)
    m = DatasetMeasurements(bucket_px=bucket_px, render_size=render_size, no_upscale=no_upscale)
    image_dirs = sorted(d for d in dataset_dir.glob("image*") if d.is_dir()) or [dataset_dir]
    for idir in image_dirs:
        cdir = dataset_dir / idir.name.replace("image", "control")
        for p in sorted(idir.glob("*.png")) + sorted(idir.glob("*.jpg")):
            m.n_images += 1
            cap = p.with_suffix(".txt")
            if cap.exists():
                text = cap.read_text(encoding="utf-8").strip()
                if text:
                    m.captions[p.name] = text
            fm = measure_face(p, bucket_px)
            if fm is None:
                m.no_face.append(p.name)
            else:
                m.faces.append(fm)
            cp = cdir / p.name
            if cp.exists() and _same_image(p, cp):
                m.self_pair_names.append(p.name)
    return m


def _same_image(a: Path, b: Path, tol: float = 3.0) -> bool:
    from PIL import Image  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    ia = np.asarray(Image.open(a).convert("RGB").resize((64, 64)), dtype=float)
    ib = np.asarray(Image.open(b).convert("RGB").resize((64, 64)), dtype=float)
    return bool(abs(ia - ib).mean() < tol)


def _insightface_measurer(no_upscale: bool = True) -> Callable[[Path, int], FaceMetrics | None]:
    def measure(path: Path, bucket_px: int) -> FaceMetrics | None:
        import numpy as np  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        from .identity import _get_face_app  # noqa: PLC0415

        app = _get_face_app()
        if app is None:
            return None
        im = Image.open(path).convert("RGB")
        # What the trainer will actually see. With bucket_no_upscale the image is
        # never blown up to fill the bucket, so reporting the upscaled face width
        # would overstate the real detail (gabi read 597px when it trains at 398).
        scale = bucket_px / max(im.size)
        if no_upscale:
            scale = min(scale, 1.0)
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))))
        faces = app.get(np.asarray(im)[:, :, ::-1])
        if not faces:
            return None
        f = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        yaw = float(f.pose[1]) if getattr(f, "pose", None) is not None else 0.0
        return FaceMetrics(path.name, int(f.bbox[2] - f.bbox[0]), yaw, f.normed_embedding)

    return measure


def gate_dataset(dataset_dir: Path, *, trigger: str = "", block: bool = False,
                 thresholds: dict | None = None, **kw) -> dict:
    """Measure + evaluate. Annotates by default; raises only when block=True."""
    report = evaluate(measure_dataset(dataset_dir, **kw), trigger=trigger, thresholds=thresholds)
    if block and not report["passed"]:
        raise DatasetGateError(dataset_dir, report)
    return report


class DatasetGateError(RuntimeError):
    def __init__(self, dataset_dir: Path, report: dict):
        lines = [f"{f['check']}: {f['detail']}" for f in report["findings"] if not f["passed"]]
        super().__init__(f"{dataset_dir} failed {len(lines)} dataset check(s):\n  " + "\n  ".join(lines))
        self.report = report
