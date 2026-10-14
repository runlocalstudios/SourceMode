"""Render one video spec: a still of her (a keeper, or a new T2I render) through
Wan 2.2 I2V, N takes, chained when longer than one leg, into her library.

    python scripts/video/run_video.py <spec.json>

The Video tab writes the spec and queues this; `sourcemode.video` does the
work. Guards first, so a bad spec dies in a second and not after a leg.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from sourcemode.assets.appearance import negative as appearance_negative
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.render import shot_prompt, t2i_workflow
from sourcemode.config import load_config, outputs_dir
from sourcemode.library import find_set, write_set_json
from sourcemode.pose.native import NEGATIVE
from sourcemode.render.client import ComfyUIClient
from sourcemode.video import (
    VideoSpec, ffmpeg_exe, leg_cap_seconds, legs_for, normalize_source, render_take, still_slot,
    validate,
)

if len(sys.argv) < 2:
    raise SystemExit(__doc__)

SPEC_PATH = Path(sys.argv[1])
if not SPEC_PATH.is_file():
    raise SystemExit(f"no spec at {SPEC_PATH}")
spec = VideoSpec.from_dict(json.loads(SPEC_PATH.read_text(encoding="utf-8")))
cfg = load_config()
OUT = outputs_dir(cfg)
CHAR = spec.character.lower()
LOG = OUT / "logs" / f"video_{CHAR}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


problems = validate(spec, leg_cap_s=leg_cap_seconds(cfg))
legs = legs_for(spec.seconds, leg_cap_seconds(cfg))
if len(legs) > 1 and not ffmpeg_exe(cfg):
    problems.append("a chained clip needs ffmpeg and there is none on this machine")
if problems:
    raise SystemExit("; ".join(problems))

name = spec.name or spec.motion.split(",")[0].split(".")[0]
d = find_set(cfg, CHAR, "video", name, create=True)
write_set_json(d, character=CHAR, kind="video", name=name, date=d.name[:10], judge_sets=[])
(d / "spec.json").write_text(SPEC_PATH.read_text(encoding="utf-8"), encoding="utf-8")
log(f"{CHAR}: {spec.takes} take(s) x {spec.seconds}s as {len(legs)} leg(s), {spec.quality}, -> {d}")

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
src_png = d / "source_src.png"
if spec.source["kind"] == "keeper":
    if not src_png.exists():
        src_png.write_bytes(Path(spec.source["path"]).read_bytes())
        log(f"  source: keeper {spec.source['path']}")
else:
    # a new still, through her LoRA at the training bucket: identity lives here
    lora = resolve_lora(cfg, CHAR)
    if not lora:
        raise SystemExit(f"no approved LoRA for {CHAR} - a new still needs one; pick a keeper instead")
    if not src_png.exists():
        slot = still_slot(spec)
        prompt = shot_prompt(CHAR, slot, CHAR, backdrop=slot["setting"] or None)
        neg = NEGATIVE + (", " + appearance_negative(CHAR) if appearance_negative(CHAR) else "")
        wf = t2i_workflow(cfg, prompt, spec.seed or 9100, f"video/{CHAR}/still", lora_path=lora["path"],
                          negative=neg, width=1024, height=1536)
        files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
        if not files:
            raise SystemExit("the still rendered nothing")
        client.fetch(files[0], src_png)
        (d / "source_src.txt").write_text(prompt, encoding="utf-8")
        log(f"  still rendered: {prompt[:120]}...")

source_png = d / "source.png"
v = cfg["video"]
normalize_source(src_png, source_png, int(v["width"]), int(v["height"]))

done = 0
base = spec.seed or 7100
for t in range(1, int(spec.takes) + 1):
    final = d / f"take_{t:02d}.mp4"
    if final.exists():
        log(f"  take {t}: already on disk, skipped")
        done += 1
        continue
    try:
        render_take(cfg, client, spec, source_png, d, take=t, seed=base + t * 1000, log=log)
        done += 1
    except Exception as exc:  # noqa: BLE001 - one take never kills the rest
        log(f"  take {t}: FAILED {exc}")

if not done:
    raise SystemExit("rendered nothing - refusing to report success")
log(f"VIDEODONE {CHAR} {done} take(s) in {d.name}")
