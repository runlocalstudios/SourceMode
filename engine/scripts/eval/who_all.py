"""Score a staged set against EVERY character's references, not just its own.

Ash's 0.50 identity floor passed 100 of 100 because Hannah scores 0.51-0.62
against Ash's references - a near miss, not the gross mismatch the floor was
built for (the "wrong bianca" case scored 0.245-0.464). The check that actually
works is relative: if another character's references score higher, it is not
this character. 35 of Ash's 100 staged images are Hannah, and every one of them
is named ash_shot_NNN.png, so nothing name-based could ever have caught it.

    python who_all.py <char> [<char> ...]
"""
import json
import sys
from collections import Counter
from pathlib import Path

from sourcemode.gates.identity import cosine, embed_image

REFS = Path("C:/Epic Games/Files/cnc info/codex/references")

banks = {}
for p in sorted(REFS.glob("*")):
    if not p.is_file() or p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        continue
    name = p.stem.split("_")[0].lower()
    if name == "universal":
        continue
    try:
        e = embed_image(p)
    except Exception:
        e = None
    if e is not None:
        banks.setdefault(name, []).append(e)

print(f"reference bank: {len(banks)} identities, "
      f"{sum(len(v) for v in banks.values())} embeddings\n")

for CHAR in sys.argv[1:]:
    CHAR = CHAR.lower()
    IMG = Path(f"outputs/lora-datasets/{CHAR}_v2/image_src")
    if CHAR not in banks:
        print(f"{CHAR}: NO REFERENCES - cannot check\n")
        continue
    if not IMG.is_dir():
        print(f"{CHAR}: no image_src\n")
        continue
    out, wrong = {}, []
    for p in sorted(IMG.glob("src_*.png")):
        e = embed_image(p)
        if e is None:
            continue
        sc = {n: max(cosine(r, e) for r in b) for n, b in banks.items()}
        top = max(sc.items(), key=lambda kv: kv[1])
        out[p.name] = {"self": round(sc[CHAR], 4),
                       "best": top[0], "best_score": round(top[1], 4)}
        if top[0] != CHAR:
            wrong.append((p.name, sc[CHAR], top[0], top[1]))
    n = len(out)
    pct = 100 * len(wrong) // n if n else 0
    flag = "  <-- CONTAMINATED" if pct >= 5 else ""
    print(f"=== {CHAR}: {n} images, {len(wrong)} match another identity better ({pct}%){flag}")
    for who, c in Counter(w[2] for w in wrong).most_common():
        print(f"      {c:>3} -> {who}")
    for f, s, w, ws in sorted(wrong, key=lambda t: t[1])[:4]:
        print(f"        {f}  {CHAR} {s:.3f}  vs {w} {ws:.3f}")
    Path(f"outputs/lora-datasets/{CHAR}_v2/who_all.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print()
