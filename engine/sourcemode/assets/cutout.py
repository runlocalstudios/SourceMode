"""Background removal for game assets.

    render (flat studio background)  ->  rembg matte  ->  RGBA PNG (+ WebP)
                                                      ->  sidecar JSON: source, model, report

The game consumes RGBA WebP at 1024x1536 (src/assets/characters/<c>/outfits/
<outfit>_NN_standing.webp). Renders may be another aspect (the photo sets are
4:5), so `fit_canvas` pads or scales into the target with transparent pixels,
anchored bottom-centre so standing figures share a floor line.

The report is a gate in the project's sense: a pure function of the alpha
channel that flags likely problems (hollow matte, figure clipped at an edge,
stray islands) for a human to look at. Nothing here rejects a file.

`remover` is injectable everywhere so the whole module is testable without
downloading a model; the real one is rembg with a per-process session cache.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw

DEFAULT_MODEL = "isnet-general-use"        # good on people at 1MP, ~170 MB download
PORTRAIT_MODEL = "birefnet-portrait"       # sharper hair, ~900 MB; opt in with --model
MATTING = {"alpha_matting_foreground_threshold": 240,
           "alpha_matting_background_threshold": 10,
           "alpha_matting_erode_size": 10}

Remover = Callable[[Image.Image], Image.Image]
_sessions: dict[str, object] = {}


def rembg_remover(model: str = DEFAULT_MODEL, *, matting: bool = True) -> Remover:
    """The real thing. Sessions are cached so a batch loads the model once."""
    from rembg import new_session, remove  # noqa: PLC0415

    if model not in _sessions:
        _sessions[model] = new_session(model)
    session = _sessions[model]

    def _remove(img: Image.Image) -> Image.Image:
        kwargs = dict(MATTING) if matting else {}
        return remove(img.convert("RGBA"), session=session, alpha_matting=matting, **kwargs)

    return _remove


# ----------------------------------------------------------------- report

def _components(mask: np.ndarray, max_side: int = 128) -> int:
    """Count 4-connected foreground islands on a downsampled mask (no scipy)."""
    h, w = mask.shape
    scale = max(1, int(np.ceil(max(h, w) / max_side)))
    small = mask[::scale, ::scale]
    seen = np.zeros_like(small, dtype=bool)
    n = 0
    hs, ws = small.shape
    for y in range(hs):
        for x in range(ws):
            if small[y, x] and not seen[y, x]:
                n += 1
                q = deque([(y, x)])
                seen[y, x] = True
                while q:
                    cy, cx = q.popleft()
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if 0 <= ny < hs and 0 <= nx < ws and small[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
    return n


def alpha_report(alpha: np.ndarray) -> dict:
    """Numbers and flags from an alpha channel (uint8 HxW). Pure; never raises on odd input."""
    a = np.asarray(alpha)
    total = a.size or 1
    fg = a > 127
    coverage = float(fg.mean())
    partial = float(((a > 0) & (a < 255)).mean())
    ys, xs = np.where(fg)
    if len(ys) == 0:
        return {"coverage": 0.0, "partial": partial, "bbox": None, "components": 0,
                "touches": [], "flags": ["empty"]}
    h, w = a.shape
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    touches = [side for side, hit in (("left", bbox[0] == 0), ("top", bbox[1] == 0),
                                       ("right", bbox[2] == w - 1), ("bottom", bbox[3] == h - 1)) if hit]
    comps = _components(fg)
    flags = []
    if coverage < 0.05:
        flags.append("tiny")
    if partial > 0.05:
        # a soft, uncertain matte — usually clothing close to the background colour.
        # 0.063 was a white sundress on light grey, visibly see-through; 0.038 was clean.
        flags.append("hollow")
    if any(s in touches for s in ("left", "right", "top")):
        flags.append("clipped")         # bottom contact is normal for a standing figure
    if comps > 1:
        flags.append("islands")
    return {"coverage": round(coverage, 4), "partial": round(partial, 4), "bbox": bbox,
            "components": comps, "touches": touches, "flags": flags, "pixels": int(total)}


# ----------------------------------------------------------------- canvas

def parse_size(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    w, h = text.lower().replace("×", "x").split("x")
    return int(w), int(h)


def fit_canvas(img: Image.Image, size: tuple[int, int], anchor: str = "bottom") -> Image.Image:
    """Place an RGBA image on a transparent WxH canvas, scaling down only if it
    doesn't fit, anchored bottom-centre (or centre)."""
    img = img.convert("RGBA")
    tw, th = size
    scale = min(tw / img.width, th / img.height, 1.0)
    if scale < 1.0:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    x = (tw - img.width) // 2
    y = th - img.height if anchor == "bottom" else (th - img.height) // 2
    canvas.paste(img, (x, y), img)
    return canvas


