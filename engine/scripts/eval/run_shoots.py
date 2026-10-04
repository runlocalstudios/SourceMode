"""Render one character through N named shoots as a SINGLE queued job.

Jeremy, 2026-10-04: "if I check a bunch of boxes and then initiate it, I would
prefer that on the GPU that is just tracked as one job, not like 10 different
jobs."

    python scripts/eval/run_shoots.py <character> boudoir,pool,gym

Each shoot writes its own judge set the moment it finishes, so a run that dies
part-way still leaves everything before it judgeable - the whole point of one
job is one queue entry, not one all-or-nothing result.

Every prompt goes through assets.render.shot_prompt, the same builder the
wardrobe pack and the epoch eval use. A shoot supplies outfit, hair, stance,
framing and setting; her age, appearance, frame and negative are shared.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path("scripts/eval").resolve()))

from sourcemode.assets.appearance import check as appearance_check  # noqa: E402
from sourcemode.assets.appearance import negative as appearance_negative  # noqa: E402
from sourcemode.assets.judge import make_set  # noqa: E402
from sourcemode.assets.render import shot_prompt  # noqa: E402
from sourcemode.assets.shoots import resolve, total_shots  # noqa: E402
from sourcemode.config import load_config, outputs_dir, workflows_dir  # noqa: E402
from sourcemode.gates.identity import cosine, embed_image  # noqa: E402
from sourcemode.pose.native import NEGATIVE  # noqa: E402
from sourcemode.render.client import ComfyUIClient  # noqa: E402
from sourcemode.render.workflow import (  # noqa: E402
    load_template, prune_placeholder_loras, substitute)
from sourcemode.train.epochs import checkpoint_dirs, load_choice  # noqa: E402

_BARE = {"--allow-incomplete-appearance"}
POS = [a for a in sys.argv if a not in _BARE]
BARE = {a for a in sys.argv if a in _BARE}
if len(POS) < 3:
    raise SystemExit(__doc__)

CHAR, IDS = POS[1].lower(), [x.strip() for x in POS[2].split(",") if x.strip()]
W, H = 1024, 1536
SEED = 9100
cfg = load_config()
OUT_ROOT = outputs_dir(cfg)
LOG = OUT_ROOT / "logs" / f"shoots_{CHAR}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


# Fail at the guard, in a second, not an hour in.
SHOOTS = resolve(IDS)                       # raises on an unknown id
pre = appearance_check(CHAR)
for w in pre["warnings"]:
    log(f"appearance: WARNING {w}")
if not pre["ok"] and "--allow-incomplete-appearance" not in BARE:
    raise SystemExit(f"{CHAR}'s appearance record is incomplete - "
                     + "; ".join(pre["missing"])
                     + ". Add it to characters/appearance.json, or pass "
                       "--allow-incomplete-appearance.")

from sourcemode.assets.lora import resolve_lora  # noqa: E402

LORA = resolve_lora(cfg, CHAR)
if not LORA:
    raise SystemExit(f"no approved LoRA for {CHAR} - choose an epoch on the judge page, "
                     f"or prune her checkpoints to the one you keep")
log(f"{CHAR}: {len(SHOOTS)} shoots, {total_shots(IDS)} shots, lora {LORA['name']}")

ref = None
for pat in (f"{CHAR}_face.*", f"{CHAR}_portrait*.*"):
    for hit in sorted(REFS.glob(pat)):
        if embed_image(hit) is not None:
            ref = embed_image(hit)
            log(f"scoring reference: {hit.name}")
            break
    if ref is not None:
        break

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
medium = cfg["render"]["medium"]
NEG = NEGATIVE + (", " + appearance_negative(CHAR) if appearance_negative(CHAR) else "")


def t2i(prompt: str, seed: int, prefix: str) -> dict:
    return prune_placeholder_loras(substitute(
        load_template(workflows_dir(cfg), "qwen_image_t2i"), {
            "MODEL": cfg["models"]["qwen_image"],
            "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
            "VAE": cfg["models"]["qwen_vae"],
            "POSITIVE": prompt, "NEGATIVE": NEG,
            "LORA_PATH": LORA["path"], "LORA_STRENGTH": 1.0,
            "LIGHTNING": "", "LIGHTNING_STRENGTH": 0.0,
            "SHIFT": float(cfg["render"]["qwen_shift"]), "SEED": seed,
            "STEPS": int(medium["qwen_t2i_steps"]), "CFG": float(medium["qwen_t2i_cfg"]),
            "WIDTH": W, "HEIGHT": H, "FILENAME_PREFIX": prefix,
        }))


done = 0
for sh in SHOOTS:
    d = OUT_ROOT / "shoots" / CHAR / sh.id
    d.mkdir(parents=True, exist_ok=True)
    items = []
    for k, slot in enumerate(sh.plan()):
        dest = d / f"{slot['id']}.png"
        try:
            if not dest.exists():
                prompt = shot_prompt(CHAR, slot, CHAR, backdrop=slot["setting"])
                files = client.outputs(client.wait(
                    client.submit(t2i(prompt, SEED + k, f"shoots/{CHAR}/{sh.id}")),
                    timeout_s=3600))
                if not files:
                    log(f"  {sh.id} {slot['id']}: no output"); continue
                client.fetch(files[0], dest)
                (d / f"{slot['id']}.txt").write_text(prompt, encoding="utf-8")
            e = embed_image(dest)
            items.append({"id": slot["id"], "path": dest, "arm": sh.id,
                          "group": str(k),
                          "score": round(float(cosine(ref, e)), 4)
                          if (ref is not None and e is not None) else None})
            done += 1
        except Exception as exc:  # noqa: BLE001 - one bad shot never kills the run
            log(f"  {sh.id} {slot['id']}: ERROR {exc}")
    if items:
        # Written per shoot, not at the end: a run that dies on shoot 4 leaves
        # shoots 1-3 judgeable rather than losing everything.
        make_set(OUT_ROOT / "judge", f"shoot_{CHAR}_{sh.id}",
                 f"{CHAR.title()} - {sh.label}", items,
                 question="Is this her? K = yes, X = no.", priority=5)
        log(f"  {sh.id}: {len(items)} shots -> judge set shoot_{CHAR}_{sh.id}")
    else:
        log(f"  {sh.id}: nothing rendered, no judge set written")

if not done:
    raise SystemExit("rendered nothing - refusing to report success")
log(f"SHOOTSDONE {CHAR} {done} shots across {len(SHOOTS)} shoots")
