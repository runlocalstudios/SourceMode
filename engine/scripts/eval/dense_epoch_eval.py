"""Coarse epoch sweep for any character's T2I LoRA. Stage 1 of the standard recipe.

    python coarse_epoch_eval.py <char> <lora_subdir> <total_epochs> [stride] [epoch_offset]

epoch_offset only changes the labels: a run resumed from another run's final
checkpoint numbers its epochs from 1 again, and judging those as "epoch 3"
beside a previous "epoch 12" invites exactly the confusion that has already
cost one sweep.

Renders every `stride`-th epoch (plus the final) on 10 frontal scenes, then loads
them into /judge labelled by epoch. The identity metric has no signal for ranking
checkpoints (rho +0.23 over 260 labels), so the grid exists to narrow the range
for Jeremy's eye, not to be scored.
"""
import json
import shutil
import sys
from pathlib import Path

from sourcemode.assets.judge import make_set
from sourcemode.config import load_config, workflows_dir
from sourcemode.gates.identity import cosine, embed_image
from sourcemode.pose.native import NEGATIVE
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.workflow import load_template, prune_placeholder_loras, substitute

# Positional args are read BY INDEX, so a trailing flag lands in one of those
# slots and is parsed as an int. "--scenes favorable" put "--scenes" into argv[9],
# the epoch offset, and killed a queued 60-render job the instant it started -
# after it had waited seven hours for the card. Split flags out first.
_FLAGS = {"--scenes", "--epochs", "--tag"}
# Bare flags take no value. They are skipped here for the same reason the valued
# ones are split out: anything left in argv lands in a positional slot by index.
_BARE = {"--allow-incomplete-appearance"}
POS, _FLAGVALS, _BARESEEN = [], {}, set()
_it = iter(sys.argv)
for _a in _it:
    if _a in _FLAGS:
        _FLAGVALS[_a] = next(_it, "")
    elif _a in _BARE:
        _BARESEEN.add(_a)
    else:
        POS.append(_a)

CHAR = POS[1]
SUB = POS[2]                 # e.g. sunny_r32 -> loras/sourcemode/<SUB>, output_name == SUB
TOTAL = int(POS[3])
START = int(POS[4]); END = int(POS[5])
# A continued run restarts its epoch numbering at 1. Pass the number of epochs
# already trained so the arms read as the real epoch and stay comparable.
OFFSET = int(POS[9]) if len(POS) > 9 else 0
# Older LoRAs trained on <name>_ch; new ones on the bare name. Pass it explicitly.
TRIGGER = POS[6]
# scene count: 20 for a confirmation pass, 10 when the epoch range is the
# whole question and 70 images is the budget
N_SCENES = int(POS[8]) if len(POS) > 8 else 20

W, H = 1024, 1536
OUT = Path(f"outputs/dense_{SUB}"); OUT.mkdir(parents=True, exist_ok=True)
LOG = Path(f"outputs/logs/dense_{SUB}.log")
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
# Checkpoint dir: the old runs live under <char>_curated/lora_<suffix>; the v2
# rebuilds save to <char>_v2/lora. Pass it explicitly rather than guess - the
# guess silently swept zero checkpoints and wrote a DONE marker anyway.
CKPT = Path(POS[7])
if not CKPT.is_dir() or not any(CKPT.glob("*.safetensors")):
    raise SystemExit(f"no checkpoints at {CKPT}; refusing to sweep nothing")
LORA_DIR = Path(f"C:/ComfyUI/models/loras/sourcemode/{SUB}")
# STRIDE 0 means "the first TOTAL epochs" - used when the coarse sweep shows a
# declining trend and the real peak sits below the lowest epoch sampled.
GRID = list(range(START, END + 1))
# --epochs 17,20,21,22,23 renders exactly those, for when the question is a few
# specific checkpoints rather than a contiguous sweep.
if "--epochs" in _FLAGVALS:
    GRID = [int(x) for x in _FLAGVALS["--epochs"].split(",") if x.strip()]

