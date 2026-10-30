"""Take the grey rim off shipped game outfits that were cut before the fix. CPU lane.

    python scripts/eval/fix_fringe.py --all [--dry-run]
    python scripts/eval/fix_fringe.py <character> [...]

Jeremy, 2026-10-30: "There are still a LOT of characters with game assets with
bad gray fringe on the photos ... Do another review of those and fix any with
gray fringe / bleed." Measured on all 1,100 shipped outfit files: the rim is on
the packs dated 2026-09-28 - cut before 05efd46 and never through SourceMode's
staging, so `recut_pack.py` (which re-cuts from her renders) had nothing to
re-cut. Those files ARE the cutouts, so the fix is applied to them in place:
the grey-cut rule from `cutout.hybrid_matte` - every soft pixel and the
outermost opaque ring take the colour of the nearest core pixel (opaque, 3 px
clear of the edge) - then `bleed` under the transparent pixels and the same
WebP save the placer uses. The alpha is untouched, so the silhouette he
approved is the silhouette that stays.

A file cut on or after the fix (mtime 2026-10-26 or later) is left alone. This
writes into the game repo at his explicit request - the third such writer
beside the pack approval and the portrait pick; it does nothing else there.
"""

import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from sourcemode.assets.cutout import EDGE_CORE, bleed
from sourcemode.assets.looks import GAME_ROOT

FIXED_SINCE = time.mktime((2026, 10, 26, 0, 0, 0, 0, 0, -1))
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
ALL, DRY = "--all" in sys.argv, "--dry-run" in sys.argv
if not ARGS and not ALL:
    raise SystemExit(__doc__)
ROOT = GAME_ROOT / "src" / "assets" / "characters"


def log(s: str) -> None:
    print(f"{datetime.now().isoformat(timespec='seconds')}  {s}", flush=True)


def core_colour_edge(arr: np.ndarray) -> tuple[np.ndarray, int]:
    """The RGBA with its edge recoloured from her core; how many pixels changed."""
    rgb, a = arr[..., :3].astype(np.float32), arr[..., 3].astype(np.float32) / 255.0
    solid = a >= 0.98
    core = ndimage.binary_erosion(solid, iterations=EDGE_CORE)
    tgt = (a > 0) & ~core
    if not tgt.any() or not core.any():
        return arr, 0
    _, (iy, ix) = ndimage.distance_transform_edt(~core, return_indices=True)
    out = rgb.copy()
    out[tgt] = rgb[iy[tgt], ix[tgt]]
    changed = int((np.abs(out - rgb).sum(axis=2) > 0).sum())
    res = arr.copy()
    res[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return bleed(res), changed


def rim_lightness(arr: np.ndarray) -> float:
    """Mean luminance of the soft edge minus its nearest core pixel: the halo."""
    rgb, a = arr[..., :3].astype(np.float32), arr[..., 3]
    opaque = a >= 250
    core = ndimage.binary_erosion(opaque, iterations=3)
    soft = (a > 8) & (a < 250)
    if not soft.any() or not core.any():
        return 0.0
    _, (iy, ix) = ndimage.distance_transform_edt(~core, return_indices=True)
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    return float((lum[soft] - lum[iy[soft], ix[soft]]).mean())


chars = sorted(d.name for d in ROOT.iterdir() if (d / "outfits").is_dir()) if ALL else [c.lower() for c in ARGS]
done = skipped = 0
for c in chars:
    od = ROOT / c / "outfits"
    files = sorted(od.glob("*.webp")) if od.is_dir() else []
    todo = [f for f in files if f.stat().st_mtime < FIXED_SINCE]
    if not todo:
        log(f"{c}: {len(files)} files, all cut since the fix - nothing to do")
        continue
    before, after = [], []
    for f in todo:
        arr = np.asarray(Image.open(f).convert("RGBA"))
        fixed, changed = core_colour_edge(arr)
        before.append(rim_lightness(arr)); after.append(rim_lightness(fixed))
        if DRY or not changed:
            skipped += 1
            continue
        tmp = f.with_suffix(".tmp.webp")
        Image.fromarray(fixed, "RGBA").save(tmp, "WEBP", quality=92, method=6, exact=True)
        tmp.replace(f)
        done += 1
    log(f"{c}: {len(todo)} of {len(files)} files {'would be ' if DRY else ''}fixed - "
        f"rim lightness {np.mean(before):+.1f} -> {np.mean(after):+.1f}")
log(f"FRINGEDONE {done} files rewritten, {skipped} unchanged, {len(chars)} characters")
