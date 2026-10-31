"""Render a story strung from his photos: each segment animates FROM one photo TO
another (or back to the same one), so her face is re-anchored at every photo
instead of drifting leg after leg.

    python scripts/video/run_story.py <story.json>

story.json (video-stories/*.json):
  name, character, size [w, h], quality, seed, suffix, negative, voice (bool),
  script ("[12s] words" lines, as the templates),
  photos {key: path},
  segments [{start: key, end: key | null, seconds, motion}]

A segment whose `end` is null is plain I2V from `start` (it lands wherever the
motion takes it). A segment that starts on the photo the previous one ended on
continues it seamlessly; any other start is a hard cut, as a film edit.

Resumable: a segment already on disk is kept, so deleting one file and
re-queueing re-renders only that segment - which also means a new VERSION of a
story needs a new `name` (cheer_joi_v2), or it inherits the old segments.
Jeremy, 2026-10-29: "your goal is to output a video for me that is a masterpiece".
`voice_pace` {exaggeration, cfg_weight} slows or lifts the voice for the whole
script; a countdown is written one number per timed line so the gaps are real.

Three opt-in story fields (cheer_joi_v3, 2026-10-31), from the v2 review: the
photos disagreed about the room, every leg started on a photo so each seam
snapped back to it, and every leg brightened +5..+13 then flashed back.
  fps         the rate the legs are rendered and played at. 16 with 5.06 s
              legs is the 81 frames the 14B model was trained on; v2 rendered
              117 frames at 24 and played 1.5x fast. Jeremy: "I am fine with
              trying 16 fps and if it looks choppy we can add interpolation."
  chain       true: every leg after the first STARTS on the previous leg's
              real last frame (its `start` is not used), so nothing snaps at a
              seam; its `end` photo still pins where it lands, which is what
              keeps her face. A leg with no `end` moves freely from there -
              never put two of those in a row, or 10 s pass unanchored.
              Jeremy: "have one leg start with a picture and then the next leg
              is a stitch from the end of the previous leg, and then ... we then
              stitch it back into a source photo."
  color_ramp  true: each leg's colour is pulled frame by frame toward a blend
              from its start image to its end photo (`video.ramp_correct`).
`--first=N` renders only the first N legs and writes proof_NN.mp4, silent - the
30 s proof before the whole story. A chained leg is rendered from the leg
before it: delete a leg and every leg after it must go too.

Output: library/<character>/<date>_video_<name>/take_01.mp4, segments in _legs/.
"""

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from sourcemode.config import ENGINE_ROOT, load_config, outputs_dir
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.passes import build_video_workflow, snap_frames
from sourcemode.video import (NEGATIVE, color_ramp, extract_last_frame, ffmpeg_exe, normalize_source, script_beats,
                              stitch, video_output, voice_mux_args)

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
if not ARGS:
    raise SystemExit(__doc__)
FIRST = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--first=")), 0))
story = json.loads(Path(ARGS[0]).read_text(encoding="utf-8"))
cfg = load_config()
if story.get("fps"):
    # the builder reads the frame rate from [video]; this story renders at its own
    cfg = {**cfg, "video": {**cfg["video"], "fps": int(story["fps"])}}
CHAIN, RAMP = bool(story.get("chain")), bool(story.get("color_ramp"))
SEGMENTS = story["segments"][:FIRST] if FIRST else story["segments"]
CHAR = story["character"].lower()
LOG = outputs_dir(cfg) / "logs" / f"video_{CHAR}.log"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


W, H = (int(x) for x in story.get("size") or (cfg["video"]["width"], cfg["video"]["height"]))
fps = int(cfg["video"]["fps"])
ff = ffmpeg_exe(cfg)
problems = [] if ff else ["a story needs ffmpeg and there is none on this machine"]
photos = {k: Path(v) for k, v in story["photos"].items()}
problems += [f"photo {k} is not on disk: {p}" for k, p in photos.items() if not p.is_file()]
for i, s in enumerate(SEGMENTS, 1):
    if i == 1 or not CHAIN:
        if not s.get("start"):
            problems.append(f"segment {i} needs a start photo")
    for key in ((s.get("start") if i == 1 or not CHAIN else None), s.get("end")):
        if key and key not in photos:
            problems.append(f"segment {i} names photo {key!r}, which is not in photos")
    if not 1 <= float(s["seconds"]) <= int(cfg["video"]["max_frames"]) / fps:
        problems.append(f"segment {i}: {s['seconds']} s is outside 1 s .. one leg")
voice_ref = None
if story.get("voice") and not FIRST:
    from sourcemode.voice.record import get as get_voice

    v = get_voice(CHAR) or {}
    voice_ref = Path(v["reference"]) if v.get("reference") else None
    if not (voice_ref and voice_ref.is_file()):
        problems.append(f"{CHAR} has no voice reference")
if problems:
    raise SystemExit("; ".join(problems))

d = find_set(cfg, CHAR, "video", story["name"], create=True)
write_set_json(d, character=CHAR, kind="video", name=story["name"], date=d.name[:10], judge_sets=[],
               story=story["name"])
(d / "spec.json").write_text(json.dumps({**story, "takes": 1, "kind": "story"}, indent=1, ensure_ascii=False),
                             encoding="utf-8")
