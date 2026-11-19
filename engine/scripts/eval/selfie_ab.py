"""Matched-seed A/B on a character's selfie slots, through the selfie pack's own
prompt, negative and graph.

Jeremy, 2026-10-25, on casey: "They're all showing the iPhone when it's not a
mirror image." Every other character's pack drew the phone only in its mirror
slots; casey's drew it on most of the rest, on two different wordings. Arms:

    A  the pack as it renders today (control)
    B  her LoRA at 0.8 instead of 1.0
    C  no "selfie" anywhere: "a close portrait picture ... one arm outstretched
       toward the viewer, her hand out of the frame" (his wording)

    python scripts/eval/selfie_ab.py <char> <slot,slot,...> <seed> [test]

Writes library/<char>/<date>_ab_<test>/<arm>/<slot>.png with the prompt
beside each, a labelled sheet, and a blind judge set ab_<char>_<test>.

`test` is `selfie-phone` (above, the default) or `third-arm`. Jeremy,
2026-11-18: "why do i get SO MANY selfies with 3 arms in them? is it because
of the arm outstretched language?" - the five rejects on disk that day all had
BOTH arms reaching past the frame edges and a third hand where the prompt puts
"her other hand". Arms:

    A  the pack as it renders today (control)
    B  no "her other hand ..." clause
    C  the reaching arm named: "taking a selfie with one arm outstretched
       toward the viewer, her hand out of the frame", other hand kept
    D  work slots only: no "on a quick break" / "in a quiet corner on her
       break" (maya's gallery selfies kept drawing her phone)

`edge-hand`: the named arm fixed the third arm, but on three of its eight
shots the reaching hand showed as a large palm at the frame edge. Jeremy,
2026-11-19: "instead of just saying hand out of the picture, I think you need
to say something like wrist and hand out of the frame." Arms:

    A  the pack as it renders today ("her wrist and hand out of the frame")
    B  the 2026-11-18 wording ("her hand out of the frame")
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
TAG = sys.argv[4] if len(sys.argv) > 4 else "selfie-phone"
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


OTHER_HAND = (", her other hand down at her side", ", her other hand resting in her lap")
BREAKS = (", on a quick break", ", in a quiet corner on her break")


def cut(phrases):
    """Drop whichever of the phrases the prompt carries; None (skip the slot)
    when it carries none, so an arm is never rendered as a copy of A."""
    def edit(p: str):
        hit = [x for x in phrases if x in p]
        if not hit:
            return None
        for x in hit:
            p = p.replace(x, "")
        return p
    return edit


def one_arm(p: str):
    for a in ("she is taking a selfie,", "she is sitting back comfortably and taking a selfie,"):
        if a in p:
            return p.replace(a, a[:-1] + " with one arm outstretched toward the viewer, "
                                         "her hand out of the frame,")
    return None


def hand_only(p: str):
    a = "her wrist and hand out of the frame"
    return p.replace(a, "her hand out of the frame") if a in p else None


TESTS = {
    "edge-hand": ((("A", 1.0, lambda p: p), ("B", 1.0, hand_only)),
                  {"A": "wrist and hand out of the frame", "B": "hand out of the frame"},
                  "No hand or palm at the edge of the frame? K = yes, X = no."),
    "selfie-phone": ((("A", 1.0, lambda p: p), ("B", 0.8, lambda p: p), ("C", 1.0, no_selfie)),
                     {"A": "as today", "B": "LoRA 0.8", "C": "no selfie wording"},
                     "Is this her, with no phone in the picture? K = yes, X = no."),
    "third-arm": ((("A", 1.0, lambda p: p), ("B", 1.0, cut(OTHER_HAND)), ("C", 1.0, one_arm),
                   ("D", 1.0, cut(BREAKS))),
                  {"A": "as today", "B": "no other-hand clause", "C": "one arm named",
                   "D": "no break wording (work)"},
                  "Two arms at most and no phone in the picture? K = yes, X = no."),
}
if TAG not in TESTS:
    raise SystemExit(f"no such test {TAG!r}: {sorted(TESTS)}")
ARMS, ARM_LABEL, QUESTION = TESTS[TAG]

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
        if prompt is None:                       # this arm's phrase is not in this slot
            continue
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
make_set(outputs_dir(cfg) / "judge", f"ab_{CHAR}_{TAG}", f"{CHAR.title()} - {TAG} A/B",
         items, question=QUESTION,
         priority=0, meta={"character": CHAR, "renders_dir": OUT, "seed": SEED,
                           "arms": ARM_LABEL})

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
    dr.text((4, r * (CH + 18) + CH + 3), f"{arm}: {ARM_LABEL[arm]}", fill=(220, 220, 230))
sheet.save(OUT / "sheet.jpg", quality=90)
log(f"judge set ab_{CHAR}_{TAG}: {len(items)} images; sheet {OUT / 'sheet.jpg'}")
log("ABDONE")