# ----------------------------------------------------------------- files

def cutout_file(src: Path, out_dir: Path, *, remover: Remover, model: str,
                size: tuple[int, int] | None = None, webp: bool = False,
                webp_quality: int = 92, root: Path | None = None) -> dict:
    """Cut one render out. Writes <stem>.png (+ .webp) and <stem>.json; returns the sidecar.

    With `root`, the source's folder structure under it is mirrored in out_dir,
    so two folders that both hold a shot_00_s9100.png (every character's photo
    set does) cannot overwrite each other."""
    src = Path(src)
    if root is not None:
        try:
            out_dir = out_dir / src.parent.relative_to(root)
        except ValueError:
            pass
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(src)
    cut = remover(img)
    if size:
        cut = fit_canvas(cut, size)
    report = alpha_report(np.asarray(cut.getchannel("A")))
    png = out_dir / f"{src.stem}.png"
    cut.save(png)
    outputs = {"png": str(png)}
    if webp:
        wp = out_dir / f"{src.stem}.webp"
        cut.save(wp, "WEBP", quality=webp_quality, method=6, exact=True)
        outputs["webp"] = str(wp)
    sidecar = {
        "source": str(src),
        "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest()[:16],
        "model": model,
        "canvas": list(cut.size),
        "outputs": outputs,
        "report": report,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out_dir / f"{src.stem}.json").write_text(json.dumps(sidecar, indent=1), encoding="utf-8")
    return sidecar


def common_root(paths: list[Path]) -> Path | None:
    """Deepest folder containing every path; None for a single file's folder."""
    if not paths:
        return None
    parents = [p.resolve().parent for p in paths]
    root = parents[0]
    for q in parents[1:]:
        while root not in q.parents and root != q:
            root = root.parent
    return root


def cutout_batch(paths: list[Path], out_dir: Path, *, remover: Remover, model: str,
                 size: tuple[int, int] | None = None, webp: bool = False,
                 log=print) -> list[dict]:
    root = common_root(paths)
    results = []
    for p in paths:
        r = cutout_file(p.resolve(), out_dir, remover=remover, model=model, size=size, webp=webp, root=root)
        rep = r["report"]
        flag = f"  [{', '.join(rep['flags'])}]" if rep["flags"] else ""
        rel = Path(r["outputs"]["png"]).relative_to(out_dir.resolve()) if Path(r["outputs"]["png"]).is_absolute() else Path(r["outputs"]["png"])
        log(f"  {rel}: coverage {rep['coverage']:.2f} partial {rep['partial']:.3f}{flag}")
        results.append(r)
    return results


def checkerboard_sheet(pngs: list[Path], out: Path, *, cell: int = 320, cols: int = 4,
                       square: int = 16) -> Path:
    """Thumbnails over a checkerboard — the only honest way to review an alpha edge."""
    rows = max(1, -(-len(pngs) // cols))
    ch = int(cell * 1.5)
    sheet = Image.new("RGB", (cols * cell, rows * (ch + 18)), (250, 250, 250))
    draw = ImageDraw.Draw(sheet)
    for i, p in enumerate(pngs):
        img = Image.open(p).convert("RGBA")
        img.thumbnail((cell - 8, ch - 8))
        board = Image.new("RGB", img.size, (200, 200, 200))
        bd = ImageDraw.Draw(board)
        for y in range(0, img.height, square):
            for x in range(0, img.width, square):
                if (x // square + y // square) % 2:
                    bd.rectangle((x, y, x + square - 1, y + square - 1), fill=(255, 255, 255))
        board.paste(img, (0, 0), img)
        x0, y0 = (i % cols) * cell + 4, (i // cols) * (ch + 18) + 16
        sheet.paste(board, (x0, y0))
        draw.text((x0, y0 - 13), p.stem[:40], fill=(30, 30, 30))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def collect(inputs: list[Path], pattern: str = "*.png") -> list[Path]:
    """Files from a mix of files and directories, image extensions only, sorted."""
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    out: list[Path] = []
    for p in inputs:
        if p.is_dir():
            out.extend(q for q in sorted(p.rglob(pattern)) if q.suffix.lower() in exts and not q.name.startswith("_"))
        elif p.suffix.lower() in exts:
            out.append(p)
    return out
