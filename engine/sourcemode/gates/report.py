"""`sourcemode gates report`: score a folder of images, write CSV + contact sheet.

Pure annotation — nothing is moved or blocked. The contact sheet is a PIL
montage sorted by score (best first) with the score printed under each tile;
tiles whose score fell below the character threshold are outlined in red.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..source import CharacterSource
from .base import Scorer

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
TILE = 256
LABEL_H = 24


def score_directory(directory: Path, source: CharacterSource, scorer: Scorer) -> list[dict]:
    """Score every image directly inside `directory` (not recursive). Sorted by score desc."""
    rows = []
    for path in sorted(Path(directory).iterdir()):
        if path.suffix.lower() not in IMAGE_EXTS or not path.is_file():
            continue
        gate = scorer.score(path, source)
        rows.append(
            {
                "file": path.name,
                "path": path,
                "score": gate.score,
                "passed": gate.passed,
                "details": gate.details,
            }
        )
    rows.sort(key=lambda r: (r["score"] is not None, r["score"] or 0.0), reverse=True)
    return rows


def write_csv(rows: list[dict], out_csv: Path) -> Path:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "score", "passed", "details"])
        for r in rows:
            writer.writerow([r["file"], "" if r["score"] is None else f"{r['score']:.4f}", r["passed"], r["details"]])
    return out_csv


def write_contact_sheet(rows: list[dict], out_png: Path, *, columns: int = 6) -> Path:
    from PIL import Image, ImageDraw  # noqa: PLC0415

    out_png.parent.mkdir(parents=True, exist_ok=True)
    n = max(1, len(rows))
    cols = min(columns, n)
    rows_count = (n + cols - 1) // cols
    cell_h = TILE + LABEL_H
    sheet = Image.new("RGB", (cols * TILE, rows_count * cell_h), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)

    for i, r in enumerate(rows):
        x = (i % cols) * TILE
        y = (i // cols) * cell_h
        try:
            img = Image.open(r["path"]).convert("RGB")
            img.thumbnail((TILE, TILE))
            sheet.paste(img, (x + (TILE - img.width) // 2, y + (TILE - img.height) // 2))
        except Exception:  # noqa: BLE001 — unreadable file still gets a labeled slot
            draw.text((x + 8, y + TILE // 2), "unreadable", fill=(255, 80, 80))
        label = "no score" if r["score"] is None else f"{r['score']:.3f}"
        if r["passed"] is False:
            draw.rectangle([x, y, x + TILE - 1, y + TILE - 1], outline=(220, 40, 40), width=3)
            label += "  FAIL"
        draw.text((x + 6, y + TILE + 4), f"{label}  {r['file'][:28]}", fill=(230, 230, 230))

    sheet.save(out_png)
    return out_png


def report_directory(
    directory: Path,
    source: CharacterSource,
    scorer: Scorer,
    out_dir: Path,
    *,
    name: str | None = None,
) -> dict:
    """Score every image in `directory`; write <name>.csv + <name>_contact.png to out_dir."""
    stem = name or f"{source.character_id}_{Path(directory).name}"
    rows = score_directory(directory, source, scorer)
    csv_path = write_csv(rows, Path(out_dir) / f"{stem}.csv")
    sheet_path = write_contact_sheet(rows, Path(out_dir) / f"{stem}_contact.png")
    scored = [r for r in rows if r["score"] is not None]
    failed = [r for r in scored if r["passed"] is False]
    return {
        "images": len(rows),
        "scored": len(scored),
        "failed": len(failed),
        "csv": str(csv_path),
        "contact_sheet": str(sheet_path),
        "mean": round(sum(r["score"] for r in scored) / len(scored), 4) if scored else None,
        "min": round(min((r["score"] for r in scored), default=0.0), 4) if scored else None,
    }
