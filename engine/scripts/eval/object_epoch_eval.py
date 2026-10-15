"""Epoch sweep for an OBJECT LoRA - the torso toy first, 2026-10-15.

    python object_epoch_eval.py <name> <output_name> <total_epochs> <start> <end> <trigger> <ckpt_dir> [n_scenes] [--dry-run] [--epochs 16,20] [--seed N]

The character sweep (dense_epoch_eval.py) scores every render against a face
reference, checks the sex of the face and reads her appearance record. None of
that applies to a toy. This renders the object scenes (sourcemode.assets.
object_scenes) on fixed seeds at every epoch, plus one no-LoRA arm so the base
model's idea of the trigger sits beside the trained ones, and loads them into
/judge as "is this the toy". The reference on the judge page is a product shot
from the training set itself.

`<name>` is the library folder the renders go under (library/<name>/<date>_sweep_...).
--dry-run prints the grid and the prompts and renders nothing.
"""
import json
import shutil
import sys
from pathlib import Path

from sourcemode.assets.judge import make_set
from sourcemode.assets.object_scenes import object_prompts
from sourcemode.config import load_config, workflows_dir
from sourcemode.pose.native import NEGATIVE
from sourcemode.render.workflow import load_template, prune_placeholder_loras, substitute

# Flags split out first: a flag left in argv lands in a positional slot by index
# (dense_epoch_eval.py lost a 60-render job that way).
_FLAGS = {"--epochs", "--seed"}
_BARE = {"--dry-run"}
POS, _FLAGVALS, _BARESEEN = [], {}, set()
_it = iter(sys.argv)
for _a in _it:
    if _a in _FLAGS:
        _FLAGVALS[_a] = next(_it, "")
    elif _a in _BARE:
        _BARESEEN.add(_a)
    else:
        POS.append(_a)
if len(POS) < 8:
    raise SystemExit(__doc__)

NAME = POS[1].lower()
SUB = POS[2]                 # musubi output_name -> loras/sourcemode/<SUB>
TOTAL = int(POS[3])
START, END = int(POS[4]), int(POS[5])
TRIGGER = POS[6]
CKPT = Path(POS[7])
N_SCENES = int(POS[8]) if len(POS) > 8 else 10
DRY = "--dry-run" in _BARESEEN

W, H = 1024, 1536
LOG = Path(f"outputs/logs/dense_{SUB}.log")
LORA_DIR = Path(f"C:/ComfyUI/models/loras/sourcemode/{SUB}")
GRID = list(range(START, END + 1))
if _FLAGVALS.get("--epochs"):
    GRID = [int(x) for x in _FLAGVALS["--epochs"].split(",") if x.strip()]
