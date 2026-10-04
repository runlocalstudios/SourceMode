"""Render a 28-look wardrobe pack through T2I + LoRA instead of the edit graph.

    python scripts/eval/pack_t2i.py zara

Jeremy, 2026-10-04: "I thought the point of training the LoRA was that we would
use T2I + LoRA to generate these. Why is it an edit? I thought only the fixed
pose or outfit fixing needed edit."

He is right that the edit path was built for pose transfer. The question this
answers is the one neither of us knows: does T2I hold the CROP tightly enough
across 28 looks to ship, without a plate forcing it?

Measured on the edit pack it is replacing (zara, 103 shots on disk):

    head turn asked, came back front     46 of 103   45%
    body turn: asked front 46 / L 32 / R 25,  got front 20 / L 23 / R 60
    crop asked upper-thigh, got other    16 of 103   14%

One plate is built per character and reused for all 28 looks, so the pack is
one photograph re-dressed 28 times and roughly half the per-look pose variation
`shot_prompt` computes is overridden. The 14% crop figure matters most: that is
the plate failing at the single job it is there for.

So this renders the SAME plan, the SAME `shot_prompt`, the same 1024x1536, the
same per-slot seed - and changes exactly one thing, the graph. Output goes to
its own root so the existing pack is untouched and both can be judged.
"""

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from sourcemode.assets.adherence import check, measure
from sourcemode.assets.appearance import negative as appearance_negative
from sourcemode.assets.catalog import plan_slots, slot_dirname
from sourcemode.assets.judge import make_set
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.render import H, W, pose_fields, shot_prompt, t2i_workflow
from sourcemode.config import load_config, outputs_dir
from sourcemode.gates.identity import cosine, embed_image
from sourcemode.pose.native import NEGATIVE
from sourcemode.render.client import ComfyUIClient

if len(sys.argv) < 2:
    raise SystemExit(__doc__)

CHAR = sys.argv[1].lower()
SEED_BASE = 7100            # same per-slot seed as the edit pack's shot_00
cfg = load_config()
OUT = outputs_dir(cfg)
ROOT = OUT / "game-assets-t2i" / CHAR / "renders"
ROOT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "logs" / f"pack_t2i_{CHAR}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


plan_path = next(iter(sorted((OUT / "game-assets" / CHAR).glob("plan*.json"))), None)
if plan_path is None:
    raise SystemExit(f"no plan for {CHAR}")
plan = json.loads(plan_path.read_text(encoding="utf-8"))
slots = plan_slots(plan)

LORA = resolve_lora(cfg, CHAR)
if not LORA:
    raise SystemExit(f"no approved LoRA for {CHAR}")
log(f"{CHAR}: {len(slots)} looks through T2I, lora {LORA['name']}, seeds {SEED_BASE}+i*1000")

REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
ref = None
for pat in (f"{CHAR}_face.*", f"{CHAR}_portrait*.*"):
    for hit in sorted(REFS.glob(pat)):
        if embed_image(hit) is not None:
            ref = embed_image(hit)
            break
    if ref is not None:
        break

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
NEG = NEGATIVE + (", " + appearance_negative(CHAR) if appearance_negative(CHAR) else "")

items, fails, done = [], Counter(), 0
for i, slot in enumerate(slots):
    d = ROOT / slot_dirname(slot)
    d.mkdir(exist_ok=True)
    seed = SEED_BASE + i * 1000
    dest = d / f"shot_00_s{seed}.png"
    # No backdrop argument: shot_prompt falls back to KEY_BACKDROP, the flat
    # magenta a shipping asset needs. Whether T2I can hold a clean keyable
    # background is part of what this measures.
    prompt = shot_prompt(CHAR, slot, plan.get("trigger"))
    try:
        if not dest.exists():
            files = client.outputs(client.wait(client.submit(
                t2i_workflow(cfg, prompt, seed, f"packT2I/{CHAR}/{slot['id']}",
                             lora_path=LORA["path"], negative=NEG, width=W, height=H)),
                timeout_s=3600))
            if not files:
                log(f"  {slot['id']}: no output")
                continue
            client.fetch(files[0], dest)
        asked = pose_fields(CHAR, slot)["asked"]
        try:
            adh = check(asked, measure(dest))
        except Exception as exc:  # noqa: BLE001 - a measurement, never a blocker
            adh = {"failed": [], "soft": [], "got": {}, "error": str(exc)}
        e = embed_image(dest)
        score = round(float(cosine(ref, e)), 4) if (ref is not None and e is not None) else None
        dest.with_suffix(".json").write_text(json.dumps({
            "source": str(dest), "asset": {"character": CHAR, "category": slot["category"],
                                           "look": slot["look"], "pose": slot["pose"], "shot": 0},
            "score": score, "asked": asked, "adherence": adh, "seed": seed,
            "prompt": prompt, "lora": LORA["path"], "graph": "qwen_image_t2i"}, indent=1),
            encoding="utf-8")
        for f in adh.get("failed") or []:
            fails[f.split(":")[0]] += 1
        items.append({"id": slot["id"], "path": dest, "arm": slot["category"],
                      "group": str(slot["look"]), "score": score})
        done += 1
        log(f"  {slot['id']}: {score} {'OK' if not adh.get('failed') else adh['failed']}")
    except Exception as exc:  # noqa: BLE001 - one bad look never kills the run
        log(f"  {slot['id']}: ERROR {exc}")

if not done:
    raise SystemExit("rendered nothing")

make_set(OUT / "judge", f"pack_{CHAR}_t2i", f"{CHAR.title()} - wardrobe pack, T2I",
         items, question="Ship this one? K = yes, X = no.",
         reference=plan.get("reference"), priority=5)

log("")
log(f"PACKT2IDONE {CHAR} {done} looks -> judge set pack_{CHAR}_t2i")
log(f"adherence failures by kind, out of {done}: {dict(fails)}")
log("compare against the edit pack: head 45%, crop 14% of 103")
