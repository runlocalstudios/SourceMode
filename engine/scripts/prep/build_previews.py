"""Build the approval preview for one or more characters.

    python build_previews.py raven mira sunny
    python build_previews.py priyanka --ds priyanka_v3

bucket_px MUST be 1536 to match how every approved dataset was measured - the
default of 1024 reports a face 30% smaller and fails the resolution gate on a set
that actually passes.
"""
import sys
from pathlib import Path

from sourcemode.config import load_config
from sourcemode.train.preview import build_preview, preview_root

root = preview_root(load_config())
ds_name = sys.argv[sys.argv.index("--ds") + 1] if "--ds" in sys.argv else None
chars = [a for a in sys.argv[1:] if not a.startswith("--") and a != ds_name]
if ds_name and len(chars) != 1:
    raise SystemExit("--ds names one dataset, so give exactly one character")
for char in chars:
    name = ds_name or f"{char}_v2"
    ds = Path(f"outputs/lora-datasets/{name}")
    if not (ds / "image_src").is_dir():
        print(f"{char}: no image_src"); continue
    d = build_preview(root, ds, dataset_id=name, trigger=char,
                      render_size=(1024, 1536), bucket_px=1536)
    g = d["gate"]
    print(f"{name}: {d['n']} images, gate {g['score']}, failing {g['failed']}")
    print(f"   caption checks failing: {d['captions']['failed']}")
    for f in g["findings"]:
        if not f["passed"]:
            print(f"   FAIL {f['check']}: {f['detail'][:96]}")
print("PREVIEWSDONE")
