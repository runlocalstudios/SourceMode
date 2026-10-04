"""Composite every placed outfit on WHITE into one review sheet.

Rule from the assetgen skill: review cutouts on white, never only on dark or a
checkerboard - white speckles, violet fringes and hair pinholes are invisible
there.    python white_sheet.py sandra
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

char = sys.argv[1]
src = Path(f"outputs/game-assets/{char}/outfits")
files = sorted(src.rglob("*.webp"))
if not files:
    raise SystemExit(f"no webp under {src}")
tw, th, cols = 320, 480, 7
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw, rows * (th + 24)), "white")
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    im = Image.open(f).convert("RGBA")
    im.thumbnail((tw, th))
    x, y = (i % cols) * tw, (i // cols) * (th + 24)
    sheet.paste(im, (x + (tw - im.width) // 2, y), im)
    d.text((x + 4, y + th + 4), f.stem, fill="black")
out = Path(f"outputs/game-assets/{char}/review_white.jpg")
sheet.save(out, quality=88)
print(f"{len(files)} outfits -> {out}")
