"""Add the gaze clause to captions whose SHOT PLAN asked her to look off camera.

    python add_plan_gaze.py <char> [--apply]

Jeremy, 2026-10-03: "go back through all the ones i've edited for gaze and evaluate
whether you need to make a systemic change - it feels to me like the same ones over
and over have the same gaze inaccurate caption."

He was right, and the numbers are unambiguous. Of 342 logged caption edits, 33 touch
gaze; 32 of the 33 ADD "looking off camera", and the same plan shots keep returning -
008, 023, 041 and 004 five times each, across five different characters. Every one of
those shots has `gaze: "off"` in the plan.

Measured over 1,355 plan-described images, the plan's three gaze values separate
cleanly by the gaze_mp residual:

    plan gaze   measured off-camera   median |residual|
    camera            2%                   0.20
    off              41%                   0.65
    away             89%                   3.59

So the "off" population really is averted - it just sits under the 0.85 threshold,
which was tuned on the "away" case. Gating on the plan AND a residual above the
camera population's own median (0.25) captions 77% of the off shots and leaves alone
the ones that measurably are on the lens.

This adds the clause in place, after the angle clause, and never touches a caption
that already mentions gaze - so Jeremy's own edits survive. `caption_from_vl.py`
carries the same rule for every set generated from here on.
"""
import json
import re
import sys
from pathlib import Path

CHAR = sys.argv[1].lower()
APPLY = "--apply" in sys.argv
DS = Path(f"outputs/lora-datasets/{CHAR}_v2")
IMG = DS / "image_src"
PLAN_FILE = Path("outputs/shot_plans/v4/shot_plan_80_main_v4.json")
PLAN_OFF_MIN = 0.25
CLAUSE = "looking just off camera"
HAS_GAZE = re.compile(r"looking (off|just off|away|at the) camera|looking away")
# inserted after the angle clause, which is where the assembler puts gaze
AFTER = re.compile(r"((?:facing the camera|turned [^,]*|in a three-quarter view[^,]*|"
                   r"turned almost to profile|shot from [^,]*))(,|$)")

plan = {r["n"]: r for r in json.loads(PLAN_FILE.read_text(encoding="utf-8"))}
manifest = json.loads((DS / "manifest.json").read_text(encoding="utf-8"))
gaze_mp = json.loads((DS / "gaze_mp.json").read_text(encoding="utf-8")) if (DS / "gaze_mp.json").is_file() else {}

changed, skipped_has, skipped_low, no_shot = [], 0, 0, 0
for m in manifest:
    name = m.get("file")
    s = re.search(r"_shot_(\d+)", Path(str(m.get("original", ""))).name, re.I)
    if not name or not s:
        no_shot += 1
        continue
    entry = plan.get(int(s.group(1)))
    if not entry or entry.get("gaze") not in ("off", "away"):
        continue
    txt = IMG / (Path(name).stem + ".txt")
    if not txt.is_file():
        continue
    cur = txt.read_text(encoding="utf-8")
    if HAS_GAZE.search(cur):
        skipped_has += 1
        continue
    resid = abs((gaze_mp.get(name) or {}).get("resid") or 0)
    if resid < PLAN_OFF_MIN:
        skipped_low += 1
        continue
    new, n = AFTER.subn(lambda mm: f"{mm.group(1)}, {CLAUSE}{mm.group(2)}", cur, count=1)
    if not n:                      # no angle clause: put it after the framing clause
        parts = cur.split(", ")
        if len(parts) < 3:
            continue
        parts.insert(2, CLAUSE)
        new = ", ".join(parts)
    changed.append((name, resid, new.strip()))

print(f"{CHAR}: {len(changed)} caption(s) to gain '{CLAUSE}'  "
      f"(already had gaze: {skipped_has}, measured on-lens: {skipped_low}, not from the plan: {no_shot})")
for name, resid, new in changed:
    print(f"  {name}  resid {resid:.2f}\n     {new[:150]}")
if not APPLY:
    print("\ndry run - pass --apply to write")
    raise SystemExit(0)
for name, _resid, new in changed:
    (IMG / (Path(name).stem + ".txt")).write_text(new + "\n", encoding="utf-8")
print(f"\nwrote {len(changed)} captions")
