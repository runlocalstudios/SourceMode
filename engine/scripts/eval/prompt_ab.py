"""Matched-seed A/B over ONE phrase in the render prompt.

The skill's rule: when the question is render-side, the answer is a matched-seed
A/B - one variable, identical seeds, measured. Reasoning about these questions
has been wrong every time; the A/B has been right every time.

Everything except the substituted phrase is held fixed: same LoRA, same epoch,
same scenes, same seeds, same steps, same negative. The render path is
dense_epoch_eval's, reused rather than re-derived.

    python scripts/eval/prompt_ab.py <char> <sub> <epoch> <ckpt_dir> <trigger>
           --find "long black hair"
           --arms "A=long black hair|B=|C=long black hair with vivid pink underlights"
           [--scenes 0,2,6]

Arms are rendered in the order given; `A=` with the text equal to --find is the
control. An EMPTY arm deletes the phrase, which is how you ask "does the LoRA
supply this on its own when the prompt says nothing".

Writes outputs/ab_<char>_<tag>/<arm>/scene_NN.png, a labelled side-by-side
sheet, and a blind judge set so the verdict comes from Jeremy's eye and not
from my colour metric.
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts/eval").resolve()))

from asset_scenes import asset_prompts  # noqa: E402

from sourcemode.assets.judge import make_set  # noqa: E402
from sourcemode.config import load_config, workflows_dir  # noqa: E402
from sourcemode.gates.identity import cosine, embed_image  # noqa: E402
from sourcemode.pose.native import NEGATIVE  # noqa: E402
from sourcemode.render.client import ComfyUIClient  # noqa: E402
from sourcemode.render.workflow import (  # noqa: E402
    load_template, prune_placeholder_loras, substitute)

# Flags are split out BEFORE any positional parsing: dense_epoch_eval read
# argv by index, a trailing --scenes landed in the epoch-offset slot, int()
# raised, and the job died four seconds after waiting seven hours for the card.
_FLAGS = {"--find", "--arms", "--scenes", "--seed", "--tag", "--source"}
POS, FLAG = [], {}
_it = iter(sys.argv)
for _a in _it:
    if _a in _FLAGS:
        FLAG[_a] = next(_it, "")
    else:
        POS.append(_a)

if len(POS) < 6:
    raise SystemExit(__doc__)

CHAR, SUB, EPOCH, CKPT_DIR, TRIGGER = POS[1], POS[2], int(POS[3]), Path(POS[4]), POS[5]
FIND = FLAG.get("--find", "")
if not FIND:
    raise SystemExit("--find is required: the exact phrase to substitute")
ARMS = [a.split("=", 1) for a in FLAG.get("--arms", "").split("|") if "=" in a]
if len(ARMS) < 2:
    raise SystemExit("--arms needs at least two, as 'A=text|B=text'")
SCENES_IDX = [int(x) for x in FLAG.get("--scenes", "0,2,6").split(",") if x.strip()]
SEED = int(FLAG.get("--seed", "90210"))

W, H = 1024, 1536
TAG = FLAG.get("--tag", "hair")
OUT = Path(f"outputs/ab_{CHAR}_{TAG}")
OUT.mkdir(parents=True, exist_ok=True)
LOG = Path(f"outputs/logs/ab_{CHAR}_{TAG}.log")
LOG.parent.mkdir(parents=True, exist_ok=True)
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
LORA_DIR = Path(f"C:/ComfyUI/models/loras/sourcemode/{SUB}")


def log(s: str) -> None:
    line = f"{__import__('datetime').datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


def ckpt_name(ep: int) -> str:
    """The final epoch saves UNNUMBERED. Accept either and fail loudly."""
    for cand in (f"{SUB}-{ep:06d}.safetensors", f"{SUB}.safetensors"):
        if (CKPT_DIR / cand).is_file():
            return cand
    raise SystemExit(f"no checkpoint for epoch {ep} in {CKPT_DIR}")


CK = ckpt_name(EPOCH)
LORA_DIR.mkdir(parents=True, exist_ok=True)
if not (LORA_DIR / CK).exists():
    shutil.copy2(CKPT_DIR / CK, LORA_DIR / CK)

# the scenes this character's sweep actually used, so the A/B is comparable to it.
# --source influencer uses her influencer batch-1 slots instead, built exactly as
# run_shoots builds them, so the A/B answers a question about that pack.
if FLAG.get("--source") == "influencer":
    from sourcemode.assets.influencer import slots as _inf_slots  # noqa: E402
    from sourcemode.assets.render import shot_prompt as _shot  # noqa: E402
    ALL = [_shot(CHAR, s, TRIGGER, backdrop=s["setting"]) for s in _inf_slots(CHAR, 1)]
else:
    ALL = asset_prompts(TRIGGER)
missing = [p for p in SCENES_IDX if p >= len(ALL)]
if missing:
    raise SystemExit(f"scene index out of range: {missing} (have {len(ALL)})")
# --find @clause swaps her WHOLE appearance description - the text between
# "portrait of " and ", her body shape" - which is not one fixed string: up-style
# looks drop the hair length from it. Jeremy, 2026-10-07, on cat: run prompts
# "without character description at all".
import re as _re  # noqa: E402

_CLAUSE = _re.compile(r"(portrait of )(.*?)(, her body shape)")
if FIND == "@clause":
    missing = [i for i in SCENES_IDX if not _CLAUSE.search(ALL[i])]
    if missing:
        raise SystemExit(f"no appearance clause found in scenes {missing}")
for p in (ALL[i] for i in SCENES_IDX):
    if FIND != "@clause" and FIND not in p:
        raise SystemExit(f"--find {FIND!r} is not in the prompt; nothing would change")

cfg = load_config()
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
medium = cfg["render"]["medium"]

ref_hit = next((h for pat in (f"{CHAR}_face.*", f"{CHAR}_portrait*.*")
                for h in sorted(REFS.glob(pat)) if embed_image(h) is not None), None)
if ref_hit is None:
    raise SystemExit(f"no reference for {CHAR} embeds - refusing to score against nothing")
ref = embed_image(ref_hit)
log(f"reference {ref_hit.name}; epoch {EPOCH} ({CK}); scenes {SCENES_IDX}; seed {SEED}")


def t2i(prompt: str, seed: int, prefix: str) -> dict:
    settings = {
        "MODEL": cfg["models"]["qwen_image"],
        "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"], "POSITIVE": prompt, "NEGATIVE": NEGATIVE,
        "LORA_PATH": rf"sourcemode\{SUB}\{CK}", "LORA_STRENGTH": 1.0,
        "LIGHTNING": "", "LIGHTNING_STRENGTH": 0.0,
        "SHIFT": float(cfg["render"]["qwen_shift"]), "SEED": seed,
        "STEPS": int(medium["qwen_t2i_steps"]), "CFG": float(medium["qwen_t2i_cfg"]),
        "WIDTH": W, "HEIGHT": H, "FILENAME_PREFIX": prefix,
    }
    return prune_placeholder_loras(
        substitute(load_template(workflows_dir(cfg), "qwen_image_t2i"), settings))


items, rows = [], []
for arm_name, arm_text in ARMS:
    d = OUT / arm_name
    d.mkdir(parents=True, exist_ok=True)
    for i in SCENES_IDX:
        # the ONE substitution. An empty arm deletes the phrase and tidies the
        # comma it leaves behind, so the sentence still reads as English.
        if FIND == "@clause":
            # "=" keeps her own clause for this scene (the control arm)
            prompt = ALL[i] if arm_text == "=" else \
                _CLAUSE.sub(lambda m: m.group(1) + arm_text + m.group(3), ALL[i], count=1)
        else:
            prompt = ALL[i].replace(FIND, arm_text) if arm_text else \
                ALL[i].replace(FIND + ", ", "").replace(FIND, "")
        dest = d / f"scene_{i:02d}.png"
        try:
            if not dest.exists():
                files = client.outputs(client.wait(client.submit(
                    t2i(prompt, SEED + i, f"ab/{CHAR}_{TAG}/{arm_name}")), timeout_s=3600))
                if not files:
                    log(f"  {arm_name} scene{i:02d}: no output"); continue
                client.fetch(files[0], dest)
            e = embed_image(dest)
            score = round(float(cosine(ref, e)), 4) if e is not None else 0.0
            rows.append({"arm": arm_name, "scene": i, "file": str(dest), "score": score})
            items.append({"id": f"{arm_name}__{i:02d}", "path": dest,
                          "arm": arm_name, "group": str(i)})
            log(f"  {arm_name} scene{i:02d}: identity {score}")
        except Exception as ex:  # noqa: BLE001
            log(f"  {arm_name} scene{i:02d}: ERROR {ex}")

if not items:
    raise SystemExit("rendered nothing - refusing to write a DONE marker")

(OUT / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

SET_ID = f"ab_{CHAR}_{TAG}"
make_set(Path("outputs/judge"), SET_ID,
         f"{CHAR.title()} - prompt A/B on {FIND!r}",
         items, question="Is this her? K = yes, X = no.", priority=0,
         reference=str(ref_hit))
log(f"judge set {SET_ID}: {len(items)} images")

# a labelled sheet, because the question "did the pink come back" is answered by
# looking, and the arms are not secret to me - only to the blind judge
try:
    from PIL import Image, ImageDraw
    CW, CH = 300, 390
    sheet = Image.new("RGB", (len(SCENES_IDX) * CW, len(ARMS) * (CH + 18)), (18, 18, 20))
    dr = ImageDraw.Draw(sheet)
    for r, (arm_name, arm_text) in enumerate(ARMS):
        for c, i in enumerate(SCENES_IDX):
            p = OUT / arm_name / f"scene_{i:02d}.png"
            if not p.is_file():
                continue
            im = Image.open(p).convert("RGB")
            im = im.crop((0, 0, im.width, int(im.height * 0.55)))
            im.thumbnail((CW, CH))
            sheet.paste(im, (c * CW, r * (CH + 18)))
        dr.text((4, r * (CH + 18) + CH + 3),
                f"{arm_name}: {arm_text or '(phrase deleted)'}"[:70], fill=(220, 220, 230))
    sp = Path(f"outputs/qc/ab_{CHAR}_{TAG}.jpg")
    sp.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(sp, quality=90)
    log(f"sheet {sp}")
except Exception as ex:  # noqa: BLE001
    log(f"sheet failed (renders are fine): {ex}")

log("ABDONE")
