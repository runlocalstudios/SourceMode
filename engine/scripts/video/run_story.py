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
re-queueing re-renders only that segment. Jeremy, 2026-10-29: "your goal is to
output a video for me that is a masterpiece".

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
from sourcemode.video import NEGATIVE, ffmpeg_exe, normalize_source, script_beats, stitch, video_output, voice_mux_args

if len(sys.argv) < 2:
    raise SystemExit(__doc__)
story = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
cfg = load_config()
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
for i, s in enumerate(story["segments"], 1):
    for key in (s["start"], s.get("end")):
        if key and key not in photos:
            problems.append(f"segment {i} names photo {key!r}, which is not in photos")
    if not 1 <= float(s["seconds"]) <= int(cfg["video"]["max_frames"]) / fps:
        problems.append(f"segment {i}: {s['seconds']} s is outside 1 s .. one leg")
voice_ref = None
if story.get("voice"):
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
shutil.copyfile(keys / f"{story['segments'][0]['start']}.png", d / "source_src.png")
total_s = sum(float(s["seconds"]) for s in story["segments"])
log(f"{CHAR}: story '{story['name']}' - {len(story['segments'])} segments, {total_s:g} s, {W}x{H}"
    f"{', voiced' if voice_ref else ''} -> {d}")

lines: list[tuple[float, Path]] = []
if voice_ref:
    beats = script_beats(story.get("script", ""))
    vdir = d / "_voice"
    vdir.mkdir(exist_ok=True)
    (vdir / "lines.json").write_text(json.dumps([t for _s, t in beats], ensure_ascii=False), encoding="utf-8")
    uv = shutil.which("uv") or "uv"
    cmd = [uv, "run", "--isolated", "--with", "chatterbox-tts", "--with", "setuptools<81", "--with", "soundfile",
           "python", str(ENGINE_ROOT / "scripts" / "voice" / "say_script.py"), str(voice_ref), str(vdir),
           str(vdir / "lines.json")]
    log(f"  voicing {len(beats)} lines")
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
record = {"segments": [], "fps": fps, "width": W, "height": H}
files = []
for i, s in enumerate(story["segments"], 1):
    out = legs / f"seg_{i:02d}.mp4"
    positive = f"{s['motion'].strip().rstrip('.')}. {suffix}".strip()
    if not out.is_file():
        t0 = time.monotonic()
        start = client.upload_image(keys / f"{s['start']}.png")
        end = client.upload_image(keys / f"{s['end']}.png") if s.get("end") else ""
        wf, settings = build_video_workflow(cfg, CHAR, positive=positive, negative=negative, image_name=start,
                                            end_image_name=end, seed=base + i, render_pass=story.get("quality", "medium"),
                                            duration_s=float(s["seconds"]), width=W, height=H)
        clip = video_output(client.outputs(client.wait(client.submit(wf), timeout_s=4 * 3600)))
        if clip is None:
            raise SystemExit(f"segment {i}: ComfyUI returned no video")
        client.fetch(clip, out)
        log(f"  segment {i}/{len(story['segments'])} {s['start']} -> {s.get('end') or '(free)'}: "
            f"{settings['LENGTH']} frames in {time.monotonic() - t0:.0f}s")
    else:
        log(f"  segment {i}: on disk, kept")
    files.append(out)
    record["segments"].append({**s, "file": str(out), "prompt": positive, "seed": base + i})

final = d / "take_01.mp4"
silent = legs / "take_01_silent.mp4"
stitch(files, silent if lines else final, fps, ffmpeg=ff)
frames = [snap_frames(float(x["seconds"]), fps, int(cfg["video"]["max_frames"])) for x in story["segments"]]
seconds = (sum(frames) - (len(frames) - 1)) / fps
if lines:
    subprocess.run(voice_mux_args(silent, lines, final, ffmpeg=ff, seconds=seconds),
                   check=True, capture_output=True, text=True, timeout=300)
record.update(file=str(final), seconds=round(seconds, 2))
final.with_suffix(".json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
log(f"VIDEODONE {CHAR} story '{story['name']}' {seconds:.1f}s in {d.name}")
