"""Render one character through N named shoots or packs as a SINGLE queued job.

Jeremy, 2026-10-04: "if I check a bunch of boxes and then initiate it, I would
prefer that on the GPU that is just tracked as one job, not like 10 different
jobs." And, on the same page: "as I complete the LoRAs, I want to be able to
trigger the game asset generation from this page."

    python scripts/eval/run_shoots.py <character> boudoir,pool,gym
    python scripts/eval/run_shoots.py <character> selfies,pack28

Two things can be ticked, and they run down different pipelines:

  kind="shoot"  rendered here - shot_prompt into the Qwen t2i graph, her
                approved LoRA, the setting kept as the backdrop. One judge set
                per shoot, written the moment that shoot finishes.
  kind="pack"   the shipped wardrobe pack. It has its own pipeline - a cropped
                magenta plate, the native single-pass graph, adherence
                measurement, then cutout and place - so this DELEGATES to
                assets.render.render_plan rather than reimplementing it. Its
                review happens on the /review page, not the judge board, so no
                judge set is written for it.

A shoot that dies does not take the others with it: each writes its output as
it finishes, so one job is one queue entry, not one all-or-nothing result.

Every rendered prompt goes through assets.render.shot_prompt, the same builder
the wardrobe pack and the epoch eval use. A shoot supplies outfit, hair, stance,
framing and setting; her age, appearance, frame and negative are shared.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path("scripts/eval").resolve()))

from sourcemode.assets.appearance import check as appearance_check  # noqa: E402
from sourcemode.assets.appearance import negative as appearance_negative  # noqa: E402
from sourcemode.assets.judge import make_set  # noqa: E402
from sourcemode.assets.lora import resolve_lora  # noqa: E402
from sourcemode.assets.render import shot_prompt  # noqa: E402
from sourcemode.assets.shoots import plan_path, resolve, total_shots  # noqa: E402
from sourcemode.config import load_config, outputs_dir, workflows_dir  # noqa: E402
from sourcemode.gates.identity import cosine, embed_image  # noqa: E402
from sourcemode.pose.native import NEGATIVE  # noqa: E402
from sourcemode.render.client import ComfyUIClient  # noqa: E402
from sourcemode.render.workflow import (  # noqa: E402
    load_template, prune_placeholder_loras, substitute)

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

LORA = resolve_lora(cfg, CHAR)
if not LORA:
    raise SystemExit(f"no approved LoRA for {CHAR} - choose an epoch on the judge page, "
                     f"or prune her checkpoints to the one you keep")

# A pack with no plan is caught here, before the card is touched - the outfits
# are a decision somebody has to make, and a missing plan is not a default.
for sh in SHOOTS:
    pp = plan_path(sh, CHAR, OUT_ROOT)
    if pp is not None and not pp.is_file():
        raise SystemExit(f"{sh.label} needs a wardrobe plan for {CHAR} and there is none at "
                         f"{pp}. Run `sourcemode assets plan {CHAR} --out {pp}` and fill in "
                         f"the outfits first.")

log(f"{CHAR}: {len(SHOOTS)} selections, {total_shots(IDS)} shots, lora {LORA['name']}")

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


def run_pack(sh) -> int:
    """Hand the wardrobe pack to its own renderer. Nothing about the shipped
    pipeline is re-derived here - the plate crop, the chroma backdrop and the
    adherence measurement all live in render_plan and stay there."""
    import json  # noqa: PLC0415

    from sourcemode.assets.render import render_plan  # noqa: PLC0415

    pp = plan_path(sh, CHAR, OUT_ROOT)
    plan = json.loads(pp.read_text(encoding="utf-8"))
    if plan.get("lora") and plan["lora"] != LORA["path"]:
        # Not fatal: the plan's source_asset was rendered from the plan's own
        # epoch, and swapping one without the other is how a pack ends up with
        # a plate and a LoRA that disagree. Say so and use the plan.
        log(f"  {sh.id}: NOTE plan uses {plan['lora']}, approved is {LORA['path']} "
            f"- rendering the plan as written")
    res = render_plan(cfg, client, plan, OUT_ROOT / "game-assets", shots=4, log=log)
    log(f"  {sh.id}: {len(res)} shots -> outputs/game-assets/{CHAR}/renders "
        f"(review on the /review page, then cutout and place)")
    return len(res)


def run_shoot(sh) -> int:
    d = OUT_ROOT / "shoots" / CHAR / sh.id
    d.mkdir(parents=True, exist_ok=True)
    items, n = [], 0
    for k, slot in enumerate(sh.plan()):
        dest = d / f"{slot['id']}.png"
        try:
            if not dest.exists():
                prompt = shot_prompt(CHAR, slot, CHAR, backdrop=slot["setting"])
                files = client.outputs(client.wait(
                    client.submit(t2i(prompt, SEED + k, f"shoots/{CHAR}/{sh.id}")),
                    timeout_s=3600))
                if not files:
                    log(f"  {sh.id} {slot['id']}: no output")
                    continue
                client.fetch(files[0], dest)
                (d / f"{slot['id']}.txt").write_text(prompt, encoding="utf-8")
            e = embed_image(dest)
            items.append({"id": slot["id"], "path": dest,
                          "arm": slot.get("tone") or sh.id, "group": str(k),
                          "score": round(float(cosine(ref, e)), 4)
                          if (ref is not None and e is not None) else None})
            n += 1
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
    return n


done = 0
for sh in SHOOTS:
    try:
        done += run_pack(sh) if sh.kind == "pack" else run_shoot(sh)
    except Exception as exc:  # noqa: BLE001 - one selection never kills the rest
        log(f"  {sh.id}: FAILED {exc}")

if not done:
    raise SystemExit("rendered nothing - refusing to report success")
log(f"SHOOTSDONE {CHAR} {done} shots across {len(SHOOTS)} selections")
