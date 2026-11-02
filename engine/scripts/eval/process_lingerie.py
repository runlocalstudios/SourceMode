"""Cut out and stage her Lingerie pack once every pose is kept. CPU lane; no card.

    python scripts/eval/process_lingerie.py <character>

The keepers -> the pack's hybrid matte (BiRefNet + key) -> RGBA WebPs under
outputs/game-assets/<char>/intimate/ by the game's chat names, plus the base
file and intimate.json (assets/intimate.py:stage).

Jeremy, 2026-11-02: "any set with all lingerie photos should be approved to
ship to game once processed" - when every pose of the pack is kept, the staged
files ship to the game's intimate folder here (assets/intimate.py:ship), his
standing approval. A partial set only stages; the Characters tab ships it.
"""

import sys
from datetime import datetime

from sourcemode.assets import intimate as I
from sourcemode.config import load_config, outputs_dir

POS = [a for a in sys.argv[1:] if not a.startswith("--")]
if not POS:
    raise SystemExit(__doc__)
CHAR = POS[0].lower()
cfg = load_config()
OUT = outputs_dir(cfg)
LOG = OUT / "logs" / f"process_lingerie_{CHAR}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


rec = I.stage(cfg, OUT, CHAR, log=log)
log(f"  {len(rec['poses'])} poses cut out, {len(rec['flagged'])} flagged by the alpha report")
from sourcemode.assets.looks import GAME_ROOT  # noqa: E402
from sourcemode.assets.shoots import BY_ID  # noqa: E402

whole = len(BY_ID[I.SHOOT].plan(character=CHAR))
if len(rec["poses"]) == whole:
    shipped = I.ship(OUT, CHAR, GAME_ROOT)
    log(f"  every pose kept ({whole}/{whole}) - shipped {len(shipped['files'])} files to {shipped['to']}")
    log(f"PROCESSDONE {CHAR} lingerie {len(rec['files'])} files staged and shipped to the game")
else:
    log(f"PROCESSDONE {CHAR} lingerie {len(rec['files'])} files staged ({len(rec['poses'])}/{whole} poses kept) "
        "- approve on the Characters tab")
