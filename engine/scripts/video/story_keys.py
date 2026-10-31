"""The key photos of a story, all in ONE room, by every method worth comparing:
one of his photos is the plate (the room), and each other key is made from it
or fitted into it, one arm per method, so he picks the method by eye.

    python scripts/video/story_keys.py <story.json> [--dry-run] [--arms a,b,...]

Measured on cheer_joi_v2 (2026-10-30): the twelve keys were twelve separate
renders, 45-69 MAD apart; every transition leg spent its whole length redrawing
the room (border change 5.1 per frame against 0.5 in a hold leg) because FLF2V
cannot move a camera between two rooms that do not agree. Jeremy: "I'd want to
see the image edit stills all next to each other before we proceed."

story.json adds:
  plate      the key that IS the room (never edited)
  key_poses  {key: "what she is doing and where"} for every other key

Arms (Qwen-Image-Edit 2511 unless said; image 1 is the subject):
  text       image 1 = plate; the pose in words. She is redrawn, no LoRA.
  ref        image 1 = plate, image 2 = his photo of the pose. She is redrawn.
  room       image 1 = his photo of the pose, image 2 = plate. The ROOM is
             redrawn behind her; Edit preserves the input's face, so identity
             stays at the level of the photos he approved.
  text_lora  the text arm with her locked T2I LoRA loaded in the Edit graph
             and her trigger in the instruction. The notes say T2I LoRAs do
             not carry into Edit; nobody here measured it, so this does.
  room_empty the room arm against an EMPTY plate: the plate is first edited
             once to remove her (plate_empty.png), because with her still in
             it the room arm sometimes took the plate woman's arms-crossed
             pose instead of his photo's. Jeremy, 2026-10-30: "room is likely
             the best bet to keep her and conform the room behind."
  face3      image 1 = plate, image 2 = his photo of the pose, image 3 = her
             face reference. Three-image Edit, identity from a dedicated face.
  video      Wan 2.2 I2V from the plate, 81 frames, the pose as the motion;
             the key is the sharpest of the last 16 frames. The room is the
             plate's by construction and the key is what the video model
             itself produces, so the FLF2V target is in-distribution.

Jeremy, on the first text-arm still: "I cannot have the facial drift. That is
unacceptable." Then: "Evaluate multiple options ... don't be closed-minded."
Every output is scored against her face reference (InsightFace cosine, QC
only - a pre-filter, his eye is final). Resumable: an arm on disk is kept.

Output: library/<character>/<date>_video_<story>-keys/<key>_<arm>.png, keys.json
and sheet.jpg (rows = keys; columns = his photo and every arm, each with its
face score). Ends with KEYSDONE.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from sourcemode.assets.looks import reference
from sourcemode.assets.lora import resolve_lora
from sourcemode.config import load_config, outputs_dir
from sourcemode.gates.identity import cosine, embed_image
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.passes import build_edit_workflow, build_video_workflow
from sourcemode.render.workflow import load_template, prune_placeholder_loras, substitute
from sourcemode.video import NEGATIVE as VIDEO_NEGATIVE
from sourcemode.video import ffmpeg_exe, sharpest_tail_frame, video_output

ALL_ARMS = ("text", "ref", "room", "room_empty", "text_lora", "face3", "video")
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
# --reroll=N --keys=a,b: N more tries per key at fresh random seeds, written to
# _tries/<key>_<arm>_s<seed>.png beside the kept still, which is not touched -
# he picks by eye. Image arms only. Jeremy, 2026-10-30, on relaxed/room_empty
# (face 0.17 where the rest held 0.44-0.68): "reroll relaxed to see if we can improve it."
REROLL = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--reroll=")), 0))
ONLY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--keys=")), None)
ARMS = tuple(next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--arms=")), ALL_ARMS))
if not ARGS or any(a not in ALL_ARMS for a in ARMS):
    raise SystemExit(__doc__)
story = json.loads(Path(ARGS[0]).read_text(encoding="utf-8"))
cfg = load_config()
CHAR = story["character"].lower()
LOG = outputs_dir(cfg) / "logs" / f"video_{CHAR}.log"
NEGATIVE = ("different room, different furniture, different camera angle, different lighting, "
            "different outfit, different woman, extra people, text, watermark, blurry, deformed hands")
# seed slot per arm: the first six keep the seeds of the 2026-10-30 run, and
# room_empty shares room's so the two differ only by the plate
SEED_SLOT = {"text": 0, "ref": 1, "room": 2, "room_empty": 2, "text_lora": 3, "face3": 4, "video": 5}
VIDEO_FRAMES = 81          # the length the 14B model was trained on
TAIL = 16                  # frames that compete to be the key


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


def instruction(arm: str, pose: str) -> str:
    if arm == "text":
        return (f"Keep the bedroom, the furniture, the camera position, the lighting and her cheerleader "
                f"outfit exactly as in the picture. Change only her: {pose}. The same woman, photorealistic.")
    if arm == "text_lora":
        return (f"{CHAR}. Keep the bedroom, the furniture, the camera position, the lighting and her cheerleader "
                f"outfit exactly as in the picture. Change only her: {pose}. The same woman, {CHAR}, photorealistic.")
    if arm == "ref":
        return (f"Keep the bedroom, the furniture, the camera position and the lighting of image 1, and the "
                f"woman's face, hair and cheerleader outfit of image 1. Pose her like the woman in image 2: "
                f"{pose}. Ignore the room in image 2. Photorealistic.")
    if arm == "face3":
        return (f"Keep the bedroom, the furniture, the camera position and the lighting of image 1 and her "
                f"cheerleader outfit. Her face is exactly the face in image 3. Pose her like the woman in image 2: "
                f"{pose}. Ignore the rooms in image 2 and image 3. Photorealistic.")
    if arm in ("room", "room_empty"):
        return ("Keep the woman of image 1 exactly as she is: her face, her hair, her outfit, her pose and where "
                "she is in the frame. Replace only the room around her with the bedroom of image 2 - the same bed, "
                "pink tufted headboard, bedding, rug, nightstand, lamp, window and soft daylight - seen from image 1's "
                "camera angle, so the room fits her pose. Photorealistic, nothing else changes.")
    if arm == "empty":
        return ("Remove the woman completely. Show the same bedroom with nobody in it: the same bed, pink tufted "
                "headboard, bedding, rug, nightstand, lamp, window and soft daylight, the same camera position "
                "and framing. Fill in what was behind her naturally. Photorealistic, nothing else changes.")
    return f"{pose}. steady camera, continuous shot, she moves slowly and gently"   # video


def edit3_workflow(instr: str, seed: int, image1: str, image2: str, image3: str) -> dict:
    """The two-image template with a third LoadImage wired to image3 of both
    text encoders (TextEncodeQwenImageEditPlus takes image1/2/3, verified
    against /object_info by the template's own note)."""
    preset = cfg["render"][story.get("quality", "medium")]
    settings = {
        "MODEL": cfg["models"]["qwen_edit"], "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"], "POSITIVE": instr, "NEGATIVE": NEGATIVE, "IMAGE": image1,
        "REF_IMAGE": image2, "LORA_PATH": "", "LORA_STRENGTH": 1.0,
        "LIGHTNING": preset.get("qwen_edit_lightning", ""), "LIGHTNING_STRENGTH": float(preset.get("lightning_strength", 1.0)),
        "SHIFT": float(cfg["render"].get("qwen_shift", 3.1)), "SEED": seed,
        "STEPS": int(preset.get("qwen_edit_steps", preset["steps"])), "CFG": float(preset.get("qwen_edit_cfg", preset["cfg"])),
        "FILENAME_PREFIX": f"sourcemode/{CHAR}_keys",
    }
    from sourcemode.config import workflows_dir  # noqa: PLC0415
    wf = substitute(load_template(workflows_dir(cfg), "qwen_image_edit_ref"), settings)
    nodes = wf["nodes"] if "nodes" in wf else wf
    nodes["902"] = {"class_type": "LoadImage", "inputs": {"image": image3}}
    nodes["903"] = {"class_type": "FluxKontextImageScale", "inputs": {"image": ["902", 0]}}
    for nid, n in nodes.items():
        if n.get("class_type") == "TextEncodeQwenImageEditPlus":
            n["inputs"]["image3"] = ["903", 0]
    return prune_placeholder_loras(wf)


