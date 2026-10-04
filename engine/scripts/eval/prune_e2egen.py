"""Delete e2egen training epochs that are not promoted winners.

Jeremy, 2026-09-29: "All of the E2E gen winners are moved to a different folder
where they are accessible in the web interface. So you can prune all of the
training epochs which are not in that winner folder."

This overrides the standing "C:/dev/e2egen is read-only, never modify" rule in
CLAUDE.md for this one operation, on his explicit instruction.

    python prune_e2egen.py            # dry run
    python prune_e2egen.py --apply

Safety, checked before anything is removed:
  1. TopLORA is OUTSIDE characters/, so a winner can never be a deletion target.
  2. Every character with checkpoints must have a winner in TopLORA - verified at
     run time, and the run ABORTS if one does not, rather than wiping a character
     that has no promoted copy anywhere.
  3. A file whose NAME matches a winner is only deleted when the TopLORA copy
     exists AND is byte-for-byte the same size. Four such duplicates exist
     (bianca_flux2_v1, sunny_flux2_v2/v3/v4).
  4. Only *.safetensors under characters/ are touched. Datasets, references and
     rendered output are left alone.
  5. Every deletion is recorded with its size to pruned_e2egen.json first.
"""
import json
import sys
from pathlib import Path

APPLY = "--apply" in sys.argv
ROOT = Path("C:/dev/e2egen")
CHARS = ROOT / "characters"
TOP = ROOT / "TopLORA"

winners = {p.name: p for p in TOP.glob("*.safetensors")}
if not winners:
    raise SystemExit("TopLORA is empty - refusing to prune anything")
win_chars = {n.split("_")[0].lower() for n in winners}
print(f"winner folder: {len(winners)} files, {len(win_chars)} characters")

# guard 2: never wipe a character that has no promoted winner
orphans = []
for d in sorted(p for p in CHARS.iterdir() if p.is_dir()):
    n = len(list(d.rglob("*.safetensors")))
    if n and d.name.lower() not in win_chars:
        orphans.append((d.name, n))
if orphans:
    for c, n in orphans:
        print(f"  !! {c}: {n} checkpoints and NO winner in TopLORA")
    raise SystemExit("aborting - promote a winner for those characters first")

rows, total = [], 0
for p in sorted(CHARS.rglob("*.safetensors")):
    if p.name in winners:
        w = winners[p.name]
        if not (w.is_file() and w.stat().st_size == p.stat().st_size):
            print(f"  keeping {p.name}: TopLORA copy missing or different size")
            continue
        why = "duplicate of a promoted winner"
    else:
        why = "training epoch, not promoted"
    mb = p.stat().st_size / 1e6
    total += mb
    rows.append({"file": str(p), "mb": round(mb), "why": why})

by_char = {}
for r in rows:
    c = Path(r["file"]).relative_to(CHARS).parts[0]
    d = by_char.setdefault(c, [0, 0.0])
    d[0] += 1; d[1] += r["mb"]
print(f"\n{'DELETED' if APPLY else 'WOULD DELETE'} {len(rows)} files, {total/1000:.1f} GB\n")
for c, (n, mb) in sorted(by_char.items(), key=lambda kv: -kv[1][1]):
    print(f"  {c:<10} {n:>4} files  {mb/1000:>5.1f} GB")
dups = [r for r in rows if r["why"].startswith("duplicate")]
print(f"\n  (of which {len(dups)} are duplicates of a TopLORA winner)")

if APPLY:
    out = Path("C:/dev/sourcemode/engine/outputs/logs/pruned_e2egen.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")   # record BEFORE deleting
    gone = 0
    for r in rows:
        try:
            Path(r["file"]).unlink(); gone += 1
        except OSError as e:
            print(f"  could not delete {r['file']}: {e}")
    print(f"\ndeleted {gone}/{len(rows)}; manifest at {out}")
    left = list(TOP.glob("*.safetensors"))
    print(f"TopLORA still holds {len(left)} winners")
