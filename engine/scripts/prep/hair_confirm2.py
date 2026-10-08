"""Binary confirmation for the hair labels the closed list gets wrong.

    python hair_confirm2.py <char> [--apply]

The closed-list pass ("loose / ponytail / bun / braid / pigtails / halfup / tucked")
is reliable on loose, pigtails and braid, and collapses ponytails and buns into
"halfup". Jeremy: "consistently just saying hair half pinned up". A wrong style
is worse than a generic one - it binds a real variable to the wrong word - so
those labels get re-asked one yes/no at a time, which is the form that has scored
12/12 (teeth) and 7/7 (braid) here.

Every image the closed list called halfup, ponytail or bun is asked, in order:
  "Is her hair pulled back into a ponytail?"  yes -> ponytail
  "Is her hair gathered up into a bun?"       yes -> bun
  neither                                     -> stays half pinned up

Writes vl_hair_confirm.jsonl, which caption_from_vl.py already reads as an override.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

CHAR = sys.argv[1].lower()
APPLY = "--apply" in sys.argv
DS = Path(f"outputs/lora-datasets/{CHAR}_v2"); IMG = DS / "image_src"
M = Path("C:/dev/e2egen/vendor/musubi-tuner")
VL, CAPTIONER = M / ".venv/Scripts/python.exe", M / "src/musubi_tuner/caption_images_by_qwen_vl.py"
VL_MODEL = "C:/ComfyUI/models/text_encoders/qwen_2.5_vl_7b.safetensors"
TMP = DS / "_hairq"
OUT = DS / "vl_hair_confirm.jsonl"

# Hannah src_018 and src_019 are both high ponytails and both answered "no".
# The old question asked about the TAIL - "a single tail hanging behind or over one
# shoulder" - and neither reads that way: the gather sits high on the crown, the
# length fans out rather than hanging as a rope, and face-framing strands are left
# out, so the model saw hair that was partly down and said no. Ask about the GATHER
# POINT instead, and say explicitly that loose strands around the face do not count.
#
# Bun is asked first: a bun is also "gathered at a single point", so asking
# ponytail first would claim every bun before the bun question ran.
# First attempt at the bun question said "with no length left hanging down her back
# or shoulders". A MESSY bun has tendrils by definition, so src_052 and src_064 -
# both plainly topknots - answered no, and the ponytail question then claimed them.
# Never qualify a style by the absence of stray hair. Ask whether the hair is
# WRAPPED against the head (bun) or HANGS LOOSE from the tie (ponytail); that is
# the real difference, and it survives tendrils in both directions.
# ONE question. Six wordings were tested against ten images Jeremy labelled, and the
# result was unambiguous:
#
#   bun       4/4 in every framing - the VL sees a knot against the head reliably
#   ponytail vs halfup   NO SIGNAL. Chained binaries made ORDER decide (bun-then-
#             ponytail called three half-ups ponytails; inserting half-up first stole
#             two real ponytails). Two 4-way questions scored 4/10 and 5/10 with
#             half-up 0/5. Three binary discriminators aimed at the distinction -
#             do the sides hang, are there two layers, are the sides swept up -
#             answered identically for both classes (one said "yes" to all seven).
#
# So the confirmation pass no longer tries to split half-up from ponytail. The closed
# list's "halfup" is kept, which Jeremy confirms is the correct call for these, and
# close_calls() flags every halfup so he can promote the handful that are ponytails.
# A generic label is recoverable; a confident wrong one binds a variable to the wrong
# word and is not. Do not reintroduce a ponytail question without new evidence.
QS = [("bun", "Ignore any loose strands around her face and neck. Is her hair wrapped, "
              "coiled or knotted into a bun sitting against her head? "
              "Answer with exactly one word: yes or no.")]
ASK = {"halfup", "ponytail", "bun"}


def ask(names, prompt, out):
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    for n in names:
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


coarse = {}
src = DS / "vl_hair.jsonl"
if not src.exists():
    print(f"{CHAR}: no vl_hair.jsonl - the shot plan covered every image, nothing to confirm")
    raise SystemExit(0)
for line in src.read_text(encoding="utf-8").splitlines():
    if line.strip():
        r = json.loads(line)
        coarse[Path(r["image_path"]).name] = re.sub(r"[^a-z]", "", r["caption"].lower())

names = sorted(n for n, a in coarse.items() if a in ASK)
print(f"{CHAR}: {len(names)} images to confirm (closed list said "
      + ", ".join(f"{a}:{sum(1 for n in names if coarse[n]==a)}" for a in sorted(ASK)) + ")")
if not names:
    print("nothing to confirm - every gathered image came from the shot plan")
    raise SystemExit(0)

result = {}
remaining = list(names)
for label, q in QS:
    if not remaining:
        break
    yes = ask(remaining, q, DS / f"_confirm_{label}.jsonl")
    for n in yes:
        result[n] = label
    remaining = [n for n in remaining if n not in yes]
    print(f"  {label}: {len(yes)} yes")
for n in remaining:
    result[n] = coarse[n]          # no question fired: keep what the closed list said
print(f"  no question fired, closed list kept: {len(remaining)}")
if TMP.exists():
    shutil.rmtree(TMP)

changed = sum(1 for n in names if result[n] != coarse[n])
print(f"  labels changed from the closed list: {changed} of {len(names)}")
if APPLY:
    # MERGE. This used to overwrite the file, and hair_recheck.py writes the SAME
    # file for the Lora-Gen shots: casey 2026-10-08, a second pass of the chain
    # ran this after her recheck and wiped 46 image-read ponytail verdicts, so
    # the plan's "worn loose" went back onto ponytails.
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    prev.update(result)
    OUT.write_text(json.dumps(prev, indent=1), encoding="utf-8")
    print(f"  wrote {OUT.name}; re-run caption_from_vl.py {CHAR} to apply (it preserves nothing else - "
          f"use fix-in-place on a hand-edited set)")
else:
    print("DRY RUN - add --apply to write vl_hair_confirm.jsonl")
