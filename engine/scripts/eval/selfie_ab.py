"""Matched-seed A/B on a character's selfie slots, through the selfie pack's own
prompt, negative and graph.

Jeremy, 2026-10-25, on casey: "They're all showing the iPhone when it's not a
mirror image." Every other character's pack drew the phone only in its mirror
slots; casey's drew it on most of the rest, on two different wordings. Arms:

    A  the pack as it renders today (control)
    B  her LoRA at 0.8 instead of 1.0
    C  no "selfie" anywhere: "a close portrait picture ... one arm outstretched
       toward the viewer, her hand out of the frame" (his wording)

    python scripts/eval/selfie_ab.py <char> <slot,slot,...> <seed>

Writes library/<char>/<date>_ab_selfie-phone/<arm>/<slot>.png with the prompt
beside each, a labelled sheet, and a blind judge set ab_<char>_selfie-phone.
"""

import sys
from datetime import datetime
from pathlib import Path

from sourcemode import library as L
from sourcemode.assets.appearance import negative as appearance_negative
from sourcemode.assets.judge import make_set
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.render import shot_prompt, t2i_workflow
from sourcemode.assets.shoots import resolve
from sourcemode.config import load_config, outputs_dir
from sourcemode.pose.native import NEGATIVE
from sourcemode.render.client import ComfyUIClient

if len(sys.argv) < 4:
    raise SystemExit(__doc__)
CHAR, IDS, SEED = sys.argv[1].lower(), sys.argv[2].split(","), int(sys.argv[3])
TAG = "selfie-phone"
W, H = 1024, 1536

# (find, replace) pairs for arm C; each must hit, or the arm is not what it says
NO_SELFIE = (
    ("a selfie, close arm's-length selfie;", "a close portrait picture;"),
    ("she is taking a selfie,", "one arm outstretched toward the viewer, her hand out of the frame,"),
    ("she is sitting back comfortably and taking a selfie,",
     "she is sitting back comfortably, one arm outstretched toward the viewer, her hand out of the frame,"),
    ("this is a casual selfie she took herself", "this is a casual picture she took herself"),
)


def no_selfie(p: str) -> str:
    for a, b in NO_SELFIE:
        p = p.replace(a, b)
    if "selfie" in p:
        raise SystemExit(f"arm C still says selfie: {p}")
    return p


ARMS = (("A", 1.0, lambda p: p), ("B", 0.8, lambda p: p), ("C", 1.0, no_selfie))

cfg = load_config()
OUT = L.find_set(cfg, CHAR, "ab", TAG, create=True)
L.write_set_json(OUT, character=CHAR, kind="ab", name=TAG, date=OUT.name[:10],
                 judge_sets=[f"ab_{CHAR}_{TAG}"])
LOG = outputs_dir(cfg) / "logs" / f"ab_{CHAR}_{TAG}.log"


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


LORA = resolve_lora(cfg, CHAR)
if not LORA:
    raise SystemExit(f"no locked LoRA for {CHAR}")
slots = {s["id"]: s for s in resolve(["selfies"])[0].plan(character=CHAR)}
missing = [i for i in IDS if i not in slots]
if missing:
    raise SystemExit(f"no such selfie slots: {missing}")
NEG = NEGATIVE + (", " + appearance_negative(CHAR) if appearance_negative(CHAR) else "")
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
log(f"{CHAR}: {len(IDS)} slots x {len(ARMS)} arms, seed {SEED}, lora {LORA['name']}")

items = []
for arm, strength, edit in ARMS:
    d = OUT / arm
    d.mkdir(parents=True, exist_ok=True)
    for k, sid in enumerate(IDS):
        slot = slots[sid]
        prompt = edit(shot_prompt(CHAR, slot, CHAR, backdrop=slot["setting"]))
        neg = NEG + (f", {slot['negative']}" if slot.get("negative") else "")
        dest = d / f"{sid}.png"
        if not dest.exists():
            files = client.outputs(client.wait(client.submit(t2i_workflow(
                cfg, prompt, SEED + k, f"ab/{CHAR}_{TAG}/{arm}", lora_path=LORA["path"],
                negative=neg, width=W, height=H, lora_strength=strength)), timeout_s=3600))
            if not files:
                log(f"  {arm} {sid}: no output")
                continue
            client.fetch(files[0], dest)
            (d / f"{sid}.txt").write_text(prompt, encoding="utf-8")
        items.append({"id": f"{arm}__{sid}", "path": dest, "arm": arm, "group": sid})
        log(f"  {arm} {sid}: done")

if not items:
    raise SystemExit("rendered nothing")
make_set(outputs_dir(cfg) / "judge", f"ab_{CHAR}_{TAG}", f"{CHAR.title()} - selfie phone A/B",
         items, question="Is this her, with no phone in the picture? K = yes, X = no.",
         priority=0, meta={"character": CHAR, "renders_dir": OUT, "seed": SEED,
                           "arms": {"A": "pack as today", "B": "LoRA 0.8",
                                    "C": "no selfie wording"}})

from PIL import Image, ImageDraw  # noqa: E402

CW, CH = 260, 390
sheet = Image.new("RGB", (len(IDS) * CW, len(ARMS) * (CH + 18)), (18, 18, 20))
dr = ImageDraw.Draw(sheet)
for r, (arm, strength, _) in enumerate(ARMS):
    for c, sid in enumerate(IDS):
        p = OUT / arm / f"{sid}.png"
        if p.is_file():
            im = Image.open(p).convert("RGB")
            im.thumbnail((CW, CH))
            sheet.paste(im, (c * CW, r * (CH + 18)))
    dr.text((4, r * (CH + 18) + CH + 3), {"A": "A: as today", "B": "B: LoRA 0.8",
                                          "C": "C: no selfie wording"}[arm], fill=(220, 220, 230))
sheet.save(OUT / "sheet.jpg", quality=90)
log(f"judge set ab_{CHAR}_{TAG}: {len(items)} images; sheet {OUT / 'sheet.jpg'}")
log("ABDONE")