# "a woman" is load-bearing, not decoration. Without it the only thing telling the
# model the subject is female is the trigger token, and a name the base model reads
# as male wins: jojo came back 80% male at epoch 1, 53% across epochs 1-3, while
# sunny and gabi - whose names carry a female prior - came back 0% and 5%. The bug
# was latent in every earlier evaluation and only surfaced on jojo.
# WHAT SHE LOOKS LIKE comes from ONE place: characters/appearance.json, read
# through sourcemode.assets.appearance. This file used to keep its own FEATURE
# and FEATURE_NEG dicts - raven's bangs, then vivienne's pink - and its own
# "a woman" subject with no age. That was a second description of the same
# character, reachable only on the favorable/standard scene sets, and it is how
# vivienne was fixed in appearance.json and still rendered black-haired here,
# and how raven's bangs negative reached the eval and never her asset pack.
#
# The rule, measured three times (priya's glasses, raven's bangs, vivienne's
# pink - the last by matched-seed A/B on 2026-10-04, 0.611/0.572/0.672):
#
#   training images  identity comes from the REFERENCE PHOTOS; text must not
#                    describe her face, hair or build (lora-gen-80 skill)
#   training captions identity must be ABSENT, so it binds to the trigger
#   inference        identity is LoRA + TEXT, and the text MUST state every
#                    trait the LoRA will not carry: age, build, hair colour,
#                    bangs, glasses. The LoRA does not learn these on its own.
#
# Those three are different jobs and must not share one rule. But within the
# inference job there is exactly one prompt builder - assets/render.shot_prompt -
# and the eval renders its output verbatim, so a sweep and a pack cannot
# describe her differently.
from sourcemode.assets.appearance import check as appearance_check  # noqa: E402
from sourcemode.assets.appearance import negative as appearance_negative  # noqa: E402

# The eval scenes ARE the asset generator's prompts, rendered verbatim through
# the LoRA - Jeremy, 2026-10-02: "The real test would be to generate 10 different
# examples that look just like the asset generator prompts." Default here and in
# train_character.ps1 since then; every sweep from 2026-10-02 on is `_asset`.
#
# The favorable and standard scene sets are SHELVED. They composed their own
# prompt - "{trigger}, a woman, {scene}" - with no age and no appearance, which
# violates the age rule (2026-10-03) and the render-time-trait rule above. The
# favorable scene LIST stays in favorable_scenes.py as data; if it is ever wanted
# again it goes through shot_prompt with a framing argument, not through a
# second builder. Results from different scene sets were never comparable and
# still are not: jojo read 77-90% on asset runs and 29% on the bare sweep.
SCENE_SET = _FLAGVALS.get("--scenes", "asset")
if SCENE_SET != "asset":
    raise SystemExit(
        f"--scenes {SCENE_SET} is shelved (2026-10-02): it built its own prompt with no "
        f"age and no appearance. Use --scenes asset, which renders the asset generator's "
        f"own prompts verbatim.")
