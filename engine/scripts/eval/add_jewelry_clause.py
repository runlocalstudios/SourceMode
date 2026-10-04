"""Caption the jewelry the generator copied out of the reference photos.

Jeremy, 2026-09-23: "add the pearl necklace at least to the captions for Trina's
photos that have the necklace... the necklace is more critical" - it is visible in
most frames, and an accessory on most of a set is an uncaptioned constant, so it
binds to the trigger and the wardrobe pipeline can never render her without it.
The same failure as priya's glasses, arriving through the generator: trina_face.jpg
wears pearl studs AND a pearl string, and the shots inherited them.

Method is the one that has worked here and nothing else has: ONE binary question
to the vision model per attribute (teeth 12/12, braid 7/7; a multiple choice scored
0/12), then verify by eye. Necklace and earrings are asked separately - a combined
question invites the model to answer about whichever it noticed.

This PATCHES ONE CLAUSE IN PLACE. It never rebuilds a caption: re-running
caption_from_vl.py over a set Jeremy is reviewing destroys his hand edits. Every
other word of every caption is left byte-identical, and an image that already
carries the clause is skipped, so the script is idempotent.

    python add_jewelry_clause.py trina --dry-run     # no GPU, shows the patch
    python add_jewelry_clause.py trina               # asks the VL, then patches
    python add_jewelry_clause.py trina --no-earrings # necklace only
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

CHAR = sys.argv[1].lower()
DRY = "--dry-run" in sys.argv
NO_EAR = "--no-earrings" in sys.argv
DS = Path(f"outputs/lora-datasets/{CHAR}_v2")
IMG = DS / "image_src"
M = Path("C:/dev/e2egen/vendor/musubi-tuner")
VL = M / ".venv/Scripts/python.exe"
CAPTIONER = M / "src/musubi_tuner/caption_images_by_qwen_vl.py"
VL_MODEL = "C:/ComfyUI/models/text_encoders/qwen_2.5_vl_7b.safetensors"
TMP = DS / "_jewelq"

# Ask about the OBJECT, and say to ignore the clothing: a high collar, a neckline
# seam or a shirt placket all sit exactly where a necklace sits, and that is the
# only thing in frame that could be mistaken for one.
Q_NECK = ("Ignore her clothing and its neckline. Is she wearing a necklace around her "
          "neck - a string of pearls or beads, or a chain? "
          "Answer with exactly one word: yes or no.")
# Earrings are often hidden by hair, and hidden is a legitimate no.
Q_EAR = ("Look at her ears. Is she wearing earrings? "
         "Answer with exactly one word: yes or no.")

NECK_CLAUSE = "a pearl necklace"
EAR_CLAUSE = "pearl stud earrings"


def ask(names, prompt, out):
    """Verbatim from hair_confirm2.py - the invocation that works here."""
    if out.exists():
        print(f"  reusing {out.name} ({sum(1 for _ in out.open(encoding='utf-8'))} answers)")
    else:
        if TMP.exists():
            shutil.rmtree(TMP)
        TMP.mkdir(parents=True)
        for n in names:
            shutil.copy2(IMG / n, TMP / n)
        subprocess.run([str(VL), str(CAPTIONER), "--image_dir", str(TMP), "--model_path",
                        VL_MODEL, "--output_file", str(out), "--prompt", prompt,
                        "--max_new_tokens", "6", "--fp8_vl"], check=True, capture_output=True)
        shutil.rmtree(TMP, ignore_errors=True)
    yes = set()
    for line in out.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["caption"].strip().lower().startswith("yes"):
                yes.add(Path(r["image_path"]).name)
    return yes


def patch(caption, clause):
    """Insert the clause immediately after the outfit clause, leaving every other
    word alone. The outfit clause is the one that starts 'wearing '; captions are
    comma-separated noun phrases, so this reads as part of what she has on."""
    if clause in caption:
        return caption, False
    parts = [p.strip() for p in caption.split(",")]
    idx = next((i for i, p in enumerate(parts) if p.startswith("wearing ")), None)
    if idx is None:
        return caption, False
    parts.insert(idx + 1, clause)
    return ", ".join(parts), True


names = sorted(p.name for p in IMG.glob("src_*.png"))
print(f"{CHAR}: {len(names)} images")

if DRY:
    # No GPU. Prove the patch itself against every caption, with a synthetic
    # "everything has both" answer, so the wording and placement can be read first.
    neck, ear = set(names), set(names)
    print("  DRY RUN - pretending every image has both\n")
else:
    neck = ask(names, Q_NECK, DS / "vl_necklace.jsonl")
    print(f"  necklace: {len(neck)} of {len(names)}")
    ear = set() if NO_EAR else ask(names, Q_EAR, DS / "vl_earrings.jsonl")
    if not NO_EAR:
        print(f"  earrings: {len(ear)} of {len(names)}")

changed = skipped = 0
samples = []
for n in names:
    t = IMG / n
    txt = t.with_suffix(".txt")
    if not txt.is_file():
        continue
    cap = txt.read_text(encoding="utf-8").strip()
    bits = []
    if n in neck:
        bits.append(NECK_CLAUSE)
    if n in ear:
        bits.append(EAR_CLAUSE)
    if not bits:
        continue
    clause = " and ".join(bits) if len(bits) > 1 else bits[0]
    new, did = patch(cap, clause)
    if not did:
        skipped += 1
        continue
    changed += 1
    if len(samples) < 3:
        samples.append((n, cap, new))
    if not DRY:
        txt.write_text(new, encoding="utf-8")

print(f"\n{'would patch' if DRY else 'patched'}: {changed}   already had it / no outfit clause: {skipped}")
for n, a, b in samples:
    print(f"\n  {n}\n    before: {a}\n    after:  {b}")
if neck:
    print("\nnecklace = yes on:", " ".join(sorted(x.replace('.png', '') for x in neck))[:400])
