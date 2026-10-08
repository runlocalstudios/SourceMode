"""Take every image whose hair is UP out of a staged set, before captioning.

    python scripts/prep/cull_hair_up.py <char> [--apply]

Jeremy, 2026-10-08, on casey: her Lora-Gen run came back ~75 of 80 in the same
high ponytail against a plan that asked for loose hair, and he does not want to
review 190 images to cull them by hand - "remove any which clearly already have
hair up". Asks the image two yes/no questions with the wordings that have
measured well here (bun 4/4; ponytail by its gather point), and moves a yes to
`_excluded/` - the same folder the Training sets page uses, so every one shows
there as removed and can be put back with one tap. Nothing is deleted.

Loads the VL, so it runs through the GPU queue.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

CHAR = sys.argv[1].lower()
APPLY = "--apply" in sys.argv
DS = Path(f"outputs/lora-datasets/{CHAR}_v2")
IMG, EXC = DS / "image_src", DS / "_excluded"
M = Path("C:/dev/e2egen/vendor/musubi-tuner")
VL, CAPTIONER = M / ".venv/Scripts/python.exe", M / "src/musubi_tuner/caption_images_by_qwen_vl.py"
VL_MODEL = "C:/ComfyUI/models/text_encoders/qwen_2.5_vl_7b.safetensors"
TMP = DS / "_hairup_q"

QS = [
    ("bun", "Ignore any loose strands around her face and neck. Is her hair wrapped, coiled "
            "or knotted into a bun sitting against her head? Answer with exactly one word: yes or no."),
    ("ponytail", "Ignore any loose strands around her face. Is her hair gathered at one point and "
                 "hanging from the tie as a tail? Answer with exactly one word: yes or no."),
]


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


names = sorted(p.name for p in IMG.glob("src_*.png"))
if not names:
    raise SystemExit(f"{CHAR}: nothing staged in {IMG}")
up: dict[str, str] = {}
remaining = list(names)
for label, q in QS:
    yes = ask(remaining, q, DS / f"_hairup_{label}.jsonl")
    for n in yes:
        up[n] = label
    remaining = [n for n in remaining if n not in yes]
    print(f"  {label}: {len(yes)} yes, {len(remaining)} left", flush=True)
if TMP.exists():
    shutil.rmtree(TMP)

print(f"{CHAR}: {len(up)} of {len(names)} read as hair up ({len(names) - len(up)} stay)")
(DS / "hair_up_cull.json").write_text(json.dumps(up, indent=1), encoding="utf-8")
if not APPLY:
    print("dry run - pass --apply to move them to _excluded")
    raise SystemExit(0)
# Through the Training sets page's own exclude, after the preview exists, so each
# one shows there as removed and restores with one tap. Moving the files by hand
# before the preview was built would make them vanish instead.
from sourcemode.config import load_config  # noqa: E402
from sourcemode.train.preview import exclude_image, load_preview, preview_root  # noqa: E402

root = preview_root(load_config())
ds_id = f"{CHAR}_v2"
if load_preview(root, ds_id) is None:
    raise SystemExit(f"no preview for {ds_id} yet - build it first, then cull")
for n in sorted(up):
    exclude_image(root, ds_id, n, True)
print(f"removed {len(up)} on the Training sets page (restorable)")
print("CULLHAIRUPDONE")
