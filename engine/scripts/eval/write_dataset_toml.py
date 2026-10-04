"""Write the musubi dataset TOML for a staged set.

This was a MANUAL step, done per character by hand, and Sandra is what happens
when it is forgotten: her training aborted eight seconds in with "file not found
... dataset_qwen_t2i.toml", after the queue had already handed her the card.

The library's `dataset_toml()` is not usable as-is - it emits a square resolution
and `bucket_no_upscale = false`, while every set that has actually trained uses
`resolution = [1024, 1536]` and `bucket_no_upscale = true` (the render aspect, no
upscaling). This writes the proven form and takes repeats from the auto-tuner.

    python write_dataset_toml.py sandra_v2 [amanda_v2 ...]
    python write_dataset_toml.py --all        # every staged set that lacks one
"""
import sys
from pathlib import Path

from sourcemode.train.dataset import choose_num_repeats

ROOT = Path("outputs/lora-datasets")
RES = "[1024, 1536]"


def write(ds_name: str, force: bool = False) -> bool:
    ds = ROOT / ds_name
    img = ds / "image_src"
    if not img.is_dir():
        print(f"  {ds_name}: no image_src, skipping")
        return False
    n = len(list(img.glob("*.png"))) + len(list(img.glob("*.jpg")))
    caps = len(list(img.glob("*.txt")))
    if n == 0:
        print(f"  {ds_name}: no images, skipping")
        return False
    if caps != n:
        print(f"  {ds_name}: {caps} captions for {n} images - caption it first, NOT writing")
        return False
    out = ds / "dataset_qwen_t2i.toml"
    if out.is_file() and not force:
        print(f"  {ds_name}: already has one")
        return False
    rep = choose_num_repeats(n)
    d = str(ds.resolve()).replace("\\", "/")
    out.write_text(
        f"# {ds_name} - {n} approved images. repeats {rep} -> {n * rep} steps/epoch, from\n"
        f"# choose_num_repeats({n}); never hardcode around the auto-tuner. Render-aspect\n"
        f"# bucket with no upscaling, because training at a different shape from the one we\n"
        f"# generate at is a real mismatch.\n"
        "[general]\n"
        f"resolution = {RES}\n"
        'caption_extension = ".txt"\n'
        "batch_size = 1\n"
        "enable_bucket = true\n"
        "bucket_no_upscale = true\n"
        "\n"
        "[[datasets]]\n"
        f'image_directory = "{d}/image_src"\n'
        f'cache_directory = "{d}/_cache_t2i"\n'
        f"num_repeats = {rep}\n", encoding="utf-8")
    print(f"  {ds_name}: {n} images x {rep} repeats = {n * rep} steps/epoch -> {out.name}")
    return True


args = [a for a in sys.argv[1:] if not a.startswith("--")]
if "--all" in sys.argv:
    args = [d.name for d in sorted(ROOT.glob("*_v2")) if d.is_dir()]
if not args:
    raise SystemExit(__doc__)
for a in args:
    write(a, force="--force" in sys.argv)
