"""Re-cut renders that already exist, several ways, and measure each - no rendering.

    python scripts/eval/cutout_bench.py [--chars amanda,zara] [--methods prod,birefnet,hybrid]
                                        [--limit N] [--force] [--refresh-cache]

Jeremy, 2026-10-20: "the goal is for me not to need to review the transparencies
once we are done with this work ... I want to be able to test and iterate on this
process without recreating 28 assets each time, and then ideally we would test it
across many of the assets I've created with both pink and gray backgrounds."

Measured first, on cici's key trial (fancy_town_04): Qwen's "magenta" is a hot pink
near (240,12,128), and a maroon dress in shadow (57,16,31) is 0.15 from it in
chromaticity - close enough that thousands of scattered pixels inside the dress key
partially. The despill band then grows 16 px out of EVERY one of those specks and
clamps R and B under G across the whole garment: the black blotches.

Methods, all run on every render found:
    prod      what ships today: grey -> rembg isnet + matting; pink -> auto chroma
    birefnet  BiRefNet-general alone (MIT), how remove.bg-style services work
    hybrid    two signals per pixel. BiRefNet says what is her; the key says what is
              exactly the backdrop. A pixel goes only where they agree, except a
              LARGE region of pure backdrop colour, which goes whatever BiRefNet says
              (the enclosed arm-to-waist gap a learned matte fills in). Despill only
              grows from that real outside, never from a speck inside a garment.

BiRefNet's mask is cached per render, so iterating on `hybrid` needs no model.
Everything runs on the CPU (this onnxruntime has no CUDA provider) - queue it with
`gpu add --cpu`.

Per character: library/<char>/<date>_ab_cutout-bench/
    <method>/<look>.webp       the cutout
    _cache/birefnet/<look>.png BiRefNet's alpha
    sheet.jpg                  each look as [render | prod | birefnet | hybrid] on a checker
    metrics.json               per look, per method
and a summary across everything at outputs/logs/cutout_bench.json.

Numbers per cutout (no human needed to read them):
    shift    share of opaque pixels whose colour moved > 40 from the render -
             despill damage; the blotch bug reads here
    holes    see-through pixels (alpha < 250) inside the figure in components of
             < 1500 px - specks punched into clothing or hair
    override hybrid only: px of pure backdrop BiRefNet called her (an enclosed gap,
             or a garment the colour of the wall)
    dropped  hybrid only: px the key calls subject that BiRefNet removed (a floor
             shadow, or a lost flyaway)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from sourcemode.assets.cutout import (alpha_report, anchor_clamp, auto_chroma_remover, key_distance,
                                      rembg_remover, sample_backdrop)
from sourcemode.config import load_config, outputs_dir
from sourcemode.library import find_set, write_set_json

ARGS = sys.argv[1:]


def opt(name: str, default: str | None = None) -> str | None:
    return ARGS[ARGS.index(name) + 1] if name in ARGS else default


cfg = load_config()
OUT = outputs_dir(cfg)
ROOT = Path(__file__).resolve().parents[3]
METHODS = (opt("--methods") or "prod,birefnet,hybrid").split(",")
CHARS = set(opt("--chars").split(",")) if opt("--chars") else None
LIMIT = int(opt("--limit") or 0)
FORCE = "--force" in ARGS
LOG = OUT / "logs" / "cutout_bench.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

BIG = 1500          # px: a region of pure backdrop this size is background, full stop
SURE_FG, SURE_BG = 0.85, 0.15
BAND = 6.0          # px of despill, grown from the real outside only


def log(s: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def sources() -> list[tuple[str, str, Path, Path]]:
    """(character, label, render, root) for every pack render on disk."""
    found = []
    for d in sorted((OUT / "game-assets").glob("*/renders")):
        for p in sorted(d.glob("*/shot_*.png")):
            found.append((d.parent.name, "pack", p, d))
    for d in sorted((ROOT / "library").glob("*/*_ab_pack-key-trial/renders")):
        for p in sorted(d.glob("*/shot_*.png")):
            found.append((d.parents[1].name, "keytrial", p, d))
    if CHARS:
        found = [f for f in found if f[0] in CHARS]
    return found


def kind_of(key: tuple[int, int, int]) -> str:
    r, g, b = key
    if max(key) - min(key) < 20:
        return "grey"
    return "pink" if r > 150 and b > 60 and g < 80 else "green" if g > 150 else "other"


_bire = None


def birefnet_alpha(img: Image.Image, cache: Path) -> np.ndarray:
    global _bire
    if cache.is_file() and "--refresh-cache" not in ARGS:
        return np.asarray(Image.open(cache).convert("L"), dtype=np.float32) / 255.0
    if _bire is None:
        from rembg import new_session  # noqa: PLC0415
        _bire = new_session("birefnet-general", providers=["CPUExecutionProvider"])
    from rembg import remove  # noqa: PLC0415
    m = remove(img.convert("RGB"), session=_bire, only_mask=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    m.save(cache)
    return np.asarray(m.convert("L"), dtype=np.float32) / 255.0


def key_alpha(rgb: np.ndarray, key: tuple[int, int, int], kind: str) -> np.ndarray:
    """1 = not the backdrop, 0 = exactly the backdrop. Chromaticity for a coloured
    key (shadowed pink is still pink); plain RGB distance for grey, where every
    neutral - white, black, grey cloth - has the backdrop's chromaticity."""
    if kind == "grey":
        d = np.sqrt(((rgb - np.asarray(key, dtype=np.float32)) ** 2).sum(axis=2))
        return np.clip((d - 6.0) / 12.0, 0.0, 1.0)
    d = key_distance(rgb, key)
    return np.clip((d - 0.045) / (0.12 - 0.045), 0.0, 1.0)


