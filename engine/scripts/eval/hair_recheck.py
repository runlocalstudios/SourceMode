"""Re-ask the image about every hair style the shot plan could not have got.

    python hair_recheck.py <char> [--apply] [--all]

Jeremy, 2026-10-03, on Marisol: "the marisol captions are all messed up because her
hair isn't long enough for a braid ... the ones of hers i saw so far are all buns
instead. take note that for all characters whose hair is not long enough for a braid
you probably need to review the hair styles."

Why it happened: `hair_confirm2.py` only reads `vl_hair.jsonl`, which the gather
writes for HAND-COLLECTED images only - "nothing to confirm, every gathered image
came from the shot plan". For plan images the caption took the plan's hair clause,
and the plan says what was ASKED, not what came back. The lora-gen-80 skill tells
the generator to substitute a style the character's real length can hold, so on a
short-haired character every braid / pigtails / long-ponytail entry is a silent
substitution: 9 of Marisol's images are captioned "braid" and are plainly buns.

This targets exactly those clauses and asks the image, using the question wordings
that have measured well here (bun 4/4; braid 7/7 as a binary). Anything that answers
no to all of them falls back to "half pinned back" - a generic label is recoverable,
a confident wrong one binds a variable to the wrong word. --all re-asks every image,
not just the length-dependent ones.

Writes vl_hair_confirm.jsonl and, with --apply, rewrites the hair clause in place
(whole clause up to the next comma, so "in a braid over one shoulder" and "in two
braids" are both replaced cleanly). Every other word of the caption is untouched,
including Jeremy's hand edits.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

CHAR = sys.argv[1].lower()
APPLY = "--apply" in sys.argv
ALL = "--all" in sys.argv
DS = Path(f"outputs/lora-datasets/{CHAR}_v2")
IMG = DS / "image_src"
M = Path("C:/dev/e2egen/vendor/musubi-tuner")
VL, CAPTIONER = M / ".venv/Scripts/python.exe", M / "src/musubi_tuner/caption_images_by_qwen_vl.py"
VL_MODEL = "C:/ComfyUI/models/text_encoders/qwen_2.5_vl_7b.safetensors"
TMP = DS / "_hairq2"
OUT = DS / "vl_hair_confirm.jsonl"

# styles the shot plan can ask for and a short-haired character cannot wear
LENGTH_DEPENDENT = ("braid", "plait", "pigtail", "high ponytail")
HAIR_CLAUSE = re.compile(r"her hair [^,]*")
# asked in this order; the first yes wins. Bun first because a bun is also
# "gathered", so asking a gather question first would claim every bun.
QS = [
    ("bun", "Ignore any loose strands around her face and neck. Is her hair wrapped, "
            "coiled or knotted into a bun sitting against her head? "
            "Answer with exactly one word: yes or no."),
    ("braid", "Is her hair plaited into a braid - three sections crossed over each other "
              "into a rope? Answer with exactly one word: yes or no."),
    ("pigtails", "Is her hair tied into two separate tails, one on each side of her head? "
                 "Answer with exactly one word: yes or no."),
    ("ponytail", "Ignore any loose strands around her face. Is her hair gathered at one "
                 "point and hanging loose from the tie as a tail? "
                 "Answer with exactly one word: yes or no."),
    # Asked LAST, before the fallback. rivera 2026-10-05: all 12 of her braid /
    # high-ponytail captions were a loose bob, every question above said no, and
    # without this they all fell back to "half pinned back" - confidently wrong.
    ("loose", "Is all of her hair hanging free - not tied, braided, clipped or pinned "
              "anywhere? Answer with exactly one word: yes or no."),
]
PHRASE = {"loose": "her hair worn loose",
          "bun": "her hair in a loose bun", "braid": "her hair in a braid over one shoulder",
          "pigtails": "her hair in pigtails", "ponytail": "her hair in a ponytail",
          "halfup": "her hair half pinned back"}


def ask(names, prompt, out):
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    # Jeremy culls on the Training sets page while this runs - casey 2026-10-08,
    # src_011 moved to _excluded between two questions and the copy raised, so
    # the whole recheck died and the plan's hair stayed on every caption. An
    # image that is gone is simply no longer asked.
    for n in names:
        if (IMG / n).is_file():
            shutil.copy2(IMG / n, TMP / n)
    if out.exists():
        out.unlink()
    subprocess.run([str(VL), str(CAPTIONER), "--image_dir", str(TMP), "--model_path", VL_MODEL,
                    "--output_file", str(out), "--prompt", prompt, "--max_new_tokens", "6",
                    "--fp8_vl"], check=True, capture_output=True)
    yes = set()
    for line in out.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["caption"].strip().lower().startswith("yes"):
                yes.add(Path(r["image_path"]).name)
    return yes


targets = {}
for txt in sorted(IMG.glob("*.txt")):
    png = txt.with_suffix(".png")
    if not png.is_file():
        continue
    m = HAIR_CLAUSE.search(txt.read_text(encoding="utf-8"))
    if not m:
        continue
    clause = m.group(0)
    if ALL or any(k in clause for k in LENGTH_DEPENDENT):
        targets[png.name] = clause
print(f"{CHAR}: {len(targets)} caption(s) to re-ask"
      + ("" if ALL else f" (clauses naming {', '.join(LENGTH_DEPENDENT)})"))
for n, c in sorted(targets.items()):
    print(f"  {n}  {c}")
if not targets:
    raise SystemExit(0)

result, remaining = {}, sorted(targets)
for label, q in QS:
    if not remaining:
        break
    yes = ask(remaining, q, DS / f"_recheck_{label}.jsonl")
    for n in yes:
        result[n] = label
    remaining = [n for n in remaining if n not in yes]
    print(f"  {label}: {len(yes)} yes, {len(remaining)} left")
for n in remaining:
    result[n] = "halfup"
if TMP.exists():
    shutil.rmtree(TMP)

print("\nverdicts:")
for n in sorted(result):
    print(f"  {n}  {targets[n]}  ->  {PHRASE[result[n]]}")
if not APPLY:
    print("\ndry run - pass --apply to write")
    raise SystemExit(0)

# MERGE, never overwrite: hair_confirm2 writes the same file for the hand-collected
# images, and the re-assemble step reads it as the override for both.
prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
prev.update(result)
OUT.write_text(json.dumps(prev, indent=1), encoding="utf-8")
changed = 0
for n, label in sorted(result.items()):
    txt = IMG / (Path(n).stem + ".txt")
    if not txt.is_file():      # removed on the page since it was asked
        continue
    cur = txt.read_text(encoding="utf-8")
    new = HAIR_CLAUSE.sub(PHRASE[label], cur, count=1)
    if new != cur:
        txt.write_text(new, encoding="utf-8")
        changed += 1
print(f"\nrewrote {changed} of {len(result)} captions; verdicts in {OUT}")

# A set already on the Training sets tab caches its captions in the preview;
# without this the page keeps showing the braids that were just corrected.
from sourcemode.config import load_config  # noqa: E402
from sourcemode.train.preview import preview_root, sync_captions  # noqa: E402

n = sync_captions(preview_root(load_config()), f"{CHAR}_v2")
if n:
    print(f"preview {CHAR}_v2: {n} caption(s) refreshed - approval lapses until re-approved")