sys.path.insert(0, str(Path("scripts/eval").resolve()))
from asset_scenes import asset_prompts  # noqa: E402
SCENES = asset_prompts(TRIGGER)
VERBATIM = True
# --tag renders into its own folder and judge set. Without it a re-run with a
# changed prompt finds the old scene_NN.png on disk, skips rendering, and judges
# the previous prompt's images under the new name.
_TAG = f"_{_FLAGVALS['--tag']}" if _FLAGVALS.get("--tag") else ""
OUT = Path(f"outputs/dense_{SUB}_asset{_TAG}"); OUT.mkdir(parents=True, exist_ok=True)
SET_ID = f"dense_{SUB}_asset{_TAG}"
# There are ten asset looks. An n=20 confirmation renders each look twice, and the
# second pass gets its own seeds (SEED + i, i = 10..19) - before this, asking for
# 20 silently rendered 10.
SCENES = (SCENES * -(-N_SCENES // len(SCENES)))[:N_SCENES]
SEED = 8800


def _sex(p):
    """Assert the output is even the right sex. Nothing checked this before, so a
    male render was silently scored and then correctly rejected by eye, depressing
    the keep rate for a reason that had nothing to do with the LoRA."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    from sourcemode.gates.identity import _get_face_app  # noqa: PLC0415

    fs = _get_face_app().get(np.asarray(Image.open(p).convert("RGB"))[:, :, ::-1])
    if not fs:
        return "?"
    f = max(fs, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    return getattr(f, "sex", None) or ("M" if getattr(f, "gender", 1) == 1 else "F")


def log(m):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(m + "\n")


cfg = load_config()
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
medium = cfg["render"]["medium"]
def _ref_path():
    """The first reference that actually EMBEDS - not merely the first that exists.

    keiko_face.jpg is a 421x421 crop InsightFace finds no face in. Picking it by
    name gave ref=None, and cosine(None, e) raises inside the per-scene try, so all
    90 renders scored as errors, rows stayed empty and no judge set was built - an
    eval that exited 0 having produced nothing to judge. Verify the reference.
    """
    seen = []
    for pat in (f"{CHAR}_face.*", f"{CHAR}_portrait1.*", f"{CHAR}_portrait*.*", f"{CHAR}_*.*"):
        for hit in sorted(REFS.glob(pat)):
            if hit in seen:
                continue
            seen.append(hit)
            if embed_image(hit) is not None:
                if hit is not seen[0]:
                    log(f"reference {seen[0].name} has no detectable face; using {hit.name}")
                return hit
    raise SystemExit(f"no reference photo for {CHAR} in {REFS} has a detectable face")


REF_PATH = _ref_path()
ref = embed_image(REF_PATH)
if ref is None:
    raise SystemExit(f"reference {REF_PATH} did not embed - refusing to score against nothing")
log(f"scoring reference: {REF_PATH.name}")

# PRE-FLIGHT. The sweep is the first time text alone has to carry her identity,
# and a missing record means the prompt is the trigger and nothing else -
# vivienne's 90 renders scored 0/90 that way. Refuse at the guard, in a second,
# rather than seven hours later. --allow-incomplete-appearance bypasses it, as
# every gate here has a bypass; the refusal is the default because the cost of
# filling the record is thirty seconds and the cost of not doing so was a sweep.
_pre = appearance_check(CHAR)
for _w in _pre["warnings"]:
    log(f"appearance: WARNING {_w}")
if not _pre["ok"]:
    for _m in _pre["missing"]:
        log(f"appearance: MISSING {_m}")
    if "--allow-incomplete-appearance" not in _BARESEEN:
        raise SystemExit(
            f"{CHAR}'s appearance record is incomplete - " + "; ".join(_pre["missing"])
            + ". Add it to characters/appearance.json, or pass --allow-incomplete-appearance "
            "to render her from the trigger alone.")
    log("appearance: incomplete, proceeding on --allow-incomplete-appearance")
_NEG = appearance_negative(CHAR)
if _NEG:
    log(f"appearance: negative in effect ({len(_NEG)} chars)")
LORA_DIR.mkdir(parents=True, exist_ok=True)


def ckpt_name(ep):
    return f"{SUB}.safetensors" if ep == TOTAL else f"{SUB}-{ep:06d}.safetensors"


for ep in GRID:
    src = CKPT / ckpt_name(ep)
    if src.exists() and not (LORA_DIR / src.name).exists():
        shutil.copy2(src, LORA_DIR / src.name)
log(f"grid {GRID}; staged {len(list(LORA_DIR.glob('*.safetensors')))} checkpoints")


def t2i(prompt, seed, lora, prefix):
    settings = {
        "MODEL": cfg["models"]["qwen_image"], "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"], "POSITIVE": prompt,
        # The character's own negative (raven's anti-bangs terms) from the same
        # record as her appearance, so the pack and the eval share it.
        "NEGATIVE": NEGATIVE + (", " + _NEG if _NEG else ""),
        "LORA_PATH": lora, "LORA_STRENGTH": 1.0,
        "LIGHTNING": "", "LIGHTNING_STRENGTH": 0.0,
        "SHIFT": float(cfg["render"]["qwen_shift"]), "SEED": seed,
        "STEPS": int(medium["qwen_t2i_steps"]), "CFG": float(medium["qwen_t2i_cfg"]),
        "WIDTH": W, "HEIGHT": H, "FILENAME_PREFIX": prefix,
    }
    return prune_placeholder_loras(substitute(load_template(workflows_dir(cfg), "qwen_image_t2i"), settings))


rows = []
ran_eps = []
for ep in GRID:
    ck = ckpt_name(ep)
    if not (LORA_DIR / ck).exists():
        log(f"ep{ep:02d}: {ck} missing, skipping"); continue
    ran_eps.append(ep)
    arm = f"ep{ep:02d}"
    d = OUT / arm; d.mkdir(parents=True, exist_ok=True)
    for i, scene in enumerate(SCENES):
        dest = d / f"scene_{i:02d}.png"
        try:
            if not dest.exists():
                files = client.outputs(client.wait(client.submit(
                    t2i(scene, SEED + i,
                        rf"sourcemode\{SUB}\{ck}", f"coarse/{SET_ID}/{arm}")), timeout_s=3600))
                if not files:
                    log(f"  {arm} scene{i:02d}: no output"); continue
                client.fetch(files[0], dest)
            e = embed_image(dest)
            rows.append({"arm": arm, "epoch": ep, "scene": i, "file": str(dest),
                         "sex": _sex(dest),
                         "score": round(float(cosine(ref, e)), 4) if e is not None else 0.0})
        except Exception as ex:  # noqa: BLE001
            log(f"  {arm} scene{i:02d}: ERROR {ex}")
    sub = [r for r in rows if r["arm"] == arm]
    male = sum(1 for r in sub if r.get("sex") == "M")
    log(f"{arm} (epoch {ep + OFFSET}): n={len(sub)}" + (f"   MALE {male}/{len(sub)} <-- prompt needs a gender anchor" if male else "   all female"))

(OUT / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
items = [{"id": f"{r['arm']}__{r['scene']:02d}", "path": Path(r["file"]),
          "arm": f"{SUB} epoch {r['epoch'] + OFFSET:02d}", "group": str(r["scene"])} for r in rows]
# Keiko's run rendered all 90 images, scored none of them (her reference had no
# detectable face, so cosine raised inside the per-scene try), left rows empty and
# skipped set creation - then exited 0. An eval that produces nothing to judge is a
# failure, and at twelve characters a week a silent one is the expensive kind.
rendered = sum(1 for d in OUT.glob("ep*") for _ in d.glob("scene_*.png"))
expected = len(ran_eps) * N_SCENES
if not items:
    log(f"FATAL: {rendered} renders on disk but 0 scored - no judge set built. "
        f"Check the scoring reference for {CHAR}.")
    raise SystemExit(2)
if len(items) < expected:
    log(f"WARNING: judge set has {len(items)} of an expected {expected} "
        f"({len(ran_eps)} epochs x {N_SCENES} scenes) - some scenes failed")
if True:
    make_set(Path("outputs/judge"), SET_ID,
             f"{CHAR.title()} - Qwen LoRA epoch eval, epochs {GRID[0]}-{GRID[-1]} ({N_SCENES} scenes)", items,
             question="Is this her? K = yes, X = no.",
             reference=REF_PATH, seed=61, priority=1)
    log(f"judge set dense_{SUB}: {len(items)} images")
male_total = sum(1 for r in rows if r.get("sex") == "M")
log(f"gender check: {male_total}/{len(rows)} male" + ("  <-- INVESTIGATE" if male_total else "  (clean)"))
log("COARSEDONE")
