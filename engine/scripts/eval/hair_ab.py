"""Matched-seed A/B over the HAIR clause alone, on her locked LoRA.

    python scripts/eval/hair_ab.py <character> [--tag NAME] [--dry-run]

Jeremy, 2026-11-04, on isabelle: "test prompts for Isabelle hair styles ...
2 different waist-up portrait shots with different angles and outfits and
expressions. Then run those 2 prompts with" nine hair phrasings.

Two scenes x the arms below. Everything but the hair clause is held fixed:
same LoRA (her lock), same negative, same scene, and one fresh random seed
per scene drawn for this run and shared by every arm (a new comparison never
reuses an old seed). Prompts come from render.shot_prompt, the shoots' own
builder, so a winning phrase means the same thing in a pack.

Writes library/<char>/<date>_ab_<tag>/<arm>/scene_N.png, a labelled sheet
(rows = arms, columns = scenes) and a judge set ab_<char>_<tag>.
--dry-run prints the 18 prompts and the seeds and touches nothing.
"""

import json
import random
import sys
from datetime import datetime
from pathlib import Path

from sourcemode.assets.appearance import negative as appearance_negative
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.render import shot_prompt, t2i_workflow
from sourcemode.config import load_config, outputs_dir
from sourcemode.pose.native import NEGATIVE

ARGS = sys.argv[1:]
POS = [a for a in ARGS if not a.startswith("--")]
if not POS:
    raise SystemExit(__doc__)
CHAR = POS[0].lower()
TAG = next((ARGS[i + 1] for i, a in enumerate(ARGS) if a == "--tag" and i + 1 < len(ARGS)), "hair")
DRY = "--dry-run" in ARGS
W, H = 1024, 1536

ARMS = [
    ("loose", "her hair worn loose"),
    ("down", "her hair worn down"),
    ("wild", "her hair worn wild"),
    ("straight", "her hair straightened"),
    ("volume", "her hair worn loose with great volume"),
    ("messybun", "her hair in a messy bun"),
    ("doneup", "her hair done up"),
    ("highpony", "her hair in a high ponytail"),
    ("pony", "her hair in a ponytail"),
]

# Two waist-up portraits that differ in angle, outfit, expression and light,
# so a phrase that only works from one side or in one outfit shows it.
SCENES = [
    {"framing": "waist-up portrait, her head and shoulders in the upper half of the frame, her face large "
                "and sharp; never a wide shot, never full-body",
     "shot_type": "waist-up portrait photo",
     "facing": "her body turned three-quarters to her left, her face toward the camera",
     "gaze": "she looks directly at the camera",
     "stance": "standing relaxed against the kitchen counter, both hands resting on the edge of it",
     "expression_natural": "a soft, warm closed-lip smile",
     "outfit": "a white fitted ribbed tank top and light-wash high-waisted jeans",
     "setting": "bright morning daylight from a window, in a sunlit kitchen"},
    {"framing": "waist-up portrait, her head and shoulders in the upper half of the frame, her face large "
                "and sharp; never a wide shot, never full-body",
     "shot_type": "waist-up portrait photo from a little below eye level",
     "facing": "her body turned side-on to her right, her head turned back toward the camera",
     "gaze": "looking back over her shoulder into the camera",
     "stance": "standing at a cafe window, one hand resting on the strap of her bag",
     "expression_natural": "a bright open-mouthed laugh",
     "outfit": "a navy blue cropped knit sweater and a black mini skirt",
     "setting": "warm evening light and soft bokeh, by the window of a small cafe at dusk"},
]
BASE = {"pose": "standing", "category": "ab", "shoes": True, "look": 1}

cfg = load_config()
LORA = resolve_lora(cfg, CHAR)
if not LORA:
    raise SystemExit(f"no locked LoRA for {CHAR}")
NEG = NEGATIVE + (", " + appearance_negative(CHAR) if appearance_negative(CHAR) else "")
SEEDS = [random.SystemRandom().randrange(1, 2**31 - 1) for _ in SCENES]


def prompt(scene: dict, hair: str) -> str:
    slot = {**BASE, **scene, "id": "ab", "hair": hair}
    return shot_prompt(CHAR, slot, CHAR, backdrop=scene["setting"])


if DRY:
    print(f"{CHAR}: lora {LORA['name']}, seeds {SEEDS}")
    for name, hair in ARMS:
        for i, sc in enumerate(SCENES):
            print(f"\n[{name} scene {i}] {prompt(sc, hair)}")
    raise SystemExit(0)

from sourcemode import library as L  # noqa: E402
from sourcemode.assets.judge import make_set  # noqa: E402
from sourcemode.render.client import ComfyUIClient  # noqa: E402

OUT = L.find_set(cfg, CHAR, "ab", TAG, create=True)
L.write_set_json(OUT, character=CHAR, kind="ab", name=TAG, date=OUT.name[:10], judge_sets=[f"ab_{CHAR}_{TAG}"])
LOG = outputs_dir(cfg) / "logs" / f"ab_{CHAR}_{TAG}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
log(f"{CHAR}: lora {LORA['name']}, {len(ARMS)} arms x {len(SCENES)} scenes, seeds {SEEDS}")
(OUT / "arms.json").write_text(json.dumps({"arms": dict(ARMS), "seeds": SEEDS, "scenes": SCENES}, indent=1),
                               encoding="utf-8")
items = []
for name, hair in ARMS:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    for i, sc in enumerate(SCENES):
        dest = d / f"scene_{i}.png"
        p = prompt(sc, hair)
        if not dest.exists():
            wf = t2i_workflow(cfg, p, SEEDS[i], f"ab/{CHAR}_{TAG}/{name}", lora_path=LORA["path"],
                              negative=NEG, width=W, height=H)
            files = client.outputs(client.wait(client.submit(wf), timeout_s=3600))
            if not files:
                log(f"  {name} scene {i}: no output")
                continue
            client.fetch(files[0], dest)
            dest.with_suffix(".txt").write_text(p, encoding="utf-8")
        items.append({"id": f"{name}__{i}", "path": dest, "arm": name, "group": str(i), "label": hair})
        log(f"  {name} scene {i}: done")

if not items:
    raise SystemExit("rendered nothing")
make_set(outputs_dir(cfg) / "judge", f"ab_{CHAR}_{TAG}", f"{CHAR.title()} - hair phrasing A/B",
         items, question="Does the hair match the phrase? K = yes, X = no.", priority=0,
         meta={"character": CHAR, "renders_dir": OUT, "arms": dict(ARMS), "seeds": SEEDS, "tag": TAG})

from PIL import Image, ImageDraw  # noqa: E402

CW, CH = 360, 540
sheet = Image.new("RGB", (len(SCENES) * CW + 260, len(ARMS) * CH), (18, 18, 20))
dr = ImageDraw.Draw(sheet)
for r, (name, hair) in enumerate(ARMS):
    dr.text((8, r * CH + CH // 2), hair, fill=(230, 230, 235))
    for c in range(len(SCENES)):
        p = OUT / name / f"scene_{c}.png"
        if p.is_file():
            im = Image.open(p).convert("RGB")
            im.thumbnail((CW, CH))
            sheet.paste(im, (260 + c * CW, r * CH))
sheet.save(OUT / "sheet.jpg", quality=88)
log(f"sheet {OUT / 'sheet.jpg'}")
log("ABDONE")