photos = {k: Path(v) for k, v in story["photos"].items()}
plate_key = story["plate"]
poses = story["key_poses"]
problems = [f"photo {k} is not on disk: {p}" for k, p in photos.items() if not p.is_file()]
if plate_key not in photos:
    problems.append(f"plate {plate_key!r} is not in photos")
problems += [f"key {k} has no key_poses line" for k in photos if k != plate_key and k not in poses]
lora = resolve_lora(cfg, CHAR)
if "text_lora" in ARMS and not lora:
    problems.append(f"{CHAR} has no locked LoRA for the text_lora arm")
face_ref = reference(CHAR)
if "face3" in ARMS and not face_ref:
    problems.append(f"{CHAR} has no face reference for the face3 arm")
ff = ffmpeg_exe(cfg)
if "video" in ARMS and not ff:
    problems.append("the video arm needs ffmpeg")
if problems:
    raise SystemExit("; ".join(problems))

d = find_set(cfg, CHAR, "video", f"{story['name']}-keys", create=True)
write_set_json(d, character=CHAR, kind="video", name=f"{story['name']}-keys", date=d.name[:10], judge_sets=[],
               story=story["name"])
keys = [k for k in photos if k != plate_key]
W, H = (int(x) for x in story.get("size") or (cfg["video"]["width"], cfg["video"]["height"]))
log(f"{CHAR}: keys for '{story['name']}' - plate {plate_key}, {len(keys)} keys x {len(ARMS)} arms {ARMS} -> {d}")