def big_components(mask: np.ndarray, min_px: int) -> np.ndarray:
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return np.zeros_like(mask)
    sizes = ndimage.sum(mask, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, dtype=bool)
    keep[1:] = sizes >= min_px
    return keep[lab]


def hybrid(rgb: np.ndarray, key, kind: str, b: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    ka = key_alpha(rgb, key, kind)
    pure_big = big_components(ka <= 0.0, BIG)
    alpha = np.where(b >= SURE_FG, 1.0, np.where(b <= SURE_BG, 0.0, ka))
    # On grey the override is off: a white polo sleeve in shade sits within a few
    # counts of a light-grey wall (cici work_01, 2026-10-20 - 3,559 px of sleeve cut
    # away), and BiRefNet filled no enclosed gap on any of her 56 renders.
    cut = pure_big if kind != "grey" else pure_big & (b < SURE_FG)
    alpha = np.where(cut, 0.0, alpha)
    out = rgb
    if kind != "grey":
        outside = big_components(alpha < 0.5, BIG)
        near = ndimage.distance_transform_edt(~outside) <= BAND
        k = np.asarray(key, dtype=np.float32)
        lo = int(np.argmin(k))
        spill = [c for c in range(3) if c != lo and k[c] - k[lo] >= 40]
        anchor = rgb[:, :, lo]
        dominant = np.all(np.stack([rgb[:, :, c] > anchor for c in spill]), axis=0)
        # ...and only where the pixel actually reads as the backdrop (ka < 1). A
        # garment in the key's own family - sienna's purple flares, every maroon -
        # is R and B over G too, and clamping its rim turned it grey (2026-10-20).
        out = anchor_clamp(rgb, key, near & dominant & (ka < 1.0) & (alpha > 0))
    stats = {"override": int((pure_big & (b >= SURE_FG)).sum()),
             "dropped": int(((ka >= 1.0) & (b <= SURE_BG) & ~pure_big).sum())}
    return np.clip(out, 0, 255), alpha, stats


def measure(rgba: np.ndarray, rgb: np.ndarray, key, kind: str) -> dict:
    a = rgba[..., 3]
    rep = alpha_report(a)
    opaque = a >= 250
    moved = np.abs(rgba[..., :3].astype(np.int16) - rgb.astype(np.int16)).max(axis=2) > 40
    fig = a >= 128
    see = (a < 250) & ~big_components(a < 128, BIG)        # partial, not the real outside
    holes = see & ~big_components(see, BIG)
    # halo: the backdrop's colour still showing on the figure's rim (coloured keys)
    halo = 0.0
    if kind in ("pink", "green"):
        rim = fig & (ndimage.distance_transform_edt(fig) <= 4)
        keyish = key_alpha(rgba[..., :3].astype(np.float32), key, kind) < 1.0
        halo = float((rim & keyish).sum() / max(rim.sum(), 1))
    return {"coverage": rep["coverage"], "partial": rep["partial"], "flags": rep["flags"],
            "halo": round(halo, 4),
            "shift": round(float((moved & opaque).sum() / max(opaque.sum(), 1)), 4),
            "holes": int((holes & ndimage.binary_fill_holes(fig)).sum())}


def checker(w: int, h: int, sq: int = 12) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w]
    on = ((yy // sq + xx // sq) % 2).astype(bool)
    arr = np.where(on[..., None], np.array([250, 250, 250]), np.array([40, 40, 46])).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def run() -> None:
    srcs = sources()
    if LIMIT:
        srcs = srcs[:LIMIT]
    log(f"cutout bench: {len(srcs)} renders, methods {METHODS}")
    prod_grey = None
    prod_pink = auto_chroma_remover()
    summary: dict[str, list] = {}
    by_char: dict[str, list] = {}
    for c, label, p, root in srcs:
        by_char.setdefault(c, []).append((label, p, root))

    for c, items in by_char.items():
        SET = find_set(cfg, c, "ab", "cutout-bench", create=True)
        write_set_json(SET, character=c, kind="ab", name="cutout-bench", date=SET.name[:10])
        mpath = SET / "metrics.json"
        metrics = json.loads(mpath.read_text(encoding="utf-8")) if mpath.is_file() else {}
        tiles = []
        for label, p, root in items:
            # a folder holding more than one shot (edit-era re-rolls) keys by file too
            look = f"{label}_{p.parent.name}" + (f"_{p.stem}" if len(list(p.parent.glob("shot_*.png"))) > 1 else "")
            img = Image.open(p)
            rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
            key, dev = sample_backdrop(img)
            kind = kind_of(key) if dev <= 18 else "noisy"
            row = metrics.setdefault(look, {"source": str(p), "key": list(key), "kind": kind})
            cells = [img.convert("RGB")]
            b = None
            for m in METHODS:
                dest = SET / m / f"{look}.webp"
                if dest.is_file() and not FORCE and m in row:
                    cells.append(Image.open(dest).convert("RGBA"))
                    continue
                t0 = time.time()
                extra = {}
                if m == "prod":
                    if kind in ("pink", "green", "other"):
                        cut = prod_pink(img)
                    else:
                        prod_grey = prod_grey or rembg_remover("isnet-general-use")
                        cut = prod_grey(img)
                    rgba = np.asarray(cut.convert("RGBA"))
                elif m == "birefnet":
                    b = birefnet_alpha(img, SET / "_cache" / "birefnet" / f"{look}.png")
                    rgba = np.dstack([rgb, b * 255.0]).astype(np.uint8)
                elif m == "hybrid":
                    b = b if b is not None else birefnet_alpha(img, SET / "_cache" / "birefnet" / f"{look}.png")
                    if kind == "noisy":
                        rgba = np.dstack([rgb, b * 255.0]).astype(np.uint8)
                    else:
                        out, alpha, extra = hybrid(rgb, key, kind, b)
                        rgba = np.dstack([out, alpha * 255.0]).astype(np.uint8)
                else:
                    raise SystemExit(f"unknown method {m}")
                row[m] = {**measure(rgba, rgb, key, kind), **extra, "secs": round(time.time() - t0, 1)}
                dest.parent.mkdir(parents=True, exist_ok=True)
                cut = Image.fromarray(rgba, "RGBA")
                cut.save(dest, "WEBP", quality=92, method=4, exact=True)
                cells.append(cut)
            log(f"  {c} {look} [{kind}] " + "  ".join(
                f"{m}: shift {row[m]['shift']:.3f} holes {row[m]['holes']} halo {row[m].get('halo', 0):.3f}"
                + (f" ovr {row[m]['override']} drop {row[m]['dropped']}" if m == "hybrid" and "override" in row[m] else "")
                for m in METHODS if m in row))
            tiles.append((look, kind, cells))
            mpath.write_text(json.dumps(metrics, indent=1), encoding="utf-8")
        # sheet: each look as a strip [render | method...] on a dark/light checker
        tw, th = 200, 300
        cols = 2
        strip_w = tw * (1 + len(METHODS)) + 10
        rows = -(-len(tiles) // cols)
        sheet = Image.new("RGB", (cols * strip_w, rows * (th + 16)), (255, 255, 255))
        draw = ImageDraw.Draw(sheet)
        bg = checker(tw, th)
        for i, (look, kind, cells) in enumerate(tiles):
            x0, y0 = (i % cols) * strip_w, (i // cols) * (th + 16) + 14
            draw.text((x0 + 2, y0 - 13), f"{look[:40]} [{kind}]  render | {' | '.join(METHODS)}",
                      fill=(20, 20, 20))
            for j, im in enumerate(cells):
                im = im.copy()
                im.thumbnail((tw, th))
                tile = bg.copy()
                if im.mode == "RGBA":
                    tile.paste(im, (0, 0), im)
                else:
                    tile.paste(im, (0, 0))
                sheet.paste(tile, (x0 + j * tw, y0))
        sheet.save(SET / "sheet.jpg", quality=88)
        summary[c] = [{"look": k, **v} for k, v in metrics.items()]
        log(f"{c}: {len(tiles)} looks -> {SET / 'sheet.jpg'}")

    sp = OUT / "logs" / "cutout_bench.json"
    old = json.loads(sp.read_text(encoding="utf-8")) if sp.is_file() else {}
    old.update(summary)
    sp.write_text(json.dumps(old, indent=1), encoding="utf-8")
    log(f"CUTOUTBENCHDONE {sum(len(v) for v in summary.values())} looks -> {sp}")


run()
