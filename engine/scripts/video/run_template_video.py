"""Render a video template for one character from a start frame she has.

    python scripts/video/run_template_video.py <spec.json>

spec.json: {"template", "character", "start" (a still on disk), "takes", "quality",
"voice" (bool), "seed"}. Written by the Video tab's Render video button.

The template is read HERE, at run time, so an edit to its legs or script made
after queueing still lands. Each leg renders its own motion line through Wan 2.2
I2V, chained from the last frame (colour-matched back to the start frame) and
stitched - `sourcemode.video.render_take`, the same chain the Video tab's form
uses. With `voice`, the script is spoken in her cloned voice (Chatterbox, CPU,
its own env) and each line is laid under the clip at its start time; the silent
take is kept in _legs/.

Output: library/<character>/<date>_video_<template>/take_01.mp4 ...
"""

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from sourcemode import video_templates as VT
from sourcemode.config import ENGINE_ROOT, load_config, outputs_dir
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient
from sourcemode.video import (
    VideoSpec, ffmpeg_exe, leg_cap_seconds, normalize_source, render_take, script_beats, validate,
    voice_mux_args,
)

if len(sys.argv) < 2:
    raise SystemExit(__doc__)
SPEC_PATH = Path(sys.argv[1])
req = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
cfg = load_config()
OUT = outputs_dir(cfg)
CHAR = str(req["character"]).lower()
tpl = VT.load(req["template"])
LOG = OUT / "logs" / f"video_{CHAR}.log"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


start = Path(req["start"])
if not start.is_file():
    raise SystemExit(f"the start frame is not on disk: {start}")
# the video is the still's aspect, pixel for pixel scaled - never a crop of it
size = list(VT.video_size_for(start))
spec = VideoSpec(character=CHAR, motion=tpl.get("summary", ""), seconds=float(tpl["seconds"]),
                 quality=req.get("quality", "medium"), takes=int(req.get("takes", 1)),
                 name=tpl["id"], source={"kind": "keeper", "path": str(start)},
                 seed=int(req.get("seed") or 0), legs=list(tpl["legs"]),
                 leg_suffix=tpl.get("leg_suffix", ""), negative_extra=tpl.get("video_negative", ""),
                 size=size, template=tpl["id"])
problems = validate(spec, leg_cap_s=leg_cap_seconds(cfg))
ff = ffmpeg_exe(cfg)
if not ff:
    problems.append("a chained clip needs ffmpeg and there is none on this machine")
voice_ref = None
if req.get("voice"):
    from sourcemode.voice.record import get as get_voice  # noqa: E402

    v = get_voice(CHAR) or {}
    voice_ref = Path(v["reference"]) if v.get("reference") else None
    if not (voice_ref and voice_ref.is_file()):
        problems.append(f"{CHAR} has no voice reference - set one on the Characters tab, or render without voice")
    if not script_beats(tpl.get("script", "")):
        problems.append(f"{tpl['name']} has no script to speak")
if problems:
    raise SystemExit("; ".join(problems))

d = find_set(cfg, CHAR, "video", tpl["id"], create=True)
write_set_json(d, character=CHAR, kind="video", name=tpl["id"], date=d.name[:10], judge_sets=[],
               template=tpl["id"])
(d / "spec.json").write_text(json.dumps({**asdict(spec), "voice": bool(req.get("voice")),
                                         "script": tpl.get("script", "")}, indent=1), encoding="utf-8")
log(f"{CHAR}: '{tpl['name']}' - {len(spec.legs)} legs, {spec.seconds:g}s, {spec.takes} take(s), "
    f"{spec.quality}{', voiced' if voice_ref else ''} -> {d}")

src_png = d / "source_src.png"
shutil.copyfile(start, src_png)
source_png = d / "source.png"
normalize_source(src_png, source_png, size[0], size[1])

# the voice first: it is CPU work, and a script that will not speak should fail
# before an hour of legs, not after
lines: list[tuple[float, Path]] = []
if voice_ref:
    beats = script_beats(tpl["script"])
    vdir = d / "_voice"
    vdir.mkdir(exist_ok=True)
    (vdir / "lines.json").write_text(json.dumps([t for _s, t in beats], ensure_ascii=False), encoding="utf-8")
    uv = shutil.which("uv") or "uv"
    cmd = [uv, "run", "--isolated", "--with", "chatterbox-tts", "--with", "setuptools<81", "--with", "soundfile",
           "python", str(ENGINE_ROOT / "scripts" / "voice" / "say_script.py"), str(voice_ref), str(vdir),
           str(vdir / "lines.json")]
    log(f"  voicing {len(beats)} lines in her voice")
    r = subprocess.run(cmd, cwd=str(ENGINE_ROOT), capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"the voice track failed: {(r.stderr or r.stdout)[-600:]}")
    lines = [(s, vdir / f"line_{i:02d}.wav") for i, (s, _t) in enumerate(beats)]
    missing = [str(p) for _s, p in lines if not p.is_file()]
    if missing:
        raise SystemExit(f"the voice track is missing {missing}")

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
done = 0
base = spec.seed or 7100
for t in range(1, spec.takes + 1):
    final = d / f"take_{t:02d}.mp4"
    if final.exists():
        log(f"  take {t}: already on disk, skipped")
        done += 1
        continue
    try:
        rec = render_take(cfg, client, spec, source_png, d, take=t, seed=base + t * 1000, log=log)
        if lines:
            silent = d / "_legs" / f"take_{t:02d}_silent.mp4"
            silent.parent.mkdir(exist_ok=True)
            final.replace(silent)
            subprocess.run(voice_mux_args(silent, lines, final, ffmpeg=ff, seconds=float(rec["seconds"])),
                           check=True, capture_output=True, text=True, timeout=300)
            log(f"  take {t}: voiced")
        done += 1
    except Exception as exc:  # noqa: BLE001 - one take never kills the rest
        log(f"  take {t}: FAILED {exc}")

if not done:
    raise SystemExit("rendered nothing - refusing to report success")
log(f"VIDEODONE {CHAR} {done} take(s) of '{tpl['name']}' in {d.name}")