record = json.loads((d / "keys.json").read_text(encoding="utf-8")) if (d / "keys.json").is_file() else {}
record.update(plate=plate_key)
record.setdefault("keys", {})
base = base_seed = int(story.get("seed") or 7100)
if not DRY:
    client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    plate_name = client.upload_image(photos[plate_key])
    face_name = client.upload_image(Path(face_ref)) if "face3" in ARMS else ""
    empty_name = ""
    if "room_empty" in ARMS:
        empty = d / "plate_empty.png"
        if not empty.is_file():
            t0 = time.monotonic()
            wf, _settings = build_edit_workflow(cfg, CHAR, instruction=instruction("empty", ""),
                                                negative="woman, person, people, girl, body, figure, text, watermark, blurry",
                                                image_name=plate_name, seed=base_seed - 1,
                                                render_pass=story.get("quality", "medium"),
                                                filename_prefix=f"sourcemode/{CHAR}_keys")
            files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
            if not files:
                raise SystemExit("empty plate: ComfyUI returned no image")
            client.fetch(files[0], empty)
            log(f"  empty plate: {time.monotonic() - t0:.0f}s -> {empty}")
        record["plate_empty"] = str(empty)
        empty_name = client.upload_image(empty)
def render_still(k: str, arm: str, text: str, seed: int, out: Path) -> None:
    """One image arm (every arm but video) for key k into out."""
    if arm == "face3":
        wf = edit3_workflow(text, seed, plate_name, client.upload_image(photos[k]), face_name)
    else:
        if arm in ("room", "room_empty"):
            image, ref = client.upload_image(photos[k]), (plate_name if arm == "room" else empty_name)
        else:
            image, ref = plate_name, (client.upload_image(photos[k]) if arm == "ref" else None)
        wf, _settings = build_edit_workflow(cfg, CHAR, instruction=text, negative=NEGATIVE, image_name=image,
                                            image_lora=lora["path"] if arm == "text_lora" else "",
                                            seed=seed, render_pass=story.get("quality", "medium"),
                                            filename_prefix=f"sourcemode/{CHAR}_keys", ref_image_name=ref)
    files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
    if not files:
        raise SystemExit(f"{k}/{arm}: ComfyUI returned no image")
    client.fetch(files[0], out)


if REROLL:
    if "video" in ARMS or not ONLY or any(k not in keys for k in ONLY):
        raise SystemExit("--reroll needs --keys= from this story and image arms only")
    import random  # noqa: PLC0415
    tries = d / "_tries"
    tries.mkdir(exist_ok=True)
    ref_emb = embed_image(Path(face_ref)) if (face_ref and not DRY) else None
    for k in ONLY:
        for arm in ARMS:
            for t in range(REROLL):
                seed = random.randrange(1, 2**31)
                out = tries / f"{k}_{arm}_s{seed}.png"
                if DRY:
                    log(f"  reroll {k}/{arm} try {t + 1}: seed {seed}")
                    continue
                t0 = time.monotonic()
                render_still(k, arm, instruction(arm, poses[k]), seed, out)
                e = embed_image(out) if ref_emb is not None else None
                face = round(cosine(ref_emb, e), 3) if e is not None else None
                log(f"  reroll {k}/{arm} try {t + 1}/{REROLL} seed {seed}: face {face} ({time.monotonic() - t0:.0f}s)")
    log(f"KEYSDONE reroll {ONLY} x {ARMS} x {REROLL} -> {tries}")
    raise SystemExit(0)

