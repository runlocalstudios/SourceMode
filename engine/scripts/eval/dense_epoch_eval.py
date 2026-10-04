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
_FLAGS = {"--scenes", "--epochs"}
POS, _FLAGVALS = [], {}
_it = iter(sys.argv)
for _a in _it:
    if _a in _FLAGS:
        _FLAGVALS[_a] = next(_it, "")
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
SUBJECT = "a woman"
# A defining hair feature the base model will not volunteer. Raven has a full
# fringe in all five references and in her training frames, but the eval prompts
# said nothing about it and many renders came back with a centre part and a bare
# forehead - a visibly different person regardless of how well the LoRA learned
# her face. Her best epoch read 50%.
#
# Wording chosen for what these models actually respond to: "bangs" rather than
# "fringe", "full" to rule out curtain and side-swept, a stated length, and a
# texture word. Paired with a negative, because the failure is the model
# reverting to its default rather than ignoring the request.
#
# vivienne is the second case and it cost a whole sweep: her 90-render eval
# scored 0/90 because the prompt asked for "long black hair" over a LoRA trained
# on black hair with pink underlights. A matched-seed A/B on 2026-10-04 settled
# it - "long black hair" and DELETING the colour both gave plain black, so the
# LoRA never learned the pink, while naming it gave her real pattern and RAISED
# identity (0.611 / 0.572 / 0.672). Same rule as raven's bangs and priya's
# glasses: a trait correctly absent from the CAPTIONS still has to be stated at
# RENDER time.
#
# NOTE: this dict duplicates characters/appearance.json, which the asset scene
# path already reads through appearance.clause(). Two sources for one fact is
# how vivienne was fixed in one of them and still wrong in the other. Worth
# collapsing into clause() rather than growing this further.
FEATURE = {
    "raven": ("her hair worn with full bangs falling straight across her forehead to just "
              "above her eyebrows, soft and slightly wispy rather than blunt cut"),
    "vivienne": ("her long black hair carrying vivid pink underlights beneath the top "
                 "layer, the pink showing through the lengths"),
}
FEATURE_NEG = {
    "raven": ("no bangs, bare forehead, exposed forehead, forehead fully visible, hair "
              "swept back off the forehead, centre parting, middle part, hair tucked "
              "behind the hairline, curtain bangs, side-swept bangs, receding hairline"),
}
FEAT = FEATURE.get(CHAR.lower(), "")
FEAT_NEG = FEATURE_NEG.get(CHAR.lower(), "")
LOOK = ("Photorealistic, natural skin texture, sharp focus. Natural realistic human "
        "proportions, correct anatomy, a normal sized head.")
SCENES = [
    "standing in a sunlit kitchen in a white tank top, facing the camera, soft smile",
    "on a city street at night under neon signs, wearing a black leather jacket, facing the camera",
    "in a cafe holding a coffee cup, wearing a denim jacket, looking straight at the camera, slight smile",
    "on a stage behind a microphone, wearing a dark top, facing the camera, singing",
    "in a rehearsal room beside a drum kit, wearing a blue t-shirt, laughing at the camera",
    "in a flower market surrounded by blooms, wearing a cream lace top, smiling widely at the camera",
    "sitting on the edge of a bed under a soft lamp, wearing an oversized sweater, facing the camera",
    "at an office desk in a blazer over a tee, facing the camera, composed expression",
    "in a gym in athletic wear, facing the camera, resting between sets",
    "on a park bench in autumn in a rust knit sweater, facing the camera, head tilted very slightly",
    "in a bright bathroom mirror selfie in a grey hoodie, facing the camera, relaxed expression",
    "at a kitchen table with a laptop, wearing a striped tee, facing the camera, small smile",
    "on a sunny balcony in a navy button-up shirt, facing the camera, squinting slightly",
    "in a library between shelves, wearing a cream blouse, facing the camera, calm expression",
    "at a beach at golden hour in a white linen shirt, facing the camera, hair moving in the wind",
    "in a car passenger seat in a black turtleneck, facing the camera, neutral expression",
    "at a birthday party holding a slice of cake, wearing a lilac top, facing the camera, grinning",
    "in a hotel lobby in a camel coat, facing the camera, polite smile",
    "in a garden centre among plants, wearing a green v-neck, facing the camera, curious expression",
    "on a rooftop at dusk in a burgundy sweater, facing the camera, contented expression",
]
# --scenes favorable swaps in the three-quarter portrait set and renders into a
# separate output dir and judge set, so the two tests never mix. Never compare a
# number from one scene set against the other - jojo scored 77-90% on asset runs
# and 29% on the bare sweep, and comparing across tests once cost a whole wrong
# conclusion about priya.
# Jeremy, 2026-09-28 and again 2026-10-02: the bare sweep (microphone, drum kit,
# rooftop...) is SHELVED. Every eval runs on the favorable three-quarter portrait
# set unless "--scenes standard" is passed explicitly. Amanda was evaluated on the
# wrong set after he had already said this once.
SCENE_SET = "asset"
if "--scenes" in _FLAGVALS:
    SCENE_SET = _FLAGVALS["--scenes"]
VERBATIM = False
if SCENE_SET == "asset":
    # Jeremy, 2026-10-02: "The real test would be to generate 10 different examples
    # that look just like the asset generator prompts." These ARE those prompts,
    # rendered verbatim - no subject, no feature clause, no LOOK suffix.
    sys.path.insert(0, str(Path("scripts/eval").resolve()))
    from asset_scenes import asset_prompts
    SCENES = asset_prompts(TRIGGER)
    VERBATIM = True
    OUT = Path(f"outputs/dense_{SUB}_asset"); OUT.mkdir(parents=True, exist_ok=True)
    SET_ID = f"dense_{SUB}_asset"
elif SCENE_SET == "favorable":
    # Lives in the REPO, not a session scratchpad - the old path pointed at one
    # session's temp dir and would break for any later session.
    sys.path.insert(0, str(Path("scripts/eval").resolve()))
    from favorable_scenes import FAVORABLE
    SCENES = FAVORABLE
    OUT = Path(f"outputs/dense_{SUB}_fav"); OUT.mkdir(parents=True, exist_ok=True)
    SET_ID = f"dense_{SUB}_fav"
else:
    SET_ID = f"dense_{SUB}"
SCENES = SCENES[:N_SCENES]
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
        "NEGATIVE": NEGATIVE + (", " + FEAT_NEG if FEAT_NEG else ""),
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
                    t2i(scene if VERBATIM else f"{TRIGGER}, {SUBJECT}, {scene}"
                        + (f", {FEAT}" if FEAT else "") + f". {LOOK}", SEED + i,
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
