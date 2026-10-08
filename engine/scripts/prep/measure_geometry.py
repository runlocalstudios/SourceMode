"""Fill geometry.json for staged images the gather never measured.

    python scripts/prep/measure_geometry.py <char>

The gather writes face size and head pose for what IT stages. Images added to a
staged set afterwards (gabi's 33 adopted face crops, 2026-10-08) had none, and
the captioner then calls every one of them "facing the camera". Loads
InsightFace, so it runs through the GPU queue like every model-loading job.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from sourcemode.gates.identity import _get_face_app

CHAR = sys.argv[1].lower()
DS = Path(f"outputs/lora-datasets/{CHAR}_v2")
IMG = DS / "image_src"
BUCKET_W, BUCKET_H = 1024, 1536

gp = DS / "geometry.json"
geom = json.loads(gp.read_text(encoding="utf-8")) if gp.is_file() else {}
todo = [p for p in sorted(IMG.glob("src_*.png")) if p.name not in geom]
print(f"{CHAR}: {len(todo)} staged image(s) without geometry")
if todo:
    app = _get_face_app()
    for p in todo:
        im = Image.open(p).convert("RGB")
        fs = app.get(np.asarray(im)[:, :, ::-1])
        if not fs:
            geom[p.name] = {}
            print(f"  {p.name}: no face")
            continue
        f = max(fs, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        fh = float(f.bbox[3] - f.bbox[1])
        scale = min(BUCKET_W / im.width, BUCKET_H / im.height)
        geom[p.name] = {"face_h_frac": round(fh / im.height, 3), "face_px": round(fh * scale),
                        "yaw": round(float(f.pose[1]), 1), "pitch": round(float(f.pose[0]), 1),
                        "w": im.width, "h": im.height}
        print(f"  {p.name}: yaw {geom[p.name]['yaw']}, face {geom[p.name]['face_px']}px")
    gp.write_text(json.dumps(geom, indent=1), encoding="utf-8")
print("GEOMETRYDONE")
