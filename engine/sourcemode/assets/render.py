"""Render every look in a plan through the native single-pass pipeline.

For each (category, look): N shots at the game's 2:3 grid, the character's LoRA
for identity, the plan's outfit + hair for the look, a solid mid-grey
background so light clothing keys cleanly. Each shot gets a sidecar with the
slot's identity and its score against the character's closeup reference, so
`assets cutout` and `assets place` never have to infer anything.

Layout:  <out>/<character>/renders/<category>_<NN>_<pose>/shot_<i>_s<seed>.png (+ .json)
Resumable: existing shots with a sidecar are skipped.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..gates.identity import cosine, embed_image
from ..pose.native import build_native_workflow
from ..pose.transfer import composite_on_plate
from .catalog import plan_slots, slot_dirname

W, H = 1024, 1536
FRAMING = ("Full-length photograph from eye level, her whole body from head to feet in frame, "
           "her face clearly visible and well lit. ")
STANDING = "She stands relaxed facing the camera, weight on one hip, a soft natural smile."
SITTING = "She sits on a plain wooden stool facing the camera, hands resting on her thighs, a soft natural smile."
LOOK = ("Photorealistic, natural skin texture, sharp focus, soft even studio lighting, "
        "a plain solid medium grey background with nothing else in frame. "
        "Natural realistic human proportions, correct anatomy.")


def shot_prompt(character: str, slot: dict) -> str:
    pose = SITTING if slot["pose"] == "sitting" else STANDING
    return (f"{character}_ch. {FRAMING}{pose} She is wearing {slot['outfit']}, {slot['hair']}. {LOOK}")


def render_plan(cfg: dict, client, plan: dict, out: Path, *, shots: int = 4, seed: int = 7100,
                lora_strength: float = 0.85, render_pass: str = "medium", log=print,
                only: set[str] | None = None) -> list[dict]:
    character = plan["character"]
    if not plan.get("lora") or not plan.get("source_asset"):
        raise ValueError("plan needs `lora` and `source_asset` to render")
    slots = [s for s in plan_slots(plan) if not only or s["id"] in only]
    blank = [s["id"] for s in slots if not s["outfit"] or not s["hair"]]
    if blank:
        raise ValueError(f"plan has looks with no outfit/hair: {', '.join(blank)}")

    root = out / character / "renders"
    root.mkdir(parents=True, exist_ok=True)
    plate = root / "_plate.png"
    if not plate.exists():
        composite_on_plate(Path(plan["source_asset"]), plate)
    image_name = client.upload_image(plate)
    ref = embed_image(Path(plan["reference"])) if plan.get("reference") else None

    results = []
    for si, slot in enumerate(slots):
        sdir = root / slot_dirname(slot)
        sdir.mkdir(exist_ok=True)
        prompt = shot_prompt(character, slot)
        (sdir / "prompt.txt").write_text(prompt, encoding="utf-8")
        for k in range(shots):
            s = seed + si * 1000 + k * 137
            dest = sdir / f"shot_{k:02d}_s{s}.png"
            side = dest.with_suffix(".json")
            if dest.exists() and side.exists():
                results.append(json.loads(side.read_text(encoding="utf-8")))
                continue
            nodes = build_native_workflow(cfg, image_name, prompt, s, f"assets/{character}/{slot['id']}",
                                          lora=plan["lora"], lora_strength=lora_strength,
                                          render_pass=render_pass, width=W, height=H)
            files = client.outputs(client.wait(client.submit(nodes), timeout_s=3600))
            if not files:
                log(f"  {slot['id']} shot {k}: no output")
                continue
            client.fetch(files[0], dest)
            score = None
            if ref is not None:
                e = embed_image(dest)
                score = round(cosine(ref, e), 4) if e is not None else 0.0
            meta = {"source": str(dest), "asset": {"character": character, "category": slot["category"],
                                                   "look": slot["look"], "pose": slot["pose"], "shot": k},
                    "score": score, "seed": s, "prompt": prompt, "lora": plan["lora"],
                    "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            side.write_text(json.dumps(meta, indent=1), encoding="utf-8")
            results.append(meta)
            log(f"  {slot['id']} shot {k}: " + (f"{score:.3f}" if score is not None else "rendered"))
    return results