for i, k in enumerate(keys, 1):
    for arm in ALL_ARMS:
        if arm not in ARMS:
            continue
        out = d / f"{k}_{arm}.png"
        text = instruction(arm, poses[k])
        seed = base + i * 10 + SEED_SLOT[arm]
        record["keys"].setdefault(k, {})[arm] = {"file": str(out), "instruction": text, "seed": seed}
        if DRY:
            log(f"  {k}/{arm}: {text}")
            continue
        if out.is_file():
            log(f"  {k}/{arm}: on disk, kept")
            continue
        t0 = time.monotonic()
        if arm == "video":
            clip = d / f"{k}_video.mp4"
            if not clip.is_file():
                wf, settings = build_video_workflow(cfg, CHAR, positive=text, negative=VIDEO_NEGATIVE, image_name=plate_name,
                                                    seed=seed, render_pass=story.get("quality", "medium"),
                                                    duration_s=VIDEO_FRAMES / int(cfg["video"]["fps"]), width=W, height=H)
                assert settings["LENGTH"] == VIDEO_FRAMES, settings["LENGTH"]
                vid = video_output(client.outputs(client.wait(client.submit(wf), timeout_s=4 * 3600)))
                if vid is None:
                    raise SystemExit(f"{k}/video: ComfyUI returned no video")
                client.fetch(vid, clip)
            dropped = sharpest_tail_frame(clip, out, ffmpeg=ff, n=TAIL)
            record["keys"][k][arm]["frames_before_end"] = dropped
        else:
            render_still(k, arm, text, seed, out)
        log(f"  {k}/{arm} ({i}/{len(keys)}): {time.monotonic() - t0:.0f}s")

# her face, scored: his photo and every arm on disk against the reference
scores: dict[tuple[str, str], float | None] = {}
if not DRY:
    ref_emb = embed_image(Path(face_ref)) if face_ref else None
    if ref_emb is None:
        log("  no face reference - arms not scored")
    else:
        def score(p: Path) -> float | None:
            e = embed_image(p)
            return round(cosine(ref_emb, e), 3) if e is not None else None
        scores[(plate_key, "his photo")] = score(photos[plate_key])
        for k in keys:
            scores[(k, "his photo")] = score(photos[k])
            record["keys"].setdefault(k, {})["his_photo_face"] = scores[(k, "his photo")]
            for arm in ALL_ARMS:
                p = d / f"{k}_{arm}.png"
                if p.is_file():
                    scores[(k, arm)] = score(p)
                    record["keys"][k].setdefault(arm, {"file": str(p)})["face"] = scores[(k, arm)]
        means = []
        for arm in ("his photo",) + ALL_ARMS:
            vals = [v for (_k, a), v in scores.items() if a == arm and v is not None]
            if vals:
                means.append(f"{arm} {sum(vals) / len(vals):.3f} (n={len(vals)})")
        log(f"  face vs {Path(face_ref).name}: " + "; ".join(means))
(d / "keys.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")

# the sheet he asked for: his photo beside every arm on disk, the plate on top
TH = (300, 450)
cols = ["his photo"] + [a for a in ALL_ARMS if any((d / f"{k}_{a}.png").is_file() for k in keys)]
rows = [(plate_key, [photos[plate_key]] + [None] * (len(cols) - 1))] + \
       [(k, [photos[k]] + [d / f"{k}_{a}.png" for a in cols[1:]]) for k in keys]
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
        draw.rectangle((x, y, x + 220, y + 14), fill="black")
        draw.text((x + 2, y + 1), label, fill="white")
sheet.save(d / "sheet.jpg", quality=88)
log(f"KEYSDONE {CHAR} '{story['name']}' {len(keys)} keys, arms {cols[1:]}, sheet {d / 'sheet.jpg'}")
