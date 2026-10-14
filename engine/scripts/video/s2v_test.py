"""The S2V trial: one still of her + one line in her voice -> N talking takes.

Jeremy, 2026-10-14: "we may as well test this out and we can always iterate".
This is the test, not the product: the Video tab gets its "She speaks" switch
only if these takes hold her face. Research and the choice of Wan2.2-S2V over
InfiniteTalk / LatentSync / Ovi / MagiHuman / LTX: the 2026-10-14 session.

    python scripts/video/s2v_test.py <character> --still <png> --audio <wav> --name <set name>
                                     [--prompt "..."] [--takes 4] [--seed 7100] [--steps 20 --cfg 6.0]

The line is made first (scripts/voice/say_line.py, Chatterbox, CPU) by the
same queue job, so the wav exists when this starts. Output goes beside her
other clips, library/<character>/<date>_video_<name>/, in the shape the Video
tab already lists: take_NN.mp4 with the voice embedded, take_NN.json, spec.json.
"""

import argparse
import json
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

from sourcemode.config import load_config, outputs_dir
from sourcemode.library import find_set, write_set_json
from sourcemode.render.client import ComfyUIClient
from sourcemode.video import NEGATIVE, S2V, normalize_source, s2v_workflow, speech_frames, video_output

ap = argparse.ArgumentParser()
ap.add_argument("character")
ap.add_argument("--still", required=True)
ap.add_argument("--audio", required=True)
ap.add_argument("--name", required=True)
ap.add_argument("--prompt", default="she talks to the camera, animated, hands moving a little as she speaks")
ap.add_argument("--takes", type=int, default=4)
ap.add_argument("--seed", type=int, default=7100)
ap.add_argument("--steps", type=int, default=S2V["steps"])
ap.add_argument("--cfg", type=float, default=S2V["cfg"])
a = ap.parse_args()

cfg = load_config()
OUT = outputs_dir(cfg)
CHAR = a.character.lower()
LOG = OUT / "logs" / f"video_{CHAR}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


still, audio = Path(a.still), Path(a.audio)
if not still.is_file():
    raise SystemExit(f"the still is not on disk: {still}")
if not audio.is_file():
    raise SystemExit(f"the line is not on disk: {audio} - did say_line.py run?")
with wave.open(str(audio)) as w:
    seconds = w.getnframes() / w.getframerate()
frames = speech_frames(seconds)
if frames is None:
    raise SystemExit(f"the line runs {seconds:.1f}s; one S2V pass covers at most "
                     f"{(S2V['max_frames'] - 1) / S2V['fps']:.1f}s - shorten it or wait for chained chunks")

d = find_set(cfg, CHAR, "video", a.name, create=True)
write_set_json(d, character=CHAR, kind="video", name=a.name, date=d.name[:10], judge_sets=[])
spec = {"character": CHAR, "motion": a.prompt, "seconds": round(seconds, 2), "quality": "s2v",
        "takes": a.takes, "name": a.name, "source": {"kind": "keeper", "path": str(still)},
        "line": str(audio), "seed": a.seed, "graph": "wan22_s2v", "steps": a.steps, "cfg": a.cfg}
(d / "spec.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
src_png = d / "source_src.png"
if not src_png.exists():
    src_png.write_bytes(still.read_bytes())
line_wav = d / "line.wav"
if not line_wav.exists():
    line_wav.write_bytes(audio.read_bytes())
source_png = d / "source.png"
normalize_source(src_png, source_png, S2V["width"], S2V["height"])
log(f"{CHAR}: S2V trial, {a.takes} take(s), {seconds:.1f}s of speech -> {frames} frames @ {S2V['fps']} fps, "
    f"{a.steps} steps cfg {a.cfg} -> {d}")

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
image_name = client.upload_image(source_png)
audio_name = client.upload_image(line_wav)       # /upload/image stores any file in the input folder
positive = f"{a.prompt.strip().rstrip('.')}. {S2V['pacing']}."
done = 0
for t in range(1, a.takes + 1):
    final = d / f"take_{t:02d}.mp4"
    if final.exists():
        log(f"  take {t}: already on disk, skipped"); done += 1; continue
    seed = a.seed + t * 1000
    t0 = time.monotonic()
    try:
        wf, settings = s2v_workflow(cfg, positive=positive, negative=NEGATIVE, image_name=image_name,
                                    audio_name=audio_name, frames=frames, seed=seed,
                                    prefix=f"video/{CHAR}/s2v", steps=a.steps, cfg_scale=a.cfg)
        files = client.outputs(client.wait(client.submit(wf), timeout_s=4 * 3600))
        clip = video_output(files)
        if clip is None:
            raise RuntimeError("ComfyUI returned no video file")
        client.fetch(clip, final)
        rec = {"take": t, "seed": seed, "fps": S2V["fps"], "width": S2V["width"], "height": S2V["height"],
               "quality": "s2v", "motion": a.prompt, "pacing": S2V["pacing"], "line": str(line_wav),
               "legs": [{"leg": 1, "seconds": round(seconds, 2), "frames": frames, "seed": seed,
                         "file": str(final), "render_s": round(time.monotonic() - t0, 1)}],
               "file": str(final), "seconds": round((frames - 1) / S2V["fps"], 2), "settings": settings}
        final.with_suffix(".json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        log(f"  take {t}: {frames} frames in {time.monotonic() - t0:.0f}s")
        done += 1
    except Exception as exc:  # noqa: BLE001 - one take never kills the rest
        log(f"  take {t}: FAILED {exc}")

if not done:
    raise SystemExit("rendered nothing - refusing to report success")
log(f"VIDEODONE {CHAR} {done} take(s) in {d.name}")
