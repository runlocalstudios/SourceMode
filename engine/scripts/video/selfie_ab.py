"""Matched-seed A/B on selfie wording, for the video plate and the game's selfie assets.

Jeremy, 2026-09-28: "Don't you think the model knows what a selfie is?" Almost
certainly - and my frame-not-camera rule was over-applied. That rule comes from ONE
exotic prompt ("the camera is his eyes as he lies back and looks down his own body")
which the model had to construct and answered with fisheye torsos. A selfie is the
opposite: it is one of the most densely represented concepts in the training data.
The same mistake was already made once here - I claimed the model would not
understand "from the thighs up" and it obeyed perfectly.

So this does not assume my version wins. Three wordings, identical seeds, identical
everything else, judged blind:

  A  bare            - does "a selfie" alone carry framing, angle and lens?
  B  Jeremy's        - names the outstretched arm explicitly
  C  frame-described - my long geometric version, the one most likely to fight a
                       good prior with clumsy wording

Rendered at 720x1280, the real 9:16 target, so the result transfers straight to
both the S2V plate and the shipped selfie assets.

    python selfie_ab.py            # 4 seeds x 3 arms = 12 renders
"""
import json
import sys
from pathlib import Path

from sourcemode.assets.judge import make_set
from sourcemode.config import load_config, workflows_dir
from sourcemode.gates.identity import cosine, embed_image
from sourcemode.pose.native import NEGATIVE
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.workflow import load_template, prune_placeholder_loras, substitute

CHAR, SUB, CKPT = "jojo", "jojo_v2", "jojo_v2-000016.safetensors"
TRIGGER = "jojo"            # jojo_v2 was trained on the bare name
# RENDER AT THE TRAINING BUCKET, NOT THE VIDEO BUCKET. The first pass rendered
# 720x1280 because that is what Wan wants, and every one of the 12 failed to look
# like her. Measured: those frames carried 349-468px faces against 367-810px
# (median 623) in her working 60% sweep, on a canvas smaller than anything
# jojo_v2 saw at resolution [1024, 1536]. Render here, then resize and centre-crop
# DOWN to 720x1280 for Wan - that is what the video rule says about sources.
W, H = 1024, 1536
SEEDS = [11, 22, 33, 44]
OUT = Path("outputs/selfie_ab_1024"); OUT.mkdir(parents=True, exist_ok=True)

# Held constant across arms so the ONLY variable is the selfie wording.
SCENE = ("wearing a cream ribbed tank top, in her bedroom with a made bed and a "
         "window behind her, soft afternoon daylight, a faint closed-mouth smile")

ARMS = {
    "A_bare": f"{TRIGGER}, a woman, taking a selfie, {SCENE}",
    "B_arm": (f"{TRIGGER}, a woman, taking a selfie photo, her arm outstretched and "
              f"visible in the frame, {SCENE}"),
    "C_framed": (f"{TRIGGER}, a woman, her bare arm reaching out of the bottom-left "
                 f"corner of the frame toward the viewer, her head and shoulders "
                 f"filling the upper half of the picture, her chin slightly lifted, "
                 f"{SCENE}"),
}

cfg = load_config()
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
medium = cfg["render"]["medium"]


def t2i(prompt, seed, prefix):
    """Substitution copied VERBATIM from dense_epoch_eval.t2i - the placeholder names
    are LORA_PATH / LIGHTNING / LIGHTNING_STRENGTH, not the ones a guess produces,
    and load_template takes (dir, name) without the .json suffix."""
    settings = {
        "MODEL": cfg["models"]["qwen_image"], "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"], "POSITIVE": prompt, "NEGATIVE": NEGATIVE,
        "LORA_PATH": rf"sourcemode\{SUB}\{CKPT}", "LORA_STRENGTH": 1.0,
        "LIGHTNING": "", "LIGHTNING_STRENGTH": 0.0,
        "SHIFT": float(cfg["render"]["qwen_shift"]), "SEED": seed,
        "STEPS": int(medium["qwen_t2i_steps"]), "CFG": float(medium["qwen_t2i_cfg"]),
        "WIDTH": W, "HEIGHT": H, "FILENAME_PREFIX": prefix,
    }
    return prune_placeholder_loras(substitute(load_template(workflows_dir(cfg), "qwen_image_t2i"), settings))

REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
ref = None
for p in sorted(REFS.glob(f"{CHAR}_*")):
    if p.stem.split("_")[0].lower() == CHAR:
        ref = embed_image(p)
        if ref is not None:
            break

rows = []
for arm, prompt in ARMS.items():
    d = OUT / arm; d.mkdir(parents=True, exist_ok=True)
    for seed in SEEDS:
        dest = d / f"seed_{seed:02d}.png"
        if not dest.exists():
            wf = t2i(prompt, seed, f"selfie_ab_1024/{arm}")
            files = client.outputs(client.wait(client.submit(wf), timeout_s=1800))
            if not files:
                print(f"  {arm} seed{seed}: no output"); continue
            client.fetch(files[0], dest)
        e = embed_image(dest)
        rows.append({"arm": arm, "seed": seed, "file": str(dest),
                     "cos": round(float(cosine(ref, e)), 4) if (ref is not None and e is not None) else None})
        print(f"  {arm} seed{seed}: {rows[-1]['cos']}")

(OUT / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

items = [{"id": f"{r['arm']}__{r['seed']:02d}", "path": r["file"], "arm": r["arm"],
          "group": str(r["seed"])} for r in rows]
if not items:
    raise SystemExit("nothing rendered - refusing to write an empty judge set")
make_set(Path("outputs/judge"), "selfie_ab_jojo_1024",
         "Jojo selfie, rendered at the TRAINING bucket 1024x1536 - is she back?", items,
         question="Does this look like a selfie she took herself?", priority=1)
print(f"judge set selfie_ab_jojo: {len(items)} images")
print("SELFIEABDONE")
