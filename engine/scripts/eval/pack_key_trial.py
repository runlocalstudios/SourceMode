"""Render a character's 28-look pack on the KEY backdrop and chroma-key it.

    python scripts/eval/pack_key_trial.py <character>

Jeremy, 2026-10-18, on Amanda's and Vera's cutouts: "lots of parts not cut
out at all, some legs are getting cut out when they shouldn't be. the
process as you are running it is not working."

Measured on those packs: the learned matte (rembg isnet) on the light-grey
studio keeps the backdrop inside enclosed gaps (arm to waist, a cutout
dress), eats grey and white garments against the grey (amanda casual_05,
vera workout_02 at 63% faded legs, cici casual_04 at 56%), and cannot tell
a white catsuit from the wall. That is the documented limit of a learned
matte; the chroma key has none of those failures because it reads colour,
not a silhouette guess. On zara's 28 magenta T2I renders the auto key came
out clean (partial under 0.016) on 19 and hollow on 8 where the model drew
a floor sweep - this trial measures both on her, with the despill fixed.

Same plan, same per-look seeds, same prompt as her pack; one change, the
backdrop. Output is a library set of its own, never her pack's folders:

    library/<char>/<date>_ab_pack-key-trial/renders/<look>/shot_00_s<seed>.png
    library/<char>/<date>_ab_pack-key-trial/cutouts/<look>/...   (auto chroma)
    library/<char>/<date>_ab_pack-key-trial/review_white.jpg     (on WHITE, 2x)
    judge set pack_<char>_key                                  (the renders)
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

from sourcemode.assets import pack as P
from sourcemode.assets.appearance import negative as appearance_negative
from sourcemode.assets.catalog import look_id, plan_slots
from sourcemode.assets.cutout import auto_chroma_remover, cutout_batch, sample_backdrop
from sourcemode.assets.judge import make_set
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.redo import judge_item
from sourcemode.assets.render import KEY_BACKDROP
from sourcemode.config import load_config, outputs_dir
from sourcemode.gates.identity import embed_image
from sourcemode.library import find_set, write_set_json
from sourcemode.pose.native import NEGATIVE
from sourcemode.render.client import ComfyUIClient

POS = [a for a in sys.argv[1:] if not a.startswith("--")]
if not POS:
    raise SystemExit(__doc__)
CHAR = POS[0].lower()
cfg = load_config()
OUT = outputs_dir(cfg)
LOG = OUT / "logs" / f"pack_key_{CHAR}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


plan_path = OUT / "game-assets" / CHAR / "plan_28.json"
if not plan_path.is_file():
    raise SystemExit(f"no approved plan for {CHAR}")
plan = json.loads(plan_path.read_text(encoding="utf-8"))
LORA = resolve_lora(cfg, CHAR)
if not LORA:
    raise SystemExit(f"no approved LoRA for {CHAR}")

SET = find_set(cfg, CHAR, "ab", "pack-key-trial", create=True)
write_set_json(SET, character=CHAR, kind="ab", name="pack-key-trial", date=SET.name[:10],
               judge_sets=[f"pack_{CHAR}_key"])
log(f"{CHAR}: 28 looks on the key backdrop -> {SET}")

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
res = P.render_pack(cfg, client, CHAR, plan, OUT, lora_path=LORA["path"], negative=NEG, ref=ref,
                    backdrop=KEY_BACKDROP, root=SET / "renders", log=log)
if not res:
    raise SystemExit("rendered nothing - refusing to write a DONE marker")

# the backdrop the model actually drew, per look: colour and how uniform
pngs = P.shots(SET / "renders")
for p in pngs:
    key, dev = sample_backdrop(Image.open(p))
    log(f"  backdrop {p.parent.name}: {key} dev {dev:.1f}" + ("  NOT UNIFORM" if dev > 18 else ""))

size = tuple(cfg.get("assets", {}).get("game_size", (1024, 1536)))
cuts = cutout_batch(pngs, SET / "cutouts", remover=auto_chroma_remover(), model="chroma:auto",
                    size=size, webp=True, log=log)
hollow = [c for c in cuts if "hollow" in c["report"]["flags"]]
log(f"  keyed {len(cuts)}: {len(hollow)} hollow, "
    f"median partial {sorted(c['report']['partial'] for c in cuts)[len(cuts) // 2]:.4f}")

# every cutout on WHITE at a readable size - the only review that shows a halo,
# a speckle or a kept patch of backdrop
tile, cols = 360, 7
th = int(tile * 1.5)
rows = -(-len(cuts) // cols)
sheet = Image.new("RGB", (cols * tile, rows * (th + 16)), (255, 255, 255))
from PIL import ImageDraw  # noqa: E402
draw = ImageDraw.Draw(sheet)
for i, c in enumerate(cuts):
    im = Image.open(c["outputs"]["png"]).convert("RGBA")
    im.thumbnail((tile, th))
    x, y = (i % cols) * tile, (i // cols) * (th + 16) + 14
    sheet.paste(im, (x, y), im)
    name = Path(c["source"]).parent.name
    draw.text((x + 2, y - 13), f"{name[:26]}  p={c['report']['partial']:.3f} {' '.join(c['report']['flags'])}",
              fill=(30, 30, 30))
white = SET / "review_white.jpg"
sheet.save(white, quality=90)
log(f"  sheet on white: {white}")

by_id = {s["id"]: s for s in plan_slots(plan)}
items = []
for meta in res:
    a = meta.get("asset") or {}
    slot = by_id.get(look_id(a["category"], int(a["look"]))) if a.get("category") else None
    if slot:
        items.append(judge_item(slot, Path(meta["source"]), kind="pack", character=CHAR,
                                source=plan_path.name, seed=meta.get("seed", 0),
                                score=meta.get("score"), arm=slot["category"]))
make_set(OUT / "judge", f"pack_{CHAR}_key", f"{CHAR.title()} - wardrobe pack on the key backdrop",
         items, question="Ship this one? K = yes, X = no.", priority=5,
         meta={"character": CHAR, "renders_dir": SET / "renders", "backdrop": "key"})
log(f"PACKKEYDONE {CHAR} {len(res)} rendered, {len(cuts)} keyed, {len(hollow)} hollow -> judge set pack_{CHAR}_key")