keys = d / "_keys"
for k, p in photos.items():
    normalize_source(p, keys / f"{k}.png", W, H)
shutil.copyfile(keys / f"{SEGMENTS[0]['start']}.png", d / "source_src.png")
total_s = sum(float(s["seconds"]) for s in SEGMENTS)
log(f"{CHAR}: story '{story['name']}' - {len(SEGMENTS)} segments{' (proof)' if FIRST else ''}, {total_s:g} s, "
    f"{W}x{H} at {fps} fps{', chained' if CHAIN else ''}{', colour ramp' if RAMP else ''}"
    f"{', voiced' if voice_ref else ''} -> {d}")

lines: list[tuple[float, Path]] = []
if voice_ref:
    beats = script_beats(story.get("script", ""))
    vdir = d / "_voice"
    vdir.mkdir(exist_ok=True)
    (vdir / "lines.json").write_text(json.dumps([t for _s, t in beats], ensure_ascii=False), encoding="utf-8")
    uv = shutil.which("uv") or "uv"
    # Jeremy, 2026-10-29: "the talk track is a little rushed at times, the cum
    # countdown is horribly rushed" - a story may set its own pace: Chatterbox's
    # cfg_weight lower than the 0.4 default speaks slower and more deliberately
    pace = story.get("voice_pace") or {}
    cmd = [uv, "run", "--isolated", "--with", "chatterbox-tts", "--with", "setuptools<81", "--with", "soundfile",
           "python", str(ENGINE_ROOT / "scripts" / "voice" / "say_script.py"), str(voice_ref), str(vdir),
           str(vdir / "lines.json"), str(pace.get("exaggeration", 0.5)), str(pace.get("cfg_weight", 0.4))]
    log(f"  voicing {len(beats)} lines (exaggeration {pace.get('exaggeration', 0.5)}, cfg_weight {pace.get('cfg_weight', 0.4)})")
    r = subprocess.run(cmd, cwd=str(ENGINE_ROOT), capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"the voice track failed: {(r.stderr or r.stdout)[-600:]}")
    lines = [(s, vdir / f"line_{i:02d}.wav") for i, (s, _t) in enumerate(beats)]

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
legs = d / "_legs"
legs.mkdir(exist_ok=True)
negative = f"{NEGATIVE}, {story['negative']}" if story.get("negative") else NEGATIVE
suffix = story.get("suffix", "")
base = int(story.get("seed") or 7100)
record = {"segments": [], "fps": fps, "width": W, "height": H, "chain": CHAIN, "color_ramp": RAMP}
files = []
prev_last: Path | None = None
for i, s in enumerate(SEGMENTS, 1):
    out = legs / f"seg_{i:02d}.mp4"
    positive = f"{s['motion'].strip().rstrip('.')}. {suffix}".strip()
    start_png = prev_last if (CHAIN and prev_last) else keys / f"{s['start']}.png"
    end_png = keys / f"{s['end']}.png" if s.get("end") else start_png
    if not out.is_file():
        t0 = time.monotonic()
        start = client.upload_image(start_png)
        end = client.upload_image(keys / f"{s['end']}.png") if s.get("end") else ""
        wf, settings = build_video_workflow(cfg, CHAR, positive=positive, negative=negative, image_name=start,
                                            end_image_name=end, seed=base + i, render_pass=story.get("quality", "medium"),
                                            duration_s=float(s["seconds"]), width=W, height=H)
        clip = video_output(client.outputs(client.wait(client.submit(wf), timeout_s=4 * 3600)))
        if clip is None:
            raise SystemExit(f"segment {i}: ComfyUI returned no video")
        client.fetch(clip, out)
        log(f"  segment {i}/{len(SEGMENTS)} {start_png.stem} -> {s.get('end') or '(free)'}: "
            f"{settings['LENGTH']} frames in {time.monotonic() - t0:.0f}s")
    else:
        log(f"  segment {i}: on disk, kept")
    use = out
    if RAMP:
        use = legs / f"seg_{i:02d}_cc.mp4"
        if not use.is_file():
            color_ramp(out, start_png, end_png, use, fps=fps, ffmpeg=ff)
    if CHAIN:
        prev_last = legs / f"seg_{i:02d}_last.png"
        extract_last_frame(use, prev_last, ffmpeg=ff)
    files.append(use)
    record["segments"].append({**s, "file": str(use), "start_image": str(start_png), "prompt": positive,
                               "seed": base + i})

final = d / (f"proof_{FIRST:02d}.mp4" if FIRST else "take_01.mp4")
silent = legs / "take_01_silent.mp4"
stitch(files, silent if lines else final, fps, ffmpeg=ff)
frames = [snap_frames(float(x["seconds"]), fps, int(cfg["video"]["max_frames"])) for x in SEGMENTS]
seconds = (sum(frames) - (len(frames) - 1)) / fps
if lines:
    subprocess.run(voice_mux_args(silent, lines, final, ffmpeg=ff, seconds=seconds),
                   check=True, capture_output=True, text=True, timeout=300)
record.update(file=str(final), seconds=round(seconds, 2))
final.with_suffix(".json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
log(f"VIDEODONE {CHAR} story '{story['name']}' {seconds:.1f}s in {d.name}")
