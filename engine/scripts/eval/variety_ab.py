"""Does a new draw of a pack look actually come out different? Three ways, on her lock.

    python scripts/eval/variety_ab.py <character> [--looks casual_01,fancy_town_01] [--draws 4] [--dry-run]

Jeremy, 2026-11-06, on amanda's full set re-drawn on fresh random seeds: "The
pictures look nearly identical." They were new seeds (7100 -> 785376134); the
pack prompt pins framing, body angle, gaze, expression, outfit, hair and a grey
studio, and Qwen-Image moves little across seeds under a prompt that tight.

Arms, every one on the same fresh seeds (one per draw, shared across arms):
  base       the pack prompt exactly as render_pack builds it, euler sampler
  ancestral  the same prompt, the euler_ancestral sampler (new noise each step)
  reroll     euler, but each draw re-rolls the pack's own pose choices - the
             rotation family, side, degrees, arms and expression - from the
             options pose_fields already uses

Writes library/<char>/<date>_ab_variety/<arm>/<look>_dN.png, sheet.jpg (rows =
look x arm, columns = draws) and a judge set ab_<char>_variety.
"""

import json
import random
import sys
from datetime import datetime

from sourcemode.assets import pack as P
from sourcemode.assets.appearance import negative as appearance_negative
from sourcemode.assets.appearance import pack_camera
from sourcemode.assets.catalog import plan_slots
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.render import EXPRESSION_TYPES, H, W, shot_prompt, t2i_workflow
from sourcemode.config import load_config, outputs_dir
from sourcemode.pose.native import NEGATIVE

ARGS = sys.argv[1:]
POS = [a for a in ARGS if not a.startswith("--")]
if not POS:
    raise SystemExit(__doc__)
CHAR = POS[0].lower()


def opt(name, default):
    return next((ARGS[i + 1] for i, a in enumerate(ARGS) if a == name and i + 1 < len(ARGS)), default)


LOOKS = opt("--looks", "casual_01,fancy_town_01").split(",")
DRAWS = int(opt("--draws", "4"))
DRY = "--dry-run" in ARGS
TAG = "variety"
ARMS = ("base", "ancestral", "reroll")

cfg = load_config()
OUT_ROOT = outputs_dir(cfg)
LORA = resolve_lora(cfg, CHAR)
if not LORA:
    raise SystemExit(f"no locked LoRA for {CHAR}")
plan = json.loads((OUT_ROOT / "game-assets" / CHAR / "plan_28.json").read_text(encoding="utf-8"))
by_id = {s["id"]: s for s in plan_slots(plan)}
missing = [x for x in LOOKS if x not in by_id]
if missing:
    raise SystemExit(f"not in {CHAR}'s plan: {missing}")

# the pack's own negative, as render_pack composes it
NEG = NEGATIVE + (", " + appearance_negative(CHAR) if appearance_negative(CHAR) else "")
have = {t.strip().lower() for t in NEG.split(",")}
for extra in (P.CAMERA_NEGATIVE, pack_camera(CHAR).get("negative") or ""):
    add = [t.strip() for t in extra.split(",") if t.strip() and t.strip().lower() not in have]
    have |= {t.lower() for t in add}
    NEG = ", ".join([NEG, *add]) if add else NEG

sysrand = random.SystemRandom()
SEEDS = [sysrand.randrange(1, 2**31 - 1) for _ in range(DRAWS)]


def rerolled(slot: dict, d: int) -> dict:
    """The slot with the pack's pose choices drawn again: pose_fields seeds its
    rng from the slot id and picks the family from `n`, so a new id and `n`
    re-roll side, degrees and arms; the expression type is drawn outright."""
    r = random.Random(SEEDS[d])
    return {**slot, "id": f"{slot['id']}_r{SEEDS[d]}", "n": r.randint(1, 4),
            "expression": r.choice(sorted(set(EXPRESSION_TYPES)))}


