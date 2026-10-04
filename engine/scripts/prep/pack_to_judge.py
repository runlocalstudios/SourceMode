"""Put an ALREADY-RENDERED wardrobe pack on the judge board, candidates and all.

    python scripts/prep/pack_to_judge.py zara

Jeremy, 2026-10-04: "I need you to run the Zara game asset pack through the
judging tool and in this case if I reject something instead of regenerating you
can just show me the next selection of the other four that were generated
unless they've already been deleted."

Zara's pack is the last one rendered four-candidates-deep - 112 images, 28
looks, every candidate still on disk. So her set is built as POOL items: each
look shows its best candidate, and a reject advances to the next best with no
GPU time at all. Packs rendered from 2026-10-04 on are one-deep and write their
own judge set as they go; this script is for the ones that came before.

"Best" is `rank_candidates`, the same ranking `assets place` uses: fewest
broken asks against what the prompt actually asked for, then identity score.
So "the next one" means the next best, not the next filename.
"""

import json
import sys
from pathlib import Path

from sourcemode.assets.catalog import look_id, plan_slots, rank_candidates
from sourcemode.assets.judge import judge_root, make_set
from sourcemode.assets.redo import pool_item
from sourcemode.config import load_config, outputs_dir

if len(sys.argv) < 2:
    raise SystemExit(__doc__)

CHAR = sys.argv[1].lower()
cfg = load_config()
OUT = outputs_dir(cfg)
cdir = OUT / "game-assets" / CHAR

plan_path = next(iter(sorted(cdir.glob("plan*.json"))), None)
if plan_path is None:
    raise SystemExit(f"no plan*.json in {cdir}")
plan = json.loads(plan_path.read_text(encoding="utf-8"))

# Group every render's sidecar by the look it belongs to. The sidecar is what
# carries the slot, the seed, the identity score and the adherence measurement,
# so nothing here has to be inferred from a filename.
by_slot: dict[str, list[dict]] = {}
for side in sorted((cdir / "renders").rglob("shot_*.json")):
    try:
        s = json.loads(side.read_text(encoding="utf-8"))
    except ValueError:
        continue
    a = s.get("asset") or {}
    if not a.get("category") or a.get("look") is None:
        continue
    if not Path(s.get("source", "")).is_file():
        continue        # "unless they've already been deleted"
    by_slot.setdefault(look_id(a["category"], int(a["look"])), []).append(s)

items, missing, depth = [], [], {}
for slot in plan_slots(plan):
    cands = rank_candidates(by_slot.get(slot["id"], []))
    if not cands:
        missing.append(slot["id"])
        continue
    depth[len(cands)] = depth.get(len(cands), 0) + 1
    items.append(pool_item(slot, cands, character=CHAR, source=plan_path.name))

if not items:
    raise SystemExit(f"{CHAR}: no renders with sidecars under {cdir / 'renders'}")

set_id = f"pack_{CHAR}"
make_set(judge_root(cfg), set_id, f"{CHAR.title()} - wardrobe pack", items,
         question="Ship this one? K = yes, X = show me the next candidate.",
         reference=plan.get("reference"), priority=5)

print(f"{set_id}: {len(items)} looks on the judge board")
print(f"  candidates per look: " + ", ".join(f"{v} looks x{k}" for k, v in sorted(depth.items())))
if missing:
    print(f"  NO renders for: {', '.join(missing)}")
print(f"  reject -> next best candidate, no GPU. Out of candidates -> queued re-render.")
