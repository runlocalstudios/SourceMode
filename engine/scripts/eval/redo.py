"""Re-render exactly the shots a finished judge set rejected.

    python scripts/eval/redo.py <judge set id>

Jeremy, 2026-10-04: "if I reject them, you queue an item to regenerate a
replacement for that. single or multiple rejected photos" - and then, on the
timing: "I want you to queue and wait until the whole set has been judged
until you determine which shots need to be regenerated." So this runs on a
COMPLETE set, re-rolls every reject in it, and leaves the keeps alone.

What it does per rejected item:

  1. deletes the rejected image and its sidecar - one image per slot, always,
     because a reject left on disk is still a candidate `assets place` can pick
  2. re-renders that slot with a NEW seed (base + 10007 x attempt), so queueing
     twice cannot hand back the same picture
  3. rewrites the judge set with the replacement under the SAME item id

Step 3 is where the loop closes without any new state: `make_set` hashes every
image and `drop_stale_verdicts` forgets the verdict on any item whose content
changed, after `append_result` has preserved the old tally. So the replacements
come back as the only unjudged items in the set, and every keep survives.

The slot is rebuilt from the catalog or the plan at redo time rather than
copied out of the manifest, so a corrected prompt reaches the re-roll instead
of a snapshot of the prompt that produced the reject.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from sourcemode.assets.appearance import negative as appearance_negative
from sourcemode.assets.judge import judge_root, load_set, make_set
from sourcemode.assets.lora import resolve_lora
from sourcemode.assets.redo import rejected, retry_seed
from sourcemode.assets.render import shot_prompt, t2i_workflow
from sourcemode.config import load_config, outputs_dir
from sourcemode.gates.identity import cosine, embed_image
from sourcemode.pose.native import NEGATIVE
from sourcemode.render.client import ComfyUIClient

if len(sys.argv) < 2:
    raise SystemExit(__doc__)

SET_ID = sys.argv[1]
W, H = 1024, 1536
cfg = load_config()
OUT_ROOT = outputs_dir(cfg)
ROOT = judge_root(cfg)
LOG = OUT_ROOT / "logs" / f"redo_{SET_ID}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


doc = load_set(ROOT, SET_ID)
if not doc:
    raise SystemExit(f"no judge set {SET_ID!r}")
targets = rejected(ROOT, SET_ID)
if not targets:
    raise SystemExit(f"{SET_ID}: nothing rejected - nothing to re-roll")

CHAR = targets[0]["redo"]["character"]
LORA = resolve_lora(cfg, CHAR)
if not LORA:
    raise SystemExit(f"no approved LoRA for {CHAR}")
log(f"{SET_ID}: re-rolling {len(targets)} of {len(doc['items'])} - {CHAR}, lora {LORA['name']}")

ref = None
for pat in (f"{CHAR}_face.*", f"{CHAR}_portrait*.*"):
    for hit in sorted(REFS.glob(pat)):
        if embed_image(hit) is not None:
            ref = embed_image(hit)
            break
    if ref is not None:
        break

client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
NEG = NEGATIVE + (", " + appearance_negative(CHAR) if appearance_negative(CHAR) else "")


def drop(p: Path) -> None:
    """A reject does not stay on disk. Its sidecar and prompt go with it."""
    for q in (p, p.with_suffix(".json"), p.with_suffix(".txt")):
        try:
            q.unlink()
        except OSError:
            pass


def redo_shoot(info: dict, seed: int) -> Path | None:
    from sourcemode.assets.shoots import BY_ID

    sh = BY_ID.get(info["source"])
    if sh is None:
        log(f"  {info['slot_id']}: unknown shoot {info['source']!r}")
        return None
    slot = next((s for s in sh.plan() if s["id"] == info["slot_id"]), None)
    if slot is None:
        log(f"  {info['slot_id']}: no longer in {sh.id} - the catalog changed")
        return None
    dest = OUT_ROOT / "shoots" / CHAR / sh.id / f"{slot['id']}.png"
    drop(dest)
    prompt = shot_prompt(CHAR, slot, CHAR, backdrop=slot["setting"])
    files = client.outputs(client.wait(client.submit(
        t2i_workflow(cfg, prompt, seed, f"shoots/{CHAR}/{sh.id}",
                     lora_path=LORA["path"], negative=NEG, width=W, height=H)),
        timeout_s=3600))
    if not files:
        log(f"  {slot['id']}: no output")
        return None
    client.fetch(files[0], dest)
    dest.with_suffix(".txt").write_text(prompt, encoding="utf-8")
    return dest


def redo_pack(info: dict, seed: int) -> Path | None:
    from sourcemode.assets.catalog import plan_slots, slot_dirname
    from sourcemode.assets.render import render_plan

    pp = OUT_ROOT / "game-assets" / CHAR / info["source"]
    if not pp.is_file():
        log(f"  {info['slot_id']}: plan {pp} is gone")
        return None
    plan = json.loads(pp.read_text(encoding="utf-8"))
    slot = next((s for s in plan_slots(plan) if s["id"] == info["slot_id"]), None)
    if slot is None:
        log(f"  {info['slot_id']}: no longer in the plan")
        return None
    sdir = OUT_ROOT / "game-assets" / CHAR / "renders" / slot_dirname(slot)
    for old in list(sdir.glob("shot_*.png")):
        drop(old)
    # `only` narrows to this one slot, so render_plan's per-slot seed offset is
    # zero and the seed passed is the seed used - which is what makes a retry
    # land on a filename this run chose rather than one it has to guess.
    res = render_plan(cfg, client, plan, OUT_ROOT / "game-assets", shots=1,
                      seed=seed, log=log, only={slot["id"]})
    return Path(res[0]["source"]) if res else None


by_id = {it["id"]: it for it in doc["items"]}
redone = 0
for it in targets:
    info = it["redo"]
    attempt = int(info.get("attempt", 0)) + 1
    seed = retry_seed(info.get("seed", 0), attempt)
    try:
        # An exhausted pool IS a pack slot - same plan, same look - so it goes
        # down the same path once its four candidates are used up.
        dest = (redo_pack(info, seed) if info["kind"] in ("pack", "pool")
                else redo_shoot(info, seed))
    except Exception as exc:  # noqa: BLE001 - one bad slot never kills the rest
        log(f"  {info['slot_id']}: ERROR {exc}")
        dest = None
    if dest is None or not Path(dest).is_file():
        continue
    e = embed_image(Path(dest))
    row = by_id[it["id"]]
    row["path"] = dest
    row["score"] = (round(float(cosine(ref, e)), 4)
                    if (ref is not None and e is not None) else None)
    row["redo"] = {**info, "attempt": attempt, "seed": info.get("seed", 0)}
    redone += 1
    log(f"  {info['slot_id']}: attempt {attempt}, seed {seed}")

if not redone:
    raise SystemExit("re-rendered nothing - refusing to rewrite the set")

# Same ids, new content: make_set re-hashes and drop_stale_verdicts re-opens
# exactly these, keeping every verdict that still refers to the same pixels.
make_set(ROOT, SET_ID, doc["title"], list(by_id.values()),
         question=doc.get("question", ""), reference=doc.get("reference"),
         priority=doc.get("priority", 50))
log(f"REDODONE {SET_ID} {redone} re-rendered, back on the judge board")
