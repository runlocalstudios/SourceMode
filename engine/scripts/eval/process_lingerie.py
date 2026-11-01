"""Cut out and stage her Lingerie pack once every pose is kept. CPU lane; no card.

    python scripts/eval/process_lingerie.py <character>

The keepers -> the pack's hybrid matte (BiRefNet + key) -> RGBA WebPs under
outputs/game-assets/<char>/intimate/ by the game's chat names, plus the base
file and intimate.json (assets/intimate.py:stage). Nothing here touches the
game repo. The approval on the Characters tab does.
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
log(f"PROCESSDONE {CHAR} lingerie {len(rec['files'])} files staged - approve on the Characters tab")
