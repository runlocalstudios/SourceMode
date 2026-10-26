"""Re-cut a shipped pack with the current cutout and re-ship the same looks. CPU lane.

    python scripts/eval/recut_pack.py <character>

For packs cut before the grey-halo fix (05efd46). Jeremy, 2026-10-26: "do the
cutouts on all other characters that were cutout before the cutout fix. Do not
make me reapprove all those ... automatically approve them this one time."

  1. refuses unless her pack has shipped, and her renders are the ones that
     shipped - nothing rendered since the staging (a new pack is approved the
     normal way, never shipped by this)
  2. `process_pack.py` re-cuts and re-stages from those same renders
  3. `pack.ship` copies exactly the files he ticked last time; the looks he
     left unticked stay as the game has them
"""

import json
import subprocess
import sys
from pathlib import Path

from sourcemode.assets import pack as P
from sourcemode.assets.looks import GAME_ROOT
from sourcemode.config import load_config, outputs_dir

if len(sys.argv) != 2:
    raise SystemExit(__doc__)
CHAR = sys.argv[1].lower()
OUT = outputs_dir(load_config())

st = P.read_staged(OUT, CHAR)
shipped = (st or {}).get("shipped")
if not shipped or not shipped.get("files"):
    raise SystemExit(f"{CHAR}: nothing shipped - approve her pack on the Characters tab")
shots = P.shots(P.renders_root(OUT, CHAR))
staged_at = P.staged_path(OUT, CHAR).stat().st_mtime
newer = [s.name for s in shots if s.stat().st_mtime > staged_at]
if newer:
    raise SystemExit(f"{CHAR}: {len(newer)} renders newer than what shipped - not hers to re-ship")
keep = list(shipped["files"])
print(f"{CHAR}: re-cutting {len(shots)} renders; will re-ship {len(keep)} files", flush=True)

proc = subprocess.run([sys.executable, str(Path(__file__).with_name("process_pack.py")), CHAR,
                       "--set", st.get("set") or f"pack_{CHAR}"])
if proc.returncode:
    raise SystemExit(f"{CHAR}: process_pack exited {proc.returncode}")

fresh = P.read_staged(OUT, CHAR) or {}
lost = sorted(set(keep) - set(fresh.get("files") or []))
if lost:
    raise SystemExit(f"{CHAR}: the re-cut did not stage {lost} - nothing shipped")
rec = P.ship(OUT, CHAR, GAME_ROOT, keep=keep)
print(f"RECUTDONE {CHAR}: shipped {len(rec['files'])}, overwrote {rec['overwrote']}, "
      f"left {len(rec['skipped'])} as the game has them", flush=True)
print(json.dumps(rec)[:300])
