"""The key photos of a story, all in ONE room: one of his photos is the plate and
every other key is Qwen-Image-Edit moving HER into the next pose in that same
room, same camera, same light.

    python scripts/video/story_keys.py <story.json> [--dry-run]

Measured on cheer_joi_v2 (2026-10-30): the twelve keys were twelve separate
renders, 45-69 MAD apart; every transition leg spent its whole length redrawing
the room (border change 5.1 per frame against 0.5 in a hold leg) because FLF2V
cannot move a camera between two rooms that do not agree. Jeremy: "I'd want to
see the image edit stills all next to each other before we proceed."

story.json adds:
  plate      the key that IS the room (used as image 1, never edited)
  key_poses  {key: "what she is doing and where"} for every other key

Two arms per key, so his eye can pick the method:
  text  image 1 = plate, the pose in words
  ref   image 1 = plate, image 2 = his original photo of that pose as a
        composition reference (TextEncodeQwenImageEditPlus image2)

Output: library/<character>/<date>_video_<story>-keys/<key>_<arm>.png and sheet.jpg
(rows = keys; columns = his photo, text arm, ref arm). Ends with KEYSDONE.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from sourcemode.config import load_config, outputs_dir
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.passes import build_edit_workflow

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
if not ARGS:
    raise SystemExit(__doc__)
story = json.loads(Path(ARGS[0]).read_text(encoding="utf-8"))
cfg = load_config()
CHAR = story["character"].lower()
LOG = outputs_dir(cfg) / "logs" / f"video_{CHAR}.log"
ARMS = ("text", "ref")
NEGATIVE = ("different room, different furniture, different camera angle, different lighting, "
            "different outfit, different woman, extra people, text, watermark, blurry, deformed hands")


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


def instruction(arm: str, pose: str) -> str:
    if arm == "text":
        return (f"Keep the bedroom, the furniture, the camera position, the lighting and her cheerleader "
                f"outfit exactly as in the picture. Change only her: {pose}. The same woman, photorealistic.")
    return (f"Keep the bedroom, the furniture, the camera position and the lighting of image 1, and the "
            f"woman's face, hair and cheerleader outfit of image 1. Pose her like the woman in image 2: "
            f"{pose}. Ignore the room in image 2. Photorealistic.")


photos = {k: Path(v) for k, v in story["photos"].items()}
plate_key = story["plate"]
poses = story["key_poses"]
problems = [f"photo {k} is not on disk: {p}" for k, p in photos.items() if not p.is_file()]
if plate_key not in photos:
    problems.append(f"plate {plate_key!r} is not in photos")
problems += [f"key {k} has no key_poses line" for k in photos if k != plate_key and k not in poses]
if problems:
    raise SystemExit("; ".join(problems))

d = find_set(cfg, CHAR, "video", f"{story['name']}-keys", create=True)
write_set_json(d, character=CHAR, kind="video", name=f"{story['name']}-keys", date=d.name[:10], judge_sets=[], story=story["name"])
keys = [k for k in photos if k != plate_key]
log(f"{CHAR}: keys for '{story['name']}' - plate {plate_key}, {len(keys)} keys x {len(ARMS)} arms -> {d}")

record = {"plate": plate_key, "keys": {}}
if not DRY:
    client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    plate_name = client.upload_image(photos[plate_key])
base = int(story.get("seed") or 7100)
for i, k in enumerate(keys, 1):
    for j, arm in enumerate(ARMS):
        out = d / f"{k}_{arm}.png"
        text = instruction(arm, poses[k])
        record["keys"].setdefault(k, {})[arm] = {"file": str(out), "instruction": text, "seed": base + i * 10 + j}
        if DRY:
            log(f"  {k}/{arm}: {text}")
            continue
        if out.is_file():
            log(f"  {k}/{arm}: on disk, kept")
            continue
        t0 = time.monotonic()
        ref = client.upload_image(photos[k]) if arm == "ref" else None
        wf, _settings = build_edit_workflow(cfg, CHAR, instruction=text, negative=NEGATIVE, image_name=plate_name,
                                            seed=base + i * 10 + j, render_pass=story.get("quality", "medium"),
                                            filename_prefix=f"sourcemode/{CHAR}_keys", ref_image_name=ref)
        files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
        if not files:
            raise SystemExit(f"{k}/{arm}: ComfyUI returned no image")
        client.fetch(files[0], out)
        log(f"  {k}/{arm} ({i}/{len(keys)}): {time.monotonic() - t0:.0f}s")
(d / "keys.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")

# the sheet he asked for: his photo beside each arm, the plate on top
TH = (300, 450)
cols = ["his photo"] + list(ARMS)
rows = [(plate_key, [photos[plate_key]] + [None] * len(ARMS))] + \
       [(k, [photos[k]] + [d / f"{k}_{arm}.png" for arm in ARMS]) for k in keys]
sheet = Image.new("RGB", (len(cols) * TH[0], len(rows) * TH[1]), "black")
draw = ImageDraw.Draw(sheet)
for r, (k, files) in enumerate(rows):
    for c, f in enumerate(files):
        x, y = c * TH[0], r * TH[1]
        if f and Path(f).is_file():
            im = Image.open(f).convert("RGB")
            im.thumbnail(TH)
            sheet.paste(im, (x, y))
        draw.rectangle((x, y, x + 150, y + 14), fill="black")
        draw.text((x + 2, y + 1), f"{k} / {cols[c]}" + (" (PLATE)" if k == plate_key and c == 0 else ""), fill="white")
sheet.save(d / "sheet.jpg", quality=88)
log(f"KEYSDONE {CHAR} '{story['name']}' {len(keys)} keys x {len(ARMS)} arms, sheet {d / 'sheet.jpg'}")
