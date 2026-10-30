"""The key photos of a story, all in ONE room: one of his photos is the plate and
every other key is Qwen-Image-Edit putting that room behind HER - his photo
of the pose stays the input, so her face stays his.

    python scripts/video/story_keys.py <story.json> [--dry-run]

Measured on cheer_joi_v2 (2026-10-30): the twelve keys were twelve separate
renders, 45-69 MAD apart; every transition leg spent its whole length redrawing
the room (border change 5.1 per frame against 0.5 in a hold leg) because FLF2V
cannot move a camera between two rooms that do not agree. Jeremy: "I'd want to
see the image edit stills all next to each other before we proceed."

story.json adds:
  plate      the key that IS the room (never edited)
  key_poses  {key: "what she is doing and where"} for every other key

Three arms per key, so his eye can pick the method:
  text  image 1 = plate, the pose in words                 (she is redrawn)
  ref   image 1 = plate, image 2 = his photo of the pose   (she is redrawn)
  room  image 1 = his photo of the pose, image 2 = plate   (the ROOM is redrawn)
The first two redraw her from the plate, and Edit without her LoRA drifts the
face - Jeremy, on the first still: "I cannot have the facial drift. That is
unacceptable." The room arm keeps his photo as the subject: Edit preserves the
input's face, so identity stays at the level of the photos he approved, and
only the background is replaced with the plate's room from that photo's camera.

Every output is scored against her face reference (InsightFace cosine, QC
only - a pre-filter, his eye is final) so the arms can be ranked.

Output: library/<character>/<date>_video_<story>-keys/<key>_<arm>.png, keys.json
and sheet.jpg (rows = keys; columns = his photo, text, ref, room, each with its
face score). Ends with KEYSDONE.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from sourcemode.assets.looks import reference
from sourcemode.config import load_config, outputs_dir
from sourcemode.gates.identity import cosine, embed_image
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
ARMS = ("text", "ref", "room")
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
    if arm == "ref":
        return (f"Keep the bedroom, the furniture, the camera position and the lighting of image 1, and the "
                f"woman's face, hair and cheerleader outfit of image 1. Pose her like the woman in image 2: "
                f"{pose}. Ignore the room in image 2. Photorealistic.")
    return ("Keep the woman of image 1 exactly as she is: her face, her hair, her outfit, her pose and where "
            "she is in the frame. Replace only the room around her with the bedroom of image 2 - the same bed, "
            "pink tufted headboard, bedding, rug, nightstand, lamp, window and soft daylight - seen from image 1's "
            "camera angle, so the room fits her pose. Photorealistic, nothing else changes.")


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
write_set_json(d, character=CHAR, kind="video", name=f"{story['name']}-keys", date=d.name[:10], judge_sets=[],
               story=story["name"])
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
        if arm == "room":
            image, ref = client.upload_image(photos[k]), plate_name
        else:
            image, ref = plate_name, (client.upload_image(photos[k]) if arm == "ref" else None)
        wf, _settings = build_edit_workflow(cfg, CHAR, instruction=text, negative=NEGATIVE, image_name=image,
                                            seed=base + i * 10 + j, render_pass=story.get("quality", "medium"),
                                            filename_prefix=f"sourcemode/{CHAR}_keys", ref_image_name=ref)
        files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
        if not files:
            raise SystemExit(f"{k}/{arm}: ComfyUI returned no image")
        client.fetch(files[0], out)
        log(f"  {k}/{arm} ({i}/{len(keys)}): {time.monotonic() - t0:.0f}s")

# her face, scored: his photo and every arm against the reference
scores: dict[tuple[str, str], float | None] = {}
if not DRY:
    ref_path = reference(CHAR)
    ref_emb = embed_image(ref_path) if ref_path else None
    if ref_emb is None:
        log("  no face reference - arms not scored")
    else:
        def score(p: Path) -> float | None:
            e = embed_image(p)
            return round(cosine(ref_emb, e), 3) if e is not None else None
        scores[(plate_key, "his photo")] = score(photos[plate_key])
        for k in keys:
            scores[(k, "his photo")] = score(photos[k])
            for arm in ARMS:
                p = d / f"{k}_{arm}.png"
                scores[(k, arm)] = score(p) if p.is_file() else None
                record["keys"][k][arm]["face"] = scores[(k, arm)]
            record["keys"][k]["his_photo_face"] = scores[(k, "his photo")]
        log(f"  face vs {Path(ref_path).name}: " + "; ".join(
            f"{arm} mean {sum(v for (kk, a), v in scores.items() if a == arm and v is not None) / max(1, sum(1 for (kk, a), v in scores.items() if a == arm and v is not None)):.3f}"
            for arm in ("his photo",) + ARMS))
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
        s = scores.get((k, cols[c]))
        label = f"{k} / {cols[c]}" + (" (PLATE)" if k == plate_key and c == 0 else "") + (f"  face {s:.2f}" if s is not None else "")
        draw.rectangle((x, y, x + 210, y + 14), fill="black")
        draw.text((x + 2, y + 1), label, fill="white")
sheet.save(d / "sheet.jpg", quality=88)
log(f"KEYSDONE {CHAR} '{story['name']}' {len(keys)} keys x {len(ARMS)} arms, sheet {d / 'sheet.jpg'}")
