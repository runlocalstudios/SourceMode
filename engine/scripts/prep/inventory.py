"""What training material a character already has, grouped by framing and angle.

    python scripts/prep/inventory.py <char> [--no-base]

Jeremy, 2026-10-05, on gabi: "are you really sure we can't train Gabi with the
assets we have? Aggregate her photos created by codex plus references and group
them by angle and shot." This answers that question for anyone - before a
Lora-Gen run is spent on a character who might already have enough.

Sources mirror gather_character.py (which runs at import, so it cannot be
imported): references, every codex run folder carrying her name, loose
`<char>_*` files and `<char>/` subfolders in shared runs, and her hand-collected
base folder unless --no-base.

Per image, CPU only (InsightFace + MediaPipe, so it goes through the GPU queue
like every model-loading job):

  framing   MediaPipe's crop class, with chest-up split by face height into
            "head & shoulders" vs "chest-up" - the curriculum's own shot types
  angle     head yaw band: frontal / slight / three-quarter / profile
  identity  best cosine against her references (a floor, never a ranking)
  face_px   face-box height once fitted to the 1024x1536 training bucket -
            the dataset gate wants 300, 400 is the target

Writes outputs/qc/inventory_<char>.json and inventory_<char>.jpg - a contact
sheet with one row per framing and one column block per angle band.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from sourcemode.assets.adherence import measure
from sourcemode.gates.identity import _get_face_app

CHAR = sys.argv[1].lower()
BASE = Path("C:/Epic Games/Files/cnc info")
REFS = BASE / "codex/references"
EXT = (".png", ".jpg", ".jpeg", ".webp")
BAD_DIR = ("wrong", "bad", "reject", "discard", "dupe", "archive", "old_", "_old", "superseded")
BUCKET_W, BUCKET_H = 1024, 1536
OUT = Path("outputs/qc")
OUT.mkdir(parents=True, exist_ok=True)


def sources() -> list[tuple[Path, str]]:
    seen, out = set(), []

    def take(p: Path, prov: str):
        if p.suffix.lower() in EXT and p.is_file() and p not in seen:
            seen.add(p)
            out.append((p, prov))

    if "--no-base" not in sys.argv and (BASE / CHAR).is_dir():
        for p in sorted((BASE / CHAR).glob("*")):
            take(p, "base")
    for p in sorted(REFS.glob(f"{CHAR}_*")):
        if p.stem.split("_")[0].lower() == CHAR:
            take(p, "references")
    for root in ("output", "outputs"):
        d = BASE / "codex" / root
        if not d.is_dir():
            continue
        for sub in sorted(x for x in d.iterdir() if x.is_dir()):
            if any(b in sub.name.lower() for b in BAD_DIR):
                continue
            if CHAR in sub.name.lower():
                for p in sorted(sub.glob("*")):
                    take(p, sub.name)
                continue
            if (sub / CHAR).is_dir():
                for p in sorted((sub / CHAR).rglob("*")):
                    take(p, f"{sub.name}/{CHAR}")
            for p in sorted(sub.glob(f"{CHAR}_*")):
                take(p, f"{sub.name} (loose)")
    return out


def angle_band(yaw: float | None) -> str:
    if yaw is None:
        return "no face"
    a = abs(yaw)
    return ("frontal" if a < 15 else "slight" if a < 30
            else "three-quarter" if a < 55 else "profile")


def framing(crop: str | None, face_frac: float | None) -> str:
    if crop == "chest-up" and face_frac is not None:
        return "head & shoulders" if face_frac >= 0.28 else "chest-up"
    return crop or "unknown"


app = _get_face_app()
refs = []
for p in sorted(REFS.glob(f"{CHAR}_*")):
    if p.suffix.lower() in EXT:
        fs = app.get(np.asarray(Image.open(p).convert("RGB"))[:, :, ::-1])
        if fs:
            refs.append(max(fs, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])).normed_embedding)
if not refs:
    raise SystemExit(f"no reference for {CHAR} has a detectable face")

rows = []
for p, prov in sources():
    try:
        im = Image.open(p).convert("RGB")
        fs = app.get(np.asarray(im)[:, :, ::-1])
        f = max(fs, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])) if fs else None
        yaw = float(f.pose[1]) if f is not None else None          # pose = [pitch, yaw, roll]
        fh = float(f.bbox[3] - f.bbox[1]) if f is not None else None
        scale = min(BUCKET_W / im.width, BUCKET_H / im.height)       # fitted, never upscaled past it
        ident = max(float(np.dot(f.normed_embedding, r)) for r in refs) if f is not None else None
        try:
            crop = measure(p).get("crop")
        except Exception:  # noqa: BLE001 - a measurement, never a blocker
            crop = None
        rows.append({"path": str(p), "source": prov, "w": im.width, "h": im.height,
                     "yaw": None if yaw is None else round(yaw, 1), "angle": angle_band(yaw),
                     "framing": framing(crop, fh / im.height if fh else None),
                     "identity": None if ident is None else round(ident, 3),
                     "face_px": None if fh is None else round(fh * scale)})
    except Exception as exc:  # noqa: BLE001
        print(f"  {p.name}: ERROR {exc}", flush=True)
print(f"{CHAR}: measured {len(rows)} images", flush=True)
if not rows:
    raise SystemExit("measured nothing")

usable = [r for r in rows if (r["identity"] or 0) >= 0.50 and (r["face_px"] or 0) >= 300]
summary = {
    "character": CHAR, "n": len(rows), "usable": len(usable),
    "usable_rule": "identity >= 0.50 against her references AND face >= 300px at 1024x1536",
    "by_source": Counter(r["source"] for r in rows),
    "usable_by_framing": Counter(r["framing"] for r in usable),
    "usable_by_angle": Counter(r["angle"] for r in usable),
    "usable_grid": {f"{r['framing']} / {r['angle']}": 0 for r in usable},
}
for r in usable:
    summary["usable_grid"][f"{r['framing']} / {r['angle']}"] += 1
(OUT / f"inventory_{CHAR}.json").write_text(
    json.dumps({"summary": summary, "images": rows}, indent=1, default=dict), encoding="utf-8")

# contact sheet: one row per framing, angle bands left to right, usable images only
# outlined green, the rest dimmed - so "what do we have" and "what would train" read
# off the same picture
FRAMES = ["head & shoulders", "chest-up", "mid-thigh-up", "knee-up", "full-body", "unknown"]
ANGLES = ["frontal", "slight", "three-quarter", "profile", "no face"]
TW, TH, LBL = 96, 144, 150
groups = defaultdict(list)
for r in rows:
    groups[(r["framing"], r["angle"])].append(r)
per_cell = {a: max([len(groups[(f, a)]) for f in FRAMES] + [1]) for a in ANGLES}
cols = sum(min(per_cell[a], 8) for a in ANGLES)
used_frames = [f for f in FRAMES if any(groups[(f, a)] for a in ANGLES)]
lines = {f: max((len(groups[(f, a)]) + 7) // 8 for a in ANGLES) or 1 for f in used_frames}
sheet = Image.new("RGB", (LBL + cols * TW + 8 * len(ANGLES), 24 + sum(lines.values()) * TH + 8 * len(used_frames)),
                  (16, 16, 18))
dr = ImageDraw.Draw(sheet)
ok = {id(r) for r in usable}
x = LBL
for a in ANGLES:
    dr.text((x + 2, 4), f"{a} ({sum(len(groups[(f, a)]) for f in FRAMES)})", fill=(230, 230, 235))
    x += min(per_cell[a], 8) * TW + 8
y = 24
for f in used_frames:
    dr.text((4, y + 4), f"{f}\n({sum(len(groups[(f, a)]) for a in ANGLES)})", fill=(230, 230, 235))
    x = LBL
    for a in ANGLES:
        for k, r in enumerate(groups[(f, a)]):
            try:
                t = Image.open(r["path"]).convert("RGB")
                t.thumbnail((TW - 4, TH - 4))
                if id(r) not in ok:
                    t = Image.blend(t, Image.new("RGB", t.size, (16, 16, 18)), 0.55)
                px, py = x + (k % 8) * TW, y + (k // 8) * TH
                sheet.paste(t, (px + 2, py + 2))
                if id(r) in ok:
                    dr.rectangle((px + 1, py + 1, px + t.width + 2, py + t.height + 2), outline=(60, 200, 110))
            except OSError:
                pass
        x += min(per_cell[a], 8) * TW + 8
    y += lines[f] * TH + 8
sheet.save(OUT / f"inventory_{CHAR}.jpg", quality=88)

print(json.dumps(summary, indent=1, default=dict))
print("INVENTORYDONE")