def prompt_for(arm: str, slot: dict, d: int) -> str:
    s = rerolled(slot, d) if arm == "reroll" else slot
    return shot_prompt(CHAR, s, plan.get("trigger"), backdrop=P.STUDIO_BACKDROP)


def workflow(arm: str, prompt: str, seed: int, prefix: str) -> dict:
    wf = t2i_workflow(cfg, prompt, seed, prefix, lora_path=LORA["path"], negative=NEG, width=W, height=H)
    if arm == "ancestral":
        for node in wf.values():
            if node.get("class_type") == "KSampler":
                node["inputs"]["sampler_name"] = "euler_ancestral"
    return wf


if DRY:
    print(f"{CHAR}: lora {LORA['name']}, seeds {SEEDS}")
    for look in LOOKS:
        for arm in ARMS:
            for d in range(DRAWS):
                print(f"\n[{look} {arm} d{d}] {prompt_for(arm, by_id[look], d)}")
    raise SystemExit(0)

from sourcemode import library as L  # noqa: E402
from sourcemode.assets.judge import make_set  # noqa: E402
from sourcemode.render.client import ComfyUIClient  # noqa: E402

OUT = L.find_set(cfg, CHAR, "ab", TAG, create=True)
L.write_set_json(OUT, character=CHAR, kind="ab", name=TAG, date=OUT.name[:10], judge_sets=[f"ab_{CHAR}_{TAG}"])
LOG = OUT_ROOT / "logs" / f"ab_{CHAR}_{TAG}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
log(f"{CHAR}: lora {LORA['name']}, looks {LOOKS}, {len(ARMS)} arms x {DRAWS} draws, seeds {SEEDS}")
(OUT / "arms.json").write_text(json.dumps({"arms": ARMS, "looks": LOOKS, "seeds": SEEDS}, indent=1),
                               encoding="utf-8")
items = []
for look in LOOKS:
    for arm in ARMS:
        d_dir = OUT / arm
        d_dir.mkdir(parents=True, exist_ok=True)
        for d in range(DRAWS):
            dest = d_dir / f"{look}_d{d}.png"
            p = prompt_for(arm, by_id[look], d)
            if not dest.exists():
                files = client.outputs(client.wait(client.submit(
                    workflow(arm, p, SEEDS[d], f"ab/{CHAR}_{TAG}/{arm}")), timeout_s=3600))
                if not files:
                    log(f"  {look} {arm} d{d}: no output")
                    continue
                client.fetch(files[0], dest)
                dest.with_suffix(".txt").write_text(p, encoding="utf-8")
            items.append({"id": f"{look}__{arm}__{d}", "path": dest, "arm": arm, "group": look,
                          "label": f"{look} {arm} draw {d}"})
            log(f"  {look} {arm} d{d}: done")

if not items:
    raise SystemExit("rendered nothing")
make_set(OUT_ROOT / "judge", f"ab_{CHAR}_{TAG}", f"{CHAR.title()} - variety across draws",
         items, question="Is this a usable pack shot? K = yes, X = no.", priority=0,
         meta={"character": CHAR, "renders_dir": OUT, "arms": list(ARMS), "seeds": SEEDS, "tag": TAG})

from PIL import Image, ImageDraw  # noqa: E402

CW, CH = 300, 450
rows = [(look, arm) for look in LOOKS for arm in ARMS]
sheet = Image.new("RGB", (DRAWS * CW + 220, len(rows) * CH), (18, 18, 20))
dr = ImageDraw.Draw(sheet)
for r, (look, arm) in enumerate(rows):
    dr.text((8, r * CH + CH // 2), f"{look}\n{arm}", fill=(230, 230, 235))
    for c in range(DRAWS):
        f = OUT / arm / f"{look}_d{c}.png"
        if f.is_file():
            im = Image.open(f).convert("RGB")
            im.thumbnail((CW, CH))
            sheet.paste(im, (220 + c * CW, r * CH))
sheet.save(OUT / "sheet.jpg", quality=88)
log(f"sheet {OUT / 'sheet.jpg'}")
log("ABDONE")
