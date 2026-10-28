"""Render a video template's start frames for one character, for review.

    python scripts/video/start_frames.py <template> <character> [--with <partner>] [--n 4]

At the source's aspect (landscape or portrait) through her LoRA, N seeds, into
library/<character>/<date>_video_<template>-start/ and a judge set
`video_<character>_<template>_start`. The still carries her identity into
every leg - Wan takes no character LoRA - so it is judged before any video
time is spent. A two-woman template (`cast: 2`) describes the partner from her
appearance record; only the lead's LoRA is loaded, so the partner's face is the
base model's reading of her sentence.

Re-running skips the seeds already on disk unless the prompt changed.
"""

import sys
from datetime import datetime

from sourcemode import video_templates as VT
from sourcemode.assets.appearance import negative as appearance_negative
from sourcemode.assets.judge import make_set
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.render import t2i_workflow
from sourcemode.assets.shoots import set_aside_if_changed
from sourcemode.config import load_config, outputs_dir
from sourcemode.library import find_set, write_set_json
from sourcemode.pose.native import NEGATIVE
from sourcemode.render.client import ComfyUIClient

POS = [a for a in sys.argv[1:] if not a.startswith("--")]
ARG = {a: sys.argv[sys.argv.index(a) + 1] for a in ("--with", "--n") if a in sys.argv}
POS = [p for p in POS if p not in ARG.values()]
if len(POS) != 2:
    raise SystemExit(__doc__)
TID, CHAR = POS[0], POS[1].lower()
PARTNER = (ARG.get("--with") or "").lower() or None
N = int(ARG.get("--n") or 4)

tpl = VT.load(TID)
cfg = load_config()
OUT = outputs_dir(cfg)
LOG = OUT / "logs" / f"video_{CHAR}.log"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


if int(tpl.get("cast", 1)) > 1 and not PARTNER:
    raise SystemExit(f"{TID} has two women - name the second with --with <character>")
lora = resolve_lora(cfg, CHAR)
if not lora:
    raise SystemExit(f"no approved LoRA for {CHAR}")
prompt = VT.start_prompt(tpl, CHAR, PARTNER)
W, H = VT.size_for(tpl)
neg = VT.start_negative(tpl, NEGATIVE + (", " + appearance_negative(CHAR) if appearance_negative(CHAR) else ""))
name = f"{TID}-start"
d = find_set(cfg, CHAR, "video", name, create=True)
set_id = f"video_{CHAR}_{TID}_start"
write_set_json(d, character=CHAR, kind="video", name=name, date=d.name[:10], judge_sets=[set_id])
log(f"{CHAR}: {N} start frames for '{tpl['name']}'{' with ' + PARTNER if PARTNER else ''} -> {d}")

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
items = []
for k in range(N):
    seed = VT.START_SEED + k * 1000
    dest = d / f"start_{k:02d}.png"
    if set_aside_if_changed(dest, prompt):
        log(f"  start_{k:02d}: the template changed - drawing it again")
    if not dest.exists():
        wf = t2i_workflow(cfg, prompt, seed, f"video/{CHAR}/{TID}", lora_path=lora["path"],
                          negative=neg, width=W, height=H)
        files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
        if not files:
            log(f"  start_{k:02d}: no output")
            continue
        client.fetch(files[0], dest)
        dest.with_suffix(".txt").write_text(prompt, encoding="utf-8")
        log(f"  start_{k:02d}: seed {seed}")
    items.append({"id": f"start_{k:02d}", "path": str(dest), "arm": TID, "group": str(k)})

if not items:
    raise SystemExit("rendered nothing - refusing to report success")
make_set(OUT / "judge", set_id, f"{CHAR.title()} - {tpl['name']} start frames", items,
         question="Is this a start frame worth animating? K = yes, X = no.", priority=5,
         meta={"character": CHAR, "video_template": TID, "renders_dir": str(d)})
log(f"STARTFRAMESDONE {CHAR} {len(items)} in judge set {set_id}")
