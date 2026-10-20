"""Matched-seed A/B on the pack's framing: why some looks come back chest-up.

    python scripts/eval/framing_ab.py <char> <spec.json>

Jeremy, 2026-10-20: "Do you have any idea why some of the pictures are so close
up?" Every look carries the same framing phrase, so the difference is in the
outfit text: 16% of looks whose outfit names nothing below the waist were
flagged clipped against 4% of those that do. And: "Do emphasis commands help
... (from the mid-thigh up:1.4)?" ComfyUI's Qwen-Image tokenizer is built with
disable_weights=True, so the weight syntax reaches the text encoder as literal
characters - it is tested here as text, not as a weight.

spec.json:
    {"looks": {"work_06": "nurse scrubs, a scrub top and matching scrub trousers", ...},
     "arms":  {"B_emphasis": ["a portrait picture from the mid-thigh up",
                              "a portrait picture (from the mid-thigh up:1.4)"],
               "C_lower":    "outfit",
               "D_noportrait": ["a portrait picture from the mid-thigh up",
                                "a photo framed from the mid-thigh up, her hips and thighs in frame"]}}

An arm is either [find, replace] on the rendered prompt, or "outfit", which
swaps the look's outfit for the one in `looks`. Each look re-renders at the
seed and with the LoRA its pack shot used; the pack shot itself is the control
(A_control), copied, not re-rendered. The crop is the pack's own adherence
measure. Writes library/<char>/<date>_ab_framing/<arm>/<look>.png, sheet.jpg,
results.json.
"""

import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from sourcemode.assets.adherence import measure
from sourcemode.assets.appearance import negative as appearance_negative
from sourcemode.assets.render import t2i_workflow
from sourcemode.config import load_config, outputs_dir
from sourcemode.library import find_set, write_set_json
from sourcemode.pose.native import NEGATIVE
from sourcemode.render.client import ComfyUIClient

if len(sys.argv) < 3:
    raise SystemExit(__doc__)

CHAR, SPEC = sys.argv[1], json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
W, H = 1024, 1536
cfg = load_config()
RENDERS = outputs_dir(cfg) / "game-assets" / CHAR / "renders"
OUT = find_set(cfg, CHAR, "ab", "framing", create=True)
write_set_json(OUT, character=CHAR, kind="ab", name="framing", date=OUT.name[:10])
NEG = NEGATIVE + (", " + appearance_negative(CHAR) if appearance_negative(CHAR) else "")
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])


def log(s: str) -> None:
    print(s, flush=True)


def crop_of(p: Path) -> str:
    try:
        return measure(p).get("crop") or "?"
    except Exception as exc:  # noqa: BLE001 - a measurement, never a blocker
        return f"error {exc}"


results: dict[str, dict] = {}
for look, new_outfit in SPEC["looks"].items():
    shot = next(iter(sorted((RENDERS / f"{look}_standing").glob("shot_*.png"))), None)
    if shot is None:
        log(f"{look}: no pack shot")
        continue
    meta = json.loads(shot.with_suffix(".json").read_text(encoding="utf-8"))
    prompt, seed, lora = meta["prompt"], meta["seed"], meta["lora"]
    row = results.setdefault(look, {"seed": seed})
    ctrl = OUT / "A_control" / f"{look}.png"
    ctrl.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(shot, ctrl)
    row["A_control"] = {"prompt": prompt, "crop": crop_of(ctrl)}
    for arm, how in SPEC["arms"].items():
        if how == "outfit":
            old = prompt.split("wearing ", 1)[1].split(", soft even studio lighting", 1)[0]
            p = prompt.replace(f"wearing {old}", f"wearing {new_outfit}", 1)
        else:
            p = prompt.replace(how[0], how[1], 1)
        if p == prompt:
            log(f"{look} {arm}: prompt unchanged - skipped")
            continue
        dest = OUT / arm / f"{look}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            files = client.outputs(client.wait(client.submit(
                t2i_workflow(cfg, p, seed, f"ab/{CHAR}/framing/{arm}", lora_path=lora,
                             negative=NEG, width=W, height=H)), timeout_s=3600))
            if not files:
                log(f"{look} {arm}: no output")
                continue
            client.fetch(files[0], dest)
        row[arm] = {"prompt": p, "crop": crop_of(dest)}
        log(f"{look} {arm}: {row[arm]['crop']}  (control {row['A_control']['crop']})")
    (OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

arms = ["A_control", *SPEC["arms"]]
tw, th = 220, 330
sheet = Image.new("RGB", (tw * len(arms), (th + 18) * len(results)), (255, 255, 255))
draw = ImageDraw.Draw(sheet)
for r, (look, row) in enumerate(results.items()):
    for c, arm in enumerate(arms):
        p = OUT / arm / f"{look}.png"
        x, y = c * tw, r * (th + 18)
        if arm in row and p.exists():
            im = Image.open(p).convert("RGB")
            im.thumbnail((tw, th))
            sheet.paste(im, (x, y + 16))
            draw.text((x + 2, y + 2), f"{look} {arm} {row[arm]['crop']}", fill=(20, 20, 20))
sheet.save(OUT / "sheet.jpg", quality=88)
summary = {arm: sum(1 for row in results.values() if arm in row and row[arm]["crop"] == "mid-thigh-up")
           for arm in arms}
log(f"FRAMINGABDONE mid-thigh-up per arm (of {len(results)}): {summary} -> {OUT / 'sheet.jpg'}")