SET_ID = f"dense_{SUB}_object"
SCENES = object_prompts(TRIGGER)
SCENES = (SCENES * -(-N_SCENES // len(SCENES)))[:N_SCENES]

if not DRY and (not CKPT.is_dir() or not any(CKPT.glob("*.safetensors"))):
    raise SystemExit(f"no checkpoints at {CKPT}; refusing to sweep nothing")


def log(m):
    print(m, flush=True)
    if not DRY:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(m + "\n")


def ckpt_name(ep):
    return f"{SUB}.safetensors" if ep == TOTAL else f"{SUB}-{ep:06d}.safetensors"


def reference_shot(dataset_dir: Path) -> Path | None:
    """A product photo from the training set, for the judge page: the first
    caption that says so, else the first image."""
    imgs = sorted(dataset_dir.glob("image_src/*.png"))
    for p in imgs:
        cap = p.with_suffix(".txt")
        if cap.is_file() and "product photo" in cap.read_text(encoding="utf-8"):
            return p
    return imgs[0] if imgs else None


if DRY:
    log(f"DRY RUN {SET_ID}: epochs {GRID} + base, {len(SCENES)} scenes, trigger {TRIGGER!r}")
    for i, s in enumerate(SCENES):
        log(f"  scene {i:02d}: {s}")
    raise SystemExit(0)

from sourcemode import library as _lib  # noqa: E402
from sourcemode.render.client import ComfyUIClient  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from asset_scenes import sweep_seed  # noqa: E402

cfg = load_config()
_NAME = _lib.set_name(SET_ID, "dense_", NAME, "v2")
OUT = _lib.find_set(cfg, NAME, "sweep", _NAME, create=True)
_lib.write_set_json(OUT, character=NAME, kind="sweep", name=_NAME, date=OUT.name[:10], judge_sets=[SET_ID])
SEED = sweep_seed(OUT, int(_FLAGVALS["--seed"]) if _FLAGVALS.get("--seed") else None)
log(f"sweep seed {SEED} (scene i renders on {SEED} + i at every epoch)")

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
medium = cfg["render"]["medium"]
LORA_DIR.mkdir(parents=True, exist_ok=True)
for ep in GRID:
    src = CKPT / ckpt_name(ep)
    if src.exists() and not (LORA_DIR / src.name).exists():
        shutil.copy2(src, LORA_DIR / src.name)
log(f"grid {GRID}; staged {len(list(LORA_DIR.glob('*.safetensors')))} checkpoints")


def t2i(prompt, seed, lora, prefix):
    settings = {
        "MODEL": cfg["models"]["qwen_image"], "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"], "POSITIVE": prompt, "NEGATIVE": NEGATIVE,
        "LORA_PATH": lora, "LORA_STRENGTH": 1.0 if lora else 0.0,
        "LIGHTNING": "", "LIGHTNING_STRENGTH": 0.0,
        "SHIFT": float(cfg["render"]["qwen_shift"]), "SEED": seed,
        "STEPS": int(medium["qwen_t2i_steps"]), "CFG": float(medium["qwen_t2i_cfg"]),
        "WIDTH": W, "HEIGHT": H, "FILENAME_PREFIX": prefix,
    }
    return prune_placeholder_loras(substitute(load_template(workflows_dir(cfg), "qwen_image_t2i"), settings))


# arm -> (epoch label, lora path or "" for the base model)
ARMS = [("base", None, "")] + [(f"ep{ep:02d}", ep, rf"sourcemode\{SUB}\{ckpt_name(ep)}") for ep in GRID
                               if (LORA_DIR / ckpt_name(ep)).exists()]
for ep in GRID:
    if not (LORA_DIR / ckpt_name(ep)).exists():
        log(f"ep{ep:02d}: {ckpt_name(ep)} missing, skipping")

rows = []
for arm, ep, lora in ARMS:
    d = OUT / arm
    d.mkdir(parents=True, exist_ok=True)
    for i, scene in enumerate(SCENES):
        dest = d / f"scene_{i:02d}.png"
        try:
            if not dest.exists():
                files = client.outputs(client.wait(client.submit(
                    t2i(scene, SEED + i, lora, f"coarse/{SET_ID}/{arm}")), timeout_s=3600))
                if not files:
                    log(f"  {arm} scene{i:02d}: no output"); continue
                client.fetch(files[0], dest)
            rows.append({"arm": arm, "epoch": ep, "scene": i, "file": str(dest)})
        except Exception as ex:  # noqa: BLE001 - one scene never kills the sweep
            log(f"  {arm} scene{i:02d}: ERROR {ex}")
    log(f"{arm}: n={sum(1 for r in rows if r['arm'] == arm)}")

(OUT / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
items = [{"id": f"{r['arm']}__{r['scene']:02d}", "path": Path(r["file"]),
          "arm": "no LoRA" if r["epoch"] is None else f"{SUB} epoch {r['epoch']:02d}",
          "group": str(r["scene"])} for r in rows]
expected = len(ARMS) * N_SCENES
if not items:
    log("FATAL: nothing rendered - no judge set built")
    raise SystemExit(2)
if len(items) < expected:
    log(f"WARNING: judge set has {len(items)} of an expected {expected} - some scenes failed")
dataset_dir = CKPT.parent if CKPT.parent.parent.name == "lora-datasets" else None
make_set(Path("outputs/judge"), SET_ID,
         f"{NAME.title()} - object LoRA epoch eval, epochs {GRID[0]}-{GRID[-1]} + base ({N_SCENES} scenes)",
         items, question="Is this the toy? K = yes, X = no.",
         reference=reference_shot(dataset_dir) if dataset_dir else None, seed=61, priority=1,
         meta={"character": NAME, "dataset": dataset_dir.name if dataset_dir else SUB, "output_name": SUB,
               "renders_dir": OUT, "epochs": [ep for _, ep, _ in ARMS if ep is not None],
               "scenes": N_SCENES, "scene_set": "object", "seed": SEED, "offset": 0, "object": True})
log(f"judge set {SET_ID}: {len(items)} images")
log("COARSEDONE")
