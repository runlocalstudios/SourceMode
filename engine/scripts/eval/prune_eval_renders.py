"""Delete the eval renders for epochs that were nowhere near winning.

    python prune_eval_renders.py          # dry run
    python prune_eval_renders.py --apply

Once an arm is judged and its checkpoint is gone, its renders can only ever be
re-judged, and an arm that lost by a wide margin will never be. Keep the winner
and anything within MARGIN keeps of it - at n=10 a 2-keep gap is inside noise, and
that is exactly the margin that made hannah's 7/7 "tie" look real.

Arms belonging to an UNRESOLVED tie are kept whole: their checkpoints still exist
and the comparison is still open.
"""
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

APPLY = "--apply" in sys.argv
MARGIN = 2
SETS = Path("outputs/judge/sets")
VERD = Path("outputs/judge/verdicts")

# Ties still open - their checkpoints are on the prune HOLD list, so keep every frame.
HOLD = {"dense_raven_v2", "dense_raven_v2_nobangs", "dense_sunny_v2",
        "dense_keiko_v2", "dense_bianca_v2", "dense_bianca_v2_fav"}

total = 0
log = []
for sp in sorted(SETS.glob("dense_*.json")):
    sid = sp.stem
    vp = VERD / sp.name
    if not vp.is_file():
        print(f"{sid:<26} no verdicts - KEEPING everything")
        continue
    if sid in HOLD:
        print(f"{sid:<26} unresolved tie - KEEPING everything")
        continue
    s = json.loads(sp.read_text(encoding="utf-8"))
    v = json.loads(vp.read_text(encoding="utf-8"))
    by = defaultdict(lambda: [0, 0])
    for i in s["items"]:
        m = re.match(r"ep(\d+)", i["id"])
        if not m:
            continue
        ep = int(m.group(1))
        d = v.get(i["id"])
        if d == "keep":
            by[ep][0] += 1; by[ep][1] += 1
        elif d == "reject":
            by[ep][1] += 1
    if not by:
        print(f"{sid:<26} nothing judged - KEEPING everything")
        continue
    best = max(k for k, n in by.values())
    keep_eps = {e for e, (k, n) in by.items() if k >= best - MARGIN}
    drop_eps = sorted(set(by) - keep_eps)
    if not drop_eps:
        print(f"{sid:<26} all arms within {MARGIN} of the winner - KEEPING everything")
        continue
    # the render dir is outputs/dense_<sub>/ep<NN>
    sub = sid[len("dense_"):]
    root = Path(f"outputs/dense_{sub}")
    freed = 0
    for ep in drop_eps:
        d = root / f"ep{ep:02d}"
        if not d.is_dir():
            continue
        mb = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1e6
        freed += mb
        log.append({"dir": str(d), "mb": round(mb), "keeps": by[ep][0], "of": by[ep][1]})
        if APPLY:
            shutil.rmtree(d, ignore_errors=True)
    total += freed
    kept = ", ".join(f"ep{e}" for e in sorted(keep_eps))
    print(f"{sid:<26} best {best}/10 | keeping {kept} | dropping {len(drop_eps)} arms, {freed/1000:.2f} GB")

print(f"\n{'DELETED' if APPLY else 'WOULD DELETE'} {len(log)} arm dirs, {total/1000:.2f} GB")
if APPLY and log:
    out = Path("outputs/logs/pruned_eval_renders.json")
    prior = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else []
    out.write_text(json.dumps(prior + log, indent=1), encoding="utf-8")
    print(f"recorded in {out}")
