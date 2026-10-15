"""Cut out and stage a pack whose every look he kept. CPU lane; no card.

    python scripts/eval/process_pack.py <character> [--set pack_<character>]

  1. the one T2I shot per look -> rembg matte -> RGBA WebP on the game canvas
  2. `place`: the cutouts named and sorted into outputs/game-assets/<char>/outfits/
  3. two sheets in review/: the mapping on a checker, and every new look beside
     what the game ships under that name today
  4. staged.json: what is ready, which verdicts it came from, and the sheets

Nothing here touches the game repo. The approval on the Characters tab does.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from sourcemode.assets import pack as P
from sourcemode.assets.catalog import mapping_sheet, place
from sourcemode.assets.cutout import cutout_batch, rembg_remover
from sourcemode.assets.judge import judge_root
from sourcemode.assets.looks import GAME_ROOT
from sourcemode.config import load_config, outputs_dir

POS = [a for a in sys.argv[1:] if not a.startswith("--")]
if not POS:
    raise SystemExit(__doc__)
CHAR = POS[0].lower()
SET = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else f"pack_{CHAR}"
cfg = load_config()
OUT = outputs_dir(cfg)
home = OUT / "game-assets" / CHAR
LOG = OUT / "logs" / f"process_{CHAR}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(s: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {s}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + chr(10))


plan_path = home / "plan_28.json"
if not plan_path.is_file():
    raise SystemExit(f"no approved plan for {CHAR}")
plan = json.loads(plan_path.read_text(encoding="utf-8"))
pngs = P.shots(P.renders_root(OUT, CHAR))
if not pngs:
    raise SystemExit(f"no T2I pack renders for {CHAR} in {P.renders_root(OUT, CHAR)}")
log(f"{CHAR}: {len(pngs)} looks -> cutout, place, sheets")

acfg = cfg.get("assets", {})
model = acfg.get("cutout_model", "isnet-general-use")
size = tuple(acfg.get("game_size", (1024, 1536)))
cut_dir = home / "cutouts"
if cut_dir.is_dir() and any(cut_dir.rglob("*.json")):
    # an older cutout tree from the Edit pack is set aside, never mixed in
    stale = [s for s in cut_dir.rglob("*.json")
             if "qwen_image_t2i" not in s.read_text(encoding="utf-8", errors="replace")]
    if stale:
        aside = cut_dir.with_name(f"cutouts_edit_{time.strftime('%Y%m%d-%H%M')}")
        cut_dir.rename(aside)
        log(f"  older cutouts set aside as {aside.name}")
results = cutout_batch(pngs, cut_dir, remover=rembg_remover(model), model=model, size=size, webp=True, log=log)
flagged = [r for r in results if r["report"]["flags"]]
log(f"  cut {len(results)}, {len(flagged)} flagged for a look")

sides = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(cut_dir.rglob("*.json"))]
sides = [s for s in sides if "outputs" in s]
mapping = place(sides, plan, OUT / "game-assets")
review = home / "review"
msheet = mapping_sheet(mapping, OUT / "game-assets", review / "mapping_checkerboard.jpg")
csheet, overwrite = P.compare_sheet(mapping, home / "outfits",
                                    GAME_ROOT / "src" / "assets" / "characters" / CHAR / "outfits",
                                    review / "compare_game.jpg")
vp = judge_root(cfg) / "verdicts" / f"{SET}.json"
doc = {"at": datetime.now().isoformat(timespec="seconds"), "set": SET, "character": CHAR,
       "n": len(mapping["slots"]), "missing": mapping["missing"],
       "files": [s["file"] for s in mapping["slots"]],
       "flagged": [{"id": s["id"], "flags": s["flags"]} for s in mapping["slots"] if s["flags"]],
       "would_overwrite": overwrite, "cutout_model": model,
       "sheets": {"mapping": str(msheet), "compare": str(csheet)},
       "verdicts_mtime": vp.stat().st_mtime if vp.is_file() else None}
P.staged_path(OUT, CHAR).write_text(json.dumps(doc, indent=1), encoding="utf-8")
log(f"  staged {doc['n']} ({len(mapping['missing'])} missing, {overwrite} would overwrite game files) "
    f"-> {P.staged_path(OUT, CHAR)}")
log(f"PROCESSDONE {CHAR} {doc['n']} staged - approve on the Characters tab")
