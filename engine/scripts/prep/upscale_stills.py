"""Upscale a folder of stills 4x through ComfyUI's Real-ESRGAN, locally.

    python scripts/prep/upscale_stills.py <in_dir> <out_dir> [--model RealESRGAN_x4plus.pth]

Jeremy, 2026-10-15, on soft video frames for the torso object set: "is there
any way to upscale the image without an AI tool that won't pass it through
moderation". Real-ESRGAN x4plus (BSD-3) runs on the card here and nothing
leaves the machine. It sharpens blur into clean edges; it recovers nothing
that was not in the frame, so it is for the object's silhouette, not detail.

Reads <in_dir> at run time, so stills dropped in before the job starts are
included. Writes <out_dir>/<stem>_x4.png and skips any that already exist.
Loads a model, so it runs through the queue like everything else.
"""
import sys
from datetime import datetime
from pathlib import Path

from sourcemode.config import load_config, outputs_dir
from sourcemode.render.client import ComfyUIClient

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(ARGS) < 2:
    raise SystemExit(__doc__)
IN, OUT = Path(ARGS[0]), Path(ARGS[1])
MODEL = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "RealESRGAN_x4plus.pth"
EXTS = {".png", ".jpg", ".jpeg", ".webp"}

cfg = load_config()
LOG = outputs_dir(cfg) / "logs" / f"upscale_{IN.name}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def graph(image_name: str, prefix: str) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": MODEL}},
        "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": prefix}},
    }


stills = sorted(p for p in IN.iterdir() if p.suffix.lower() in EXTS and not p.name.startswith("_"))
if not stills:
    raise SystemExit(f"no stills in {IN}")
OUT.mkdir(parents=True, exist_ok=True)
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
log(f"{len(stills)} stills in {IN} -> {OUT}, {MODEL}")
done = 0
for p in stills:
    dest = OUT / f"{p.stem}_x4.png"
    if dest.exists():
        log(f"  {p.name}: already done")
        continue
    name = client.upload_image(p)
    files = client.outputs(client.wait(client.submit(graph(name, f"upscale/{IN.name}/{p.stem}")), timeout_s=1800))
    if not files:
        log(f"  {p.name}: no output")
        continue
    client.fetch(files[0], dest)
    done += 1
    log(f"  {p.name} -> {dest.name}")
log(f"UPSCALEDONE {done} written to {OUT}")
