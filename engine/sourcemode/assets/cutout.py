"""Background removal for game assets.

    render (flat studio background)  ->  rembg matte  ->  RGBA PNG (+ WebP)
    render (magenta chroma key)      ->  chroma key   ->  sidecar JSON: source, model, report

Two removers. `rembg_remover` is a learned matte for renders on an uncontrolled
background. `chroma_remover` is for renders we shot ourselves against #FF00FF
(the Codex convention - it appears in no character's wardrobe palette; #00FF00 is
the fallback if one ever wears magenta). When we control the background the key is
exact, instant and needs no model, so prefer it.

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

MAGENTA = (255, 0, 255)                    # Codex chroma key
GREEN = (0, 255, 0)                        # fallback when magenta clashes with wardrobe

Remover = Callable[[Image.Image], Image.Image]
_sessions: dict[str, object] = {}


def sample_backdrop(img: Image.Image, band: int = 40) -> tuple[tuple[int, int, int], float]:
    """The backdrop colour actually present, read off the border, with its uniformity.

    Asking a diffusion model for #FF00FF does not get you #FF00FF: "bright magenta
    chroma-key" produced (243,5,159) and (218,11,84) on consecutive seeds. What it
    does produce is *uniform* (mean deviation 2-4), so detect the colour instead of
    assuming it. Returns ((r,g,b), deviation); a high deviation means the border is
    not a clean backdrop and the caller should not key blind.
    """
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    edge = np.concatenate([a[:band].reshape(-1, 3), a[-band:].reshape(-1, 3),
                           a[:, :band].reshape(-1, 3), a[:, -band:].reshape(-1, 3)])
    med = np.median(edge, axis=0)
    dev = float(np.median(np.abs(edge - med).mean(axis=1)))
    return tuple(int(v) for v in med), dev


def chromaticity(rgb: np.ndarray) -> np.ndarray:
    """Colour direction with brightness divided out, so a shadowed backdrop still
    matches the lit one."""
    total = np.maximum(rgb.sum(axis=-1, keepdims=True), 1.0)
    return rgb / total


def key_distance(rgb: np.ndarray, key: tuple[int, int, int]) -> np.ndarray:
    """Chromaticity distance to an arbitrary sampled backdrop colour, 0 = identical.

    Used when the backdrop is whatever the model produced rather than a colour we
    chose. Brightness-invariant, so magenta or green in shadow inside an enclosed
    gap matches the lit backdrop around it.
    """
    k = chromaticity(np.asarray(key, dtype=np.float32).reshape(1, 1, 3))
    return np.sqrt(((chromaticity(rgb) - k) ** 2).sum(axis=-1))


def key_spill(rgb: np.ndarray, key: tuple[int, int, int], *,
              floor: float = 20.0) -> np.ndarray:
    """How much of `key` a pixel is, as 0..1, independent of brightness.

    Two production failures come from getting this wrong, and they are the same
    failure. A plain difference like min(R,B) - G scores shadowed magenta in an
    enclosed gap, say (40,2,44), at 38 - and crimson clothing (180,20,60) at 40.
    Indistinguishable: tighten the threshold to key the gap and red garments get
    keyed too, which is the tarnished red from earlier Codex batches.

    What separates them is balance. Real magenta has R and B roughly equal at any
    brightness; crimson is 180 red against 60 blue. So combine "both ends far above
    the middle channel" with "both ends similar to each other":

        magenta (255,0,255) -> 1.00      crimson  (180,20,60) -> 0.22
        shadowed(40,2,44)   -> 0.86      hot red  (255,0,40)  -> 0.16
                                         skin/black           -> 0.00
    """
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    if key == MAGENTA:
        lo, hi, mid = np.minimum(r, b), np.maximum(r, b), g
    elif key == GREEN:
        lo = hi = g
        mid = np.maximum(r, b)
    else:
        k = np.asarray(key, dtype=np.float32)
        return np.clip(1.0 - np.sqrt(((rgb - k) ** 2).sum(axis=2)) / 255.0, 0.0, 1.0)
    safe_lo = np.maximum(lo, 1.0)
    purity = np.clip((lo - mid) / safe_lo, 0.0, 1.0)      # ends clear of the middle channel
    balance = np.clip(lo / np.maximum(hi, 1.0), 0.0, 1.0)  # ...and close to each other
    # Purity is a ratio, so at very low luminance a couple of counts of sensor or
    # codec noise reads as high keyness: 2.9% of near-black pixels in val's black
    # latex scored above the keying threshold and came out punched full of holes.
    # A backdrop we lit ourselves is never near-black, so ramp keyness away below
    # `floor`. The ramp ends well under the darkest backdrop the enclosed-gap case
    # needs - shadowed magenta at (40,2,44) has lo = 40 and is untouched.
    if floor > 0:
        lit = np.clip((lo - floor * 0.4) / (floor * 0.6), 0.0, 1.0)
        return purity * balance * lit
    return purity * balance


def auto_chroma_remover(*, inner: float = 0.045, outer: float = 0.12,
                        despill: float = 1.0, max_dev: float = 18.0) -> Remover:
    """Key whatever uniform backdrop the plate actually has, detected per image.

    Use this when the backdrop is a colour someone else chose and it is not exactly
    the one they meant. Val's green plates measure (45,227,36) through (94,229,63) -
    the yellower ones score only 0.60 on the fixed green test, landing in the soft
    edge ramp and leaving a haze. Sampling the border instead sidesteps the whole
    question of which green was intended.

    inner/outer are chromaticity distances, so a shadowed backdrop inside an
    enclosed gap still matches the lit backdrop around it. Despill is unpremultiply,
    leaving fully opaque pixels byte-identical.
    """

    def _remove(img: Image.Image) -> Image.Image:
        rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
        key, dev = sample_backdrop(img)
        if dev > max_dev:                     # border is not a clean backdrop
            return img.convert("RGBA")
        d = key_distance(rgb, key)
        alpha = np.clip((d - inner) / max(outer - inner, 1e-6), 0.0, 1.0)
        # Despill EVERY retained pixel by clamping the key's channels to its anchor,
        # the way the Codex skill does. Unpremultiply left 20.3% of edge pixels
        # magenta on Amanda's v3 pack; this is 0% by construction.
        out = np.clip(anchor_clamp(rgb, key, alpha > 0.0), 0, 255)
        return Image.fromarray(np.dstack([out, alpha * 255.0]).astype(np.uint8), "RGBA")

    return _remove


def anchor_clamp(rgb: np.ndarray, key: tuple[int, int, int], where: np.ndarray) -> np.ndarray:
    """Despill by clamping the key's strong channels to the channel it leaves alone.

    Ported from the Codex skill's `remove_backgrounds.py`, which produces 0.0% magenta
    edge pixels against our 20.3% on Amanda's v3 pack (measured 2026-10-03). The
    unpremultiply despill above is correct in theory and under-corrects in practice,
    because its cap is derived from the pixel's own excess and a hair pixel that is
    MOSTLY backdrop still carries a legitimate-looking excess after the division.

    The clamp has no such failure mode: for a magenta key (R and B strong, G the
    anchor) every treated pixel ends with R <= G-1 and B <= G-1, so it cannot read as
    magenta afterwards, whatever alpha says. It is applied to every retained pixel,
    not only the partial band - a fully opaque hair strand lit by the backdrop is
    exactly where the halo lives.
    """
    # Which channels the key is MADE of: the darkest channel anchors, and every
    # channel clearly above it spills. The Codex version keyed off the gap between
    # the top two channels instead, which classifies a clean #FF00FF correctly but
    # misreads the dirty pink the edit model actually returns - (204,20,122) has a
    # 82-count gap between red and blue, so red alone was treated as the spill and
    # blue was left at 122 against green's 20. Still magenta. Anchoring on the
    # darkest channel has no such edge case.
    k = np.asarray(key, dtype=np.int16)
    lo = int(np.argmin(k))
    spill = [c for c in range(3) if c != lo and k[c] - k[lo] >= 40]
    if not spill:                                # not a chroma key at all
        return rgb.astype(np.float32)
    anchor_ch = [c for c in range(3) if c not in spill]
    out = rgb.astype(np.int16).copy()
    anchor = np.maximum(np.max(out[:, :, anchor_ch], axis=2) - 1, 0)
    for c in spill:
        out[:, :, c] = np.where(where, np.minimum(out[:, :, c], anchor), out[:, :, c])
    return out.astype(np.float32)


def despill_unpremultiply(rgb: np.ndarray, alpha: np.ndarray,
                          key: tuple[int, int, int]) -> np.ndarray:
    """Recover the foreground colour of a keyed pixel, removing no more key than
    the pixel actually shows.

    Unpremultiply assumes alpha is true coverage, but ours is a keyness ramp. Where
    the two disagree it over-subtracts: across val's eleven plates 72,437 of 86,230
    partial-alpha pixels came out more than 25 counts VIOLET, a GREEN backdrop
    having pushed them magenta. The mirror of the red tarnish, and just as wrong.

    So the amount of key removed from each of its strong channels is capped at the
    excess that channel actually carries over the channels the key leaves alone.
    The cap is applied BEFORE the division by alpha, which is what makes it hold
    afterwards too: removing more than the excess is what inverts a pixel past
    neutral into the key's complement, and no backdrop can do that.
    """
    k = np.asarray(key, dtype=np.float32)
    a = alpha[..., None]
    want = (1.0 - a) * k                       # what plain unpremultiply removes
    strong = k > k.mean()
    if strong.any() and not strong.all():
        floor = rgb[..., ~strong].min(axis=-1)[..., None]
        room = np.maximum(rgb - floor, 0.0)    # the excess actually present
        want = np.where(strong, np.minimum(want, room), want)
    return (rgb - want) / np.maximum(a, 1e-3)


def suppress_edge_spill(rgba: np.ndarray, key: tuple[int, int, int], *,
                        band_px: float = 48.0, strength: float = 1.0) -> np.ndarray:
    """Remove key-colour dominance from OPAQUE pixels near the matte edge.

    Unpremultiply only corrects pixels the key rated partially transparent. A hair
    strand that came out fully opaque but caught bounce off the backdrop keeps it:
    val's auburn curls held 22,789 opaque pixels with green above both other
    channels, reading as olive against the checkerboard.

    Limited to a band around the edge because that is where bounce physically
    lands - a green garment in the middle of a torso is further away and untouched,
    which is the same reason despill must never be applied globally.
    """
    from scipy import ndimage  # noqa: PLC0415

    rgb, alpha = rgba[..., :3].astype(np.float32), rgba[..., 3]
    dist = ndimage.distance_transform_edt(alpha > 0)
    weight = np.clip(1.0 - (dist - band_px) / max(band_px * 0.5, 1e-6), 0.0, 1.0)
    weight[alpha == 0] = 0.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    if key == GREEN:
        excess = g - np.maximum(r, b)
        m = excess > 0
        rgb[..., 1] = np.where(m, g - strength * weight * excess, g)
    elif key == MAGENTA:
        excess = np.minimum(r, b) - g
        m = excess > 0
        rgb[..., 0] = np.where(m, r - strength * weight * excess, r)
        rgb[..., 2] = np.where(m, b - strength * weight * excess, b)
    return np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)


def fill_alpha_holes(rgba: np.ndarray, max_area: int = 400,
                     opaque_at: int = 250) -> tuple[np.ndarray, int]:
    """Make small interior islands of non-opaque pixels fully opaque.

    A chroma key punches holes inside dark hair and dark clothing wherever a pixel
    happens to score as key-coloured - val's curls came out speckled, and her black
    latex dress had 5.6% of its area non-opaque, reading as white dots on any light
    background. A genuine gap between curls connects to the outside of the
    silhouette; an isolated interior island of a few hundred pixels does not, so it
    is safe to close.

    `opaque_at` is the threshold for "this pixel is part of the figure". It counts
    PARTIAL alpha as a hole, not just near-transparent: the speckles are mostly
    alpha 129-250, which an `alpha < 128` test misses entirely, and in the latex
    those outnumbered the near-transparent ones ten to one.

    Filled pixels take the colour of the nearest opaque pixel. Their own RGB is
    unreliable - a fully keyed pixel is pure backdrop, and one at alpha 0.01 has
    been unpremultiplied by a near-zero divisor - and interior islands are small
    enough that the nearest opaque neighbour is the same strand or fabric.
    """
    from scipy import ndimage  # noqa: PLC0415

    alpha = rgba[..., 3]
    holes = alpha < opaque_at
    # 8-connectivity: a diagonal chain of transparent pixels is a real gap that
    # reaches the outside, and labelling it as enclosed would fill a genuine hole.
    labels, n = ndimage.label(holes, structure=ndimage.generate_binary_structure(2, 2))
    if n == 0:
        return rgba, 0
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    border.discard(0)
    sizes = ndimage.sum(holes, labels, index=np.arange(1, n + 1))
    fill = np.zeros(n + 1, dtype=bool)
    for i in range(1, n + 1):
        if i not in border and sizes[i - 1] <= max_area:
            fill[i] = True
    mask = fill[labels]
    out = rgba.copy()
    if mask.any():
        _, (iy, ix) = ndimage.distance_transform_edt(mask, return_indices=True)
        out[..., :3][mask] = rgba[..., :3][iy[mask], ix[mask]]
        out[..., 3][mask] = 255
    return out, int(mask.sum())


def chroma_remover(key: tuple[int, int, int] = MAGENTA, *, inner: float = 0.40,
                   outer: float = 0.70, despill: float = 1.0,
                   edge_spill_px: float = 0.0) -> Remover:
    """Key a backdrop we rendered ourselves to alpha, with correct despill.

    Alpha comes from `key_spill` (0..1), so it is brightness-invariant: every
    magenta pixel keys whether lit or in shadow, including regions fully enclosed
    by the figure - the gap between an arm and a hip. A learned matte cannot do
    this; it predicts a filled silhouette and leaves interior gaps opaque.
    `inner`/`outer` are keyness thresholds: below inner fully figure, above outer
    fully background, ramping between so hair stays soft.

    Despill is unpremultiply, not subtraction. An edge pixel is a mix,
    observed = a*foreground + (1-a)*key, so the foreground is recovered as
    (observed - (1-a)*key) / a. Where a == 1 that is exactly the observed colour,
    which is why saturated reds come through untouched; subtracting the magenta
    excess from every pixel instead turns crimson (180,20,60) into (140,20,20) -
    the tarnished red seen in earlier Codex batches.
    """

    def _remove(img: Image.Image) -> Image.Image:
        rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
        spill = key_spill(rgb, key)
        alpha = 1.0 - np.clip((spill - inner) / max(outer - inner, 1e-6), 0.0, 1.0)

        out = rgb
        if despill > 0:
            a = alpha[..., None]
            recovered = despill_unpremultiply(rgb, alpha, key)
            # Blend by `despill` so it can be dialled back, and never touch pixels
            # the key considers fully background.
            out = np.where(a > 0, rgb + despill * (recovered - rgb), rgb)
        out = np.clip(out, 0, 255)

        rgba = np.dstack([out, alpha * 255.0]).astype(np.uint8)
        if edge_spill_px > 0:
            rgba = suppress_edge_spill(rgba, key, band_px=edge_spill_px, strength=despill)
        return Image.fromarray(rgba, mode="RGBA")

    return _remove


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

def source_meta(src: Path) -> dict | None:
    """Slot identity for a render: its render sidecar if it has one, else the
    <category>_<NN>_<pose> folder it sits in. None for a loose image."""
    from .catalog import parse_runtime_name  # noqa: PLC0415

    side = src.with_suffix(".json")
    if side.exists():
        try:
            data = json.loads(side.read_text(encoding="utf-8"))
            if isinstance(data.get("asset"), dict):
                return {"asset": data["asset"], "score": data.get("score"), "adherence": data.get("adherence")}
        except (OSError, ValueError):
            pass
    parsed = parse_runtime_name(src.parent.name + ".x")
    if parsed:
        return {"asset": {"character": src.parents[2].name if len(src.parents) > 2 else None, **parsed}, "score": None}
    return None


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
    frame_note = None
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
        "framing": frame_note,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    meta = source_meta(src)
    if meta:
        sidecar["asset"] = meta["asset"]
        sidecar["score"] = meta.get("score")
        sidecar["adherence"] = meta.get("adherence")
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
