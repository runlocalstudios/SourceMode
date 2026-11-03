"""Cut out and stage one of her intimate packs once every pose is kept. CPU lane; no card.

    python scripts/eval/process_intimate.py <character> <outfit>

`outfit` is a pack in assets/intimate.py:PACKS - lingerie or pajamas. The
keepers -> the pack's hybrid matte (BiRefNet + key) -> RGBA WebPs under
outputs/game-assets/<char>/intimate/ by the game's chat names, plus the base
file and the pack's record (assets/intimate.py:stage).

Jeremy, 2026-11-02: "any set with all lingerie photos should be approved to
ship to game once processed" - when every pose of the pack is kept, the staged
files ship to the game's intimate folder here (assets/intimate.py:ship), his
standing approval; the same rule for the pajama pack (2026-11-03). A partial
set only stages; the Characters tab ships it. The ship runs the game's
`npm run sync:intimate` and logs its output.
"""

import sys
from datetime import datetime

from sourcemode.assets import intimate as I
from sourcemode.config import load_config, outputs_dir

POS = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(POS) < 2 or POS[1].lower() not in I.PACKS:
    raise SystemExit(__doc__)
CHAR = POS[0].lower()
OUTFIT = POS[1].lower()
cfg = load_config()
OUT = outputs_dir(cfg)
LOG = OUT / "logs" / f"process_{OUTFIT}_{CHAR}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


rec = I.stage(cfg, OUT, CHAR, OUTFIT, log=log)
log(f"  {len(rec['poses'])} poses cut out, {len(rec['flagged'])} flagged by the alpha report")
from sourcemode.assets.looks import GAME_ROOT  # noqa: E402
from sourcemode.assets.shoots import BY_ID  # noqa: E402

whole = len(BY_ID[I.PACKS[OUTFIT]["shoot"]].plan(character=CHAR))
if len(rec["poses"]) == whole:
    shipped = I.ship(OUT, CHAR, GAME_ROOT, outfit=OUTFIT)
    log(f"  every pose kept ({whole}/{whole}) - shipped {len(shipped['files'])} files to {shipped['to']}")
    sync = shipped["sync"]
    log(f"  {sync['cmd']}: {'ok' if sync['ok'] else 'FAILED'} - {sync['output']}")
    if not sync["ok"]:
        log(f"  the game's intimatePacks.js is stale until `{sync['cmd']}` runs in {GAME_ROOT}")
    log(f"PROCESSDONE {CHAR} {OUTFIT} {len(rec['files'])} files staged and shipped to the game")
else:
    log(f"PROCESSDONE {CHAR} {OUTFIT} {len(rec['files'])} files staged ({len(rec['poses'])}/{whole} poses kept) "
        "- approve on the Characters tab")
