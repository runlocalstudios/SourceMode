"""Judge set for the seeded Amanda run - a blind cull before anything is captioned.

Each item carries its azimuth as the arm and its hair seed as the group, so a
pattern in the rejects reads straight out of the verdicts afterwards (the last
cull showed ponytail 0/9 and denim/street 1/12 that way).
"""
import json
from pathlib import Path

from sourcemode.assets.judge import make_set

import sys
SET = sys.argv[1] if len(sys.argv) > 1 else "cull_amanda_seeded"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("outputs/loragen_local/amanda")
rows = json.loads((OUT / "scores.json").read_text(encoding="utf-8"))
kept = [r for r in rows if r.get("keep")]
items = [{"id": f"shot_{r['n']:03d}", "path": r["file"],
          "arm": r.get("azimuth", "?"), "group": r.get("hair", "?")} for r in kept]
if not items:
    raise SystemExit("nothing passed the gates - refusing to write an empty judge set")
ref = Path("C:/Epic Games/Files/cnc info/codex/references/amanda_face.jpg")
make_set(Path("outputs/judge"), SET,
         "Amanda from 4 REAL hair seeds - is this her?", items,
         question="Is this Amanda? Keepers become training data.",
         reference=str(ref) if ref.is_file() else None, priority=1)
print(f"{SET}: {len(items)} images (of {len(rows)} generated)")
